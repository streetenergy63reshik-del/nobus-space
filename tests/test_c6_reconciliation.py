from contextlib import closing
from datetime import UTC, datetime, timedelta
import json
import sqlite3

import pytest

from scripts import backup_telegram_runtime as backup
from src.application import runtime_reconciliation as r
from src.application.runtime_maintenance import runtime_database_paths, validate_runtime_set
from src.contracts.models import canonical_json_digest
from src.storage import SQLiteStore
from tests.test_c5_backup_recovery import fixture_runtime, safe_restore
from tests.test_telegram_bindings import config


def setup(tmp_path):
    source,target=tmp_path/'source',tmp_path/'restored'
    fixture_runtime(source)
    original=backup.backup(runtime_database_paths(source),tmp_path/'original-backup')
    safe_restore(original,target)
    later=backup.backup(runtime_database_paths(source),tmp_path/'post-failure-backup')
    binding=tmp_path/'binding.json'
    binding.write_text(json.dumps(config()),encoding='utf-8')
    return source,target,original,later,binding


def test_hold_opens_only_for_exact_owner_plan_and_receipt_is_atomic(tmp_path):
    source,target,original,later,binding=setup(tmp_path)
    store=SQLiteStore(target/'task-runtime.sqlite3')
    assert store.restore_reconciliation_required()
    plan=r.prepare(target,later,binding,original_runtime=source)
    assert store.restore_reconciliation_required()
    result=r.approve(target,later,binding,plan,original_runtime=source,confirmation=canonical_json_digest(plan))
    assert result['status']=='PASS' and not store.restore_reconciliation_required()
    assert store.miniapp_restore_cutoff() is not None
    validate_runtime_set(target)
    with closing(sqlite3.connect(target/'task-runtime.sqlite3')) as db:
        assert db.execute("SELECT count(*) FROM runtime_reconciliations WHERE state='approved'").fetchone()[0]==1
    with pytest.raises(ValueError):
        r.approve(target,later,binding,plan,original_runtime=source,confirmation=canonical_json_digest(plan))


@pytest.mark.parametrize('kind',['wrong_confirmation','expired','forged_watermark','foreign_owner','old_evidence','changed_data'])
def test_invalid_plan_never_clears_hold(tmp_path,kind):
    source,target,original,later,binding=setup(tmp_path)
    plan=r.prepare(target,later,binding,original_runtime=source)
    confirmation=canonical_json_digest(plan)
    if kind=='wrong_confirmation': confirmation='sha256:'+'0'*64
    if kind=='expired':
        plan['expires_at']=(datetime.now(UTC)-timedelta(seconds=1)).isoformat()
        confirmation=canonical_json_digest(plan)
    if kind=='forged_watermark':
        plan['watermark']['task-runtime.sqlite3']='sha256:'+'0'*64
        confirmation=canonical_json_digest(plan)
    if kind=='foreign_owner':
        value=json.loads(binding.read_text())
        value['bindings'][0]['user_id']=value['bindings'][0]['chat_id']=43
        binding.write_text(json.dumps(value))
    if kind=='old_evidence': later=original
    if kind=='changed_data':
        SQLiteStore(target/'task-runtime.sqlite3').claim_miniapp_auth_replay('owner','sha256:'+'f'*64,
            auth_expires_at=datetime.now(UTC)+timedelta(minutes=1),claimed_at=datetime.now(UTC))
    with pytest.raises(Exception):
        r.approve(target,later,binding,plan,original_runtime=source,confirmation=confirmation)
    assert SQLiteStore(target/'task-runtime.sqlite3').restore_reconciliation_required()


def test_post_snapshot_change_requires_reconciliation_not_risk_acceptance(tmp_path):
    source,target,original,later,binding=setup(tmp_path)
    SQLiteStore(source/'task-runtime.sqlite3').claim_miniapp_auth_replay('owner','sha256:'+'e'*64,
        auth_expires_at=datetime.now(UTC)+timedelta(minutes=1),claimed_at=datetime.now(UTC))
    newer=backup.backup(runtime_database_paths(source),tmp_path/'changed-backup')
    with pytest.raises(ValueError,match='post-snapshot change'):
        r.prepare(target,newer,binding,original_runtime=source)
    assert SQLiteStore(target/'task-runtime.sqlite3').restore_reconciliation_required()


def test_audit_write_failure_rolls_back_hold_change(tmp_path,monkeypatch):
    source,target,original,later,binding=setup(tmp_path)
    plan=r.prepare(target,later,binding,original_runtime=source)
    def failed(*args): raise OSError('synthetic audit failure')
    monkeypatch.setattr(r,'_write',failed)
    with pytest.raises(OSError):
        r.approve(target,later,binding,plan,original_runtime=source,confirmation=canonical_json_digest(plan))
    assert SQLiteStore(target/'task-runtime.sqlite3').restore_reconciliation_required()


def test_source_changed_after_later_snapshot_never_reopens_target(tmp_path):
    source,target,original,later,binding=setup(tmp_path)
    plan=r.prepare(target,later,binding,original_runtime=source)
    SQLiteStore(source/'task-runtime.sqlite3').claim_miniapp_auth_replay('owner','sha256:'+'d'*64,
        auth_expires_at=datetime.now(UTC)+timedelta(minutes=1),claimed_at=datetime.now(UTC))
    with pytest.raises(ValueError,match='source changed'):
        r.approve(target,later,binding,plan,original_runtime=source,confirmation=canonical_json_digest(plan))
    assert SQLiteStore(target/'task-runtime.sqlite3').restore_reconciliation_required()


def test_other_original_root_cannot_supply_no_delta_proof(tmp_path):
    source,target,original,later,binding=setup(tmp_path)
    foreign=tmp_path/'foreign'
    fixture_runtime(foreign)
    with pytest.raises(ValueError,match='binding mismatch'):
        r.prepare(target,later,binding,original_runtime=foreign)
    assert SQLiteStore(target/'task-runtime.sqlite3').restore_reconciliation_required()
