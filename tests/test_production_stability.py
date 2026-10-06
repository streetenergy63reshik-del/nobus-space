"""Synthetic regressions: transport grammar, responsive Core, cancellation safety."""
import asyncio
import threading
from types import SimpleNamespace
from uuid import uuid4

import pytest

from scripts.runtime_diagnostics import classify_relay
from src.application.durable_product import DurableProductTelegramControlPlane
from tests.test_telegram_bot_api import Checkpoint, api_for, response
from src.transport.telegram.bot_api import TelegramPollingBoundary


@pytest.mark.parametrize("payload,expected", [
    (b"Timeout, server synthetic not responding.\n", "transport_timeout"),
    (b"client_loop: send disconnect: Broken pipe\n", "transport_reset"),
    (b"client_loop: send disconnect: Connection reset by peer\n", "transport_reset"),
    (b"Connection to synthetic closed by remote host.\n", "transport_reset"),
    (b"Read from remote host synthetic: Connection reset by peer\nclient_loop: send disconnect: Broken pipe\n", "transport_reset"),
    (b"Timeout, server synthetic not responding.\nPermission denied\n", "authentication"),
    (b"remote says Timeout, server synthetic not responding.\n", "unknown"),
    (b"Timeout, server synthetic not responding.\nunexpected banner\n", "unknown"),
    (b"Timeout, server synthetic not responding.\nclient_loop: send disconnect: Broken pipe\n", "unknown"),
])
def test_openssh_established_transport(payload, expected):
    assert classify_relay(payload) == expected
    assert classify_relay(payload, complete=False) == "unknown"


@pytest.mark.asyncio
async def test_idle_claim_does_not_block_core_and_stop_waits_for_transaction():
    entered, release = threading.Event(), threading.Event()
    def claim(**kwargs):
        entered.set()
        assert release.wait(3)
        return None
    product = object.__new__(DurableProductTelegramControlPlane)
    product._telegram_state = SimpleNamespace(claim=claim)
    product._lease_owner = uuid4()
    product._execution_queue = asyncio.Queue()
    product._execution_queue.put_nowait(None)
    worker = asyncio.create_task(product._execution_worker())
    responsive = False
    try:
        await asyncio.sleep(.05)
        responsive = entered.is_set() and not release.is_set() and not worker.done()
        worker.cancel()
        await asyncio.sleep(.05)
        assert not worker.done(), "stop must wait for the storage transaction"
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await worker
    assert responsive, "Core loop must respond while SQLite is busy"
    assert product._execution_queue._unfinished_tasks == 0


@pytest.mark.asyncio
async def test_poll_checkpoint_does_not_block_core_and_cancel_releases_late_lease():
    entered, release = threading.Event(), threading.Event()
    class SlowCheckpoint(Checkpoint):
        def acquire(self, owner_id, at):
            entered.set()
            assert release.wait(3)
            return super().acquire(owner_id, at)
    checkpoint = SlowCheckpoint(0)
    api = api_for(lambda request: response([]))
    poll = asyncio.create_task(TelegramPollingBoundary(api, lambda _: asyncio.sleep(0, result=True), checkpoint).poll_once())
    responsive = False
    try:
        await asyncio.sleep(.05)
        responsive = entered.is_set() and not release.is_set()
        poll.cancel()
        await asyncio.sleep(.05)
        assert not poll.done()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await poll
        await api.aclose()
    assert responsive
    assert not checkpoint.owned and checkpoint.offset == 0


@pytest.mark.asyncio
async def test_cancelled_claim_releases_exact_job_after_repeated_cancel(tmp_path):
    from tests.test_durable_telegram_state import _store
    from src.contracts.models import canonical_json_digest
    from src.storage.nonblocking import run_storage
    state = _store(tmp_path)
    task_id, owner = uuid4(), uuid4()
    state.enqueue(kind="draft", tenant_id="tenant-a", task_id=task_id,
                  binding_digest=canonical_json_digest({"synthetic": True}), payload={"synthetic": True})
    entered, release = threading.Event(), threading.Event()
    def claim():
        job = state.claim(lease_owner=owner, lease_seconds=60)
        entered.set()
        assert release.wait(3)
        return job
    task = asyncio.create_task(run_storage(claim, on_cancel=lambda job: state.release(job, lease_owner=owner)))
    assert await asyncio.to_thread(entered.wait, 1)
    task.cancel()
    await asyncio.sleep(.01)
    task.cancel()
    await asyncio.sleep(.01)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    reclaimed = state.claim(lease_owner=uuid4(), lease_seconds=60)
    assert reclaimed is not None and reclaimed.task_id == task_id
    assert reclaimed.attempt_count == 2


@pytest.mark.asyncio
async def test_real_sqlite_lock_keeps_core_responsive(tmp_path):
    import sqlite3
    from src.storage.nonblocking import run_storage
    from src.transport.telegram.sqlite_checkpoint import SQLitePollingCheckpointStore
    path = tmp_path / "checkpoint.sqlite3"
    store = SQLitePollingCheckpointStore(path, consumer_id="synthetic", busy_timeout_ms=2000)
    connection = sqlite3.connect(path, isolation_level=None)
    connection.execute("BEGIN IMMEDIATE")
    operation = asyncio.create_task(run_storage(store.acquire, uuid4(), __import__('datetime').datetime.now(__import__('datetime').UTC)))
    try:
        await asyncio.sleep(.1)
        assert not operation.done()
    finally:
        connection.rollback()
        connection.close()
    lease = await operation
    assert lease is not None
    assert await run_storage(store.release, lease)


@pytest.mark.asyncio
async def test_cancelled_advance_waits_for_commit_before_releasing_lease():
    entered, release = threading.Event(), threading.Event()
    events = []
    class SlowCheckpoint(Checkpoint):
        def advance(self, **kwargs):
            entered.set()
            assert release.wait(3)
            result = super().advance(**kwargs)
            events.append("committed")
            return result
        def release(self, lease):
            events.append("released")
            return super().release(lease)
    checkpoint = SlowCheckpoint(0)
    api = api_for(lambda request: response([{"update_id": 0}]))
    boundary = TelegramPollingBoundary(api, lambda _: asyncio.sleep(0, result=True), checkpoint)
    task = asyncio.create_task(boundary.poll_once())
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        task.cancel()
        await asyncio.sleep(.01)
        assert checkpoint.owned and not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert events == ["committed", "released"] and checkpoint.offset == 1
    finally:
        release.set()
        await api.aclose()


@pytest.mark.parametrize("extra", [b"unexpected", b"Permission denied", b"Host key verification failed", b"remote port forwarding failed"])
def test_transport_does_not_mask_permanent_or_extra_output(extra):
    cause = classify_relay(b"client_loop: send disconnect: Broken pipe\n" + extra + b"\n")
    assert cause not in {"transport_timeout", "transport_reset", "transport_refused", "transport_unreachable"}
