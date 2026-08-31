"""Acceptance tests for channel-neutral status and Mini App verified results."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from src.application.miniapp import (
    MiniAppCore,
    MiniAppCoreUnavailableError,
    MiniAppTaskNotFoundError,
)
from src.application.product_status import (
    ProductTaskStatus,
    product_task_state,
)
from src.contracts import WorkerEvent, WorkerEventType
from src.contracts.models import canonical_json_digest
from src.models.task import Task, TaskStatus
from src.storage import (
    DeliveryReceipt,
    OutboxCorruptionError,
    OutboxMessage,
    OutboxStatus,
    ReceiptType,
    SQLiteStore,
)
from src.transport.miniapp import create_miniapp_app
from tests.test_miniapp import (
    BOT_TOKEN,
    OWNER_ID,
    ORIGIN,
    Clock,
    headers,
    signed_init_data,
)
from tests.test_sqlite_store import persist, persisted_draft, verification_bundle


DESTINATION = "sha256:" + "d" * 64


def _answered_store(path: Path) -> tuple[SQLiteStore, Task, OutboxMessage]:
    store, manager, task, revision = persisted_draft(
        path,
        result={
            "output_digest": canonical_json_digest({"output": "answer"}),
            "summary": "must not be exposed",
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
        user_message="Проверенный ответ владельцу.",
    )
    return store, task, enqueued.message


def _service(store: SQLiteStore) -> MiniAppCore:
    return MiniAppCore(
        store=store,
        bot_token=BOT_TOKEN,
        owner_user_id=OWNER_ID,
        tenant_id="tenant-a",
        clock=Clock(),
    )


def test_product_status_mapper_is_exhaustive_and_channel_neutral() -> None:
    expected = {
        ProductTaskStatus.QUEUED,
        ProductTaskStatus.WORKING,
        ProductTaskStatus.WAITING,
        ProductTaskStatus.READY,
        ProductTaskStatus.ATTENTION,
        ProductTaskStatus.FAILED,
    }

    mapped = {status: product_task_state(status) for status in TaskStatus}

    assert set(mapped) == set(TaskStatus)
    assert {state.status for state in mapped.values()} == expected
    assert mapped[TaskStatus.ANSWERED].status is ProductTaskStatus.READY
    assert mapped[TaskStatus.ANSWERED].terminal is True
    assert mapped[TaskStatus.WAITING_INPUT].status is ProductTaskStatus.WAITING
    assert mapped[TaskStatus.ESCALATE].status is ProductTaskStatus.ATTENTION
    with pytest.raises(ValueError, match="product task status is invalid"):
        product_task_state("answered")  # type: ignore[arg-type]


def test_store_reads_only_exact_bound_verified_answer(tmp_path: Path) -> None:
    store, task, message = _answered_store(tmp_path / "state.sqlite3")
    snapshot = store.read_task("tenant-a", task.id)
    assert snapshot is not None

    restored = store.read_verified_answer(
        "tenant-a",
        task.id,
        task_revision=snapshot.revision,
        task_projection_digest=snapshot.snapshot_digest,
        contract_digest=snapshot.projection.contract_digest,
        result_revision=snapshot.projection.result_revision,
        result_digest=snapshot.projection.result_digest,
    )

    assert restored == message
    assert store.read_verified_answer(
        "tenant-b",
        task.id,
        task_revision=snapshot.revision,
        task_projection_digest=snapshot.snapshot_digest,
        contract_digest=snapshot.projection.contract_digest,
        result_revision=snapshot.projection.result_revision,
        result_digest=snapshot.projection.result_digest,
    ) is None
    assert store.read_verified_answer(
        "tenant-a",
        task.id,
        task_revision=snapshot.revision + 1,
        task_projection_digest=snapshot.snapshot_digest,
        contract_digest=snapshot.projection.contract_digest,
        result_revision=snapshot.projection.result_revision,
        result_digest=snapshot.projection.result_digest,
    ) is None


def test_core_result_rechecks_session_task_revision_and_safe_allowlist(
    tmp_path: Path,
) -> None:
    store, task, _ = _answered_store(tmp_path / "state.sqlite3")
    foreign = persist(store, tenant_id="tenant-b")
    service = _service(store)
    token = service.authenticate(signed_init_data()).access_token
    detail = service.task_detail(token, task.id)

    result = service.task_result(
        token,
        task.id,
        result_revision=detail.result_revision,
    )

    assert result.answer == "Проверенный ответ владельцу."
    assert result.product_status is ProductTaskStatus.READY
    assert set(result.model_dump(mode="json")) == {
        "task_id",
        "task_revision",
        "product_status",
        "result_revision",
            "result_digest",
            "answer",
            "artifact",
        }
    assert result.artifact is not None
    assert set(result.artifact.model_dump(mode="json")) == {
        "artifact_id",
        "filename",
        "media_type",
        "size",
        "content_digest",
    }
    forbidden = (
        "tenant-a",
        DESTINATION,
        "message_id",
        "lease_id",
        "summary",
        "output_digest",
        "content_base64",
        "artifact_fingerprint",
    )
    assert all(value not in result.model_dump_json() for value in forbidden)
    for task_id, revision in (
        (task.id, detail.result_revision + 1),
        (foreign.id, detail.result_revision),
        (uuid4(), detail.result_revision),
    ):
        with pytest.raises(MiniAppTaskNotFoundError, match="^task_not_found$"):
            service.task_result(token, task_id, result_revision=revision)


def test_core_answer_corruption_is_safe_unavailable(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    store, task, message = _answered_store(path)
    service = _service(store)
    token = service.authenticate(signed_init_data()).access_token
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE outbox_messages SET message_json = '{}' WHERE message_id = ?",
            (str(message.message_id),),
        )

    with pytest.raises(MiniAppCoreUnavailableError, match="^core_unavailable$"):
        service.task_result(token, task.id, result_revision=task.result_revision)


def test_verified_answer_is_repeatable_after_ack_and_restart(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    store, task, message = _answered_store(path)
    lease_owner = uuid4()
    claimed_at = message.updated_at + timedelta(seconds=1)
    claimed = store.claim_outbox_messages(
        task.tenant_id,
        lease_owner=lease_owner,
        lease_duration_seconds=30,
        now=claimed_at,
    )[0]
    assert claimed.lease_id is not None
    acked = store.record_outbox_receipt(
        DeliveryReceipt(
            receipt_id=uuid4(),
            tenant_id=task.tenant_id,
            message_id=claimed.message_id,
            lease_id=claimed.lease_id,
            attempt_count=claimed.attempt_count,
            receipt_type=ReceiptType.ACK,
            received_at=claimed_at + timedelta(seconds=1),
        ),
        lease_owner=lease_owner,
        now=claimed_at + timedelta(seconds=1),
    )
    assert acked.status is OutboxStatus.ACKED
    restarted = SQLiteStore(path)
    service = _service(restarted)
    token = service.authenticate(
        signed_init_data(query_id="answer-after-restart")
    ).access_token
    with sqlite3.connect(path) as connection:
        before = tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("task_snapshots", "outbox_messages", "audit_events")
        )

    first = service.task_result(
        token, task.id, result_revision=task.result_revision
    )
    second = service.task_result(
        token, task.id, result_revision=task.result_revision
    )

    with sqlite3.connect(path) as connection:
        after = tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("task_snapshots", "outbox_messages", "audit_events")
        )
    assert first == second
    assert first.result_digest == message.result_digest
    assert before == after


def _insert_event(path: Path, event: WorkerEvent) -> None:
    data = event.model_dump(mode="json")
    event_json = json.dumps(
        data,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            """INSERT INTO audit_events
               (tenant_id,task_id,attempt_id,sequence,event_id,contract_digest,
                worker_identity,event_digest,event_json)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                event.tenant_id,
                str(event.task_id),
                str(event.attempt_id),
                event.sequence,
                str(event.event_id),
                event.contract_digest,
                event.worker_identity,
                canonical_json_digest(data),
                event_json,
            ),
        )


def test_events_are_bounded_stable_and_drop_payload_worker_identity(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.sqlite3"
    store = SQLiteStore(path)
    task = persist(store)
    attempt_id = uuid4()
    for sequence, event_type, payload in (
        (1, WorkerEventType.STARTED, {"lease_ref": "internal-lease"}),
        (2, WorkerEventType.PROGRESS, {"stage": "private worker text"}),
        (
            3,
            WorkerEventType.RESULT_READY,
            {
                "result_ref": "internal-output-ref",
                "result_revision": 1,
                "result_digest": "sha256:" + "a" * 64,
            },
        ),
    ):
        _insert_event(
            path,
            WorkerEvent(
                event_id=uuid4(),
                tenant_id=task.tenant_id,
                task_id=task.id,
                attempt_id=attempt_id,
                contract_digest=task.contract_digest,
                worker_identity="worker:private",
                sequence=sequence,
                event_type=event_type,
                emitted_at=datetime(2026, 8, 30, 10, sequence, tzinfo=UTC),
                payload=payload,
            ),
        )
    service = _service(store)
    token = service.authenticate(signed_init_data()).access_token

    events = service.task_events(token, task.id, limit=2)

    assert [event.kind for event in events] == ["progress", "result_ready"]
    assert all(set(event.model_dump()) == {"kind", "emitted_at"} for event in events)
    serialized = "".join(event.model_dump_json() for event in events)
    assert all(
        marker not in serialized
        for marker in (
            "tenant-a",
            "worker:private",
            "private worker text",
            "internal-output-ref",
            str(attempt_id),
        )
    )


def test_result_and_events_api_are_strict_and_sanitized(tmp_path: Path) -> None:
    store, task, _ = _answered_store(tmp_path / "state.sqlite3")
    service = _service(store)
    token = service.authenticate(signed_init_data()).access_token
    app = create_miniapp_app(service, allowed_host="testserver", allowed_origin=ORIGIN)

    with TestClient(app) as client:
        detail = client.get(f"/api/tasks/{task.id}", headers=headers(token))
        revision = detail.json()["result_revision"]
        result = client.get(
            f"/api/tasks/{task.id}/result?revision={revision}",
            headers=headers(token),
        )
        events = client.get(
            f"/api/tasks/{task.id}/events?limit=20",
            headers=headers(token),
        )
        unknown = client.get(
            f"/api/tasks/{uuid4()}/result?revision={revision}",
            headers=headers(token),
        )
        extra = client.get(
            f"/api/tasks/{task.id}/result?revision={revision}&tenant_id=tenant-b",
            headers=headers(token),
        )
        body_attempts = (
            client.request(
                "GET",
                "/api/tasks?limit=20",
                content=b'{"tenant_id":"tenant-b"}',
                headers=headers(token),
            ),
            client.request(
                "GET",
                f"/api/tasks/{task.id}",
                content=b'{"tenant_id":"tenant-b"}',
                headers=headers(token),
            ),
            client.request(
                "GET",
                f"/api/tasks/{task.id}/result?revision={revision}",
                content=b'{"tenant_id":"tenant-b"}',
                headers=headers(token),
            ),
            client.request(
                "GET",
                f"/api/tasks/{task.id}/events?limit=20",
                content=b'{"tenant_id":"tenant-b"}',
                headers=headers(token),
            ),
        )

    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    assert result.json()["answer"] == "Проверенный ответ владельцу."
    assert events.status_code == 200
    assert events.json() == {"events": []}
    assert unknown.status_code == 404
    assert extra.status_code == 400
    assert "tenant-b" not in extra.text
    assert all(response.status_code == 400 for response in body_attempts)
    assert all("tenant-b" not in response.text for response in body_attempts)


def test_static_ui_polls_without_persisting_bearer_or_rendering_raw_html() -> None:
    script = Path("src/transport/miniapp_static/app.js").read_text(encoding="utf-8")

    assert "/result?revision=" in script
    assert "/events?limit=" in script
    assert "setTimeout" in script and "clearTimeout" in script
    assert "let requestGeneration = 0" in script
    assert script.count("selectionIsCurrent(taskId, generation)") >= 4
    assert "textContent" in script
    assert "innerHTML" not in script
    assert "localStorage" not in script
    assert "sessionStorage" not in script
