"""Gate 4E durability and adversarial checks for the safe local outbox."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.contracts import RiskLevel
from src.contracts.models import canonical_json_digest
from src.models.task import Task, TaskSource, TaskStatus
from src.storage import (
    DeliveryReceipt,
    OutboxCorruptionError,
    OutboxEnqueueResult,
    OutboxLeaseError,
    OutboxMessage,
    OutboxReceiptConflictError,
    OutboxStatus,
    ReceiptType,
    SQLiteStore,
    SnapshotConflictError,
    StoreCorruptionError,
)
from tests.test_sqlite_store import (
    bound_values,
    persist,
    persisted_draft,
    verification_bundle,
)


DESTINATION = "sha256:" + "d" * 64


def enqueue(
    store: SQLiteStore,
    *,
    max_attempts: int = 3,
    destination_ref: str = DESTINATION,
) -> tuple[Task, Task, datetime, OutboxEnqueueResult]:
    task = persist(store)
    transitioned = task.model_copy(
        update={
            "status": TaskStatus.PARSING,
            "updated_at": task.updated_at + timedelta(seconds=1),
        }
    )
    now = task.updated_at + timedelta(seconds=2)
    result = store.save_task_and_enqueue_status(
        transitioned,
        expected_revision=1,
        destination_ref=destination_ref,
        max_attempts=max_attempts,
        now=now,
    )
    return task, transitioned, now, result


def receipt_for(message, receipt_type: ReceiptType, received_at: datetime):
    assert message.lease_id is not None
    return DeliveryReceipt(
        receipt_id=uuid4(),
        tenant_id=message.tenant_id,
        message_id=message.message_id,
        lease_id=message.lease_id,
        attempt_count=message.attempt_count,
        receipt_type=receipt_type,
        received_at=received_at,
    )


def test_schema_contains_outbox_tables_and_indexes(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    SQLiteStore(path)
    SQLiteStore(path)
    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
    assert {"outbox_messages", "outbox_receipts"} <= tables
    assert {"idx_outbox_pending", "idx_outbox_expired"} <= indexes


def test_save_and_enqueue_is_one_atomic_transition(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    _, transitioned, _, result = enqueue(store)
    assert result.created is True
    assert result.task_revision == 2
    assert result.message.status is OutboxStatus.PENDING
    assert result.message.task_status is TaskStatus.PARSING
    snapshot = store.read_task(transitioned.tenant_id, transitioned.id)
    assert snapshot is not None
    assert snapshot.revision == 2
    assert snapshot.projection.status is TaskStatus.PARSING


def test_legacy_outbox_row_without_user_message_remains_readable(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.sqlite3"
    store = SQLiteStore(path)
    _, _, _, result = enqueue(store)
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT message_json FROM outbox_messages WHERE message_id = ?",
            (str(result.message.message_id),),
        ).fetchone()
        assert row is not None
        legacy = json.loads(row[0])
        assert legacy.pop("user_message") is None
        legacy_json = json.dumps(
            legacy,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        connection.execute(
            "UPDATE outbox_messages SET message_json = ?, message_digest = ? "
            "WHERE message_id = ?",
            (
                legacy_json,
                canonical_json_digest(legacy),
                str(result.message.message_id),
            ),
        )

    restored = SQLiteStore(path).read_outbox_message(
        result.message.tenant_id,
        result.message.message_id,
    )

    assert restored is not None
    assert restored.user_message is None
    assert restored.message_fingerprint == result.message.message_fingerprint

def test_verified_answer_survives_restart_in_durable_outbox(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    store, manager, task, revision = persisted_draft(
        path,
        result={
            "output_digest": canonical_json_digest({"output": "answer"}),
            "summary": "not stored",
            "result_kind": "answer",
        },
    )
    for status, level_count in (
        (TaskStatus.L1_VALIDATED, 1),
        (TaskStatus.L2_VERIFIED, 2),
    ):
        task = asyncio.run(
            manager.update(
                task.id,
                status=status,
                verification_bundle=verification_bundle(task, level_count),
            )
        )
        assert task is not None
        store.save_task(task, expected_revision=revision)
        revision += 1

    answer = "Проверенный ответ после перезапуска."
    task = asyncio.run(
        manager.update(
            task.id,
            status=TaskStatus.ANSWERED,
            verification_bundle=verification_bundle(task, 3),
        )
    )
    assert task is not None
    enqueued = store.save_task_and_enqueue_status(
        task,
        expected_revision=revision,
        destination_ref=DESTINATION,
        user_message=answer,
    )

    restarted = SQLiteStore(path)
    claimed = restarted.claim_outbox_messages(
        task.tenant_id,
        lease_owner=uuid4(),
        lease_duration_seconds=60,
    )

    assert len(claimed) == 1
    assert claimed[0].message_id == enqueued.message.message_id
    assert claimed[0].task_status is TaskStatus.ANSWERED
    assert claimed[0].user_message == answer

def test_enqueue_rollback_leaves_task_and_outbox_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    store = SQLiteStore(path)
    task = persist(store)
    transitioned = task.model_copy(
        update={
            "status": TaskStatus.PARSING,
            "updated_at": task.updated_at + timedelta(seconds=1),
        }
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TRIGGER reject_outbox BEFORE INSERT ON outbox_messages
               BEGIN SELECT RAISE(ABORT, 'forced'); END"""
        )
    with pytest.raises(StoreCorruptionError):
        store.save_task_and_enqueue_status(
            transitioned,
            expected_revision=1,
            destination_ref=DESTINATION,
        )
    snapshot = store.read_task(task.tenant_id, task.id)
    assert snapshot is not None
    assert snapshot.revision == 1
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM outbox_messages").fetchone()[0] == 0


def test_uncertain_commit_retry_is_a_true_noop(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    _, transitioned, now, first = enqueue(store)
    second = store.save_task_and_enqueue_status(
        transitioned,
        expected_revision=1,
        destination_ref=DESTINATION,
        now=now + timedelta(seconds=10),
    )
    assert second.created is False
    assert second.message == first.message
    snapshot = store.read_task(transitioned.tenant_id, transitioned.id)
    assert snapshot is not None
    assert snapshot.revision == 2


def test_reused_binding_cannot_change_retry_policy(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    _, transitioned, now, _ = enqueue(store, max_attempts=2)
    with pytest.raises(ValueError):
        store.save_task_and_enqueue_status(
            transitioned,
            expected_revision=1,
            destination_ref=DESTINATION,
            max_attempts=3,
            now=now,
        )


def test_stale_task_with_different_message_hits_cas(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    _, transitioned, now, _ = enqueue(store)
    with pytest.raises(SnapshotConflictError):
        store.save_task_and_enqueue_status(
            transitioned,
            expected_revision=1,
            destination_ref="sha256:" + "e" * 64,
            now=now,
        )


@pytest.mark.parametrize("value", [True, 0, 11, 1.5, "3"])
def test_max_attempts_is_strict(tmp_path: Path, value: object) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    task = persist(store)
    with pytest.raises(ValueError, match="max_attempts"):
        store.save_task_and_enqueue_status(
            task,
            expected_revision=1,
            destination_ref=DESTINATION,
            max_attempts=value,  # type: ignore[arg-type]
        )


def test_raw_destination_is_rejected_before_write(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    store = SQLiteStore(path)
    marker = "RAW-CHAT-ID-E4"
    task = persist(store)
    with pytest.raises(ValueError, match="destination_ref"):
        store.save_task_and_enqueue_status(
            task,
            expected_revision=1,
            destination_ref=marker,
        )
    raw = b"".join(
        candidate.read_bytes()
        for candidate in path.parent.glob(f"{path.name}*")
        if candidate.is_file()
    )
    assert marker.encode() not in raw


def test_claim_returns_post_update_lease(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    _, _, enqueued_at, result = enqueue(store)
    owner = uuid4()
    claimed = store.claim_outbox_messages(
        result.message.tenant_id,
        lease_owner=owner,
        lease_duration_seconds=30,
        now=enqueued_at + timedelta(seconds=1),
    )
    assert len(claimed) == 1
    assert claimed[0].status is OutboxStatus.LEASED
    assert claimed[0].lease_owner == owner
    assert claimed[0].lease_id is not None
    assert claimed[0].attempt_count == 1
    assert claimed[0].state_revision == 2
    assert store.read_outbox_message(
        result.message.tenant_id, result.message.message_id
    ) == claimed[0]


def test_claim_is_tenant_scoped(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    _, _, now, result = enqueue(store)
    assert store.claim_outbox_messages(
        "tenant-b",
        lease_owner=uuid4(),
        lease_duration_seconds=30,
        now=now + timedelta(seconds=1),
    ) == ()
    assert store.read_outbox_message(
        "tenant-b", result.message.message_id
    ) is None


def test_concurrent_claim_has_one_winner(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    _, _, now, result = enqueue(store)
    claim_at = now + timedelta(seconds=1)

    def claim(_: int) -> int:
        return len(
            store.claim_outbox_messages(
                result.message.tenant_id,
                lease_owner=uuid4(),
                lease_duration_seconds=30,
                now=claim_at,
            )
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        outcomes = list(executor.map(claim, range(8)))
    assert outcomes.count(1) == 1
    assert outcomes.count(0) == 7


def test_expired_final_attempt_becomes_failed(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    _, _, now, result = enqueue(store, max_attempts=1)
    store.claim_outbox_messages(
        result.message.tenant_id,
        lease_owner=uuid4(),
        lease_duration_seconds=1,
        now=now + timedelta(seconds=1),
    )
    assert store.claim_outbox_messages(
        result.message.tenant_id,
        lease_owner=uuid4(),
        lease_duration_seconds=30,
        now=now + timedelta(seconds=3),
    ) == ()
    stored = store.read_outbox_message(
        result.message.tenant_id, result.message.message_id
    )
    assert stored is not None
    assert stored.status is OutboxStatus.FAILED
    assert stored.attempt_count == 1


def test_stale_lease_generation_cannot_ack_reclaim(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    _, _, now, result = enqueue(store)
    owner = uuid4()
    first = store.claim_outbox_messages(
        result.message.tenant_id,
        lease_owner=owner,
        lease_duration_seconds=1,
        now=now + timedelta(seconds=1),
    )[0]
    second = store.claim_outbox_messages(
        result.message.tenant_id,
        lease_owner=owner,
        lease_duration_seconds=30,
        now=now + timedelta(seconds=3),
    )[0]
    assert first.lease_id != second.lease_id
    stale = receipt_for(first, ReceiptType.ACK, now + timedelta(seconds=1))
    with pytest.raises(OutboxLeaseError):
        store.record_outbox_receipt(
            stale, lease_owner=owner, now=now + timedelta(seconds=4)
        )


def test_expired_receipt_is_rejected(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    _, _, now, result = enqueue(store)
    owner = uuid4()
    claimed = store.claim_outbox_messages(
        result.message.tenant_id,
        lease_owner=owner,
        lease_duration_seconds=1,
        now=now + timedelta(seconds=1),
    )[0]
    receipt = receipt_for(claimed, ReceiptType.ACK, now + timedelta(seconds=1))
    with pytest.raises(OutboxLeaseError):
        store.record_outbox_receipt(
            receipt, lease_owner=owner, now=now + timedelta(seconds=3)
        )


def test_ack_is_bound_and_append_only(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    _, _, now, result = enqueue(store)
    owner = uuid4()
    claimed = store.claim_outbox_messages(
        result.message.tenant_id,
        lease_owner=owner,
        lease_duration_seconds=30,
        now=now + timedelta(seconds=1),
    )[0]
    receipt = receipt_for(claimed, ReceiptType.ACK, now + timedelta(seconds=2))
    updated = store.record_outbox_receipt(
        receipt, lease_owner=owner, now=now + timedelta(seconds=2)
    )
    assert updated.status is OutboxStatus.ACKED
    assert updated.lease_id is None
    assert store.read_outbox_receipts(updated.tenant_id, updated.message_id) == (
        receipt,
    )
    with pytest.raises(OutboxReceiptConflictError):
        store.record_outbox_receipt(
            receipt, lease_owner=owner, now=now + timedelta(seconds=3)
        )


@pytest.mark.parametrize("kind", [ReceiptType.NACK, ReceiptType.TIMEOUT])
def test_failed_attempt_is_rescheduled(tmp_path: Path, kind: ReceiptType) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    _, _, now, result = enqueue(store, max_attempts=2)
    owner = uuid4()
    claimed = store.claim_outbox_messages(
        result.message.tenant_id,
        lease_owner=owner,
        lease_duration_seconds=30,
        now=now + timedelta(seconds=1),
    )[0]
    receipt = receipt_for(claimed, kind, now + timedelta(seconds=2))
    updated = store.record_outbox_receipt(
        receipt, lease_owner=owner, now=now + timedelta(seconds=2)
    )
    assert updated.status is OutboxStatus.PENDING
    assert updated.next_attempt_at == now + timedelta(seconds=3)


def test_wrong_owner_is_rejected_without_mutation(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    _, _, now, result = enqueue(store)
    owner = uuid4()
    claimed = store.claim_outbox_messages(
        result.message.tenant_id,
        lease_owner=owner,
        lease_duration_seconds=30,
        now=now + timedelta(seconds=1),
    )[0]
    receipt = receipt_for(claimed, ReceiptType.ACK, now + timedelta(seconds=2))
    with pytest.raises(OutboxLeaseError):
        store.record_outbox_receipt(
            receipt, lease_owner=uuid4(), now=now + timedelta(seconds=2)
        )
    assert store.read_outbox_message(
        claimed.tenant_id, claimed.message_id
    ) == claimed


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE outbox_messages SET status = 'acked'",
        "UPDATE outbox_messages SET attempt_count = attempt_count + 1",
        "UPDATE outbox_messages SET message_json = '{}'",
        "UPDATE outbox_messages SET message_digest = 'sha256:' || printf('%064d', 0)",
    ],
)
def test_lifecycle_tamper_is_rejected(tmp_path: Path, sql: str) -> None:
    path = tmp_path / "state.sqlite3"
    store = SQLiteStore(path)
    _, _, _, result = enqueue(store)
    with sqlite3.connect(path) as connection:
        connection.execute(sql)
    with pytest.raises(OutboxCorruptionError):
        store.read_outbox_message(
            result.message.tenant_id, result.message.message_id
        )


def test_restart_recovers_pending_message(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    store = SQLiteStore(path)
    _, _, now, result = enqueue(store)
    recovered = SQLiteStore(path)
    assert recovered.read_outbox_message(
        result.message.tenant_id, result.message.message_id
    ) == result.message
    claimed = recovered.claim_outbox_messages(
        result.message.tenant_id,
        lease_owner=uuid4(),
        lease_duration_seconds=30,
        now=now + timedelta(seconds=1),
    )
    assert len(claimed) == 1


def test_outbox_contains_no_operational_text_fields(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    store = SQLiteStore(path)
    _, _, _, _ = enqueue(store)
    with sqlite3.connect(path) as connection:
        schema = " ".join(
            row[0]
            for row in connection.execute(
                "SELECT sql FROM sqlite_master WHERE name LIKE 'outbox_%'"
            )
            if row[0]
        )
        row = connection.execute(
            "SELECT message_json FROM outbox_messages"
        ).fetchone()[0]
    forbidden = ("instruction", "transcript", "raw_chat", "payload", "token", "result_text")
    assert all(marker not in schema.casefold() for marker in forbidden)
    assert all(marker not in row.casefold() for marker in forbidden)


@pytest.mark.parametrize(
    ("lease_duration_seconds", "limit"),
    [(0, 1), (3601, 1), (True, 1), (30, 0), (30, 101), (30, True)],
)
def test_claim_rejects_unbounded_inputs(
    tmp_path: Path,
    lease_duration_seconds: object,
    limit: object,
) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    with pytest.raises(ValueError):
        store.claim_outbox_messages(
            "tenant-a",
            lease_owner=uuid4(),
            lease_duration_seconds=lease_duration_seconds,  # type: ignore[arg-type]
            limit=limit,  # type: ignore[arg-type]
        )


def test_claim_normalizes_non_utc_server_time(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    _, _, queued_at, _ = enqueue(store)
    offset = timezone(timedelta(hours=5, minutes=30))
    claimed = store.claim_outbox_messages(
        "tenant-a",
        lease_owner=uuid4(),
        lease_duration_seconds=30,
        now=queued_at.astimezone(offset),
    )
    assert claimed[0].updated_at.utcoffset() == timedelta(0)

@pytest.mark.parametrize(
    ("field_name", "value_factory"),
    [
        ("source", lambda task: TaskSource.API),
        ("risk", lambda task: RiskLevel.MEDIUM),
        ("agent_id", lambda task: "different-executor"),
        ("created_at", lambda task: task.created_at - timedelta(seconds=1)),
        ("updated_at", lambda task: task.updated_at + timedelta(seconds=100)),
    ],
)
def test_replay_cannot_alias_changed_task_projection(
    tmp_path: Path, field_name: str, value_factory
) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    _, transitioned, _, first = enqueue(store)
    changed = transitioned.model_copy(
        update={field_name: value_factory(transitioned)}
    )
    before = store.read_task(transitioned.tenant_id, transitioned.id)
    with pytest.raises(SnapshotConflictError):
        store.save_task_and_enqueue_status(
            changed,
            expected_revision=1,
            destination_ref=DESTINATION,
            now=changed.updated_at + timedelta(seconds=1),
        )
    assert store.read_task(transitioned.tenant_id, transitioned.id) == before
    with sqlite3.connect(store._path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM outbox_messages").fetchone()[0] == 1
    assert first.message.task_projection_digest


def test_mixed_offset_expired_lease_is_reclaimed(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    _, _, queued_at, _ = enqueue(store)
    plus_five = timezone(timedelta(hours=5))
    first = store.claim_outbox_messages(
        "tenant-a",
        lease_owner=uuid4(),
        lease_duration_seconds=1,
        now=queued_at.astimezone(plus_five),
    )[0]
    second = store.claim_outbox_messages(
        "tenant-a",
        lease_owner=uuid4(),
        lease_duration_seconds=30,
        now=queued_at + timedelta(seconds=2),
    )[0]
    assert second.message_id == first.message_id
    assert second.attempt_count == 2
    assert second.updated_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE outbox_receipts SET attempt_count = attempt_count + 1",
        "UPDATE outbox_receipts SET receipt_digest = 'sha256:' || printf('%064d', 0)",
        "UPDATE outbox_receipts SET receipt_json = '{broken'",
    ],
)
def test_receipt_tamper_is_rejected(tmp_path: Path, sql: str) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    _, _, queued_at, _ = enqueue(store)
    claimed = store.claim_outbox_messages(
        "tenant-a",
        lease_owner=(owner := uuid4()),
        lease_duration_seconds=30,
        now=queued_at,
    )[0]
    receipt = receipt_for(claimed, ReceiptType.ACK, queued_at)
    store.record_outbox_receipt(receipt, lease_owner=owner, now=queued_at)
    with sqlite3.connect(store._path) as connection:
        connection.execute(sql)
    with pytest.raises(OutboxCorruptionError):
        store.read_outbox_receipts("tenant-a", claimed.message_id)


def test_receipts_are_ordered_chronologically_across_offsets(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    _, _, queued_at, _ = enqueue(store)
    owner = uuid4()
    first = store.claim_outbox_messages(
        "tenant-a", lease_owner=owner, lease_duration_seconds=30, now=queued_at
    )[0]
    first_time = queued_at.astimezone(timezone(timedelta(hours=5)))
    store.record_outbox_receipt(
        receipt_for(first, ReceiptType.NACK, first_time),
        lease_owner=owner,
        now=queued_at,
    )
    second_time = queued_at + timedelta(seconds=2)
    second = store.claim_outbox_messages(
        "tenant-a", lease_owner=owner, lease_duration_seconds=30, now=second_time
    )[0]
    store.record_outbox_receipt(
        receipt_for(second, ReceiptType.ACK, second_time),
        lease_owner=owner,
        now=second_time,
    )
    receipts = store.read_outbox_receipts("tenant-a", first.message_id)
    assert [item.received_at for item in receipts] == sorted(
        item.received_at for item in receipts
    )
    assert all(item.received_at.utcoffset() == timedelta(0) for item in receipts)


def test_task_snapshot_cannot_be_deleted_while_outbox_exists(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    _, transitioned, _, _ = enqueue(store)
    with sqlite3.connect(store._path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "DELETE FROM task_snapshots WHERE tenant_id = ? AND task_id = ?",
                (transitioned.tenant_id, str(transitioned.id)),
            )


def test_concurrent_duplicate_enqueue_has_one_creation(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    task = persist(store)
    transitioned = task.model_copy(
        update={
            "status": TaskStatus.PARSING,
            "updated_at": task.updated_at + timedelta(seconds=1),
        }
    )

    def write_once(_: int) -> OutboxEnqueueResult:
        return store.save_task_and_enqueue_status(
            transitioned,
            expected_revision=1,
            destination_ref=DESTINATION,
            now=task.updated_at + timedelta(seconds=2),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write_once, range(2)))
    assert sorted(item.created for item in results) == [False, True]
    assert results[0].message.message_id == results[1].message.message_id

def test_outbox_contracts_reject_naive_timestamps(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    _, _, queued_at, result = enqueue(store)
    message_data = result.message.model_dump()
    message_data["created_at"] = datetime(2026, 1, 1)
    with pytest.raises(ValidationError):
        OutboxMessage.model_validate(message_data)

    claimed = store.claim_outbox_messages(
        "tenant-a",
        lease_owner=uuid4(),
        lease_duration_seconds=30,
        now=queued_at,
    )[0]
    assert claimed.lease_id is not None
    with pytest.raises(ValidationError):
        DeliveryReceipt(
            receipt_id=uuid4(),
            tenant_id=claimed.tenant_id,
            message_id=claimed.message_id,
            lease_id=claimed.lease_id,
            attempt_count=claimed.attempt_count,
            receipt_type=ReceiptType.ACK,
            received_at=datetime(2026, 1, 1),
        )


def test_gate4c_non_utc_snapshot_remains_readable(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    store = SQLiteStore(path)
    incoming, contract, task = bound_values()
    offset = timezone(timedelta(hours=5))
    legacy_task = task.model_copy(
        update={
            "created_at": task.created_at.astimezone(offset),
            "updated_at": task.updated_at.astimezone(offset),
        }
    )
    created, expected = store.claim_ingress_with_task(
        incoming, contract, legacy_task
    )
    assert created is True
    recovered = SQLiteStore(path).read_task(legacy_task.tenant_id, legacy_task.id)
    assert recovered == expected
    assert recovered is not None
    assert recovered.projection.updated_at.utcoffset() == timedelta(hours=5)