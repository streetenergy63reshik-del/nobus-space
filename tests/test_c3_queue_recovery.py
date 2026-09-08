"""C3 crash/lease/status regressions using disposable state and synthetic data."""
import asyncio
import json
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.application.durable_product import DurableProductTelegramControlPlane
from src.application.durable_telegram_state import (
    DurableTelegramStateError, SQLiteTelegramState, execution_lease, guarded_task_write,
)
from src.contracts.models import canonical_json_digest
from tests.test_durable_telegram_state import _store


def admit(state, tenant="owner"):
    task = uuid4()
    return state.enqueue(kind="draft", tenant_id=tenant, task_id=task,
        binding_digest=canonical_json_digest({"task": str(task)}), payload={"synthetic": True})


@pytest.mark.parametrize("after_commit", [False, True])
def test_hard_process_exit_admission_boundary(tmp_path, after_commit):
    path = tmp_path / "crash.sqlite3"
    script = '''
import os, sys, json
from uuid import UUID
from src.application.durable_telegram_state import SQLiteTelegramState
from src.contracts.models import canonical_json_digest
s=SQLiteTelegramState(sys.argv[1], encode=lambda v:json.dumps(v).encode(), decode=json.loads)
if sys.argv[2] == 'False': os._exit(71)
s.enqueue(kind='draft',tenant_id='owner',task_id=UUID(int=1),binding_digest=canonical_json_digest({'fixture':1}),payload={'synthetic':True})
os._exit(72)
'''
    result = subprocess.run([sys.executable, "-c", script, str(path), str(after_commit)],
        capture_output=True, timeout=15)
    assert result.returncode == (72 if after_commit else 71)
    state = SQLiteTelegramState(path, encode=lambda v: json.dumps(v).encode(), decode=json.loads)
    assert state.queue_counts() == (0, int(after_commit))
    if after_commit:
        first = state.claim(lease_owner=uuid4())
        assert first.task_id.int == 1 and first.attempt_count == 1


def test_clock_rechecked_after_lock_for_heartbeat_and_ack(tmp_path, monkeypatch):
    now = [datetime(2026, 9, 6, tzinfo=UTC)]
    state = _store(tmp_path, clock=lambda: now[0])
    admit(state)
    owner = uuid4()
    job = state.claim(lease_owner=owner, lease_seconds=5)
    original = state._transaction

    @contextmanager
    def delayed_lock():
        with original() as connection:
            now[0] += timedelta(seconds=6)
            yield connection

    monkeypatch.setattr(state, "_transaction", delayed_lock)
    with pytest.raises(DurableTelegramStateError, match="lease_lost"):
        state.renew(job, lease_owner=owner, lease_seconds=30)
    with pytest.raises(DurableTelegramStateError, match="lease_lost"):
        state.ack(job, lease_owner=owner)
    assert state.queue_snapshot()["recovering"] == 1


@pytest.mark.parametrize("mutation", ["tenant", "task", "contract", "payload", "expiry", "aba"])
def test_authoritative_write_is_fenced(tmp_path, mutation):
    now = [datetime(2026, 9, 6, tzinfo=UTC)]
    state = _store(tmp_path, clock=lambda: now[0])
    admit(state)
    owner = uuid4()
    job = state.claim(lease_owner=owner, lease_seconds=5)
    tenant, task, digest = job.tenant_id, job.task_id, job.binding_digest
    if mutation == "tenant": tenant = "foreign"
    if mutation == "task": task = uuid4()
    if mutation == "contract": digest = canonical_json_digest({"foreign": True})
    if mutation == "payload": job = replace(job, payload={"synthetic": False})
    if mutation in {"expiry", "aba"}: now[0] += timedelta(seconds=6)
    if mutation == "aba":
        second = state.claim(lease_owner=owner, lease_seconds=5)
        assert second.job_id == job.job_id and second.lease_id != job.lease_id
    token = execution_lease.set((state, job, owner))
    try:
        with pytest.raises(DurableTelegramStateError):
            with guarded_task_write(tenant, task, digest):
                pytest.fail("stale or foreign writer reached authoritative commit")
    finally:
        execution_lease.reset(token)


def test_corrupt_poison_retained_without_blocking_next_fifo(tmp_path):
    state = _store(tmp_path)
    poison = admit(state)
    with sqlite3.connect(state.path) as connection:
        connection.execute("UPDATE telegram_jobs SET payload=? WHERE job_id=?", (b"broken", str(poison.job_id)))
    healthy = admit(state, "other")
    claimed = state.claim(lease_owner=uuid4())
    assert claimed.job_id == healthy.job_id
    assert state.dead_letter_count() == 1
    with sqlite3.connect(state.path) as connection:
        assert connection.execute("SELECT payload FROM telegram_jobs WHERE job_id=?", (str(poison.job_id),)).fetchone()[0] == b"broken"


@pytest.mark.asyncio
async def test_status_ready_expired_worker_down_and_store_failure(tmp_path, monkeypatch):
    now = [datetime(2026, 9, 6, tzinfo=UTC)]
    state = _store(tmp_path, clock=lambda: now[0])
    admit(state)
    state.claim(lease_owner=uuid4(), lease_seconds=5)
    admit(state)
    admit(state, "foreign")
    worker = asyncio.create_task(asyncio.Event().wait())
    control = object.__new__(DurableProductTelegramControlPlane)
    control._admission_readiness = None
    control._telegram_state = state
    control._execution_workers = (worker,)
    control._execution_concurrency = 1
    control._closing = control._closed = False
    control._worker_error = None
    control._voice_service = None
    control._product_runtime = SimpleNamespace(_worker=SimpleNamespace(generation_available=True))
    try:
        assert "В работе: 1" in control._status_text()
        assert "В очереди: 1" in control._status_text(tenant_id="owner")
        assert "В очереди: 2" in control._status_text()
        control.assert_healthy()
        poison = admit(state)
        with sqlite3.connect(state.path) as db:
            db.execute("UPDATE telegram_jobs SET status='failed',failure_code='synthetic_failure' WHERE job_id=?", (str(poison.job_id),))
        assert "Требуют внимания: 1" in control._status_text(tenant_id="owner")
        assert "Требуют внимания: 0" in control._status_text(tenant_id="foreign")
        now[0] += timedelta(seconds=6)
        text = control._status_text()
        assert "В работе: 0" in text and "Восстанавливаются: 1" in text
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        assert "Исполнитель: недоступен" in control._status_text()
        with pytest.raises(RuntimeError): control.assert_healthy()
        def broken(*args): raise RuntimeError("private payload C:/secret/runtime.db")
        monkeypatch.setattr(state, "queue_snapshot", broken)
        text = control._status_text()
        assert "недоступен" in text and "secret" not in text and "private" not in text
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)


@pytest.mark.asyncio
async def test_startup_orphan_reconcile_preserves_valid_job_and_second_restart(tmp_path):
    from src.core.policy import task_contract_digest
    from src.models.task import TaskStatus
    from tests.test_c3_result_recovery import runtime
    from tests.test_sqlite_store import contract_for, envelope
    from src.contracts import IngressSource

    core = runtime(tmp_path)
    incoming = envelope(source=IngressSource.API)
    contract = contract_for(incoming)
    task = await core._begin_task(contract, incoming)
    task = await core._start_worker(contract, task)
    # A second valid queued admission must survive the same inventory sweep.
    second_envelope = envelope(source=IngressSource.API, idempotency_key="c3-second")
    second = contract_for(second_envelope)
    await core._begin_task(second, second_envelope)
    state = _store(tmp_path)
    state.enqueue(kind="miniapp_draft", tenant_id=second.tenant_id, task_id=second.task_id,
        binding_digest=task_contract_digest(second), payload={"prepared": {
            "contract": second.model_dump(mode="json"), "envelope_revision": second_envelope.envelope_revision},
            "envelope": second_envelope.model_dump(mode="json")})
    control = object.__new__(DurableProductTelegramControlPlane)
    control._admission_readiness = None
    control._product_runtime, control._telegram_state = core, state
    control._reconcile_tasks()
    failed = core._store.read_task(contract.tenant_id, contract.task_id)
    assert failed.projection.status is TaskStatus.FAILED
    assert core._store.read_task(second.tenant_id, second.task_id).projection.status is TaskStatus.PENDING
    assert state.queue_counts() == (0, 1)
    # Fresh Core/control replays the same persisted state without a worker.
    restarted = runtime(tmp_path)
    control._product_runtime = restarted
    control._reconcile_tasks()
    assert restarted._store.read_task(contract.tenant_id, contract.task_id) == failed
    with sqlite3.connect(restarted._store._path) as db:
        assert db.execute("SELECT COUNT(*) FROM outbox_messages").fetchone()[0] == 1
    assert restarted._store.attention_task_ids(contract.tenant_id) == (contract.task_id,)


@pytest.mark.asyncio
async def test_expired_job_cannot_seal_real_core_result(tmp_path):
    from src.contracts import IngressSource
    from src.core.policy import task_contract_digest
    from tests.test_c3_result_recovery import runtime
    from tests.test_sqlite_store import contract_for, envelope

    now = [datetime(2026, 9, 6, tzinfo=UTC)]
    core = runtime(tmp_path)
    incoming = envelope(source=IngressSource.API)
    contract = contract_for(incoming)
    task = await core._begin_task(contract, incoming)
    task = await core._start_worker(contract, task)
    state = _store(tmp_path, clock=lambda: now[0])
    state.enqueue(kind="draft", tenant_id=contract.tenant_id, task_id=task.id,
        binding_digest=task_contract_digest(contract), payload={"synthetic": True})
    owner = uuid4()
    job = state.claim(lease_owner=owner, lease_seconds=5)
    before = core._store.read_task(task.tenant_id, task.id)
    now[0] += timedelta(seconds=6)
    token = execution_lease.set((state, job, owner))
    try:
        with pytest.raises(DurableTelegramStateError, match="lease_lost"):
            await core._record_worker_result(contract, task, '{"answer":"late"}', result_kind="answer")
    finally:
        execution_lease.reset(token)
    assert core._store.read_task(task.tenant_id, task.id) == before
    assert core._store.read_sealed_answer(task.tenant_id, task.id) is None


@pytest.mark.asyncio
async def test_restart_parsing_requires_attention_without_provider_replay(tmp_path):
    from src.core.policy import task_contract_digest
    from src.contracts import IngressSource
    from src.application.durable_runtime import PreparedTask
    from src.models.task import TaskStatus
    from src.workers.codex_cli import CodexCliResult
    from tests.test_c3_result_recovery import runtime
    from tests.test_sqlite_store import contract_for, envelope
    incoming = envelope(source=IngressSource.API)
    contract = contract_for(incoming)
    prepared = PreparedTask(contract, incoming.envelope_revision)
    core = runtime(tmp_path)
    task = await core._begin_task(contract, incoming)
    await core._start_worker(contract, task)
    restarted = runtime(tmp_path)
    calls = []
    async def execute(value):
        calls.append(value)
        return CodexCliResult(message='{"answer":"A recovered synthetic result."}')
    restarted._execute_worker = execute
    assert not await restarted.recover_prepared(prepared, incoming)
    assert calls == []
    snapshot = restarted._store.read_task(contract.tenant_id, contract.task_id)
    assert snapshot.projection.status is TaskStatus.FAILED
    assert await restarted.is_task_terminal(contract.tenant_id, contract.task_id, task_contract_digest(contract))
    again = runtime(tmp_path)
    assert not await again.recover_prepared(prepared, incoming)
    assert again._store.read_task(contract.tenant_id, contract.task_id) == snapshot
