"""Synthetic acceptance of the 19 September repair; no production names/state."""
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import io
import json
import sqlite3
import threading
import time

import pytest

from scripts import run_nobus_space_live as s
from scripts import reboot_recovery as reboot
from scripts import runtime_diagnostics as diag
from scripts import observe_nobus_runtime as observer
from scripts import check_nobus_space_health as health
from scripts import run_telegram_backup_cycle as backup
from src.application import runtime_maintenance as maintenance
from tests.test_m1_s1_runtime_supervisor import _record, _BINDING, _Event, _Process
from tests.test_c5_backup_recovery import fixture_runtime
from tests.test_c6_managed_backups import fake_cycle, _isolated_backup_mutexes


@pytest.mark.parametrize('payload,expected', [
    (b'ssh: connect to host synthetic port 22: Connection timed out\n','transport_timeout'),
    (b'ssh: connect to host synthetic port 22: Connection refused\n','transport_refused'),
    (b'read from remote host synthetic: Connection reset by peer\n','transport_reset'),
    (b'ssh: connect to host synthetic port 22: No route to host\n','transport_unreachable'),
    (b'Permission denied (publickey).\n','authentication'),
    (b'Host key verification failed.\n','host_verification'),
    (b'Load key "private": invalid format\n','key'),
    (b'Bad configuration option\n','configuration'),
    (b'ssh: connect to host synthetic port 22: Connection refused\nPermission denied\n','authentication'),
    (b'remote says Connection refused\n','unknown'),
    (b'','unknown'), (b'x'*8193,'unknown'),
])
def test_relay_allowlist(payload, expected):
    assert diag.classify_relay(payload) == expected
    assert diag.classify_relay(payload, complete=False) == 'unknown'


@pytest.mark.parametrize('stage',['relay_start','startup','steady'])
@pytest.mark.parametrize('cause',sorted(diag.RELAY_CAUSES))
def test_relay_policy(stage,cause):
    terminal={'stage':stage,'error_class':'relay_exit','relay_cause':cause,'relay_exit_code':255,
              'core_exit_code':None,'local_ready':None,'public_ready':None}
    args=dict(status=1,terminal=terminal,core_outcome=None if stage=='relay_start' else {'status':'STOPPED'},
              core_outcome_error=None,cleanup_ok=True,attempt=1,retry_budget=10)
    assert s._recovery_disposition(**args) == ('retry' if cause in diag.TRANSIENT_RELAY_CAUSES else 'stop_non_retryable')
    args['cleanup_ok']=False
    assert s._recovery_disposition(**args)=='stop_cleanup_failed'
    args.update(cleanup_ok=True,attempt=11)
    assert s._recovery_disposition(**args)==('stop_budget_exhausted' if cause in diag.TRANSIENT_RELAY_CAUSES else 'stop_non_retryable')


def started(root,boot='sha256:'+'a'*64):
    s._initialize_recovery(root=root,activation_binding=_BINDING)
    for event in ('control_starting','control_ready'):
        _record(root,'b'*32,'c'*32,event,stage='recovery_control',supervisor_exit_code=0 if event=='control_ready' else None)
    _record(root,'b'*32,'d'*32,'starting',boot_id=boot)


@pytest.fixture
def no_native_mutex(monkeypatch):
    # Never acquire production mutexes in a synthetic test.
    from src.application import windows_singleton
    monkeypatch.setattr(windows_singleton,'WindowsNamedMutex',lambda *a: nullcontext())


def test_reboot_preserves_history_and_consumes_budget(tmp_path,no_native_mutex):
    started(tmp_path)
    before,digests=s._runtime_history(root=tmp_path,activation_binding=_BINDING)
    assert reboot.reconcile(s,SimpleNamespace(),root=tmp_path,binding=_BINDING,
                            current_boot='sha256:'+'e'*64,validate=lambda:None,absent=lambda:True)
    rows,after=s._runtime_history(root=tmp_path,activation_binding=_BINDING)
    assert rows[:-1]==before and after[:-1]==digests
    assert rows[-1]['event']=='reboot_reconciled' and rows[-1]['reset_of_digest']==digests[-1]
    state=s._recovery_state(root=tmp_path,activation_binding=_BINDING)
    assert state['state']=='resume' and state['next_attempt']==2
    assert not reboot.reconcile(s,SimpleNamespace(),root=tmp_path,binding=_BINDING,
                               current_boot='sha256:'+'e'*64,validate=lambda:None,absent=lambda:True)
    _record(tmp_path,'b'*32,'f'*32,'control_starting',attempt=2,stage='recovery_control')


@pytest.mark.parametrize('case',['same_boot','children','effects','legacy','corrupt','binding'])
def test_reboot_denies_unsafe_continuation(tmp_path,no_native_mutex,case):
    started(tmp_path,boot=None if case=='legacy' else 'sha256:'+'a'*64)
    def validate():
        if case=='effects': raise ValueError('synthetic unknown effect')
    if case=='corrupt':
        with (tmp_path/s.RUNTIME_EVENT_LOG_NAME).open('ab') as stream:stream.write(b'incomplete')
    content=(tmp_path/s.RUNTIME_EVENT_LOG_NAME).read_bytes()
    try:
        result=reboot.reconcile(s,SimpleNamespace(),root=tmp_path,
            binding='sha256:'+'0'*64 if case=='binding' else _BINDING,
            current_boot='sha256:'+('a' if case=='same_boot' else 'e')*64,
            validate=validate,absent=lambda:case!='children')
        assert result is False
    except ValueError:
        assert case=='effects'
    assert (tmp_path/s.RUNTIME_EVENT_LOG_NAME).read_bytes()==content


def test_reboot_effect_validation_is_readonly_and_rejects_unknown_capability(tmp_path):
    runtime=tmp_path/'state'
    store,queue,_,_=fixture_runtime(runtime)
    reboot.validate_effects(runtime)
    from src.application.product_effects import DurableProductEffectVault,ProductEffectKind
    vault=DurableProductEffectVault(queue)
    token=vault.issue(kind=ProductEffectKind.ARTIFACT,tenant_id='synthetic',user_id=1,chat_id=1,payload={'synthetic':True})
    with pytest.raises(ValueError,match='effect capability'):
        reboot.validate_effects(runtime)


def test_production_verifier_identity_does_not_normalize_binding(monkeypatch):
    monkeypatch.setattr(s.sys,'executable','C:/synthetic/python.exe')
    monkeypatch.setattr(s.sys,'_base_executable','C:/synthetic/base/python.exe')
    with pytest.raises(ValueError,match='windowed'): s.require_production_identity()
    monkeypatch.setattr(s.sys,'executable','C:/synthetic/pythonw.exe')
    monkeypatch.setattr(s.sys,'_base_executable','C:/synthetic/base/pythonw.exe')
    s.require_production_identity()


def test_local_probe_contract_and_safe_diagnostics(monkeypatch):
    seen=[]
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,limit):assert limit==256;return b'{"status":"ready"}'
    class Opener:
        def open(self,request,timeout):seen.append((request,timeout));return Response()
    monkeypatch.setattr(s.urllib.request,'build_opener',lambda *a:Opener())
    assert s.ready()
    assert seen[0][0].get_header('Host')=='app.nobusspace.com' and seen[0][1]==2
    assert s._LOCAL_READINESS_PROBE.last['status']=='PASS'
    assert s._LOCAL_READINESS_PROBE.last['http_status']==200


def test_diagnostic_oversize_capture_does_not_authorize_retry():
    capture=diag.RelayCapture(io.BytesIO(b'ssh: connect to host x port 22: Connection refused\n'+b'x'*9000))
    assert capture.finish()=='unknown' and not capture.content


def test_diagnostic_rejects_payload_and_preserves_typed_failure(tmp_path):
    check={'boundary':'public','status':'FAIL','at':'2026-09-19T00:00:00Z','http_status':502,
           'body_matches':False,'error_class':'http_error','elapsed_ms':10,'deadline_ms':5000}
    value={'run_id':'a'*32,'attempt':1,'stage':'steady','checks':[check]}
    diag.write_diagnostic(tmp_path,'readiness',value)
    row=json.loads((tmp_path/'readiness.jsonl').read_bytes())
    authentication=row.pop('authentication')
    s._verify_authentication(row,authentication,entropy=b'nobus:diagnostic:1')
    check['payload']='must not persist'
    with pytest.raises(ValueError):diag.write_diagnostic(tmp_path,'readiness',value)
    assert b'must not persist' not in (tmp_path/'readiness.jsonl').read_bytes()


def test_backup_cleanup_already_stopped_never_requests_stop(monkeypatch):
    operations=[]
    config={'tasks':{'main':{'name':'synthetic-main'},'health':{'name':'synthetic-health'}}}
    monkeypatch.setattr(backup,'_bound_task',lambda c,op,name:operations.append(op))
    monkeypatch.setattr(backup,'_stopped',lambda c:True)
    monkeypatch.setattr(backup,'_runner',lambda mode:pytest.fail('stop on absent runtime'))
    assert backup._cleanup(config,time.monotonic,lambda _:None)
    assert operations==['Disable','Disable']


def test_failed_backup_keeps_copy_and_safe_operator_recovery(tmp_path,monkeypatch):
    path,digest,states,events=fake_cycle(tmp_path,monkeypatch)
    original=backup._runner
    monkeypatch.setattr(backup,'_runner',lambda mode:False if mode=='--check-ready' else original(mode))
    ticks=iter(range(0,10000,20))
    with pytest.raises(ValueError,match='restart readiness'):
        backup.cycle(path,digest,clock=lambda:next(ticks),wait=lambda _:None)
    receipt=backup.managed._certificate(tmp_path/'backup-cycle-state.dpapi')
    assert receipt['phase']=='failed_operator_required' and receipt['backup_status']=='VERIFIED'
    assert receipt['generation'] and receipt['admission_hold'] and receipt['cleanup_proven']
    assert receipt['failure_class']=='restart_not_ready'
    from src.contracts.models import canonical_json_digest
    monkeypatch.setattr(backup,'_runner',original)
    result=backup.cycle(path,digest,recover_failure_digest=canonical_json_digest(receipt))
    assert result['status']=='PASS' and result['runtime_ready']


def test_readonly_store_does_not_enter_admission_write_path(tmp_path):
    runtime=tmp_path/'state';fixture_runtime(runtime)
    store=maintenance._read_only_store(runtime/'task-runtime.sqlite3')
    with store._connect() as con:
        with pytest.raises(sqlite3.OperationalError):con.execute('CREATE TABLE forbidden(x)')
    assert store.restore_reconciliation_required() is False


def test_observer_retains_independent_checks_on_failure(tmp_path,monkeypatch):
    runtime=tmp_path/'state';fixture_runtime(runtime)
    monkeypatch.setattr(observer.s,'ready',lambda:False)
    monkeypatch.setattr(observer.s,'public_ready',lambda:False)
    monkeypatch.setattr(observer.s,'readiness_details',lambda:[{'boundary':b,'status':'FAIL'} for b in ('local','public')])
    original=maintenance.validate_runtime_database
    def validate(path):
        if path.name=='task-runtime.sqlite3':raise RuntimeError('synthetic unavailable')
        original(path)
    monkeypatch.setattr(maintenance,'validate_runtime_database',validate)
    result=observer.observe(runtime)['checks']
    assert result['delivery']=={'status':'NOT CHECKED','reason':'task_database_unverified'}
    assert result['checkpoint']['status']=='PASS' and result['local']['status']=='FAIL'


def test_boot_identity_native_read_is_stable():
    # Read-only native query, never reboots the host.
    assert reboot.boot_identity()==reboot.boot_identity()
    assert s._digest(reboot.boot_identity())


def test_reboot_checks_active_polling_lease(tmp_path):
    runtime=tmp_path/'state';fixture_runtime(runtime)
    from src.transport.telegram.sqlite_checkpoint import SQLitePollingCheckpointStore
    from datetime import UTC,datetime,timedelta
    # A real protected checkpoint exercises its normal lease API.
    checkpoint=SQLitePollingCheckpointStore(runtime/'telegram-checkpoint.sqlite3',consumer_id='synthetic-boot')
    from uuid import uuid4
    lease=checkpoint.acquire(uuid4(),datetime.now(UTC))
    assert lease is not None
    with pytest.raises(ValueError,match='lease active'):reboot.validate_effects(runtime)
    assert checkpoint.release(lease)
    reboot.validate_effects(runtime)


def test_observer_admission_hold_does_not_erase_integrity(tmp_path,monkeypatch):
    runtime=tmp_path/'state';fixture_runtime(runtime)
    root=tmp_path/'backups'
    ownership=backup.managed.initialize(root,runtime,'sha256:'+'a'*64)
    backup.managed.create_generation(root,runtime,ownership)
    backup.managed.hold_admission(root,ownership)
    monkeypatch.setattr(observer.s,'ready',lambda:False)
    monkeypatch.setattr(observer.s,'public_ready',lambda:False)
    monkeypatch.setattr(observer.s,'readiness_details',lambda:[{'boundary':b,'status':'FAIL'} for b in ('local','public')])
    checks=observer.observe(runtime,backup_root=root,ownership=ownership)['checks']
    assert checks['admission_hold']=={'status':'PASS','value':True}
    assert checks['backup']['status']=='PASS' and checks['backup_freshness']['status']=='PASS'
    assert checks['cross_database']['status']=='PASS' and checks['delivery']['status']=='PASS'


def test_relay_terminal_v4_survives_authenticated_serialization(tmp_path):
    started(tmp_path)
    _record(tmp_path,'b'*32,'d'*32,'terminal',stage='relay_start',error_class='relay_exit',
            supervisor_exit_code=1,relay_exit_code=255,relay_cause='transport_refused',
            recovery_disposition='retry',cleanup_outcome='proven')
    rows,_=s._runtime_history(root=tmp_path,activation_binding=_BINDING)
    assert rows[-1]['relay_cause']=='transport_refused' and rows[-1]['schema']=='nobus-runtime-event-4'


def test_health_failure_preserves_each_check_without_recovery(tmp_path,monkeypatch):
    runtime=tmp_path/'state';fixture_runtime(runtime)
    validate=health.db.validate_runtime_database
    def failing(path):
        if path.name=='telegram-state.sqlite3':raise ValueError('synthetic')
        validate(path)
    monkeypatch.setattr(health.db,'validate_runtime_database',failing)
    def pair(_):
        for probe in (s._LOCAL_READINESS_PROBE,s._PUBLIC_READINESS_PROBE):
            probe.last={'status':'PASS','at':'2026-09-19T00:00:00Z','http_status':200,'body_matches':True,
                        'error_class':None,'elapsed_ms':1,'deadline_ms':2000}
        return True,True
    monkeypatch.setattr(s,'_readiness_pair',pair)
    result=health.check(runtime,tmp_path/'diag')
    assert result['status']=='FAIL'
    failed=[row for row in result['checks'] if row['status']=='FAIL']
    assert len(failed)==1 and failed[0]['boundary']=='telegram-state.sqlite3'
    assert failed[0]['error_class']=='database_failed'
    assert all(row['status']=='PASS' for row in result['checks'] if row['boundary']!='telegram-state.sqlite3')


def test_rollback_reader_preserves_new_history_without_data_restore(tmp_path,no_native_mutex):
    import subprocess
    import importlib.util
    root=Path(__file__).resolve().parents[1]
    legacy=tmp_path/'rollback'/'scripts'/'run_nobus_space_live.py'
    legacy.parent.mkdir(parents=True)
    content=subprocess.check_output(['git','show','0bd63db06fd9f6e73f6a5ed174b4b8da2859ee5c:scripts/run_nobus_space_live.py'],cwd=root)
    legacy.write_bytes(content)
    subprocess.run(['git','apply',str(root/'ops/windows/m1-s1-rollback-compat.patch')],cwd=tmp_path/'rollback',check=True,capture_output=True)
    spec=importlib.util.spec_from_file_location('rollback_supervisor',legacy)
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    history=tmp_path/'history';started(history)
    reboot.reconcile(s,SimpleNamespace(),root=history,binding=_BINDING,
        current_boot='sha256:'+'e'*64,validate=lambda:None,absent=lambda:True)
    assert old._runtime_history(root=history)==s._runtime_history(root=history)
    assert old._recovery_state(root=history,activation_binding=_BINDING)['next_attempt']==2
    # Clean stop is mandatory before either direction's exact-digest rebind.
    with pytest.raises(RuntimeError):
        old._rebind_recovery(s._last_runtime_event(root=history)[1],root=history,activation_binding='sha256:'+'f'*64)
    for event in ('control_starting','control_ready'):
        _record(history,'b'*32,'f'*32,event,attempt=2,stage='recovery_control',supervisor_exit_code=0 if event=='control_ready' else None)
    _record(history,'b'*32,'d'*32,'starting',attempt=2,boot_id='sha256:'+'e'*64)
    _record(history,'b'*32,'d'*32,'terminal',attempt=2,stage='steady',error_class='planned_stop',
            supervisor_exit_code=0,core_outcome={'status':'STOPPED'},cleanup_outcome='proven',recovery_disposition='stop_planned')
    for event in ('control_closing','control_closed'):
        _record(history,'b'*32,'f'*32,event,attempt=2,stage='recovery_control',supervisor_exit_code=0,
            cleanup_outcome='proven',recovery_disposition='stop_planned')
    before,digests=s._runtime_history(root=history)
    old._rebind_recovery(digests[-1],root=history,activation_binding='sha256:'+'f'*64)
    after,_=s._runtime_history(root=history)
    assert after[:-1]==before


def test_reboot_waits_for_same_lease_then_continues_once(tmp_path,no_native_mutex):
    from datetime import UTC,datetime,timedelta
    from uuid import uuid4
    from src.transport.telegram.sqlite_checkpoint import SQLitePollingCheckpointStore
    runtime=tmp_path/'state';fixture_runtime(runtime)
    now=datetime.now(UTC)
    checkpoint=SQLitePollingCheckpointStore(runtime/'telegram-checkpoint.sqlite3',consumer_id='synthetic',lease_duration_seconds=240)
    checkpoint.acquire(uuid4(),now)
    history=tmp_path/'history';started(history)
    clock=[0.0]
    def wait(seconds):clock[0]+=seconds
    assert reboot.reconcile(s,SimpleNamespace(),root=history,binding=_BINDING,
        current_boot='sha256:'+'e'*64,absent=lambda:True,
        validate=lambda:reboot.validate_effects(runtime,now=now+timedelta(seconds=clock[0])),
        clock=lambda:clock[0],wait=wait)
    assert 240<=clock[0]<241
    assert s._recovery_state(root=history,activation_binding=_BINDING)['next_attempt']==2
    assert sum(row['event']=='reboot_reconciled' for row in s._runtime_history(root=history)[0])==1


@pytest.mark.parametrize('cause',['changed','never_expires','runtime_appears'])
def test_reboot_lease_wait_remains_bounded_and_exclusive(tmp_path,no_native_mutex,cause):
    started(tmp_path);clock=[0.0];calls=[0]
    before=(tmp_path/s.RUNTIME_EVENT_LOG_NAME).read_bytes()
    def wait(seconds):clock[0]+=seconds
    def validate():
        calls[0]+=1
        if cause=='runtime_appears' and calls[0]>1:return 'initial'
        raise reboot.PreviousPollingLease(1,'changed' if cause=='changed' and calls[0]>1 else 'initial')
    if cause=='runtime_appears':
        assert not reboot.reconcile(s,SimpleNamespace(),root=tmp_path,binding=_BINDING,
            current_boot='sha256:'+'e'*64,absent=lambda:calls[0]==0,validate=validate,clock=lambda:clock[0],wait=wait)
    else:
        with pytest.raises(ValueError,match='changed or deadline'):
            reboot.reconcile(s,SimpleNamespace(),root=tmp_path,binding=_BINDING,
                current_boot='sha256:'+'e'*64,absent=lambda:True,validate=validate,clock=lambda:clock[0],wait=wait)
    assert clock[0]<=300 and (tmp_path/s.RUNTIME_EVENT_LOG_NAME).read_bytes()==before


def test_reboot_delivered_capability_is_safe_unknown_still_stops(tmp_path):
    from src.application.product_effects import DurableProductEffectVault,ProductEffectKind
    runtime=tmp_path/'state';_,queue,_,_=fixture_runtime(runtime)
    vault=DurableProductEffectVault(queue)
    token=vault.issue(kind=ProductEffectKind.ARTIFACT,tenant_id='synthetic',user_id=1,chat_id=1,payload={'synthetic':True})
    binding=vault.read(token,tenant_id='synthetic',user_id=1,chat_id=1)
    for state in ('executing','unknown','completed'):
        binding=vault.transition(binding,state=state,result={'delivered':False})
        with pytest.raises(ValueError,match='effect capability'):reboot.validate_effects(runtime)
    vault.transition(binding,state='delivered',result={'delivered':True})
    reboot.validate_effects(runtime)


@pytest.mark.parametrize('extra,expected',[({'backup_status':'VERIFIED'},True),({'backup_status':'NOT_CREATED'},False),({'backup_status':'VERIFIED','unreviewed':True},False)])
def test_backup_journal_writer_and_restart_reader_agree(tmp_path,extra,expected):
    config=tmp_path/'cycle.json';digest='sha256:'+'c'*64
    backup._journal(tmp_path/'backup-cycle-state.dpapi',digest,'restart_permitted',
        attempt_id='a'*32,generation='daily-20260919T033000-'+'b'*32,**extra)
    assert s._backup_restart_authorized(config,digest) is expected


@pytest.mark.parametrize('outcome',['recoverable','permanent','exhausted'])
def test_backup_waits_only_for_authenticated_retry_progress(tmp_path,monkeypatch,outcome):
    path,digest,states,events=fake_cycle(tmp_path,monkeypatch)
    ticks=[0.0];original=backup._runner
    def runner(mode):
        if mode=='--check-ready':return outcome=='recoverable' and ticks[0]>=421
        return original(mode)
    def progress(*args):
        if outcome=='permanent':raise ValueError('runtime recovery stopped')
        return 1 if ticks[0]<360 else 2+int((ticks[0]-360)//400)
    monkeypatch.setattr(backup,'_runner',runner)
    monkeypatch.setattr(backup,'_recovery_progress',progress)
    def wait(seconds):ticks[0]+=seconds
    if outcome=='recoverable':
        assert backup.cycle(path,digest,clock=lambda:ticks[0],wait=wait)['runtime_ready']
        assert 421<=ticks[0]<435
    else:
        with pytest.raises(ValueError):backup.cycle(path,digest,clock=lambda:ticks[0],wait=wait)
        receipt=backup.managed._certificate(tmp_path/'backup-cycle-state.dpapi')
        assert receipt['phase']=='failed_operator_required' and receipt['backup_status']=='VERIFIED'
        assert receipt['admission_hold'] and receipt['cleanup_proven']
        assert ticks[0]<=1140
        if outcome=='permanent':assert ticks[0]==0


@pytest.mark.parametrize('cause',['transport_refused','unknown'])
def test_backup_progress_reads_authenticated_supervisor_history(tmp_path,cause):
    runtime=tmp_path/'state';history=runtime/s.RECOVERY_DIRECTORY_NAME
    started(history)
    binding,initial=backup._recovery_anchor(runtime)
    _record(history,'b'*32,'d'*32,'terminal',stage='relay_start',error_class='relay_exit',
        supervisor_exit_code=1,relay_exit_code=255,relay_cause=cause,cleanup_outcome='proven',
        recovery_disposition='retry' if cause=='transport_refused' else 'stop_non_retryable')
    if cause=='transport_refused':
        assert backup._recovery_progress(runtime,binding,initial)==2
    else:
        with pytest.raises(ValueError,match='recovery stopped'):backup._recovery_progress(runtime,binding,initial)
        _,stopped_head=backup._recovery_anchor(runtime)
        with pytest.raises(ValueError,match='recovery stopped'):backup._recovery_progress(runtime,binding,stopped_head)
    with pytest.raises((ValueError,RuntimeError)):
        backup._recovery_progress(runtime,'sha256:'+'0'*64,initial)


@pytest.mark.parametrize('changed',[False,True])
def test_reboot_rechecks_native_boot_proof_before_commit(tmp_path,no_native_mutex,monkeypatch,changed):
    started(tmp_path)
    identities=iter(['sha256:'+'e'*64,'sha256:'+('f' if changed else 'e')*64])
    monkeypatch.setattr(reboot,'boot_identity',lambda:next(identities))
    before=(tmp_path/s.RUNTIME_EVENT_LOG_NAME).read_bytes()
    if changed:
        with pytest.raises(ValueError,match='boot identity changed'):
            reboot.reconcile(s,SimpleNamespace(),root=tmp_path,binding=_BINDING,validate=lambda:None,absent=lambda:True)
        assert (tmp_path/s.RUNTIME_EVENT_LOG_NAME).read_bytes()==before
    else:
        assert reboot.reconcile(s,SimpleNamespace(),root=tmp_path,binding=_BINDING,validate=lambda:None,absent=lambda:True)
