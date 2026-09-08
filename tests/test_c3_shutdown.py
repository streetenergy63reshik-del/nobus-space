"""Offline C3 shutdown: cancellation, durable recovery and stale authority."""

import asyncio
from contextlib import suppress
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.application import durable_product as product
from src.application.durable_telegram_state import DurableTelegramStateError, guarded_task_write
from src.application.telegram_product import _QueuedPatch
from tests.test_durable_telegram_state import _store
from tests.test_runtime_operations import _proposal


async def _nothing(*args, **kwargs):
    return None


def _control(tmp_path):
    control = object.__new__(product.DurableProductTelegramControlPlane)
    control._admission_readiness = None
    control._telegram_state = _store(tmp_path)
    control._product_runtime = SimpleNamespace(_worker=SimpleNamespace(generation_available=True))
    control._product_effects = None
    control._closing = control._closed = control._close_failed = False
    control._close_lock = asyncio.Lock()
    control._close_task = None
    control._execution_queue = asyncio.Queue()
    control._execution_workers = ()
    control._cleanup_pending = set()
    control._execution_concurrency = 1
    control._lease_owner = uuid4()
    control._worker_error = None
    control._worker_error_count = control._active_jobs = 0
    control.deliver_pending = _nothing
    control._set_progress = control._clear_progress = _nothing
    return control


@pytest.mark.asyncio
async def test_simultaneous_close_survives_cancelled_caller(tmp_path):
    control = _control(tmp_path)
    started, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    cleanups = []

    async def worker():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanups.append("worker")
            cleaning.set()
            await release.wait()

    task = asyncio.create_task(worker())
    control._execution_workers = (task,)
    await started.wait()
    caller = asyncio.create_task(control.close())
    await cleaning.wait()
    peer = asyncio.create_task(control.close())
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    assert control._closing and not control._closed
    assert not control._close_task.done()
    release.set()
    await asyncio.wait_for(peer, 2)
    await control.close()
    assert cleanups == ["worker"]
    assert task.cancelled()
    assert control._closed and not control._close_failed


@pytest.mark.asyncio
@pytest.mark.parametrize("component", ("worker", "effect"))
async def test_resistant_cleanup_is_bounded_and_closed_intake_stays_closed(tmp_path, monkeypatch, component):
    monkeypatch.setattr(product, "_SHUTDOWN_SECONDS", 0.02)
    monkeypatch.setattr(product, "_CLEANUP_SECONDS", 0.02)
    control = _control(tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()
    owned = []

    async def resistant():
        owned.append(asyncio.current_task())
        entered.set()
        while not release.is_set():
            with suppress(asyncio.CancelledError):
                await release.wait()

    if component == "worker":
        control._execution_workers = (asyncio.create_task(resistant()),)
        await entered.wait()
    else:
        control._product_effects = SimpleNamespace(close=resistant)
    try:
        with pytest.raises(RuntimeError, match="did not close safely"):
            await asyncio.wait_for(control.close(), 2)
        assert entered.is_set() and control._closed and control._close_failed
        with pytest.raises(RuntimeError, match="unavailable"):
            control.assert_healthy()
        with pytest.raises(RuntimeError, match="queue is closing"):
            await control.submit_miniapp_task("blocked", None)
        assert await control._submit_draft(None, None, None) is False
        assert await control._submit_patch(None, approver_identity="owner", approval_evidence_ref="safe") is False
        with pytest.raises(RuntimeError, match="did not close safely"):
            await control.close()
        old_workers = control._execution_workers
        await control.start()
        assert control._execution_workers == old_workers
    finally:
        release.set()
        await asyncio.gather(*owned, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ("patch", "voice"))
async def test_shutdown_releases_job_and_fences_late_resistant_commit(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(product, "_SHUTDOWN_SECONDS", 0.5)
    monkeypatch.setattr(product, "_CLEANUP_SECONDS", 0.02)
    control = _control(tmp_path)
    proposal = _proposal()
    inserted = control._telegram_state.enqueue(kind=kind, tenant_id=proposal.tenant_id,
        task_id=proposal.task_id, binding_digest=proposal.patch_digest, payload={"synthetic": True})
    entered, release = asyncio.Event(), asyncio.Event()
    owned, commits, blocked = [], [], []

    async def operation(*args, **kwargs):
        owned.append(asyncio.current_task())
        entered.set()
        while not release.is_set():
            with suppress(asyncio.CancelledError):
                await release.wait()
        try:
            with guarded_task_write(proposal.tenant_id, proposal.task_id, proposal.contract_digest):
                commits.append("late-authoritative-result")
        except DurableTelegramStateError as error:
            blocked.append(str(error))

    if kind == "patch":
        control._product_runtime.apply_proposal = operation

        async def restore(job):
            return _QueuedPatch(proposal, "telegram:owner", "approval")

        control._restore = restore
    else:
        control._durable_voice = SimpleNamespace(run=operation)
    await control.start()
    control._wake()
    await asyncio.wait_for(entered.wait(), 2)
    try:
        with pytest.raises(RuntimeError, match="did not close safely"):
            await asyncio.wait_for(control.close(), 2)
        assert control._closed and control._close_failed
        with pytest.raises(RuntimeError, match="unavailable"):
            control.assert_healthy()
        # The wrapper has stopped even though its child ignored cancellation.
        assert owned and not owned[0].done()
        reopened = _store(tmp_path)
        assert reopened.queue_counts() == (0, 1)
        replacement_owner = uuid4()
        recovered = reopened.claim(lease_owner=replacement_owner, lease_seconds=30)
        assert recovered is not None and recovered.job_id == inserted.job_id
        assert recovered.task_id == proposal.task_id and recovered.attempt_count == 2
        release.set()
        await asyncio.wait_for(asyncio.gather(*owned), 2)
        assert commits == []
        assert blocked == ["runtime_job_lease_lost"]
        # The late completion did not ACK or corrupt the new owner's lease.
        reopened.ack(recovered, lease_owner=replacement_owner)
        assert reopened.queue_counts() == (0, 0)
    finally:
        release.set()
        await asyncio.gather(*owned, return_exceptions=True)
