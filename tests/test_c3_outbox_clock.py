from datetime import UTC, datetime
from pathlib import Path
from threading import Thread, Event
from uuid import uuid4
import sqlite3
import time
import pytest
from tests.test_miniapp_result import _answered_store
from src.storage import DeliveryReceipt, ReceiptType, OutboxLeaseError
from src.storage.outbox import delivery_parts, DeliveryPartReceipt

@pytest.mark.parametrize('operation', ['part_receipt', 'whole_receipt', 'bind_manifest'])
def test_real_sqlite_lock_expiry(tmp_path, operation):
    store, task, original = _answered_store(tmp_path / 'tasks.sqlite3')
    owner = uuid4()
    message = store.claim_outbox_messages('tenant-a', lease_owner=owner, lease_duration_seconds=1, limit=1)[0]
    parts = delivery_parts(message, (('text', b'one'),))
    if operation == 'part_receipt':
        store.bind_delivery_parts(message, parts, lease_owner=owner, now=datetime.now(UTC))
    locked = Event()
    def hold_lock():
        with sqlite3.connect(store._path, isolation_level=None) as connection:
            connection.execute('BEGIN IMMEDIATE')
            locked.set()
            time.sleep(1.3)
            connection.commit()
    blocker = Thread(target=hold_lock)
    blocker.start()
    assert locked.wait(2)
    captured = datetime.now(UTC)
    assert captured < message.lease_expires_at
    try:
        with pytest.raises(OutboxLeaseError):
            if operation == 'part_receipt':
                part = parts[0]
                receipt = DeliveryPartReceipt(receipt_id=uuid4(), tenant_id=message.tenant_id, message_id=message.message_id, lease_id=message.lease_id, attempt_count=message.attempt_count, received_at=captured, part_id=part.part_id, manifest_digest=part.manifest_digest, part_index=part.index)
                store.record_delivery_part(receipt, lease_owner=owner, now=captured)
            elif operation == 'whole_receipt':
                receipt = DeliveryReceipt(receipt_id=uuid4(), tenant_id=message.tenant_id, message_id=message.message_id, lease_id=message.lease_id, attempt_count=message.attempt_count, receipt_type=ReceiptType.ACK, received_at=captured)
                store.record_outbox_receipt(receipt, lease_owner=owner, now=captured)
            else:
                store.bind_delivery_parts(message, parts, lease_owner=owner, now=captured)
    finally:
        blocker.join(3)
    assert datetime.now(UTC) > message.lease_expires_at

@pytest.mark.asyncio
async def test_core_lock_cannot_outlive_queue_authority(tmp_path):
    import json
    from tests.test_c3_result_recovery import runtime
    from tests.test_durable_telegram_state import _store
    from tests.test_sqlite_store import contract_for, envelope
    from src.contracts import IngressSource
    from src.core.policy import task_contract_digest
    from src.application.durable_telegram_state import execution_lease, DurableTelegramStateError
    core = runtime(tmp_path / 'core')
    incoming = envelope(source=IngressSource.API)
    contract = contract_for(incoming)
    task = await core._start_worker(contract, await core._begin_task(contract, incoming))
    queue = _store(tmp_path / 'queue')
    queue.enqueue(kind='draft', tenant_id=contract.tenant_id, task_id=contract.task_id, binding_digest=task_contract_digest(contract), payload={'synthetic': True})
    owner = uuid4()
    job = queue.claim(lease_owner=owner, lease_seconds=5)
    time.sleep(4.2)
    locked = Event()
    def hold_lock():
        with sqlite3.connect(core._store._path, isolation_level=None) as connection:
            connection.execute('BEGIN IMMEDIATE')
            locked.set()
            time.sleep(1.3)
            connection.commit()
    blocker = Thread(target=hold_lock)
    blocker.start()
    assert locked.wait(2)
    token = execution_lease.set((queue, job, owner))
    try:
        with pytest.raises(DurableTelegramStateError):
            await core._record_worker_result(contract, task, json.dumps({'answer':'Synthetic sealed answer.'}), result_kind='answer')
    finally:
        execution_lease.reset(token)
        blocker.join(3)

