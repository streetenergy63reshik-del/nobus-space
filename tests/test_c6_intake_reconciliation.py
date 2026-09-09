"""Offline C6 regression: a closed request can never become a later task."""
from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.application.miniapp import (
    MiniAppCoreUnavailableError, MiniAppRequestCancelled, MiniAppRequestNotAccepted,
    MiniAppTaskConflictError, MiniAppTaskNotFoundError,
)
from src.application.durable_semantic import DurableSemanticClarificationStore
from src.application.runtime_maintenance import validate_runtime_database
from src.application.semantic_admission import SemanticAdmissionError, SemanticAdmissionService
from src.security.dpapi import protect_current_user
from src.storage import SQLiteStore
from src.storage import sqlite_store as storage_module
from src.storage.sqlite_store import MiniAppAdmissionClosedError, MiniAppCancelledRequest, MiniAppRequestRecord
from tests.test_c4_miniapp_recovery import KEY, service_for
from tests.test_miniapp import Clock, _miniapp_admission, signed_init_data
from tests.test_semantic_admission import _Compiler, _security_proposal


def setup(tmp_path):
    store, queue, admission = _miniapp_admission(tmp_path)
    clock = Clock()
    core = service_for(store, admission, clock)
    grant = core.authenticate(signed_init_data())
    return store, queue, admission, clock, core, grant


def enable_semantic(admission, queue, compiler):
    admission._enable_semantic_admission = True
    admission._semantic_admission = SemanticAdmissionService(compiler)
    admission._semantic_clarifications = DurableSemanticClarificationStore(queue)


@pytest.mark.parametrize('code', ['SEMANTIC_COMPILER_TIMEOUT', 'SEMANTIC_PROPOSAL_INVALID', 'unsafe provider text'])
def test_known_pre_admission_failure_is_fenced_typed_and_never_recompiled(tmp_path, monkeypatch, code):
    store, queue, admission, clock, core, grant = setup(tmp_path)
    original = admission.submit_miniapp_task
    calls = []

    async def failed(*args, **kwargs):
        calls.append(1)
        raise SemanticAdmissionError(code, provider_code='secret /private/path')

    monkeypatch.setattr(admission, 'submit_miniapp_task', failed)
    for _ in range(2):
        with pytest.raises(MiniAppRequestNotAccepted, match='^semantic_unavailable$'):
            asyncio.run(core.create_task(grant.access_token, 'Синтетический запрос.', KEY))
    result = core.request_state(grant.access_token, KEY)
    assert result.state == 'not_accepted'
    assert result.failure_code == (code if code.startswith('SEMANTIC_') else 'SEMANTIC_FAILED')
    assert result.phase == 'semantic' and len(result.request_ref) == 16
    assert result.failure_phase == 'intake' and result.elapsed_seconds >= 0
    assert result.received_at <= result.updated_at <= result.deadline_at
    assert not result.legacy_timing and calls == [1]
    assert 'secret' not in result.model_dump_json() and 'private/path' not in result.model_dump_json()
    record = store.read_miniapp_request('owner', core._auth_context_ref, KEY)
    with pytest.raises(MiniAppAdmissionClosedError):
        asyncio.run(original('Синтетический запрос.', record.envelope))
    assert store.list_tasks('owner') == () and queue.queue_counts() == (0, 0)
    monkeypatch.setattr(admission, 'submit_miniapp_task', original)
    assert asyncio.run(core.create_task(grant.access_token, 'Следующий запрос.', KEY + '-next')).task_id


def test_unknown_is_not_refusal_but_deadline_reconciliation_is_a_permanent_fence(tmp_path, monkeypatch):
    store, queue, admission, clock, core, grant = setup(tmp_path)
    original = admission.submit_miniapp_task
    calls = []

    async def unknown(*args, **kwargs):
        calls.append(1)
        raise OSError('private diagnostic')

    monkeypatch.setattr(admission, 'submit_miniapp_task', unknown)
    with pytest.raises(MiniAppCoreUnavailableError):
        asyncio.run(core.create_task(grant.access_token, 'Неизвестный исход.', KEY))
    result = core.request_state(grant.access_token, KEY)
    assert result.state == 'pending' and result.failure_code == 'ADMISSION_UNKNOWN'
    record = store.read_miniapp_request('owner', core._auth_context_ref, KEY)
    original_envelope = record.envelope.model_dump_json()

    class ExpiredClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return record.admission_deadline + timedelta(seconds=1)

    with monkeypatch.context() as patch:
        patch.setattr(storage_module, 'datetime', ExpiredClock)
        result = core.request_state(grant.access_token, KEY)
        assert result.state == 'not_accepted' and result.detail == 'request_expired'
    # Even moving the clock back cannot reopen the durable fence.
    restarted = service_for(SQLiteStore(store._path), admission, clock)
    recovered = restarted.recover_session(grant.recovery_token)
    assert restarted.request_state(recovered.access_token, KEY) == result
    with pytest.raises(MiniAppAdmissionClosedError):
        asyncio.run(original('Неизвестный исход.', record.envelope))
    with pytest.raises(MiniAppRequestNotAccepted, match='request_expired'):
        asyncio.run(restarted.create_task(recovered.access_token, 'Неизвестный исход.', KEY))
    assert store.read_miniapp_request('owner', core._auth_context_ref, KEY).envelope.model_dump_json() == original_envelope
    assert calls == [1] and store.list_tasks('owner') == () and queue.queue_counts() == (0, 0)


def test_cancellation_during_semantic_completion_cannot_create_or_deliver(tmp_path):
    store, queue, admission, clock, core, grant = setup(tmp_path)

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        class PausedCompiler(_Compiler):
            async def compile_semantic(self, *args, **kwargs):
                entered.set()
                await release.wait()
                return await super().compile_semantic(*args, **kwargs)

        compiler = PausedCompiler(_security_proposal(('respond',)))
        enable_semantic(admission, queue, compiler)
        posting = asyncio.create_task(core.create_task(grant.access_token, 'Подготовь ответ.', KEY))
        await asyncio.wait_for(entered.wait(), 2)
        cancelled = await asyncio.wait_for(core.cancel_absent_request(grant.access_token, KEY), 2)
        assert cancelled.state == 'not_accepted' and cancelled.detail == 'request_cancelled'
        assert not posting.done()
        release.set()
        with pytest.raises(MiniAppRequestCancelled):
            await posting
        assert core.request_state(grant.access_token, KEY) == cancelled
        assert compiler.calls
        count = len(compiler.calls)
        with pytest.raises(MiniAppRequestCancelled):
            await core.create_task(grant.access_token, 'Подготовь ответ.', KEY)
        assert len(compiler.calls) == count

    asyncio.run(scenario())
    assert store.list_tasks('owner') == () and queue.queue_counts() == (0, 0)
    assert store.delivery_counts('owner')['confirmed_parts'] == 0


def test_accepted_first_cancel_and_transport_cancellation_preserve_original_task(tmp_path, monkeypatch):
    store, queue, admission, clock, core, grant = setup(tmp_path)
    original = admission.submit_miniapp_task

    async def scenario():
        accepted, release = asyncio.Event(), asyncio.Event()
        ids = []

        async def delayed_ack(*args, **kwargs):
            ids.append(await original(*args, **kwargs))
            accepted.set()
            await release.wait()
            return ids[0]

        monkeypatch.setattr(admission, 'submit_miniapp_task', delayed_ack)
        posting = asyncio.create_task(core.create_task(grant.access_token, 'Один результат.', KEY))
        await asyncio.wait_for(accepted.wait(), 2)
        with sqlite3.connect(store._path) as db:
            before = db.execute('SELECT payload FROM miniapp_requests').fetchone()[0]
        result = await core.cancel_absent_request(grant.access_token, KEY)
        assert result.state == 'accepted' and result.task_id == ids[0]
        posting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await posting
        assert core.request_state(grant.access_token, KEY) == result
        with sqlite3.connect(store._path) as db:
            assert db.execute('SELECT payload FROM miniapp_requests').fetchone()[0] == before
        repeated = await core.create_task(grant.access_token, 'Один результат.', KEY)
        assert repeated.task_id == ids[0]

    asyncio.run(scenario())
    assert len(store.list_tasks('owner')) == 1 and queue.queue_counts() == (0, 1)


def test_transport_cancel_before_admission_closes_request_and_allows_next(tmp_path, monkeypatch):
    store, queue, admission, clock, core, grant = setup(tmp_path)
    original = admission.submit_miniapp_task

    async def scenario():
        entered = asyncio.Event()

        async def wait_forever(*args, **kwargs):
            entered.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(admission, 'submit_miniapp_task', wait_forever)
        posting = asyncio.create_task(core.create_task(grant.access_token, 'Прерванная отправка.', KEY))
        await asyncio.wait_for(entered.wait(), 2)
        posting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await posting
        result = core.request_state(grant.access_token, KEY)
        assert result.detail == 'request_interrupted' and result.failure_code == 'TRANSPORT_CANCELLED'
        monkeypatch.setattr(admission, 'submit_miniapp_task', original)
        assert (await core.create_task(grant.access_token, 'Новая задача.', KEY + '-next')).task_id

    asyncio.run(scenario())
    assert len(store.list_tasks('owner')) == 1


def test_prequeued_unknown_is_fenced_at_actual_recovery_admission(tmp_path, monkeypatch):
    store, queue, admission, clock, core, grant = setup(tmp_path)
    runtime = admission._product_runtime
    original = runtime.admit_prepared

    async def unknown(*args, **kwargs):
        raise OSError('between durable queue and task admission')

    monkeypatch.setattr(runtime, 'admit_prepared', unknown)
    with pytest.raises(MiniAppCoreUnavailableError):
        asyncio.run(core.create_task(grant.access_token, 'Один сохранённый черновик.', KEY))
    assert store.list_tasks('owner') == () and queue.queue_counts() == (0, 1)
    assert asyncio.run(core.cancel_absent_request(grant.access_token, KEY)).state == 'not_accepted'
    monkeypatch.setattr(runtime, 'admit_prepared', original)
    job = queue.claim(lease_owner=uuid4())
    assert asyncio.run(admission._restore(job)) is None
    assert store.list_tasks('owner') == () and store.delivery_counts('owner')['confirmed_parts'] == 0
    assert core.request_state(grant.access_token, KEY).detail == 'request_cancelled'


def test_cancel_and_ingress_claim_are_atomic_across_store_connections(tmp_path):
    store, queue, admission, clock, core, grant = setup(tmp_path)
    envelope = core._task_envelope(core._session(grant.access_token),
        instruction='Гонка транзакций.', idempotency_key=KEY, display_title=None)
    store.write_miniapp_request(MiniAppRequestRecord(envelope=envelope), claim=True)
    prepared = asyncio.run(admission._product_runtime.build_instruction('Гонка транзакций.', envelope))
    barrier = threading.Barrier(2)

    def admit():
        barrier.wait()
        try:
            return asyncio.run(admission._product_runtime.admit_prepared(prepared, envelope))
        except MiniAppAdmissionClosedError:
            return False

    def cancel():
        barrier.wait()
        return SQLiteStore(store._path).cancel_absent_miniapp_request(MiniAppCancelledRequest(
            tenant_id='owner', auth_context_ref=core._auth_context_ref, idempotency_key=KEY))

    with ThreadPoolExecutor(max_workers=2) as pool:
        admitted, cancelled = pool.submit(admit), pool.submit(cancel)
        accepted, result = admitted.result(), cancelled.result()
    claim = store.read_ingress_claim(envelope)
    assert (claim is not None) == accepted
    assert (result.state == 'not_accepted') != accepted
    assert len(store.list_tasks('owner')) == int(accepted)


def test_legacy_protected_row_is_preserved_then_reconciled_without_invented_arrival(tmp_path):
    store, queue, admission, clock, core, grant = setup(tmp_path)
    envelope = core._task_envelope(core._session(grant.access_token),
        instruction='Старая отправка.', idempotency_key=KEY, display_title=None)
    # Construct the exact pre-C6 protected row shape in this disposable fixture only.
    value = MiniAppRequestRecord(envelope=envelope).model_dump(mode='json', exclude={
        'received_at', 'updated_at', 'admission_deadline', 'phase', 'failure_code', 'failure_phase'})
    payload = protect_current_user(json.dumps(value).encode(), entropy=storage_module._MINIAPP_REQUEST_ENTROPY)
    with sqlite3.connect(store._path) as db:
        db.execute('INSERT INTO miniapp_requests VALUES (?,?,?,?,?)', (
            'owner', KEY, core._auth_context_ref, payload, 'sha256:' + hashlib.sha256(payload).hexdigest()))
    reopened = SQLiteStore(store._path)
    with sqlite3.connect(store._path) as db:
        assert db.execute('SELECT payload FROM miniapp_requests').fetchone()[0] == payload
    service = service_for(reopened, admission, clock)
    fresh = service.recover_session(grant.recovery_token)
    result = service.request_state(fresh.access_token, KEY)
    assert result.detail == 'request_expired' and result.failure_code == 'LEGACY_PENDING_RECONCILED'
    assert result.legacy_timing and result.received_at is None and result.updated_at is not None
    assert reopened.read_miniapp_request('owner', core._auth_context_ref, KEY).envelope == envelope
    with sqlite3.connect(store._path) as db:
        assert db.execute('SELECT count(*) FROM miniapp_requests').fetchone()[0] == 1
    validation_copy = tmp_path / 'task-runtime.sqlite3'
    with sqlite3.connect(store._path) as source_db, sqlite3.connect(validation_copy) as target_db:
        source_db.backup(target_db)
    validate_runtime_database(validation_copy)
    with pytest.raises(MiniAppAdmissionClosedError):
        asyncio.run(admission.submit_miniapp_task('Старая отправка.', envelope))


def test_actual_envelope_arrival_and_replay_binding_remain_stable(tmp_path):
    store, queue, admission, clock, core, grant = setup(tmp_path)
    issued_at = clock.now
    clock.advance(seconds=15)
    created = asyncio.run(core.create_task(grant.access_token, 'Один запрос.', KEY))
    first = store.read_miniapp_request('owner', core._auth_context_ref, KEY)
    assert first.envelope.received_at == clock.now and first.envelope.received_at > issued_at
    clock.advance(seconds=10)
    assert asyncio.run(core.create_task(grant.access_token, 'Один запрос.', KEY)).task_id == created.task_id
    assert store.read_miniapp_request('owner', core._auth_context_ref, KEY) == first
    with pytest.raises(MiniAppTaskConflictError):
        asyncio.run(core.create_task(grant.access_token, 'Другие bytes.', KEY))
    assert len(store.list_tasks('owner')) == 1


def test_foreign_context_cannot_close_or_read_owner_pending(tmp_path):
    store, queue, admission, clock, core, grant = setup(tmp_path)
    envelope = core._task_envelope(core._session(grant.access_token),
        instruction='Закрытая область.', idempotency_key=KEY, display_title=None)
    store.write_miniapp_request(MiniAppRequestRecord(envelope=envelope), claim=True)
    record = store.read_miniapp_request('owner', core._auth_context_ref, KEY)
    for tenant, context in [('foreign', core._auth_context_ref), ('owner', 'sha256:' + 'f' * 64)]:
        assert store.reconcile_miniapp_request(tenant, context, KEY, detail='request_cancelled') == (None, None)
    assert store.read_miniapp_request('owner', core._auth_context_ref, KEY) == record


def test_status_separates_core_semantic_intake_and_historical_attention(tmp_path, monkeypatch):
    store, queue, admission, clock, core, grant = setup(tmp_path)
    admission._voice_service = None
    admission._closed = False
    admission._execution_concurrency = 1
    admission._execution_workers = [SimpleNamespace(done=lambda: False)]
    admission._worker_error = None
    compiler = _Compiler(_security_proposal(('respond',)))
    enable_semantic(admission, queue, compiler)
    monkeypatch.setattr(admission._product_runtime._store, 'attention_task_ids', lambda tenant: tuple(str(i) for i in range(31)))
    status = admission._status_text('owner')
    assert 'Core: доступен' in status and 'ещё не проверен' in status
    assert 'Приём задач: доступен' not in status
    assert 'история задач): 31' in status
    admission._semantic_admission.last_status = 'unavailable'
    status = admission._status_text('owner')
    assert 'Приём задач: временно недоступен' in status and 'Исполнитель: готов' in status
    admission._semantic_admission.last_status = 'ready'
    assert 'Приём задач: доступен' in admission._status_text('owner')
    envelope = core._task_envelope(core._session(grant.access_token),
        instruction='Отправка.', idempotency_key=KEY, display_title=None)
    store.write_miniapp_request(MiniAppRequestRecord(envelope=envelope), claim=True)
    status = admission._status_text('owner')
    assert 'приём не завершён: 1' in status and 'отмените отправку' in status
    assert 'приём не завершён: 0' in admission._status_text('foreign')


def test_semantic_health_tracks_real_offline_failure_and_next_success(tmp_path):
    store, queue, admission, clock, core, grant = setup(tmp_path)
    compiler = _Compiler({'invalid': 'synthetic provider response'})
    enable_semantic(admission, queue, compiler)
    service = admission._semantic_admission
    assert service.last_status == 'not_checked'
    with pytest.raises(MiniAppRequestNotAccepted, match='semantic_unavailable'):
        asyncio.run(core.create_task(grant.access_token, 'Подготовь ответ.', KEY))
    assert service.last_status == 'unavailable' and service.last_changed_at.tzinfo is not None
    failed = core.request_state(grant.access_token, KEY)
    assert failed.failure_code == 'SEMANTIC_PROPOSAL_INVALID' and failed.failure_phase == 'semantic'
    compiler.value = _security_proposal(('respond',))
    created = asyncio.run(core.create_task(grant.access_token, 'Подготовь ответ.', KEY + '-next'))
    assert created.task_id and service.last_status == 'ready'
    assert core.request_state(grant.access_token, KEY).failure_code == failed.failure_code


def test_cancelled_http_operation_leaves_durable_recoverable_outcome(tmp_path, monkeypatch):
    import httpx
    from src.transport.miniapp import create_miniapp_app
    from tests.test_miniapp import headers, ORIGIN

    store, queue, admission, clock, core, grant = setup(tmp_path)

    async def scenario():
        entered = asyncio.Event()

        async def blocked(*args, **kwargs):
            entered.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(admission, 'submit_miniapp_task', blocked)
        app = create_miniapp_app(core, allowed_host='testserver', allowed_origin=ORIGIN)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
            posting = asyncio.create_task(client.post('/api/tasks', json={'instruction': 'Запрос по HTTP.'},
                headers={**headers(grant.access_token), 'Idempotency-Key': KEY}))
            await asyncio.wait_for(entered.wait(), 2)
            posting.cancel()
            with pytest.raises(asyncio.CancelledError):
                await posting
            response = await client.get('/api/requests/' + KEY, headers=headers(grant.access_token))
            assert response.status_code == 200
            assert response.json()['state'] == 'not_accepted' and response.json()['detail'] == 'request_interrupted'
            assert response.json()['failure_code'] == 'TRANSPORT_CANCELLED'

    asyncio.run(scenario())
    assert store.list_tasks('owner') == () and queue.queue_counts() == (0, 0)
