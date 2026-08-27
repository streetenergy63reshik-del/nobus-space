"""Security and read-only acceptance tests for the thin Telegram Mini App."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from src.application.miniapp import (
    MiniAppAuthenticationError,
    MiniAppCore,
    MiniAppCoreUnavailableError,
    MiniAppSessionGrant,
)
from src.application.runtime_maintenance import validate_runtime_database
from src.contracts import IngressKind, IngressSource, TaskContract, TrustedIngressEnvelope
from src.contracts.models import canonical_json_digest
from src.orchestrator.state_manager import StateManager
from src.storage import SQLiteStore
from src.transport.miniapp import create_miniapp_app


BOT_TOKEN = "123456:exact-test-bot-token"
OTHER_BOT_TOKEN = "654321:other-test-bot-token"
OWNER_ID = 700000001
NOW = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
ORIGIN = "https://testserver"
RECORDED_TOKEN = "o" * 32


class Clock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **values: int) -> None:
        self.now += timedelta(**values)


def signed_init_data(
    *,
    bot_token: str = BOT_TOKEN,
    owner_id: int = OWNER_ID,
    auth_date: datetime = NOW,
    query_id: str = "AAEAAAE",
) -> str:
    fields = {
        "auth_date": str(int(auth_date.timestamp())),
        "query_id": query_id,
        "user": json.dumps(
            {"id": owner_id, "first_name": "Owner"},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    check = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode([*fields.items(), ("hash", signature)])


def core(tmp_path: Path, clock: Clock | None = None) -> MiniAppCore:
    return MiniAppCore(
        store=SQLiteStore(tmp_path / "state.sqlite3"),
        bot_token=BOT_TOKEN,
        owner_user_id=OWNER_ID,
        tenant_id="owner",
        clock=clock or Clock(),
        init_data_ttl=timedelta(minutes=5),
        session_ttl=timedelta(minutes=2),
        future_skew=timedelta(seconds=30),
    )


def authorize(service: MiniAppCore, raw: str | None = None) -> str:
    return service.authenticate(raw or signed_init_data()).access_token


def persist_task(
    store: SQLiteStore,
    *,
    tenant_id: str,
    task_id: UUID,
    updated_at: datetime,
) -> None:
    ingress_values = {
        "schema_version": "1",
        "ingress_id": task_id,
        "tenant_id": tenant_id,
        "source": IngressSource.TELEGRAM,
        "actor_identity": "telegram:owner",
        "external_message_id": f"update:{task_id}",
        "idempotency_key": f"idem-{task_id}",
        "received_at": updated_at,
        "kind": IngressKind.TEXT,
        "content_ref": "sha256:" + "a" * 64,
        "auth_context_ref": "sha256:" + "b" * 64,
    }
    ingress_values["envelope_revision"] = canonical_json_digest(
        TrustedIngressEnvelope.model_construct(
            **ingress_values, envelope_revision="sha256:" + "0" * 64
        ).model_dump(mode="json", exclude={"envelope_revision"})
    )
    ingress = TrustedIngressEnvelope.model_validate(ingress_values)
    contract = TaskContract.model_validate(
        {
            "task_id": task_id,
            "idempotency_key": ingress.idempotency_key,
            "ingress_digest": ingress.envelope_revision,
            "tenant_id": tenant_id,
            "source": "telegram",
            "instruction": "private content that must not reach Mini App",
            "allowed_paths": ("workspace",),
            "permissions": ("read",),
            "risk": "low",
            "acceptance_criteria": ("Return safe metadata.",),
            "timeout_seconds": 60,
            "quality_profile": "standard",
        }
    )
    task = asyncio.run(StateManager().create_from_contract(contract)).model_copy(
        update={"created_at": updated_at, "updated_at": updated_at}
    )
    created, _ = store.claim_ingress_with_task(ingress, contract, task)
    assert created is True


def headers(token: str | None = None) -> dict[str, str]:
    result = {"Origin": ORIGIN}
    if token is not None:
        result["Authorization"] = f"Bearer {token}"
    return result


def test_core_accepts_only_exact_bot_signature_and_owner(tmp_path: Path) -> None:
    service = core(tmp_path)

    grant = service.authenticate(signed_init_data())

    assert grant.expires_in == 120
    assert service.list_tasks(grant.access_token, limit=20) == ()
    with pytest.raises(MiniAppAuthenticationError, match="^unauthorized$"):
        service.authenticate(signed_init_data(bot_token=OTHER_BOT_TOKEN))


@pytest.mark.parametrize(
    "auth_date",
    (NOW - timedelta(minutes=5, seconds=1), NOW + timedelta(seconds=31)),
)
def test_core_rejects_expired_and_future_auth_date(
    tmp_path: Path, auth_date: datetime
) -> None:
    service = core(tmp_path)

    with pytest.raises(MiniAppAuthenticationError, match="^unauthorized$"):
        service.authenticate(signed_init_data(auth_date=auth_date))


def test_core_rejects_init_data_replay(tmp_path: Path) -> None:
    service = core(tmp_path)
    raw = signed_init_data()

    service.authenticate(raw)
    restarted = core(tmp_path)

    with pytest.raises(MiniAppAuthenticationError, match="^unauthorized$"):
        restarted.authenticate(urlencode(list(reversed(parse_qsl(raw)))))


def test_core_rejects_wrong_owner(tmp_path: Path) -> None:
    service = core(tmp_path)

    with pytest.raises(MiniAppAuthenticationError, match="^unauthorized$"):
        service.authenticate(signed_init_data(owner_id=OWNER_ID + 1))


def test_session_expires_and_raw_bearer_is_not_retained(tmp_path: Path) -> None:
    clock = Clock()
    service = core(tmp_path, clock)
    raw = signed_init_data()
    token = authorize(service, raw)

    assert token not in repr(service.__dict__)
    durable_bytes = b"".join(
        path.read_bytes() for path in tmp_path.glob("state.sqlite3*") if path.is_file()
    )
    assert token.encode() not in durable_bytes
    assert raw.encode() not in durable_bytes
    clock.advance(minutes=2)

    with pytest.raises(MiniAppAuthenticationError, match="^unauthorized$"):
        service.list_tasks(token, limit=20)


def test_runtime_maintenance_validates_durable_replay_rows(tmp_path: Path) -> None:
    database = tmp_path / "task-runtime.sqlite3"
    service = MiniAppCore(
        store=SQLiteStore(database),
        bot_token=BOT_TOKEN,
        owner_user_id=OWNER_ID,
        tenant_id="owner",
        clock=Clock(),
    )
    authorize(service)
    validate_runtime_database(database)

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE miniapp_auth_replays SET replay_digest = ?",
            ("not-a-digest",),
        )
        connection.commit()

    with pytest.raises(RuntimeError, match="miniapp auth replay binding mismatch"):
        validate_runtime_database(database)


class RecordingCore:
    def __init__(self) -> None:
        self.received: list[str] = []

    def authenticate(self, raw_init_data: str) -> MiniAppSessionGrant:
        self.received.append(raw_init_data)
        return MiniAppSessionGrant(access_token=RECORDED_TOKEN, expires_in=120)

    def list_tasks(self, bearer: str, *, limit: int) -> tuple[object, ...]:
        return ()

    def task_detail(self, bearer: str, task_id: UUID) -> object:
        raise AssertionError("not called")


def test_boundary_bounds_and_forwards_raw_init_data_unchanged() -> None:
    recorder = RecordingCore()
    app = create_miniapp_app(recorder, allowed_host="testserver", allowed_origin=ORIGIN)
    raw = signed_init_data() + "&start_param=%D1%82%D0%B5%D1%81%D1%82"

    with TestClient(app) as client:
        response = client.post(
            "/api/session",
            content=raw.encode(),
            headers={**headers(), "Content-Type": "text/plain; charset=utf-8"},
        )
        oversized = client.post(
            "/api/session",
            content=b"x" * 4097,
            headers={**headers(), "Content-Type": "text/plain"},
        )

    assert response.status_code == 200
    assert response.json() == {"access_token": RECORDED_TOKEN, "expires_in": 120}
    assert recorder.received == [raw]
    assert oversized.status_code == 413


def test_browser_reads_work_without_origin_but_wrong_origin_is_rejected(
    tmp_path: Path,
) -> None:
    service = core(tmp_path)
    token = authorize(service)
    app = create_miniapp_app(service, allowed_host="testserver", allowed_origin=ORIGIN)

    with TestClient(app) as client:
        browser_read = client.get(
            "/api/tasks", headers={"Authorization": f"Bearer {token}"}
        )
        wrong_origin = client.get(
            "/api/tasks",
            headers={
                "Authorization": f"Bearer {token}",
                "Origin": "https://attacker.example",
            },
        )
        session_without_origin = client.post(
            "/api/session",
            content=signed_init_data(query_id="missing-origin"),
            headers={"Content-Type": "text/plain"},
        )

    assert browser_read.status_code == 200
    assert wrong_origin.status_code == session_without_origin.status_code == 403


def test_chunked_init_data_stops_at_limit_before_buffering_remaining_chunks() -> None:
    recorder = RecordingCore()
    app = create_miniapp_app(recorder, allowed_host="testserver", allowed_origin=ORIGIN)
    chunks = [b"x" * 4096, b"y", b"z"]
    received_chunks = 0
    sent: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        nonlocal received_chunks
        chunk = chunks[received_chunks]
        received_chunks += 1
        return {
            "type": "http.request",
            "body": chunk,
            "more_body": received_chunks < len(chunks),
        }

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    asyncio.run(
        app(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.3"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "https",
                "path": "/api/session",
                "raw_path": b"/api/session",
                "query_string": b"",
                "headers": [
                    (b"host", b"testserver"),
                    (b"origin", ORIGIN.encode()),
                    (b"content-type", b"text/plain"),
                ],
                "client": ("127.0.0.1", 12345),
                "server": ("testserver", 443),
            },
            receive,
            send,
        )
    )

    response_start = next(message for message in sent if message["type"] == "http.response.start")
    assert response_start["status"] == 413
    assert received_chunks == 2
    assert recorder.received == []


def test_init_data_body_read_has_total_timeout() -> None:
    recorder = RecordingCore()
    app = create_miniapp_app(
        recorder,
        allowed_host="testserver",
        allowed_origin=ORIGIN,
        init_data_read_timeout_seconds=0.01,
    )
    sent: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        await asyncio.sleep(0.05)
        return {"type": "http.request", "body": b"x", "more_body": True}

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    asyncio.run(
        app(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.3"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "https",
                "path": "/api/session",
                "raw_path": b"/api/session",
                "query_string": b"",
                "headers": [
                    (b"host", b"testserver"),
                    (b"origin", ORIGIN.encode()),
                    (b"content-type", b"text/plain"),
                ],
                "client": ("127.0.0.1", 12345),
                "server": ("testserver", 443),
            },
            receive,
            send,
        )
    )

    response_start = next(message for message in sent if message["type"] == "http.response.start")
    assert response_start["status"] == 408
    assert recorder.received == []


def test_bearer_is_header_only_and_never_echoed_or_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    service = core(tmp_path)
    app = create_miniapp_app(service, allowed_host="testserver", allowed_origin=ORIGIN)
    with TestClient(app) as client:
        session = client.post(
            "/api/session",
            content=signed_init_data(),
            headers={**headers(), "Content-Type": "text/plain"},
        ).json()
        token = session["access_token"]
        rejected = client.get(f"/api/tasks?access_token={token}", headers=headers())
        accepted = client.get("/api/tasks", headers=headers(token))

    assert rejected.status_code == 400
    assert accepted.status_code == 200
    assert token not in rejected.text
    assert token not in caplog.text


def test_list_is_tenant_scoped_bounded_stable_and_safe(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    owner_ids = (
        UUID("00000000-0000-0000-0000-000000000003"),
        UUID("00000000-0000-0000-0000-000000000001"),
        UUID("00000000-0000-0000-0000-000000000002"),
    )
    persist_task(store, tenant_id="owner", task_id=owner_ids[0], updated_at=NOW)
    persist_task(store, tenant_id="owner", task_id=owner_ids[1], updated_at=NOW)
    persist_task(
        store,
        tenant_id="owner",
        task_id=owner_ids[2],
        updated_at=NOW - timedelta(minutes=1),
    )
    foreign_id = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    persist_task(store, tenant_id="foreign", task_id=foreign_id, updated_at=NOW)
    service = MiniAppCore(
        store=store,
        bot_token=BOT_TOKEN,
        owner_user_id=OWNER_ID,
        tenant_id="owner",
        clock=Clock(),
    )
    token = authorize(service)

    tasks = service.list_tasks(token, limit=2)

    assert tuple(item.task_id for item in tasks) == (owner_ids[1], owner_ids[0])
    assert all(item.task_id != foreign_id for item in tasks)
    assert set(tasks[0].model_dump(mode="json")) == {
        "task_id",
        "status",
        "source",
        "risk",
        "created_at",
        "updated_at",
    }
    assert "private content" not in repr(tasks)


def test_detail_rechecks_session_tenant_and_task_binding(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    owner_task = UUID("00000000-0000-0000-0000-000000000010")
    foreign_task = UUID("00000000-0000-0000-0000-000000000011")
    persist_task(store, tenant_id="owner", task_id=owner_task, updated_at=NOW)
    persist_task(store, tenant_id="foreign", task_id=foreign_task, updated_at=NOW)
    service = MiniAppCore(
        store=store,
        bot_token=BOT_TOKEN,
        owner_user_id=OWNER_ID,
        tenant_id="owner",
        clock=Clock(),
    )
    app = create_miniapp_app(service, allowed_host="testserver", allowed_origin=ORIGIN)
    token = authorize(service, signed_init_data(query_id="detail"))

    with TestClient(app) as client:
        own = client.get(f"/api/tasks/{owner_task}", headers=headers(token))
        foreign = client.get(f"/api/tasks/{foreign_task}", headers=headers(token))
        unknown = client.get(
            "/api/tasks/00000000-0000-0000-0000-000000000012",
            headers=headers(token),
        )
        malformed = client.get("/api/tasks/not-a-uuid", headers=headers(token))

    assert own.status_code == 200
    assert own.json()["task_id"] == str(owner_task)
    assert foreign.status_code == unknown.status_code == malformed.status_code == 404
    assert foreign.json() == unknown.json() == malformed.json() == {
        "detail": "task_not_found"
    }


def test_unknown_fields_and_client_selected_authority_are_rejected(tmp_path: Path) -> None:
    service = core(tmp_path)
    token = authorize(service)
    app = create_miniapp_app(service, allowed_host="testserver", allowed_origin=ORIGIN)

    with TestClient(app) as client:
        query = client.get("/api/tasks?tenant_id=foreign", headers=headers(token))
        authority_header = client.get(
            "/api/tasks",
            headers={**headers(token), "X-Tenant-Id": "foreign"},
        )
        json_auth = client.post(
            "/api/session",
            json={"init_data": signed_init_data(), "role": "owner"},
            headers=headers(),
        )

    assert query.status_code == authority_header.status_code == 400
    assert json_auth.status_code == 415
    assert "foreign" not in query.text


def test_core_unavailable_returns_safe_ui_state_without_mutation() -> None:
    class UnavailableCore(RecordingCore):
        def authenticate(self, raw_init_data: str) -> MiniAppSessionGrant:
            raise MiniAppCoreUnavailableError("core_unavailable")

    unavailable = UnavailableCore()
    app = create_miniapp_app(
        unavailable, allowed_host="testserver", allowed_origin=ORIGIN
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/session",
            content=signed_init_data(),
            headers={**headers(), "Content-Type": "text/plain"},
        )
        page = client.get("/")
        script = client.get("/app.js")

    assert response.status_code == 503
    assert response.json() == {"detail": "Nobus Space временно недоступен"}
    assert "Nobus Space временно недоступен" in page.text
    assert "localStorage" not in script.text
    assert "initDataUnsafe" not in script.text
