from datetime import UTC,datetime,timedelta
import json
import shutil

import pytest

from src.application import managed_backups as b
from src.application import runtime_maintenance as m
from src.contracts.models import canonical_json_digest
from scripts import run_telegram_backup_cycle as cycle
from tests.test_c5_backup_recovery import fixture_runtime


def test_retention_7days_4weeks_is_reversible_and_never_adopts_old_backups(tmp_path):
    runtime=tmp_path/'runtime'
    fixture_runtime(runtime)
    root=tmp_path/'managed'
    ownership=b.initialize(root,runtime,'sha256:'+'a'*64)
    first=b.create_generation(root,runtime,ownership)
    entries=b._certificate(first/'generation.dpapi')
    # Synthetic generations contain identical genuine encrypted snapshot bytes.
    start=datetime(2026,8,1,3,30,tzinfo=UTC)
    for number in range(40):
        stamp=start+timedelta(days=number)
        name='daily-'+stamp.strftime('%Y%m%dT%H%M%S')+'-'+f'{number:032x}'
        dest=root/name
        dest.mkdir()
        shutil.copytree(first/'snapshot',dest/'snapshot')
        intent=dict(b._certificate(first/'intent.dpapi'),name=name,identity=b._identity(dest),local_time=stamp.isoformat())
        (dest/'intent.dpapi').write_bytes(b.CODEC.encode(intent))
        inventory,_=b._inventory(dest)
        value=dict(entries,name=name,identity=b._identity(dest),local_time=stamp.isoformat(),files=inventory)
        (dest/'generation.dpapi').write_bytes(b.CODEC.encode(value))
    old=tmp_path/'previous-user-backup'
    old.mkdir()
    (old/'marker').write_bytes(b'preserve')
    dry=b.retention(root,ownership)
    assert 7<=len(dry['kept'])<=11 and dry['quarantined']==0
    applied=b.retention(root,ownership,apply=True)
    assert applied['selected']==dry['selected'] and applied['deleted']==0
    assert (old/'marker').read_bytes()==b'preserve'
    for name in applied['selected']:
        assert (root/'quarantine'/name/'generation.dpapi').is_file()
    assert b.retention(root,ownership)['selected']==[]


def test_extra_or_changed_file_prevents_quarantine(tmp_path):
    runtime=tmp_path/'runtime'
    fixture_runtime(runtime)
    root=tmp_path/'managed'
    ownership=b.initialize(root,runtime,'sha256:'+'a'*64)
    generation=b.create_generation(root,runtime,ownership)
    (generation/'unexpected').write_bytes(b'not-owned')
    with pytest.raises(ValueError,match='unowned'):
        b.retention(root,ownership,apply=True)
    assert generation.is_dir() and not (root/'quarantine').exists()
    with pytest.raises(ValueError):
        b.retention(root,'sha256:'+'b'*64,apply=True)


def fake_cycle(tmp_path,monkeypatch):
    runtime=tmp_path/'runtime'
    fixture_runtime(runtime)
    root=tmp_path/'backups'
    ownership=b.initialize(root,runtime,'sha256:'+'a'*64)
    events=[]
    states={name:{'name':name,'enabled':True,'state':'Running','last_result':0,'signature':{'test':'synthetic'}}
            for name in ('NobusSpaceTestMain','NobusSpaceTestHealth')}
    def task(operation,name):
        events.append(operation+':'+name)
        if operation=='Disable': states[name]['enabled']=False
        if operation=='Enable': states[name]['enabled']=True
        if operation=='Start': states[name]['state']='Running'
        if operation=='Stop': states[name]['state']='Disabled'
        return dict(states[name])
    def runner(mode):
        events.append(mode)
        if mode=='--stop': states['NobusSpaceTestMain']['state']='Disabled'
        return True
    monkeypatch.setattr(cycle,'_task',task)
    monkeypatch.setattr(cycle,'_runner',runner)
    monkeypatch.setattr(cycle,'_port_closed',lambda:True)
    inputs={name:m.file_evidence(cycle.ROOT/name) for name in (
        'ops/windows/Invoke-NobusSpaceTask.ps1','docs/11-Контекст-продукта.md')}
    config={'schema':'c6-backup-cycle-1','application':m.application_binding(),'runtime':str(runtime),
        'backup_root':str(root),'ownership':ownership,'inputs':inputs,
        'tasks':{role:{'name':name,'signature':states[name]['signature']} for role,name in
                 [('main','NobusSpaceTestMain'),('health','NobusSpaceTestHealth')]}}
    path=tmp_path/'cycle.json'
    path.write_text(json.dumps(config))
    return path,canonical_json_digest(config),states,events


def test_cycle_orders_stop_backup_restart_and_preserves_disabled_intent(tmp_path,monkeypatch):
    path,digest,states,events=fake_cycle(tmp_path,monkeypatch)
    result=cycle.cycle(path,digest)
    assert result['status']=='PASS' and result['backup_created']
    assert events.index('--stop')<events.index('Start:NobusSpaceTestMain')<events.index('--check-ready')
    assert all(v['enabled'] for v in states.values())
    states['NobusSpaceTestMain']['enabled']=False
    result=cycle.cycle(path,digest)
    assert result['status']=='SKIPPED' and not result['backup_created']
    assert not states['NobusSpaceTestMain']['enabled']


def test_copy_failure_stops_admission_and_does_not_restart_or_claim_pass(tmp_path,monkeypatch):
    path,digest,states,events=fake_cycle(tmp_path,monkeypatch)
    def fail(*args,**kwargs): raise OSError('synthetic copy failure')
    monkeypatch.setattr(b,'create_generation',fail)
    with pytest.raises(OSError):
        cycle.cycle(path,digest)
    assert not any(v['enabled'] for v in states.values())
    assert 'Start:NobusSpaceTestMain' not in events
    receipt=b._certificate(tmp_path/'backup-cycle-state.dpapi')
    assert receipt['phase']=='failed_operator_required'
    with pytest.raises(ValueError,match='previous backup'):
        cycle.cycle(path,digest)


def test_backup_freshness_and_capacity_block_admission(tmp_path,monkeypatch):
    from types import SimpleNamespace
    runtime=tmp_path/'runtime'
    fixture_runtime(runtime)
    root=tmp_path/'managed'
    ownership=b.initialize(root,runtime,'sha256:'+'a'*64)
    with pytest.raises((OSError,ValueError)):
        b.assert_recent(root,ownership,runtime)
    b.create_generation(root,runtime,ownership)
    b.assert_recent(root,ownership,runtime)
    monkeypatch.setattr(shutil,'disk_usage',lambda _:SimpleNamespace(free=255*1024*1024))
    with pytest.raises(RuntimeError,match='disk capacity'):
        b.assert_recent(root,ownership,runtime)
    monkeypatch.undo()
    # Advance the clock without changing or forging an authenticated snapshot.
    class Tomorrow(datetime):
        @classmethod
        def now(cls,tz=None):
            return datetime.now(tz)+timedelta(hours=25)
    monkeypatch.setattr(b,'datetime',Tomorrow)
    with pytest.raises(RuntimeError,match='freshness'):
        b.assert_recent(root,ownership,runtime)


def test_explicit_failed_cycle_recovery_retains_failure_and_rejects_replay(tmp_path,monkeypatch):
    path,digest,states,events=fake_cycle(tmp_path,monkeypatch)
    original=b.create_generation
    monkeypatch.setattr(b,'create_generation',lambda *args,**kwargs:(_ for _ in ()).throw(OSError('synthetic')))
    with pytest.raises(OSError): cycle.cycle(path,digest)
    old=b._certificate(tmp_path/'backup-cycle-state.dpapi')
    confirmation=canonical_json_digest(old)
    monkeypatch.setattr(b,'create_generation',original)
    states['NobusSpaceTestHealth']['state']='Disabled'
    with pytest.raises(ValueError):
        cycle.cycle(path,digest,recover_failure_digest='sha256:'+'0'*64)
    result=cycle.cycle(path,digest,recover_failure_digest=confirmation)
    assert result['status']=='PASS' and all(v['enabled'] for v in states.values())
    retained=list(tmp_path.glob('failed-cycle-*.dpapi'))
    assert len(retained)==1 and b._certificate(retained[0])==old
    with pytest.raises(ValueError,match='no matching'):
        cycle.cycle(path,digest,recover_failure_digest=confirmation)


def test_missed_daily_run_backs_up_before_starting_stopped_enabled_runtime(tmp_path,monkeypatch):
    path,digest,states,events=fake_cycle(tmp_path,monkeypatch)
    states['NobusSpaceTestMain'].update(state='Ready',last_result=1)
    result=cycle.cycle(path,digest)
    assert result['status']=='PASS' and result['backup_created']
    assert '--stop' not in events
    assert events.index('Disable:NobusSpaceTestMain')<events.index('Start:NobusSpaceTestMain')


def test_unavailable_backup_never_accepts_or_queues_miniapp_task(tmp_path):
    from fastapi.testclient import TestClient
    from tests.test_c3_multipart_input import setup,post,form
    app,token,store,queue,admission,compiler=setup(tmp_path)
    def unavailable(*, for_admission): raise RuntimeError('synthetic expired backup')
    admission._admission_readiness=unavailable
    with TestClient(app) as client:
        response=post(client,token,*form())
    assert response.status_code==503
    assert queue.queue_counts()==(0,0) and compiler.calls==[]
    assert len(store.list_tasks('owner',limit=20))==0


def test_refused_graceful_stop_is_forced_verified_and_keeps_admission_hold(tmp_path,monkeypatch):
    path,digest,states,events=fake_cycle(tmp_path,monkeypatch)
    config=json.loads(path.read_text())
    b.create_generation(tmp_path/'backups',tmp_path/'runtime',config['ownership'])
    monkeypatch.setattr(cycle,'_runner',lambda _:False)
    with pytest.raises(ValueError,match='graceful stop'):
        cycle.cycle(path,digest)
    assert all(not s['enabled'] and s['state']!='Running' for s in states.values())
    receipt=b._certificate(tmp_path/'backup-cycle-state.dpapi')
    assert receipt['cleanup_proven'] is True and receipt['admission_hold'] is True
    assert 'Stop:NobusSpaceTestMain' in events
    with pytest.raises(RuntimeError,match='backup cycle'):
        b.assert_recent(tmp_path/'backups',config['ownership'],tmp_path/'runtime')


def test_failed_forced_stop_is_reported_without_false_cleanup_proof(tmp_path,monkeypatch):
    path,digest,states,events=fake_cycle(tmp_path,monkeypatch)
    original=cycle._task
    def refuses_stop(operation,name):
        if operation=='Stop': return dict(states[name])
        return original(operation,name)
    monkeypatch.setattr(cycle,'_task',refuses_stop)
    monkeypatch.setattr(cycle,'_runner',lambda _:False)
    tick=[0]
    def clock():
        tick[0]+=10
        return tick[0]
    with pytest.raises(ValueError):
        cycle.cycle(path,digest,clock=clock,wait=lambda _:None)
    receipt=b._certificate(tmp_path/'backup-cycle-state.dpapi')
    assert receipt['cleanup_proven'] is False and receipt['admission_hold'] is True
    assert states['NobusSpaceTestMain']['state']=='Running'
    assert 'Start:NobusSpaceTestMain' not in events


@pytest.mark.parametrize('failure',['snapshot','certificate','pointer'])
def test_partial_generation_can_be_recovered_once_without_adopting_other_data(tmp_path,monkeypatch,failure):
    from scripts import backup_telegram_runtime as backup_module
    path,digest,states,events=fake_cycle(tmp_path,monkeypatch)
    config=json.loads(path.read_text())
    original_backup=backup_module.backup
    original_write=m.write_bytes_durable
    def interrupted_backup(sources,destination):
        original_backup(sources,destination)
        raise OSError('synthetic crash after data write')
    def interrupted_write(destination,content):
        if (failure=='certificate' and destination.name=='generation.dpapi'):
            raise OSError('synthetic certificate write')
        original_write(destination,content)
        if failure=='pointer' and destination.name=='latest-pending.dpapi':
            raise OSError('synthetic crash before pointer publish')
    if failure=='snapshot': monkeypatch.setattr(backup_module,'backup',interrupted_backup)
    else: monkeypatch.setattr(m,'write_bytes_durable',interrupted_write)
    with pytest.raises(OSError): cycle.cycle(path,digest)
    root=tmp_path/'backups'
    failed=b._certificate(tmp_path/'backup-cycle-state.dpapi')
    names={p.name for p in root.iterdir() if p.is_dir()}
    assert len(names)==1
    monkeypatch.setattr(backup_module,'backup',original_backup)
    monkeypatch.setattr(m,'write_bytes_durable',original_write)
    result=cycle.cycle(path,digest,recover_failure_digest=canonical_json_digest(failed))
    assert result['status']=='PASS'
    if failure!='pointer':
        assert {p.name for p in (root/'quarantine').iterdir()}==names
    # A complete certificate with a valid pending pointer is already a usable copy.
    b.assert_recent(root,config['ownership'],tmp_path/'runtime')
    with pytest.raises(ValueError,match='no matching'):
        cycle.cycle(path,digest,recover_failure_digest=canonical_json_digest(failed))


def test_quarantine_limits_include_nested_files_and_preflight_preserves_all_sources(tmp_path,monkeypatch):
    runtime=tmp_path/'runtime'
    fixture_runtime(runtime)
    root=tmp_path/'backups'
    ownership=b.initialize(root,runtime,'sha256:'+'a'*64)
    generation=b.create_generation(root,runtime,ownership)
    _,amount=b._inventory(generation)
    monkeypatch.setattr(b,'MAX_QUARANTINE_BYTES',amount-1)
    with pytest.raises(ValueError,match='quarantine capacity'):
        b._move_to_quarantine(root,ownership,[generation])
    assert generation.exists() and not (root/'quarantine').exists()
    monkeypatch.setattr(b,'MAX_QUARANTINE_BYTES',amount+1024)
    b._move_to_quarantine(root,ownership,[generation])
    monkeypatch.setattr(b,'MAX_QUARANTINE_ENTRIES',0)
    with pytest.raises(ValueError,match='quarantine capacity'):
        b.retention(root,ownership)


def test_partial_recovery_rejects_foreign_attempt_and_unknown_member(tmp_path,monkeypatch):
    from scripts import backup_telegram_runtime as backup_module
    runtime=tmp_path/'runtime'
    fixture_runtime(runtime)
    root=tmp_path/'backups'
    ownership=b.initialize(root,runtime,'sha256:'+'a'*64)
    def failure(*args): raise OSError('synthetic')
    monkeypatch.setattr(backup_module,'backup',failure)
    with pytest.raises(OSError): b.create_generation(root,runtime,ownership,attempt_id='a'*32)
    generation=next(p for p in root.iterdir() if p.is_dir())
    with pytest.raises(ValueError,match='another cycle'):
        b.recover_partial(root,ownership,'b'*32)
    (generation/'unexpected').write_bytes(b'preserve')
    with pytest.raises(ValueError,match='unowned'):
        b.recover_partial(root,ownership,'a'*32)
    assert (generation/'unexpected').read_bytes()==b'preserve'


@pytest.mark.parametrize('unknown',[False,True])
def test_interrupted_staging_is_bound_and_unknown_nested_data_is_preserved(tmp_path,monkeypatch,unknown):
    from scripts import backup_telegram_runtime as backup_module
    runtime=tmp_path/'runtime'
    fixture_runtime(runtime)
    root=tmp_path/'backups'
    ownership=b.initialize(root,runtime,'sha256:'+'a'*64)
    def interrupted(sources,destination):
        staging=destination/'backup-12345678'
        staging.mkdir(parents=True)
        shutil.copyfile(sources[0],staging/sources[0].name)
        if unknown: (staging/'foreign-document').write_bytes(b'preserve')
        raise OSError('synthetic power loss inside staging')
    monkeypatch.setattr(backup_module,'backup',interrupted)
    with pytest.raises(OSError): b.create_generation(root,runtime,ownership,attempt_id='a'*32)
    generation=next(p for p in root.iterdir() if p.is_dir())
    if unknown:
        with pytest.raises(ValueError,match='unowned snapshot'):
            b.recover_partial(root,ownership,'a'*32)
        assert (generation/'snapshot/backup-12345678/foreign-document').read_bytes()==b'preserve'
    else:
        before,_=b._inventory(generation)
        assert b.recover_partial(root,ownership,'a'*32)==1
        quarantined=root/'quarantine'/generation.name
        after,_=b._inventory(quarantined)
        after.pop('recovery.dpapi')
        assert after==before
        assert b._quarantine(root,ownership)[1]==1


def test_repeated_explicit_recovery_keeps_original_attempt_after_transient_failure(tmp_path,monkeypatch):
    from scripts import backup_telegram_runtime as backup
    path,digest,states,events=fake_cycle(tmp_path,monkeypatch)
    original_backup=backup.backup
    def partial(sources,destination):
        original_backup(sources,destination)
        raise OSError('synthetic crash after snapshot')
    monkeypatch.setattr(backup,'backup',partial)
    with pytest.raises(OSError):cycle.cycle(path,digest)
    root=tmp_path/'backups'
    generation=next(p for p in root.iterdir() if p.is_dir())
    original_attempt=b._certificate(generation/'intent.dpapi')['attempt_id']
    monkeypatch.setattr(backup,'backup',original_backup)
    original_move=b._move_to_quarantine
    monkeypatch.setattr(b,'_move_to_quarantine',lambda *args:(_ for _ in ()).throw(OSError('synthetic transient capacity/move failure')))
    failed=b._certificate(tmp_path/'backup-cycle-state.dpapi')
    with pytest.raises(OSError):
        cycle.cycle(path,digest,recover_failure_digest=canonical_json_digest(failed))
    monkeypatch.setattr(b,'_move_to_quarantine',original_move)
    failed=b._certificate(tmp_path/'backup-cycle-state.dpapi')
    assert failed['attempt_id']==original_attempt
    result=cycle.cycle(path,digest,recover_failure_digest=canonical_json_digest(failed))
    assert result['status']=='PASS'
    assert (root/'quarantine'/generation.name/'recovery.dpapi').exists()


def healthy_control(tmp_path,root,runtime,ownership):
    from tests.test_miniapp import _miniapp_admission
    _,queue,control=_miniapp_admission(tmp_path)
    control._closed=False
    control._execution_concurrency=0
    control._worker_error=None
    control._admission_readiness=lambda *,for_admission:b.assert_recent(root,ownership,runtime,for_admission=for_admission)
    return control,queue


def test_planned_hold_does_not_turn_operational_health_into_abnormal_exit(tmp_path,monkeypatch):
    path,digest,states,events=fake_cycle(tmp_path,monkeypatch)
    config=json.loads(path.read_text())
    root,runtime=tmp_path/'backups',tmp_path/'runtime'
    b.create_generation(root,runtime,config['ownership'])
    control,queue=healthy_control(tmp_path/'control',root,runtime,config['ownership'])
    original=b.hold_admission
    checked=[]
    def hold_then_health(*args):
        original(*args)
        control.assert_healthy()
        checked.append(True)
    monkeypatch.setattr(b,'hold_admission',hold_then_health)
    result=cycle.cycle(path,digest)
    assert result['status']=='PASS' and checked==[True]
    assert states['NobusSpaceTestMain']['last_result']==0
    assert queue.queue_counts()==(0,0)


def test_planned_pause_crosses_real_polling_without_ack_and_allows_shutdown(tmp_path):
    import asyncio
    from scripts.run_telegram_control import _poll_with_unavailable_backoff
    from src.transport.telegram.bot_api import TelegramPollingBoundary
    from tests.test_telegram_bot_api import Checkpoint,api_for,response
    runtime=tmp_path/'runtime'
    fixture_runtime(runtime)
    root=tmp_path/'backups'
    ownership=b.initialize(root,runtime,'sha256:'+'a'*64)
    b.create_generation(root,runtime,ownership)
    control,queue=healthy_control(tmp_path/'control',root,runtime,ownership)
    b.hold_admission(root,ownership)
    async def probe():
        api=api_for(lambda request:response([{'update_id':10}]))
        checkpoint=Checkpoint(10)
        async def handler(update):
            return await control._handle_ingress(None)
        polling=TelegramPollingBoundary(api,handler,checkpoint)
        sleeps=[]
        async def sleep(seconds):
            sleeps.append(seconds)
            assert checkpoint.advances==[] and not checkpoint.owned
            control.assert_healthy()
            raise asyncio.CancelledError
        try:
            with pytest.raises(asyncio.CancelledError):
                await _poll_with_unavailable_backoff(polling,api,{},timeout=0,announce=False,sleeper=sleep,health_check=control.assert_healthy)
            assert sleeps==[1.0] and checkpoint.offset==10 and not checkpoint.owned
        finally:
            await api.aclose()
    asyncio.run(probe())
    assert queue.queue_counts()==(0,0)


def test_planned_hold_still_returns_503_without_miniapp_creation(tmp_path):
    from fastapi.testclient import TestClient
    from tests.test_c3_multipart_input import setup,post,form
    runtime=tmp_path/'runtime'
    fixture_runtime(runtime)
    root=tmp_path/'backups'
    ownership=b.initialize(root,runtime,'sha256:'+'a'*64)
    b.create_generation(root,runtime,ownership)
    b.hold_admission(root,ownership)
    app,token,store,queue,admission,compiler=setup(tmp_path/'app')
    admission._admission_readiness=lambda *,for_admission:b.assert_recent(root,ownership,runtime,for_admission=for_admission)
    with TestClient(app) as client:
        result=post(client,token,*form())
    assert result.status_code==503 and queue.queue_counts()==(0,0) and compiler.calls==[]
    assert len(store.list_tasks('owner',limit=20))==0
