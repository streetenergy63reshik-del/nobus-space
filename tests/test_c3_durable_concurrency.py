"""C3 process-loss and two real durable queue loops with synthetic execution."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from src.application.durable_product import DurableProductTelegramControlPlane
from src.application.durable_telegram_state import (
    DurableJob,
    DurableTelegramStateError,
    guarded_task_write,
)
from src.contracts import IngressSource
from src.core.policy import task_contract_digest
from tests.test_durable_telegram_state import _store
from tests.test_sqlite_store import contract_for, envelope


def test_hard_exit_after_claim_before_worker_reclaims_same_job(tmp_path):
    now = datetime(2026, 9, 6, 12, tzinfo=UTC)
    script = r'''
import json, os, sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from uuid import UUID
from tests.test_durable_telegram_state import _store
from src.contracts.models import canonical_json_digest
root = Path(sys.argv[1]); now = datetime.fromisoformat(sys.argv[2])
state = _store(root, clock=lambda: now)
state.enqueue(kind='draft', tenant_id='tenant-a', task_id=UUID(int=7),
    binding_digest=canonical_json_digest({'synthetic':7}), payload={'synthetic':7})
job = state.claim(lease_owner=UUID(int=8), lease_seconds=5)
print(json.dumps({'pid':os.getpid(),'job':asdict(job)},default=str),flush=True)
os._exit(73)
(root/'worker-was-called').write_text('unexpected',encoding='utf8')
'''
    child = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), now.isoformat()],
        capture_output=True, timeout=15, check=False,
    )
    assert child.returncode == 73
    receipt = json.loads(child.stdout)
    assert receipt["pid"] > 0
    values = receipt["job"]
    for key in ("job_id", "task_id", "lease_id"):
        values[key] = UUID(values[key])
    stale = DurableJob(**values)
    assert not (tmp_path / "worker-was-called").exists()
    clock = [now]
    restarted = _store(tmp_path, clock=lambda: clock[0])
    assert restarted.queue_counts() == (1, 0)
    assert restarted.claim(lease_owner=uuid4(), lease_seconds=5) is None
    clock[0] += timedelta(seconds=6)
    new_owner = uuid4()
    recovered = restarted.claim(lease_owner=new_owner, lease_seconds=5)
    assert recovered is not None
    assert recovered.job_id == stale.job_id and recovered.task_id == stale.task_id
    assert recovered.payload == stale.payload and recovered.binding_digest == stale.binding_digest
    assert recovered.lease_id != stale.lease_id and recovered.attempt_count == 2
    with pytest.raises(DurableTelegramStateError):
        restarted.ack(stale, lease_owner=UUID(int=8))
    with pytest.raises(DurableTelegramStateError):
        restarted.fail(stale, lease_owner=UUID(int=8), failure_code="stale_worker")
    restarted.ack(recovered, lease_owner=new_owner)
    assert _store(tmp_path, clock=lambda: clock[0]).queue_counts() == (0, 0)


@pytest.mark.asyncio
async def test_two_durable_workers_preserve_capacity_fifo_and_tenant_bindings(tmp_path):
    clock = [datetime(2026, 9, 6, 12, tzinfo=UTC)]
    queue = _store(tmp_path, clock=lambda: clock[0], max_jobs=6)
    expected, admitted = {}, []

    def enqueue(tenant, name):
        clock[0] += timedelta(milliseconds=1)
        incoming = envelope(
            tenant_id=tenant, source=IngressSource.API,
            idempotency_key="c3-durable-" + name,
            external_message_id="c3-durable-" + name,
        )
        contract = contract_for(incoming, instruction="Синтетическая задача " + name)
        job = queue.enqueue(
            kind="miniapp_draft", tenant_id=tenant, task_id=contract.task_id,
            binding_digest=task_contract_digest(contract), payload={
                "prepared": {"contract": contract.model_dump(mode="json"),
                             "envelope_revision": incoming.envelope_revision},
                "envelope": incoming.model_dump(mode="json"),
            },
        )
        expected[job.task_id] = (tenant, name)
        admitted.append(job)
        return job

    for tenant, name in (("tenant-a", "a0"), ("tenant-a", "a1"),
                         ("tenant-b", "b0"), ("tenant-a", "a2"),
                         ("tenant-b", "b1"), ("tenant-a", "a3")):
        enqueue(tenant, name)

    control = object.__new__(DurableProductTelegramControlPlane)
    control._admission_readiness = None
    control._telegram_state = queue
    control._product_runtime = SimpleNamespace()
    control._product_effects = None
    control._lease_owner = uuid4()
    control._execution_queue = asyncio.Queue(maxsize=40)
    control._execution_workers = ()
    control._execution_concurrency = 2
    control._active_jobs = 0
    control._worker_error = None
    control._worker_error_count = 0
    control._closing = control._closed = control._close_failed = False
    control._close_task = None
    control._cleanup_pending = set()
    control._close_lock = asyncio.Lock()
    two_started, release_first, tenant_b_started, release_b = (asyncio.Event() for _ in range(4))
    started, finished = [], {"tenant-a": [], "tenant-b": []}
    active = peak = 0

    async def progress(*args):
        return None

    async def execute(durable, job):
        nonlocal active, peak
        tenant, name = expected[durable.task_id]
        assert job.prepared.contract.tenant_id == job.envelope.tenant_id == tenant
        assert job.prepared.contract.task_id == durable.task_id
        assert task_contract_digest(job.prepared.contract) == durable.binding_digest
        # Production restore and task-local authority must both reject rebinding.
        with pytest.raises(RuntimeError, match="binding mismatch"):
            control._miniapp_draft_binding(replace(durable, tenant_id="foreign"))
        with pytest.raises(DurableTelegramStateError):
            with guarded_task_write("foreign", durable.task_id, durable.binding_digest):
                pytest.fail("foreign task write reached execution")
        with guarded_task_write(tenant, durable.task_id, durable.binding_digest):
            pass
        started.append(name)
        active += 1
        peak = max(peak, active)
        if len(started) == 2:
            two_started.set()
        try:
            if name in {"a0", "a1"}:
                await release_first.wait()
            if name == "b0":
                tenant_b_started.set()
                await release_b.wait()
            await asyncio.sleep(0)
            finished[tenant].append(name)
        finally:
            active -= 1

    control._set_progress = control._clear_progress = progress
    control._execute_with_lease = execute
    async def simulated_terminal(tenant, task, digest):
        expected_tenant, name = expected[task]
        return tenant == expected_tenant and name in finished[tenant]
    control._product_runtime.is_task_terminal = simulated_terminal
    try:
        await control.start()
        assert len(control._execution_workers) == 2
        for _ in admitted:
            control._wake()
        await asyncio.wait_for(two_started.wait(), timeout=2)
        assert queue.queue_counts() == (2, 4)
        with pytest.raises(DurableTelegramStateError, match="runtime_queue_full"):
            enqueue("tenant-a", "overflow")
        assert len(admitted) == 6
        release_first.set()
        await asyncio.wait_for(tenant_b_started.wait(), timeout=2)
        enqueue("tenant-a", "a4")
        control._wake()
        release_b.set()
        await asyncio.wait_for(control._execution_queue.join(), timeout=3)
        assert started == ["a0", "a1", "b0", "a2", "b1", "a3", "a4"]
        assert sorted(finished["tenant-a"]) == ["a0", "a1", "a2", "a3", "a4"]
        assert sorted(finished["tenant-b"]) == ["b0", "b1"]
        assert peak == 2 and active == control._active_jobs == 0
        assert queue.queue_counts() == (0, 0) and queue.dead_letter_count() == 0
        assert control._worker_error is None
        assert _store(tmp_path, clock=lambda: clock[0]).queue_counts() == (0, 0)
    finally:
        release_first.set()
        release_b.set()
        await asyncio.wait_for(control.close(), timeout=3)
    assert control._closed and not control._execution_workers
