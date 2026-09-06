"""Offline regressions for the real smoke polling boundary and trial limits."""
from types import SimpleNamespace
import json

import pytest

from tests.gate_c2 import product_smoke as smoke


def boundary(path, api, handler):
    store = smoke.SQLitePollingCheckpointStore(path, consumer_id='c2-product-smoke', lease_duration_seconds=240)
    return smoke.TelegramPollingBoundary(api, handler, store)


@pytest.mark.asyncio
async def test_restart_replay_uses_durable_offset_and_only_new_update_reaches_handler(tmp_path):
    calls = []
    async def handler(payload):
        calls.append(payload['update_id'])
        return True
    api = smoke.LocalTransport(tmp_path)
    first = boundary(tmp_path/'polling.sqlite3', api, handler)
    await smoke.poll_update(api, first, {'update_id':101})
    reopened = boundary(tmp_path/'polling.sqlite3', api, handler)
    await smoke.poll_update(api, reopened, {'update_id':101})
    await smoke.poll_update(api, reopened, {'update_id':102})
    assert calls == [101,102]
    assert [(r['next_offset'],r['acknowledged']) for r in api.rows] == [(102,1),(102,0),(103,1)]


@pytest.mark.asyncio
async def test_unacknowledged_update_is_retried_after_restart(tmp_path):
    calls = []
    async def failed(payload):
        calls.append(('failed',payload['update_id']))
        return False
    async def accepted(payload):
        calls.append(('accepted',payload['update_id']))
        return True
    api = smoke.LocalTransport(tmp_path)
    with pytest.raises(RuntimeError, match='polling_update_not_acknowledged'):
        await smoke.poll_update(api,boundary(tmp_path/'polling.sqlite3',api,failed),{'update_id':101})
    assert api.rows[-1]['next_offset'] is None
    await smoke.poll_update(api,boundary(tmp_path/'polling.sqlite3',api,accepted),{'update_id':101})
    assert calls == [('failed',101),('accepted',101)]
    assert api.rows[-1]['next_offset'] == 102


@pytest.mark.parametrize('cap,seconds', [(8,600),(24,1200)])
def test_trial_turn_cap_and_one_continuous_window(tmp_path, monkeypatch,cap,seconds):
    monkeypatch.setattr(smoke.time,'time',lambda:1000)
    budget=smoke.Budget(tmp_path,max_turns=cap,max_seconds=seconds)
    for n in range(1,cap+1):
        assert budget.reserve('synthetic','compiler')==n
    with pytest.raises(RuntimeError,match='authorization_budget_exhausted'):
        budget.reserve('synthetic','compiler')
    other=tmp_path/'elapsed';other.mkdir()
    budget=smoke.Budget(other,max_turns=cap,max_seconds=seconds)
    budget.reserve('synthetic','compiler')
    monkeypatch.setattr(smoke.time,'time',lambda:1000+seconds)
    assert budget.snapshot()['remaining_seconds']==0
    with pytest.raises(RuntimeError,match='authorization_budget_exhausted'):
        budget.reserve('synthetic','compiler')
    assert budget.snapshot()['turns_reserved']==1


@pytest.mark.asyncio
async def test_pending_unknown_authorization_rejected_before_ledger_or_provider(tmp_path,monkeypatch):
    folder=tmp_path/'plan';folder.mkdir()
    (folder/'UNKNOWN-TRIAL.json').write_text(json.dumps({'status':'PENDING_AUTHORIZATION','max_turns':8,'continuous_seconds':600}))
    monkeypatch.setattr(smoke,'ROOT',tmp_path)
    monkeypatch.setattr(smoke,'FOLDER',folder)
    monkeypatch.setattr(smoke,'source_binding',lambda _model:{})
    args=SimpleNamespace(run=tmp_path/'.runtime/c2/closure/guard',scenario='conditional_supported_unknown_text',model=tmp_path,unknown_authorized_trial=True)
    with pytest.raises(RuntimeError,match='unknown_provider_trial_not_authorized'):
        await smoke.run(args)
    assert not (folder/'unknown-trial-20260906').exists()
    assert not (folder/'budget.sqlite3').exists()


@pytest.mark.asyncio
@pytest.mark.parametrize('scenario,status,error', [
    ('transform_text','PENDING_AUTHORIZATION','closure_provider_trial_not_authorized'),
    ('conditional_text','AUTHORIZED','scenario_outside_closure_authorization'),
    ('transform_text','AUTHORIZED','closure_authorized_source_changed'),
])
async def test_closure_trial_rejects_pending_or_foreign_scope_before_provider(tmp_path,monkeypatch,scenario,status,error):
    folder=tmp_path/'plan';folder.mkdir()
    (folder/'CLOSURE-TRIAL.json').write_text(json.dumps({'status':status,'max_turns':24,'continuous_seconds':1200}))
    monkeypatch.setattr(smoke,'ROOT',tmp_path)
    monkeypatch.setattr(smoke,'FOLDER',folder)
    monkeypatch.setattr(smoke,'source_binding',lambda _model:{})
    args=SimpleNamespace(run=tmp_path/'.runtime/c2/closure/guard',scenario=scenario,model=tmp_path,
                         unknown_authorized_trial=False,closure_authorized_trial=True)
    with pytest.raises(RuntimeError,match=error):
        await smoke.run(args)
    assert not (folder/'closure-trial-20260906').exists()
    assert not (folder/'budget.sqlite3').exists()


@pytest.mark.asyncio
async def test_unknown_grant_cannot_be_used_for_a_different_scenario(tmp_path,monkeypatch):
    folder=tmp_path/'plan';folder.mkdir()
    (folder/'UNKNOWN-TRIAL.json').write_text(json.dumps({'status':'AUTHORIZED','max_turns':8,'continuous_seconds':600}))
    monkeypatch.setattr(smoke,'ROOT',tmp_path)
    monkeypatch.setattr(smoke,'FOLDER',folder)
    monkeypatch.setattr(smoke,'source_binding',lambda _model:{})
    args=SimpleNamespace(run=tmp_path/'.runtime/c2/closure/guard',scenario='negation_text',model=tmp_path,unknown_authorized_trial=True)
    with pytest.raises(RuntimeError,match='scenario_outside_unknown_authorization'):
        await smoke.run(args)
    assert not (folder/'unknown-trial-20260906').exists()
