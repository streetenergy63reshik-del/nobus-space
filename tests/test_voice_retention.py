"""Green B04 counterpart. Offline synthetic fixtures; run only after root backup fix."""
from __future__ import annotations
import asyncio
from contextlib import closing
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4
import pytest
from src.application.durable_telegram_state import SQLiteTelegramState, DpapiJsonCodec, DurableTelegramStateError
from src.contracts.models import canonical_json_digest
from src.security.dpapi import protect_current_user
from tests.test_durable_voice import harness, claim, rows
from tests.test_telegram_product import voice_update, text_update
import src.application.durable_voice as voice_module

MARKER='synthetic-fixed-retention-only-not-private'
ERRORS=(DurableTelegramStateError,sqlite3.DatabaseError,OSError,ValueError)

def make(tmp_path,*,offset=timedelta(0),timeout=100):
    clock=[datetime.now(UTC)+offset]
    state=SQLiteTelegramState(tmp_path/'telegram-state.sqlite3',clock=lambda:clock[0],busy_timeout_ms=timeout)
    job=state.enqueue(kind='voice',tenant_id='owner',task_id=uuid4(),
        binding_digest=canonical_json_digest({'synthetic':1}),
        payload={'stage':'downloaded','audio':MARKER,'expires_at':(clock[0]+timedelta(hours=1)).isoformat()})
    return state,job,clock

def forbid_content_decode(state):
    decoded=[];old=state._decode
    def decode(blob):
        value=old(blob)
        if value:
            decoded.append(True)
            pytest.fail('nonempty expired content reached decoder')
        return value
    state._decode=decode
    return decoded

def raw_row(state):
    with sqlite3.connect(state.path) as db:
        return db.execute("SELECT status,payload,payload_digest,updated_at,lease_id FROM telegram_jobs WHERE kind='voice'").fetchone()

def evidence(name,**facts):print(json.dumps({'check':name,**facts},sort_keys=True))

@pytest.mark.parametrize('flag',[False,True])
def test_startup_expiry_before_decode_and_independent_of_feature_flag(tmp_path,flag):
    state,job,clock=make(tmp_path);clock[0]+=timedelta(hours=2)
    codec=DpapiJsonCodec();seen=[]
    def decode(blob):
        value=codec.decode(blob);seen.append(bool(value));assert not value;return value
    # No control-plane feature flag is required for authoritative state expiry.
    reopened=SQLiteTelegramState(state.path,clock=lambda:clock[0],decode=decode)
    owner_harness,_=harness(tmp_path/'control')
    owner_harness.control._enable_semantic_admission=flag
    owner_harness.control._telegram_state=reopened
    found=reopened.read_voice(tenant_id='owner',task_id=job.task_id)
    assert found is not None and found.payload=={} and not any(seen)
    assert raw_row(reopened)[0]=='finished'
    evidence('startup',flag=flag,expired_content_decrypts=0)

@pytest.mark.parametrize('state_kind',['pending','waiting','leased','expired_lease','failed'])
def test_all_expired_states_scrub_before_read_and_claim(tmp_path,state_kind):
    state,job,clock=make(tmp_path);owner=uuid4()
    if state_kind!='pending':
        job=state.claim(lease_owner=owner,lease_seconds=60 if state_kind=='expired_lease' else 14400)
        if state_kind=='waiting': state.checkpoint_voice(job,lease_owner=owner,payload=dict(job.payload,stage='waiting'),status='waiting')
        if state_kind=='failed': state.fail(job,lease_owner=owner,failure_code='synthetic_failure')
    clock[0]+=timedelta(hours=2);seen=forbid_content_decode(state)
    assert state.claim(lease_owner=uuid4()) is None
    assert state.read_voice(tenant_id='owner',task_id=job.task_id).payload=={}
    assert raw_row(state)[0]=='finished' and raw_row(state)[4] is None and not seen
    evidence('all_states',previous=state_kind,scrubbed=True,expired_content_decrypts=0)

def test_exact_one_hour_boundary_and_replay_tombstone_does_not_slide(tmp_path):
    state,job,clock=make(tmp_path);created=clock[0]
    clock[0]=created+timedelta(hours=1)-timedelta(microseconds=1)
    assert state.read_voice(tenant_id='owner',task_id=job.task_id).payload['audio']==MARKER
    clock[0]=created+timedelta(hours=1);forbid_content_decode(state)
    assert state.read_voice(tenant_id='owner',task_id=job.task_id).payload=={}
    scrubbed_at=raw_row(state)[3]
    clock[0]+=timedelta(hours=23,minutes=59)
    state.sweep_voice();state.sweep_voice()
    assert raw_row(state)[3]==scrubbed_at
    clock[0]=datetime.fromisoformat(scrubbed_at)+timedelta(hours=24)
    assert state.read_voice(tenant_id='owner',task_id=job.task_id) is None
    evidence('exact_boundary',expires_at_one_hour=True,tombstone_not_extended=True)

@pytest.mark.parametrize('operation',['renew','checkpoint','confirm'])
def test_expired_stale_lease_cannot_write_or_confirm(tmp_path,operation):
    state,job,clock=make(tmp_path);owner=uuid4()
    job=state.claim(lease_owner=owner,lease_seconds=14400)
    if operation=='confirm': job=state.checkpoint_voice(job,lease_owner=owner,payload=dict(job.payload,stage='waiting'),status='waiting')
    clock[0]+=timedelta(hours=1);forbid_content_decode(state)
    if operation=='renew':
        with pytest.raises(ERRORS):state.renew(job,lease_owner=owner,lease_seconds=14400)
    elif operation=='checkpoint':
        with pytest.raises(ERRORS):state.checkpoint_voice(job,lease_owner=owner,payload=dict(job.payload,stage='transcribed'))
    else:
        assert state.confirm_voice(job,reply_update_id=11,payload=dict(job.payload,stage='confirmed')) is False
    assert state.read_voice(tenant_id='owner',task_id=job.task_id).payload=={}
    evidence('stale_lease',operation=operation,expired_writer_rejected=True)

@pytest.mark.asyncio
@pytest.mark.parametrize('phase',['download','asr','prepare'])
async def test_ongoing_stage_crossing_ttl_cannot_publish_or_enqueue(tmp_path,monkeypatch,phase):
    h,compiler=harness(tmp_path);c=h.control;clock=[datetime.now(UTC)]
    class ControlledDate(datetime):
        @classmethod
        def now(cls,tz=None):return clock[0] if tz else clock[0].replace(tzinfo=None)
    monkeypatch.setattr(voice_module,'datetime',ControlledDate)
    c._telegram_state._clock=lambda:clock[0]
    await c.handle(voice_update(10))
    if phase=='prepare':
        await c._durable_voice.run(claim(c));await c.handle(text_update('да',11,reply_to_message_id=10))
        old=c._product_runtime.build_instruction
        async def late(*a,**kw):
            result=await old(*a,**kw);clock[0]+=timedelta(seconds=2);return result
        c._product_runtime.build_instruction=late
    elif phase=='asr':
        old=c._voice_service.preview_from_bytes
        async def late(*a,**kw):
            result=await old(*a,**kw);clock[0]+=timedelta(seconds=2);return result
        c._voice_service.preview_from_bytes=late
    else:
        old=c._api.download_file
        async def late(*a,**kw):
            result=await old(*a,**kw);clock[0]+=timedelta(seconds=2);return result
        c._api.download_file=late
    sent_before=len(h.api.sent)
    clock[0]+=timedelta(minutes=59,seconds=59)
    job=c._telegram_state.claim(lease_owner=c._lease_owner,lease_seconds=14400)
    try:await c._durable_voice.run(job)
    except ERRORS:pass
    assert c._telegram_state.read_voice(tenant_id=job.tenant_id,task_id=job.task_id).payload=={}
    assert rows(c)==[('voice','finished')]
    assert not any('Проверьте распознанный текст' in str(item) for item in h.api.sent[sent_before:])
    if phase=='download':assert c.asr_calls==0
    if phase!='prepare':assert not compiler.inputs
    assert h.runtime.applied==[] and h.api.documents==[]
    evidence('crossing_ttl',phase=phase,no_late_preview_or_draft=True)

@pytest.mark.asyncio
async def test_running_deadline_cancels_pending_await_and_has_no_late_result(tmp_path):
    h,compiler=harness(tmp_path);c=h.control
    await c.handle(voice_update(10));job=claim(c)
    # Actual monotonic timeout, not merely a simulated wall-clock jump.
    with sqlite3.connect(c._telegram_state.path) as db:
        db.execute('UPDATE telegram_jobs SET created_at=? WHERE job_id=?',
            ((datetime.now(UTC)-timedelta(hours=1)+timedelta(seconds=.15)).isoformat(),str(job.job_id)))
    cancelled=[];completed=[]
    async def never(audio):
        try:await asyncio.sleep(2);completed.append(True)
        finally:cancelled.append(True)
        raise AssertionError('should never finish native fake')
    c._voice_service.preview_from_bytes=never
    before=asyncio.get_running_loop().time()
    try:await c._durable_voice.run(job)
    except (TimeoutError,*ERRORS):pass
    elapsed=asyncio.get_running_loop().time()-before
    assert elapsed<1 and cancelled==[True] and not completed
    assert c._telegram_state.read_voice(tenant_id=job.tenant_id,task_id=job.task_id).payload=={}
    assert not compiler.inputs and rows(c)==[('voice','finished')]
    evidence('actual_deadline',cancelled=True,seconds=round(elapsed,3))

@pytest.mark.parametrize('operation',['read','claim','startup','backup'])
def test_cleanup_write_failure_blocks_content_access_and_retry_is_idempotent(tmp_path,operation):
    state,job,clock=make(tmp_path);clock[0]+=timedelta(hours=1)
    seen=forbid_content_decode(state)
    with sqlite3.connect(state.path) as db:
        db.execute("CREATE TRIGGER synthetic_cleanup_failure BEFORE UPDATE ON telegram_jobs BEGIN SELECT RAISE(ABORT,'synthetic disk full'); END")
    with pytest.raises(ERRORS):
        if operation=='read':state.read_voice(tenant_id='owner',task_id=job.task_id)
        elif operation=='claim':state.claim(lease_owner=uuid4())
        elif operation=='startup':SQLiteTelegramState(state.path,clock=lambda:clock[0],decode=state._decode)
        else:state.backup(tmp_path/'refused.sqlite3')
    assert not seen and raw_row(state)[0]=='pending'
    with sqlite3.connect(state.path) as db:db.execute('DROP TRIGGER synthetic_cleanup_failure')
    state.sweep_voice();state.sweep_voice()
    assert state.read_voice(tenant_id='owner',task_id=job.task_id).payload=={}
    evidence('cleanup_failure',operation=operation,access_blocked=True,retry_idempotent=True)

def test_busy_wal_cleanup_failure_remains_visible_until_reader_releases(tmp_path):
    state,job,clock=make(tmp_path,timeout=10)
    with closing(sqlite3.connect(state.path,isolation_level=None)) as reader:
        reader.execute('BEGIN')
        reader.execute('SELECT payload FROM telegram_jobs').fetchone()  # Own synthetic old read snapshot.
        clock[0]+=timedelta(hours=1)
        with pytest.raises(ERRORS):state.sweep_voice()
        # Retrying may not call an incompletely truncated WAL successfully cleaned.
        with pytest.raises(ERRORS):state.sweep_voice()
        reader.rollback()
    state.sweep_voice();state.sweep_voice()
    assert state.read_voice(tenant_id='owner',task_id=job.task_id).payload=={}
    evidence('busy_cleanup',failure_persists_until_quiescent=True)

@pytest.mark.parametrize('active',[False,True])
def test_state_backup_never_copies_voice_content(tmp_path,active):
    state,job,clock=make(tmp_path)
    target=tmp_path/'state-backup.sqlite3'
    if active:
        with pytest.raises(ERRORS):state.backup(target)
        assert not target.exists()
        assert state.read_voice(tenant_id='owner',task_id=job.task_id).payload['audio']==MARKER
    else:
        clock[0]+=timedelta(hours=1);forbid_content_decode(state)
        result=state.backup(target);restored=SQLiteTelegramState(result,clock=lambda:clock[0])
        assert restored.read_voice(tenant_id='owner',task_id=job.task_id).payload=={}
    evidence('state_backup',active=active,raw_voice_not_copied=True)

def track_expired_codec(monkeypatch):
    old=DpapiJsonCodec.decode;seen=[]
    def decode(self,blob):
        value=old(self,blob)
        if value.get('audio')==MARKER:
            seen.append(True);pytest.fail('backup/staging decrypted synthetic voice content')
        return value
    monkeypatch.setattr(DpapiJsonCodec,'decode',decode)
    return seen

@pytest.mark.parametrize('active',[False,True])
def test_actual_quiescent_backup_sanitizes_or_refuses_before_decrypt(tmp_path,monkeypatch,active):
    from tests.test_ops_queue1 import _runtime_databases
    from scripts.backup_telegram_runtime import _backup_quiescent
    sources=_runtime_databases(tmp_path/'sources')
    moment=datetime.now(UTC)-(timedelta(0) if active else timedelta(hours=2))
    state=SQLiteTelegramState(sources[2],clock=lambda:moment)
    job=state.enqueue(kind='voice',tenant_id='owner',task_id=uuid4(),binding_digest=canonical_json_digest({'synthetic':1}),
        payload={'stage':'downloaded','audio':MARKER,'expires_at':(moment+timedelta(hours=1)).isoformat()})
    seen=track_expired_codec(monkeypatch);destination=tmp_path/'backup'
    if active:
        with pytest.raises(ERRORS):_backup_quiescent(sources,destination)
        assert not (destination/'manifest.json').exists()
        assert raw_row(state)[0]=='pending'
    else:
        manifest=_backup_quiescent(sources,destination)
        assert manifest.exists()
        copied=SQLiteTelegramState(destination/'telegram-state.sqlite3')
        assert copied.read_voice(tenant_id='owner',task_id=job.task_id).payload=={}
    assert not seen
    evidence('actual_backup',active=active,no_content_decrypt=True)

def legacy_authenticated_snapshot(tmp_path):
    # Explicitly creates an old-version signed fixture, not a production backup.
    from tests.test_ops_queue1 import _runtime_databases
    from scripts.backup_telegram_runtime import _BACKUP_ENTROPY
    sources=_runtime_databases(tmp_path/'legacy-source');moment=datetime.now(UTC)-timedelta(hours=2)
    state=SQLiteTelegramState(sources[2],clock=lambda:moment)
    job=state.enqueue(kind='voice',tenant_id='owner',task_id=uuid4(),binding_digest=canonical_json_digest({'synthetic':1}),
        payload={'stage':'downloaded','audio':MARKER,'expires_at':(moment+timedelta(hours=1)).isoformat()})
    backup=tmp_path/'legacy-signed-backup';backup.mkdir()
    manifest={'schema_version':2,'created_at':moment.isoformat(),'quiescent':True,'files':[]}
    for source in sources:
        target=backup/source.name
        with closing(sqlite3.connect(source)) as src,closing(sqlite3.connect(target)) as dst:src.backup(dst)
        data=target.read_bytes()
        manifest['files'].append({'name':target.name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    digest=canonical_json_digest(manifest)
    (backup/'manifest-auth.bin').write_bytes(protect_current_user(digest.encode('ascii'),entropy=_BACKUP_ENTROPY))
    manifest['authentication']={'file':'manifest-auth.bin','manifest_digest':digest}
    path=backup/'manifest.json';path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return path,job

@pytest.mark.parametrize('tamper',[False,True])
def test_authenticated_restore_staging_expires_before_content_validation(tmp_path,monkeypatch,tamper):
    from scripts.restore_telegram_runtime import _restore_quiescent
    manifest,job=legacy_authenticated_snapshot(tmp_path)
    source=manifest.parent/'telegram-state.sqlite3'
    if tamper:
        with source.open('ab') as output:output.write(b'synthetic-tamper')
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in manifest.parent.iterdir() if p.is_file()}
    seen=track_expired_codec(monkeypatch);destination=tmp_path/'restored-runtime'
    if tamper:
        with pytest.raises((ValueError,RuntimeError)):_restore_quiescent(manifest,destination)
        assert not (destination/'telegram-state.sqlite3').exists()
    else:
        _restore_quiescent(manifest,destination)
        restored=SQLiteTelegramState(destination/'telegram-state.sqlite3')
        assert restored.read_voice(tenant_id='owner',task_id=job.task_id).payload=={}
    after={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in manifest.parent.iterdir() if p.is_file()}
    assert before==after and not seen
    evidence('authenticated_staging',tampered=tamper,source_preserved=True,no_expired_content_decrypt=True)

def test_current_sqlite_logical_scrub_does_not_claim_dpapi_key_erasure(tmp_path):
    state,job,clock=make(tmp_path);old=raw_row(state)[1]
    clock[0]+=timedelta(hours=1);state.sweep_voice()
    assert state.read_voice(tenant_id='owner',task_id=job.task_id).payload=={}
    assert DpapiJsonCodec().decode(old)['audio']==MARKER
    evidence('crypto_limit',logical_scrub=True,retained_fixture_ciphertext_key_not_destroyed=True)
