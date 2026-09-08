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
        for filename in entries['files']:
            shutil.copyfile(first/filename,dest/filename)
        value=dict(entries,name=name,identity=[dest.stat().st_dev,dest.stat().st_ino],local_time=stamp.isoformat())
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
    monkeypatch.setattr(b,'create_generation',lambda *args:(_ for _ in ()).throw(OSError('synthetic')))
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
    def unavailable(): raise RuntimeError('synthetic expired backup')
    admission._admission_readiness=unavailable
    with TestClient(app) as client:
        response=post(client,token,*form())
    assert response.status_code==503
    assert queue.queue_counts()==(0,0) and compiler.calls==[]
    assert len(store.list_tasks('owner',limit=20))==0
