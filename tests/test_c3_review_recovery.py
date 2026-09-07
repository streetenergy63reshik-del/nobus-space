"""Independent L3 probes: synthetic local fixtures only, no provider calls."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, UTC, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from src.application.durable_telegram_state import execution_lease
from src.application.network_commands import NetworkCommandProposal
from src.application.product_effects import ProductEffectKind, _network_payload
from src.contracts.models import canonical_json_digest
from src.models.task import TaskStatus
from src.storage import StoreCorruptionError, OutboxLeaseError
from src.storage.outbox import message_fingerprint, message_id_for
from tests.test_c3_result_recovery import runtime, seal
from tests.test_c3_delivery_parts import claim, Clock, Sender, part_receipt
from tests.test_miniapp_result import _answered_store
from tests.test_product_effects import _service


@pytest.mark.asyncio
async def test_missing_seal_cannot_enable_rehashed_foreign_answer(tmp_path):
    value = runtime(tmp_path)
    prepared, incoming, task = await seal(value)
    assert await value.recover_prepared(prepared, incoming) is False
    with sqlite3.connect(value._store._path) as db:
        raw = json.loads(db.execute('SELECT message_json FROM outbox_messages').fetchone()[0])
        raw['user_message'] = 'Synthetic substituted answer not matching sealed result'
        fields = {key: raw[key] for key in ('tenant_id', 'task_id', 'task_revision',
            'task_projection_digest', 'contract_digest', 'result_revision', 'result_digest',
            'destination_ref', 'user_message')}
        fields['task_status'] = TaskStatus.ANSWERED
        fingerprint = message_fingerprint(**fields)
        identifier = message_id_for(fingerprint)
        raw.update(message_fingerprint=fingerprint, message_id=str(identifier))
        db.execute('DELETE FROM sealed_answers')
        db.execute('UPDATE outbox_messages SET message_id=?,message_fingerprint=?,message_json=?,message_digest=?',
            (str(identifier), fingerprint, json.dumps(raw), canonical_json_digest(raw)))
    with pytest.raises(StoreCorruptionError):
        value._store.read_outbox_message(task.tenant_id, identifier)


@pytest.mark.asyncio
async def test_stale_queue_context_cannot_execute_network_effect(tmp_path, monkeypatch):
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    service = _service(tmp_path, client)
    state = service._vault._state
    now = [datetime.now(UTC)]
    monkeypatch.setattr(state, '_clock', lambda: now[0])
    proposal = NetworkCommandProposal(tool='git-fetch', argv=('synthetic',),
        working_directory='synthetic', input_digest='sha256:' + 'a' * 64,
        source='synthetic', destination='synthetic', digest='sha256:' + 'b' * 64)
    token = service._vault.issue(kind=ProductEffectKind.NETWORK, tenant_id='owner', user_id=7,
        chat_id=7, payload=_network_payload(proposal), idempotency_key='sha256:' + 'c' * 64)
    from src.application.durable_product import _effect_task_id
    payload = {'synthetic': True}
    state.enqueue(kind='effect', tenant_id='owner', task_id=_effect_task_id('owner', token),
        binding_digest=canonical_json_digest(payload), payload=payload)
    owner = uuid4()
    old = state.claim(lease_owner=owner, lease_seconds=5)
    now[0] += timedelta(seconds=6)
    fresh = state.claim(lease_owner=uuid4(), lease_seconds=5)
    assert fresh.lease_id != old.lease_id
    called = []
    def synthetic_run(*args, **kwargs):
        called.append('synthetic effect')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(service._network, 'run', synthetic_run)
    context = execution_lease.set((state, old, owner))
    try:
        try:
            await service.resolve(token, expected_kind=ProductEffectKind.NETWORK, approve=True,
                tenant_id='owner', user_id=7, chat_id=7,
                approval_ref='telegram-owner-confirmation:sha256:' + 'd' * 64)
        except Exception:
            pass
        assert called == [], 'stale queue generation crossed effect authority'
        assert service._vault.read(token, tenant_id='owner', user_id=7, chat_id=7).state == 'pending'
    finally:
        execution_lease.reset(context)
        await client.aclose()




@pytest.mark.asyncio
async def test_foreign_tenant_cannot_read_existing_seal(tmp_path):
    value = runtime(tmp_path)
    prepared, incoming, task = await seal(value)
    assert value._store.read_sealed_answer('foreign', task.id) is None
    assert value._store.read_task('foreign', task.id) is None


@pytest.mark.asyncio
async def test_missing_seal_before_terminal_never_becomes_success(tmp_path):
    value = runtime(tmp_path)
    prepared, incoming, task = await seal(value)
    with sqlite3.connect(value._store._path) as db:
        db.execute('DELETE FROM sealed_answers')
    restarted = runtime(tmp_path)
    assert await restarted.recover_prepared(prepared, incoming) is False
    assert restarted._store.read_task(task.tenant_id, task.id).projection.status is TaskStatus.ESCALATE


def test_foreign_manifest_does_not_bind(tmp_path):
    from src.storage.outbox import delivery_parts
    store, _, _ = _answered_store(tmp_path / 'tasks.sqlite3')
    clock = Clock()
    owner, message = claim(store, clock)
    foreign = message.model_copy(update={'message_fingerprint': 'sha256:' + 'f' * 64})
    with pytest.raises(ValueError):
        parts = delivery_parts(foreign, (('text', b'foreign'),))
        store.bind_delivery_parts(message, parts, lease_owner=owner, now=clock())


@pytest.mark.asyncio
async def test_fresh_control_start_is_ready_before_first_provider_task(tmp_path):
    from src.workers.codex_sdk import CodexSdkAdapter, ResilientCodexAdapter
    from tests.test_codex_sdk import _paths, _Client
    from tests.test_c3_shutdown import _control
    owner, workspace, home, temp = _paths(tmp_path)
    client = _Client()
    primary = CodexSdkAdapter(workspace_root=workspace, owner_root=owner,
        codex_home=home, temp_root=temp, client_factory=lambda _: client)
    control = _control(tmp_path)
    control._product_runtime._worker = ResilientCodexAdapter(primary,
        SimpleNamespace(execute=lambda *args: None), SimpleNamespace(verify=lambda *args: None))
    try:
        await control.start()
        control.assert_healthy()
        assert client.start_values == [], 'readiness must not perform a provider task'
    finally:
        await control.close()
        await primary.close()
