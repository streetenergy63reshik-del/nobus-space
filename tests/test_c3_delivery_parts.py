"""C3 durable multipart delivery receipts and the remote/local unknown window."""
from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest

from src.application.durable_runtime import DurableFakeRuntime
from src.storage import DeliveryReceipt, OutboxCorruptionError, OutboxLeaseError, OutboxReceiptConflictError, OutboxStatus, ReceiptType, SQLiteStore
from src.storage.outbox import DeliveryPartReceipt, delivery_parts
from src.transport.telegram.bot_api import TelegramStatusSender
from tests.test_miniapp_result import _answered_store, DESTINATION
from tests.test_telegram_bot_api import api_for, response


class Clock:
    def __init__(self):
        self.value = datetime.now(UTC) + timedelta(seconds=30)
    def __call__(self):
        return self.value
    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


class Sender:
    def __init__(self, *, fail=None):
        self.calls = []
        self.fail = fail
    def delivery_manifest(self, message):
        return delivery_parts(message, (("text", b"one"), ("text", b"two"), ("document", b"complete")))
    async def send_part(self, message, part):
        self.calls.append(part.index)
        if part.index == self.fail:
            raise RuntimeError("synthetic unavailable")
        return True


def runtime(store, clock):
    result = object.__new__(DurableFakeRuntime)
    result._store = store
    result._clock = clock
    result._destination_refs = {"tenant-a": DESTINATION}
    return result


@pytest.fixture
def pending(tmp_path):
    store, task, message = _answered_store(tmp_path / "tasks.sqlite3")
    return store, message, Clock()


def claim(store, clock):
    owner = uuid4()
    message = store.claim_outbox_messages("tenant-a", lease_owner=owner,
        lease_duration_seconds=60, limit=1, now=clock())[0]
    return owner, message


def part_receipt(message, part, clock):
    return DeliveryPartReceipt(receipt_id=uuid4(), tenant_id=message.tenant_id,
        message_id=message.message_id, lease_id=message.lease_id,
        attempt_count=message.attempt_count, received_at=clock(), part_id=part.part_id,
        manifest_digest=part.manifest_digest, part_index=part.index)


@pytest.mark.asyncio
async def test_partial_failure_only_retries_unconfirmed_parts_after_restart(pending):
    store, message, clock = pending
    first = Sender(fail=1)
    outcome = await runtime(store, clock).deliver_pending("tenant-a", first)
    assert outcome[0].status is OutboxStatus.PENDING
    assert first.calls == [0, 1]
    assert [receipt is not None for _, receipt in store.read_delivery_parts("tenant-a", message.message_id)] == [True, False, False]
    assert store.read_outbox_receipts("tenant-a", message.message_id)[-1].receipt_type is ReceiptType.TIMEOUT
    assert store.delivery_counts("tenant-a")["unknown"] == 1
    clock.advance(2)
    second = Sender()
    restarted = SQLiteStore(store._path)
    outcome = await runtime(restarted, clock).deliver_pending("tenant-a", second)
    assert outcome[0].status is OutboxStatus.ACKED
    assert second.calls == [1, 2]
    assert restarted.delivery_counts("tenant-a")["confirmed_parts"] == 3
    assert await runtime(SQLiteStore(store._path), clock).deliver_pending("tenant-a", second) == ()


@pytest.mark.asyncio
async def test_crash_after_part_receipt_before_next_send_never_repeats_ack(pending, monkeypatch):
    class Crash(BaseException):
        pass
    store, message, clock = pending
    original = store.record_delivery_part
    def crash_after_commit(receipt, **kwargs):
        original(receipt, **kwargs)
        raise Crash()
    monkeypatch.setattr(store, "record_delivery_part", crash_after_commit)
    sender = Sender()
    with pytest.raises(Crash):
        await runtime(store, clock).deliver_pending("tenant-a", sender)
    assert sender.calls == [0]
    clock.advance(61)
    second = Sender()
    await runtime(SQLiteStore(store._path), clock).deliver_pending("tenant-a", second)
    assert second.calls == [1, 2]


@pytest.mark.asyncio
async def test_remote_accept_before_local_receipt_retains_narrow_replay_window(pending, monkeypatch):
    store, message, clock = pending
    def unavailable(*args, **kwargs):
        raise RuntimeError("synthetic receipt store unavailable")
    monkeypatch.setattr(store, "record_delivery_part", unavailable)
    first = Sender()
    await runtime(store, clock).deliver_pending("tenant-a", first)
    assert first.calls == [0]
    assert store.read_outbox_receipts("tenant-a", message.message_id)[-1].receipt_type is ReceiptType.TIMEOUT
    clock.advance(2)
    second = Sender()
    await runtime(SQLiteStore(store._path), clock).deliver_pending("tenant-a", second)
    assert second.calls == [0, 1, 2]  # At-least-once residual is explicit, never called exactly-once.


def test_whole_ack_requires_every_part_and_stale_part_ack_is_fenced(pending):
    store, original, clock = pending
    owner, message = claim(store, clock)
    parts = Sender().delivery_manifest(message)
    store.bind_delivery_parts(message, parts, lease_owner=owner, now=clock())
    receipt = DeliveryReceipt(receipt_id=uuid4(), tenant_id=message.tenant_id,
        message_id=message.message_id, lease_id=message.lease_id, attempt_count=message.attempt_count,
        receipt_type=ReceiptType.ACK, received_at=clock())
    with pytest.raises(OutboxReceiptConflictError):
        store.record_outbox_receipt(receipt, lease_owner=owner, now=clock())
    stale = part_receipt(message, parts[0], clock)
    clock.advance(61)
    next_owner, new_message = claim(store, clock)
    with pytest.raises(OutboxLeaseError):
        store.record_delivery_part(stale, lease_owner=owner, now=clock())
    assert all(ack is None for _, ack in store.read_delivery_parts("tenant-a", original.message_id))
    assert new_message.lease_id != message.lease_id


@pytest.mark.parametrize("mutation", ["DELETE FROM outbox_delivery_parts", "UPDATE outbox_delivery_parts SET part_digest='bad'", "UPDATE outbox_delivery_parts SET receipt_digest='bad'"])
def test_tampered_or_missing_manifest_fails_closed(pending, mutation):
    store, original, clock = pending
    owner, message = claim(store, clock)
    parts = Sender().delivery_manifest(message)
    store.bind_delivery_parts(message, parts, lease_owner=owner, now=clock())
    store.record_delivery_part(part_receipt(message, parts[0], clock), lease_owner=owner, now=clock())
    with sqlite3.connect(store._path) as db:
        db.execute(mutation)
    with pytest.raises(OutboxCorruptionError):
        store.read_delivery_parts("tenant-a", original.message_id)
    assert store.read_delivery_parts("foreign-tenant", original.message_id) == ()


@pytest.mark.asyncio
async def test_actual_telegram_renderer_restarts_at_document_without_repeating_text(tmp_path, monkeypatch):
    from tests import test_c3_result_recovery as sealed
    monkeypatch.setattr(sealed, "ANSWER", ("Проверенный материал. " * 100).strip())
    value = sealed.runtime(tmp_path)
    prepared, incoming, task = await sealed.seal(value)
    assert await value.recover_prepared(prepared, incoming) is False
    assert value._store.read_task(task.tenant_id, task.id).projection.status.value == "answered"
    clock = Clock(); value._clock = clock
    calls = []
    failed_document = False
    def handler(request):
        nonlocal failed_document
        method = request.url.path.rsplit("/", 1)[-1]
        calls.append(method)
        if method == "sendDocument":
            if not failed_document:
                failed_document = True
                return httpx.Response(503)
            return response({"message_id": 5, "chat": {"id": 42},
                             "document": {"file_id": "synthetic", "file_unique_id": "synthetic"}})
        return response({"message_id": len(calls), "chat": {"id": 42}})
    api = api_for(handler)
    sender = TelegramStatusSender(api, {"tenant-a": (DESTINATION, 42)}, technical_details=False)
    try:
        outcome = await value.deliver_pending("tenant-a", sender)
        assert outcome[0].status is OutboxStatus.PENDING
        assert calls.count("sendMessage") == 1
        before = list(calls)
        clock.advance(2)
        outcome = await runtime(SQLiteStore(value._store._path), clock).deliver_pending("tenant-a", sender)
        assert outcome[0].status is OutboxStatus.ACKED
        assert calls == before + ["sendDocument"]
    finally:
        await api.aclose()
