"""Acceptance tests for one task-bound Mini App and Telegram artifact."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from src.application.miniapp import MiniAppCoreUnavailableError
from src.contracts.models import canonical_json_digest
from src.storage import SQLiteStore
from src.storage.outbox import message_fingerprint, message_id_for
from src.transport.miniapp import create_miniapp_app
from src.transport.telegram.bot_api import TelegramStatusSender
from tests.test_miniapp import ORIGIN, headers, signed_init_data
from tests.test_miniapp_result import _answered_store, _service
from tests.test_sqlite_store import persist
from tests.test_telegram_bot_api import DESTINATION_REF, api_for, response


def _authorized_client(path: Path):
    store, task, message = _answered_store(path)
    service = _service(store)
    token = service.authenticate(
        signed_init_data(query_id=f"artifact-{task.id}")
    ).access_token
    client = TestClient(
        create_miniapp_app(
            service,
            allowed_host="testserver",
            allowed_origin=ORIGIN,
        )
    )
    detail = service.task_detail(token, task.id)
    return store, task, message, service, token, client, detail


def test_answer_registers_one_immutable_task_bound_artifact(tmp_path: Path) -> None:
    store, task, message = _answered_store(tmp_path / "state.sqlite3")
    snapshot = store.read_task(task.tenant_id, task.id)
    assert snapshot is not None
    artifact = message.artifact
    assert artifact is not None
    content = artifact.content_bytes()

    assert content == "Проверенный ответ владельцу.".encode("utf-8")
    assert artifact.tenant_id == task.tenant_id
    assert artifact.task_id == task.id
    assert artifact.task_revision == snapshot.revision
    assert artifact.task_projection_digest == snapshot.snapshot_digest
    assert artifact.contract_digest == task.contract_digest
    assert artifact.result_revision == task.result_revision
    assert artifact.result_digest == task.result_digest
    assert artifact.size == len(content)
    assert artifact.content_digest == "sha256:" + hashlib.sha256(content).hexdigest()
    assert artifact.filename == f"nobus-result-{task.id}.txt"
    assert artifact.media_type == "text/plain; charset=utf-8"
    assert "/" not in artifact.filename and "\\" not in artifact.filename


def test_artifact_api_rechecks_task_revision_and_never_exposes_path(
    tmp_path: Path,
) -> None:
    store, task, message, service, token, client, detail = _authorized_client(
        tmp_path / "state.sqlite3"
    )
    foreign = persist(store, tenant_id="tenant-b")
    result = service.task_result(
        token, task.id, result_revision=detail.result_revision
    )
    artifact = result.artifact
    assert artifact is not None
    url = (
        f"/api/tasks/{task.id}/artifacts/{artifact.artifact_id}"
        f"?revision={result.result_revision}"
    )

    downloaded = client.get(url, headers=headers(token))

    assert downloaded.status_code == 200
    assert downloaded.content == message.artifact.content_bytes()  # type: ignore[union-attr]
    assert downloaded.headers["content-type"] == artifact.media_type
    assert downloaded.headers["content-disposition"] == (
        f'attachment; filename="{artifact.filename}"'
    )
    assert downloaded.headers["etag"] == f'"{artifact.content_digest[7:]}"'
    assert token not in str(downloaded.request.url)
    assert "C:\\" not in downloaded.text

    hidden = (
        f"/api/tasks/{task.id}/artifacts/{uuid4()}?revision={result.result_revision}",
        f"/api/tasks/{task.id}/artifacts/{artifact.artifact_id}?revision={result.result_revision + 1}",
        f"/api/tasks/{foreign.id}/artifacts/{artifact.artifact_id}?revision={result.result_revision}",
        f"/api/tasks/{uuid4()}/artifacts/{artifact.artifact_id}?revision={result.result_revision}",
    )
    for candidate in hidden:
        denied = client.get(candidate, headers=headers(token))
        assert denied.status_code == 404
        assert denied.json() == {"detail": "task_not_found"}
    assert client.get(url + "&tenant_id=tenant-b", headers=headers(token)).status_code == 400
    traversal = client.get(
        f"/api/tasks/{task.id}/artifacts/..%2F..",
        headers=headers(token),
    )
    assert traversal.status_code == 404
    assert "C:\\" not in traversal.text


def test_artifact_is_repeatable_after_restart_without_new_state(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    _, task, _, service, token, _, detail = _authorized_client(path)
    first_result = service.task_result(
        token, task.id, result_revision=detail.result_revision
    )
    assert first_result.artifact is not None
    first = service.task_artifact(
        token,
        task.id,
        first_result.artifact.artifact_id,
        result_revision=first_result.result_revision,
    )
    with sqlite3.connect(path) as connection:
        before = tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("task_snapshots", "outbox_messages", "audit_events")
        )

    restarted = _service(SQLiteStore(path))
    restarted_token = restarted.authenticate(
        signed_init_data(query_id="artifact-after-restart")
    ).access_token
    second_result = restarted.task_result(
        restarted_token, task.id, result_revision=detail.result_revision
    )
    assert second_result.artifact == first_result.artifact
    second = restarted.task_artifact(
        restarted_token,
        task.id,
        second_result.artifact.artifact_id,  # type: ignore[union-attr]
        result_revision=second_result.result_revision,
    )
    with sqlite3.connect(path) as connection:
        after = tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("task_snapshots", "outbox_messages", "audit_events")
        )
    assert first == second
    assert before == after


def test_existing_answer_without_artifact_remains_readable(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    store, task, message = _answered_store(path)
    legacy_fingerprint = message_fingerprint(
        tenant_id=message.tenant_id,
        task_id=message.task_id,
        task_revision=message.task_revision,
        task_projection_digest=message.task_projection_digest,
        contract_digest=message.contract_digest,
        result_revision=message.result_revision,
        result_digest=message.result_digest,
        destination_ref=message.destination_ref,
        task_status=message.task_status,
        user_message=message.user_message,
    )
    legacy = message.model_copy(
        update={
            "artifact": None,
            "message_fingerprint": legacy_fingerprint,
            "message_id": message_id_for(legacy_fingerprint),
        }
    )
    data = legacy.model_dump(mode="json", exclude={"artifact"})
    with sqlite3.connect(path) as connection:
        connection.execute(
            """UPDATE outbox_messages
               SET message_id = ?, message_fingerprint = ?,
                   message_digest = ?, message_json = ?
               WHERE tenant_id = ? AND message_id = ?""",
            (
                str(legacy.message_id),
                legacy.message_fingerprint,
                canonical_json_digest(data),
                json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                message.tenant_id,
                str(message.message_id),
            ),
        )
    service = _service(SQLiteStore(path))
    token = service.authenticate(
        signed_init_data(query_id="legacy-answer-after-upgrade")
    ).access_token

    detail = service.task_detail(token, task.id)
    result = service.task_result(
        token, task.id, result_revision=detail.result_revision
    )

    assert result.answer == message.user_message
    assert result.artifact is None
    assert detail.has_artifact is False


def test_artifact_content_tamper_is_safe_unavailable(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    _, task, message, service, token, _, detail = _authorized_client(path)
    assert message.artifact is not None
    with sqlite3.connect(path) as connection:
        raw = json.loads(
            connection.execute(
                "SELECT message_json FROM outbox_messages WHERE message_id = ?",
                (str(message.message_id),),
            ).fetchone()[0]
        )
        raw["artifact"]["content_base64"] = "AAAA"
        connection.execute(
            "UPDATE outbox_messages SET message_json = ? WHERE message_id = ?",
            (json.dumps(raw, separators=(",", ":")), str(message.message_id)),
        )

    with pytest.raises(MiniAppCoreUnavailableError, match="^core_unavailable$"):
        service.task_artifact(
            token,
            task.id,
            message.artifact.artifact_id,
            result_revision=detail.result_revision,
        )


def test_telegram_and_miniapp_deliver_identical_artifact_bytes(
    tmp_path: Path,
) -> None:
    store, task, message, _, token, client, detail = _authorized_client(
        tmp_path / "state.sqlite3"
    )
    result = client.get(
        f"/api/tasks/{task.id}/result?revision={detail.result_revision}",
        headers=headers(token),
    ).json()
    artifact = result["artifact"]
    download = client.get(
        f"/api/tasks/{task.id}/artifacts/{artifact['artifact_id']}"
        f"?revision={result['result_revision']}",
        headers=headers(token),
    )
    claimed = store.claim_outbox_messages(
        task.tenant_id,
        lease_owner=uuid4(),
        lease_duration_seconds=30,
        now=message.updated_at,
    )[0]
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request.read()
        calls.append(request)
        if str(request.url).endswith("/sendDocument"):
            return response(
                {
                    "message_id": 2,
                    "chat": {"id": 42},
                    "document": {"file_id": "id", "file_unique_id": "unique"},
                }
            )
        return response({"message_id": 1, "chat": {"id": 42}})

    api = api_for(handler)
    sender = TelegramStatusSender(
        api,
        {task.tenant_id: (DESTINATION_REF, 42)},
        technical_details=False,
    )
    try:
        assert asyncio.run(sender(claimed))
    finally:
        asyncio.run(api.aclose())

    document = next(call for call in calls if str(call.url).endswith("/sendDocument"))
    assert download.content == message.artifact.content_bytes()  # type: ignore[union-attr]
    assert download.content in document.content
    assert hashlib.sha256(download.content).hexdigest() == artifact["content_digest"][7:]


def test_frontend_downloads_artifact_with_memory_only_bearer() -> None:
    source = (
        Path(__file__).parents[1]
        / "src"
        / "transport"
        / "miniapp_static"
        / "app.js"
    ).read_text(encoding="utf-8")

    assert "/artifacts/" in source
    assert "URL.createObjectURL" in source
    assert "URL.revokeObjectURL" in source
    assert "Authorization" in source
    assert "localStorage" not in source
    assert "innerHTML" not in source
