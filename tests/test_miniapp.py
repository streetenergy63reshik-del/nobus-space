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

from src.application.durable_product import DurableProductTelegramControlPlane
from src.application.durable_telegram_state import DurableJob, SQLiteTelegramState
from src.application.miniapp import (
    MiniAppAuthenticationError,
    MiniAppCore,
    MiniAppCoreUnavailableError,
    MiniAppTaskConflictError,
    MiniAppSessionGrant,
)
from src.application.runtime_maintenance import validate_runtime_database
from src.contracts import IngressKind, IngressSource, TaskContract, TrustedIngressEnvelope
from src.contracts.models import canonical_json_digest
from src.orchestrator.state_manager import StateManager
from src.storage import SQLiteStore
from src.transport.miniapp import create_miniapp_app
from tests.test_telegram_task_control import TENANT_ID, build_harness


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


def test_loopback_http_origin_and_health_readiness_are_bounded() -> None:
    recorder = RecordingCore()
    ready = True

    def readiness() -> None:
        if not ready:
            raise RuntimeError("private failure detail")

    app = create_miniapp_app(
        recorder,
        allowed_host="127.0.0.1",
        allowed_origin="http://127.0.0.1:8765",
        readiness=readiness,
    )

    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        live = client.get("/healthz")
        available = client.get("/readyz")
        ready = False
        unavailable = client.get("/readyz")

    assert live.status_code == available.status_code == 200
    assert live.json() == {"status": "ok"}
    assert available.json() == {"status": "ready"}
    assert unavailable.status_code == 503
    assert unavailable.json() == {"status": "unavailable"}
    assert "private" not in unavailable.text


def test_plain_http_is_rejected_outside_exact_loopback() -> None:
    with pytest.raises(ValueError, match="allowed_origin"):
        create_miniapp_app(
            RecordingCore(),
            allowed_host="miniapp.example",
            allowed_origin="http://miniapp.example",
        )


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


def _queue_codec(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()


def _miniapp_admission(
    tmp_path: Path,
) -> tuple[SQLiteStore, SQLiteTelegramState, DurableProductTelegramControlPlane]:
    harness = build_harness(tmp_path)
    queue = SQLiteTelegramState(
        tmp_path / "telegram-state.sqlite3",
        encode=_queue_codec,
        decode=json.loads,
    )
    admission = object.__new__(DurableProductTelegramControlPlane)
    admission._closing = False
    admission._telegram_state = queue
    admission._product_runtime = harness.runtime
    admission._execution_workers = ()

    async def start() -> None:
        return None

    admission.start = start  # type: ignore[method-assign]
    admission._wake = lambda: None  # type: ignore[method-assign]
    return SQLiteStore(harness.db_path), queue, admission


def test_create_task_is_session_bound_idempotent_and_uses_existing_queue(
    tmp_path: Path,
) -> None:
    store, queue, admission = _miniapp_admission(tmp_path)
    service = MiniAppCore(
        store=store,
        task_admission=admission,
        bot_token=BOT_TOKEN,
        owner_user_id=OWNER_ID,
        tenant_id=TENANT_ID,
        clock=Clock(),
    )
    token = authorize(service, signed_init_data(query_id="create"))
    request_id = "request-00000000-0000-4000-8000-000000000001"

    created = asyncio.run(
        service.create_task(token, "  Проверь локальный статус  ", request_id)
    )
    repeated = asyncio.run(
        service.create_task(token, "Проверь локальный статус", request_id)
    )

    assert repeated == created
    assert created.status == "queued"
    assert queue.queue_counts() == (0, 1)
    task = store.read_task(TENANT_ID, created.task_id)
    assert task is not None
    job = queue.claim(lease_owner=UUID("00000000-0000-4000-8000-000000000099"))
    assert job is not None
    assert job.kind == "miniapp_draft"
    assert job.task_id == created.task_id
    assert job.payload["envelope"]["tenant_id"] == TENANT_ID
    assert job.payload["envelope"]["source"] == "api"
    assert job.payload["envelope"]["actor_identity"] == "telegram:owner"
    assert job.payload["envelope"]["idempotency_key"] == request_id
    assert token not in repr(job.payload)

    class RecoveryRuntime:
        recovered: tuple[object, object] | None = None
        drafted: list[object] = []

        async def recover_prepared(self, prepared: object, envelope: object) -> bool:
            self.recovered = (prepared, envelope)
            return True

        async def draft_prepared(self, prepared: object) -> object:
            self.drafted.append(prepared)

            class Outcome:
                task_id = created.task_id

            return Outcome()

    recovery_runtime = RecoveryRuntime()
    recovery = object.__new__(DurableProductTelegramControlPlane)
    recovery._product_runtime = recovery_runtime
    restored = asyncio.run(recovery._restore(job))
    assert restored is not None
    assert restored.prepared.contract.task_id == created.task_id
    assert recovery_runtime.recovered == (restored.prepared, restored.envelope)

    delivered = 0

    async def hold_lease(_: object) -> None:
        await asyncio.Event().wait()

    async def deliver_pending() -> int:
        nonlocal delivered
        delivered += 1
        return delivered

    recovery._renew = hold_lease
    recovery.deliver_pending = deliver_pending
    asyncio.run(recovery._execute_with_lease(job, restored))
    assert recovery_runtime.drafted == [restored.prepared]
    assert delivered == 1

    tampered = DurableJob(
        job.job_id,
        job.kind,
        "foreign",
        job.task_id,
        job.binding_digest,
        job.payload,
        job.attempt_count,
        job.lease_id,
    )
    with pytest.raises(RuntimeError, match="binding mismatch"):
        asyncio.run(recovery._restore(tampered))


def test_create_task_reuses_idempotency_after_restart_and_rejects_rebinding(
    tmp_path: Path,
) -> None:
    store, queue, admission = _miniapp_admission(tmp_path)
    service = MiniAppCore(
        store=store,
        task_admission=admission,
        bot_token=BOT_TOKEN,
        owner_user_id=OWNER_ID,
        tenant_id=TENANT_ID,
        clock=Clock(),
    )
    token = authorize(service, signed_init_data(query_id="first-session"))
    request_id = "request-00000000-0000-4000-8000-000000000002"
    created = asyncio.run(service.create_task(token, "Первая задача", request_id))

    with pytest.raises(MiniAppTaskConflictError, match="^request_conflict$"):
        asyncio.run(service.create_task(token, "Подменённая задача", request_id))

    restarted = MiniAppCore(
        store=store,
        task_admission=admission,
        bot_token=BOT_TOKEN,
        owner_user_id=OWNER_ID,
        tenant_id=TENANT_ID,
        clock=Clock(),
    )
    second_token = authorize(
        restarted,
        signed_init_data(query_id="second-session"),
    )
    repeated = asyncio.run(
        restarted.create_task(second_token, "Первая задача", request_id)
    )
    assert repeated == created
    assert queue.queue_counts() == (0, 1)

    leased = queue.claim(lease_owner=UUID("00000000-0000-4000-8000-000000000098"))
    assert leased is not None and leased.task_id == created.task_id
    queue.ack(
        leased,
        lease_owner=UUID("00000000-0000-4000-8000-000000000098"),
    )
    with pytest.raises(MiniAppCoreUnavailableError, match="^core_unavailable$"):
        asyncio.run(service.create_task(token, "Первая задача", request_id))


def test_concurrent_same_request_creates_one_task_and_one_queue_job(
    tmp_path: Path,
) -> None:
    store, queue, admission = _miniapp_admission(tmp_path)
    service = MiniAppCore(
        store=store,
        task_admission=admission,
        bot_token=BOT_TOKEN,
        owner_user_id=OWNER_ID,
        tenant_id=TENANT_ID,
        clock=Clock(),
    )
    token = authorize(service, signed_init_data(query_id="concurrent-create"))
    request_id = "request-00000000-0000-4000-8000-000000000005"

    async def create_twice() -> tuple[object, object]:
        first, second = await asyncio.gather(
            service.create_task(token, "Одна задача", request_id),
            service.create_task(token, "Одна задача", request_id),
        )
        return first, second

    first, second = asyncio.run(create_twice())

    assert first == second
    assert len(store.list_tasks(TENANT_ID, limit=20)) == 1
    assert queue.queue_counts() == (0, 1)


def test_queue_failure_happens_before_task_or_outbox_persistence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, queue, admission = _miniapp_admission(tmp_path)
    service = MiniAppCore(
        store=store,
        task_admission=admission,
        bot_token=BOT_TOKEN,
        owner_user_id=OWNER_ID,
        tenant_id=TENANT_ID,
        clock=Clock(),
    )
    token = authorize(service, signed_init_data(query_id="queue-failure"))

    def fail_enqueue(**_: object) -> object:
        raise OSError("synthetic queue failure")

    monkeypatch.setattr(queue, "enqueue", fail_enqueue)
    with pytest.raises(MiniAppCoreUnavailableError, match="^core_unavailable$"):
        asyncio.run(
            service.create_task(
                token,
                "Не должна сохраниться",
                "request-00000000-0000-4000-8000-000000000006",
            )
        )

    assert store.list_tasks(TENANT_ID, limit=20) == ()
    with sqlite3.connect(tmp_path / "gate5a3.sqlite3") as connection:
        outbox_count = connection.execute(
            "SELECT count(*) FROM outbox_messages"
        ).fetchone()
    assert outbox_count == (0,)


def test_restart_recovers_core_task_from_queue_first_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class SimulatedCrash(BaseException):
        pass

    store, queue, admission = _miniapp_admission(tmp_path)
    runtime = admission._product_runtime
    original_admit = runtime.admit_prepared

    async def crash_before_core_admission(*_: object) -> bool:
        raise SimulatedCrash

    monkeypatch.setattr(runtime, "admit_prepared", crash_before_core_admission)
    service = MiniAppCore(
        store=store,
        task_admission=admission,
        bot_token=BOT_TOKEN,
        owner_user_id=OWNER_ID,
        tenant_id=TENANT_ID,
        clock=Clock(),
    )
    token = authorize(service, signed_init_data(query_id="queue-first-crash"))
    request_id = "request-00000000-0000-4000-8000-000000000007"

    with pytest.raises(SimulatedCrash):
        asyncio.run(service.create_task(token, "Восстанови задачу", request_id))
    with pytest.raises(SimulatedCrash):
        asyncio.run(service.create_task(token, "Восстанови задачу", request_id))
    assert store.list_tasks(TENANT_ID, limit=20) == ()
    assert queue.queue_counts() == (0, 1)

    with pytest.raises(MiniAppTaskConflictError, match="^request_conflict$"):
        asyncio.run(service.create_task(token, "Другая задача", request_id))
    restarted = MiniAppCore(
        store=store,
        task_admission=admission,
        bot_token=BOT_TOKEN,
        owner_user_id=OWNER_ID,
        tenant_id=TENANT_ID,
        clock=Clock(),
    )
    second_token = authorize(
        restarted,
        signed_init_data(query_id="queue-first-second-session"),
    )
    with pytest.raises(SimulatedCrash):
        asyncio.run(
            restarted.create_task(
                second_token,
                "Восстанови задачу",
                request_id,
            )
        )
    assert queue.queue_counts() == (0, 1)

    monkeypatch.setattr(runtime, "admit_prepared", original_admit)
    durable = queue.claim(
        lease_owner=UUID("00000000-0000-4000-8000-000000000097")
    )
    assert durable is not None
    restored = asyncio.run(admission._restore(durable))
    assert restored is not None
    snapshot = store.read_task(TENANT_ID, durable.task_id)
    assert snapshot is not None
    assert snapshot.projection.status.value == "pending"

    repeated = asyncio.run(
        service.create_task(token, "Восстанови задачу", request_id)
    )
    assert repeated.task_id == durable.task_id


def test_exhausted_queue_first_intent_fails_before_core_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class SimulatedCrash(BaseException):
        pass

    store, queue, admission = _miniapp_admission(tmp_path)
    runtime = admission._product_runtime
    original_admit = runtime.admit_prepared

    async def crash_before_core_admission(*_: object) -> bool:
        raise SimulatedCrash

    monkeypatch.setattr(runtime, "admit_prepared", crash_before_core_admission)
    service = MiniAppCore(
        store=store,
        task_admission=admission,
        bot_token=BOT_TOKEN,
        owner_user_id=OWNER_ID,
        tenant_id=TENANT_ID,
        clock=Clock(),
    )
    token = authorize(service, signed_init_data(query_id="queue-first-exhausted"))
    request_id = "request-00000000-0000-4000-8000-000000000008"

    with pytest.raises(SimulatedCrash):
        asyncio.run(service.create_task(token, "Не оставляй orphan", request_id))

    lease_owner = UUID("00000000-0000-4000-8000-000000000096")
    for attempt in range(1, 4):
        durable = queue.claim(lease_owner=lease_owner)
        assert durable is not None
        assert durable.attempt_count == attempt
        queue.release(durable, lease_owner=lease_owner)
    assert queue.queue_counts() == (0, 0)
    assert queue.dead_letter_count() == 1

    monkeypatch.setattr(runtime, "admit_prepared", original_admit)
    with pytest.raises(MiniAppCoreUnavailableError, match="^core_unavailable$"):
        asyncio.run(service.create_task(token, "Не оставляй orphan", request_id))

    assert store.list_tasks(TENANT_ID, limit=20) == ()
    assert queue.dead_letter_count() == 1
    with sqlite3.connect(tmp_path / "gate5a3.sqlite3") as connection:
        outbox_count = connection.execute(
            "SELECT count(*) FROM outbox_messages"
        ).fetchone()
    assert outbox_count == (0,)


def test_create_task_boundary_rejects_unknown_authority_and_reuses_request_id(
    tmp_path: Path,
) -> None:
    store, _, admission = _miniapp_admission(tmp_path)
    service = MiniAppCore(
        store=store,
        task_admission=admission,
        bot_token=BOT_TOKEN,
        owner_user_id=OWNER_ID,
        tenant_id=TENANT_ID,
        clock=Clock(),
    )
    token = authorize(service, signed_init_data(query_id="boundary-create"))
    app = create_miniapp_app(service, allowed_host="testserver", allowed_origin=ORIGIN)
    mutation_headers = {
        **headers(token),
        "Content-Type": "application/json",
        "Idempotency-Key": "request-00000000-0000-4000-8000-000000000003",
    }

    with TestClient(app) as client:
        created = client.post(
            "/api/tasks",
            json={"instruction": "Покажи состояние проекта"},
            headers=mutation_headers,
        )
        repeated = client.post(
            "/api/tasks",
            json={"instruction": "Покажи состояние проекта"},
            headers=mutation_headers,
        )
        conflict = client.post(
            "/api/tasks",
            json={"instruction": "Подменённый запрос"},
            headers=mutation_headers,
        )
        authority = client.post(
            "/api/tasks",
            json={"instruction": "Покажи состояние", "tenant_id": "foreign"},
            headers=mutation_headers,
        )
        missing_key = client.post(
            "/api/tasks",
            json={"instruction": "Покажи состояние"},
            headers={**headers(token), "Content-Type": "application/json"},
        )
        duplicate_field = client.post(
            "/api/tasks",
            content='{"instruction":"one","instruction":"two"}',
            headers=mutation_headers,
        )
        oversized = client.post(
            "/api/tasks",
            content=b"x" * 16_385,
            headers=mutation_headers,
        )

    assert created.status_code == repeated.status_code == 202
    assert created.json() == repeated.json()
    assert conflict.status_code == 409
    assert mutation_headers["Idempotency-Key"] not in conflict.text
    assert authority.status_code == missing_key.status_code == 400
    assert duplicate_field.status_code == 400
    assert oversized.status_code == 413
    assert "foreign" not in authority.text


def test_create_task_core_unavailable_does_not_mutate_state(tmp_path: Path) -> None:
    class UnavailableAdmission:
        async def submit_miniapp_task(self, instruction: str, envelope: object) -> UUID:
            raise RuntimeError("private failure")

        def miniapp_task_submitted(
            self, tenant_id: str, task_id: UUID, contract_digest: str
        ) -> bool:
            return False

    store = SQLiteStore(tmp_path / "state.sqlite3")
    service = MiniAppCore(
        store=store,
        task_admission=UnavailableAdmission(),
        bot_token=BOT_TOKEN,
        owner_user_id=OWNER_ID,
        tenant_id=TENANT_ID,
        clock=Clock(),
    )
    token = authorize(service, signed_init_data(query_id="unavailable-create"))

    with pytest.raises(MiniAppCoreUnavailableError, match="^core_unavailable$"):
        asyncio.run(
            service.create_task(
                token,
                "Не должна сохраниться",
                "request-00000000-0000-4000-8000-000000000004",
            )
        )

    assert store.list_tasks(TENANT_ID, limit=20) == ()


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
        "status_label",
        "terminal",
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
    assert "Idempotency-Key" in script.text
    assert "crypto.randomUUID()" in script.text
    assert "Задача принята. Статус временно недоступен." in script.text
    assert script.text.index("let created;") > script.text.index(
        'createTask.addEventListener("submit"'
    )
