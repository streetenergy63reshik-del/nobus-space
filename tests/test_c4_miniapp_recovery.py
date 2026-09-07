"""C4 session generations and durable unknown-request reconciliation."""

from __future__ import annotations

import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from src.application.durable_semantic import DurableSemanticClarificationStore
from src.application.miniapp import (
    MiniAppAuthenticationError, MiniAppCore, MiniAppCoreUnavailableError,
    MiniAppRequestNotAccepted, MiniAppTaskConflictError, MiniAppTaskNotFoundError,
)
from src.application.runtime_maintenance import validate_runtime_database
from src.application.semantic_admission import (
    SemanticAdmissionService, SemanticClarificationRejected, SemanticClarificationRequired,
)
from src.storage import SQLiteStore
from src.transport.miniapp import create_miniapp_app
from tests.test_miniapp import (
    BOT_TOKEN, OTHER_BOT_TOKEN, OWNER_ID, ORIGIN, Clock, _miniapp_admission,
    core, headers, signed_init_data,
)
from tests.test_semantic_admission import _Compiler, _security_proposal
from tests.test_telegram_task_control import TENANT_ID


KEY = "c4-request-0000000000000001"
COOKIE = "nobus_miniapp_recovery"


def service_for(store, admission, clock, **changes):
    return MiniAppCore(store=store, task_admission=admission, bot_token=BOT_TOKEN,
                       owner_user_id=OWNER_ID, tenant_id=TENANT_ID, clock=clock, **changes)


def test_cookie_recovery_survives_reload_rotates_and_never_extends_signature(tmp_path):
    clock = Clock()
    service = core(tmp_path, clock)
    app = create_miniapp_app(service, allowed_host="testserver", allowed_origin=ORIGIN)
    with TestClient(app, base_url=ORIGIN) as client:
        auth = client.post("/api/session", content=signed_init_data(),
                           headers={**headers(), "Content-Type": "text/plain"})
        assert auth.status_code == 200
        assert set(auth.json()) == {"access_token", "expires_in"}
        first = auth.json()["access_token"]
        cookie = client.cookies.get(COOKIE)
        for expected in ("HttpOnly", "SameSite=strict", "Secure", "Path=/api/session", "Max-Age=300"):
            assert expected in auth.headers["set-cookie"]
        assert cookie not in auth.text
        clock.advance(seconds=120)
        assert client.get("/api/tasks", headers=headers(first)).status_code == 401
        recovered = client.post("/api/session/recover", headers=headers())
        second = recovered.json()["access_token"]
        assert recovered.status_code == 200 and second != first
        assert client.cookies.get(COOKIE) != cookie
        assert client.get("/api/tasks", headers=headers(second)).status_code == 200
        assert client.get("/api/tasks", headers=headers(first)).status_code == 401
        assert client.post("/api/session/recover", headers={**headers(), "Cookie": f"{COOKIE}={cookie}"}).status_code == 401
        clock.advance(seconds=179)
        last = client.post("/api/session/recover", headers=headers())
        assert last.status_code == 200 and last.json()["expires_in"] == 1
        clock.advance(seconds=1)
        assert client.get("/api/tasks", headers=headers(last.json()["access_token"])).status_code == 401
        assert client.post("/api/session/recover", headers=headers()).status_code == 401
        assert client.post("/api/session", content=signed_init_data(),
                           headers={**headers(), "Content-Type": "text/plain"}).status_code == 401
        fresh = client.post("/api/session", content=signed_init_data(auth_date=clock.now, query_id="fresh"),
                            headers={**headers(), "Content-Type": "text/plain"})
        assert fresh.status_code == 200


@pytest.mark.parametrize("change", ["tenant", "bot", "owner"])
def test_recovery_is_bound_to_exact_owner_bot_and_tenant(tmp_path, change):
    service = core(tmp_path)
    grant = service.authenticate(signed_init_data())
    other = MiniAppCore(store=SQLiteStore(tmp_path / "state.sqlite3"),
        bot_token=OTHER_BOT_TOKEN if change == "bot" else BOT_TOKEN,
        owner_user_id=OWNER_ID + 1 if change == "owner" else OWNER_ID,
        tenant_id="foreign" if change == "tenant" else "owner", clock=Clock())
    with pytest.raises(MiniAppAuthenticationError):
        other.recover_session(grant.recovery_token)
    assert service.list_tasks(grant.access_token) == ()


def test_restart_and_concurrent_rotation_keep_one_generation(tmp_path):
    original = core(tmp_path)
    grant = original.authenticate(signed_init_data())
    first, second = core(tmp_path), core(tmp_path)

    def recover(service):
        try:
            return service.recover_session(grant.recovery_token)
        except MiniAppAuthenticationError:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(recover, (first, second)))
    assert sum(value is not None for value in results) == 1
    with pytest.raises(MiniAppAuthenticationError):
        original.list_tasks(grant.access_token)
    fresh = original.authenticate(signed_init_data(query_id="new-launch"))
    for value, service in zip(results, (first, second)):
        if value is not None:
            with pytest.raises(MiniAppAuthenticationError):
                service.list_tasks(value.access_token)
            with pytest.raises(MiniAppAuthenticationError):
                service.recover_session(value.recovery_token)
    assert original.list_tasks(fresh.access_token) == ()


def test_recovery_boundary_requires_origin_empty_body_single_cookie_and_bearer_for_tasks(tmp_path):
    service = core(tmp_path)
    grant = service.authenticate(signed_init_data())
    app = create_miniapp_app(service, allowed_host="testserver", allowed_origin=ORIGIN)
    cookie = f"{COOKIE}={grant.recovery_token}"
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.post("/api/session/recover", headers={"Cookie": cookie}).status_code == 403
        assert client.post("/api/session/recover", headers={**headers(), "Cookie": cookie}, content="x").status_code == 400
        assert client.post("/api/session/recover?token=x", headers={**headers(), "Cookie": cookie}).status_code == 400
        assert client.post("/api/session/recover", headers={**headers(), "Cookie": cookie + "; " + cookie}).status_code == 401
        assert client.get("/api/tasks", headers={"Cookie": cookie}).status_code == 401
        assert client.get("/api/tasks", headers=[("Authorization", f"Bearer {grant.access_token}"),
                                                ("Authorization", f"Bearer {grant.access_token}")]).status_code == 401
        assert client.post("/api/session/recover", headers={**headers(), "Cookie": cookie}).status_code == 200


def test_loopback_cookie_has_only_explicit_local_secure_exception(tmp_path):
    service = core(tmp_path)
    origin = "http://127.0.0.1:8899"
    with TestClient(create_miniapp_app(service, allowed_host="127.0.0.1", allowed_origin=origin), base_url=origin) as client:
        response = client.post("/api/session", content=signed_init_data(),
            headers={"Origin": origin, "Content-Type": "text/plain"})
        assert "Secure" not in response.headers["set-cookie"]
        assert "HttpOnly" in response.headers["set-cookie"]
        assert client.post("/api/session/recover", headers={"Origin": origin}).status_code == 200


def test_ack_loss_reload_and_changed_input_use_one_durable_task(tmp_path):
    store, queue, admission = _miniapp_admission(tmp_path)
    clock = Clock()
    service = service_for(store, admission, clock)
    grant = service.authenticate(signed_init_data())
    created = asyncio.run(service.create_task(grant.access_token, "Кратко объясни структуру задачи.", KEY))
    # Discard the create ACK, reopen Core and recover using only the opaque marker.
    restarted = service_for(SQLiteStore(store._path), admission, clock)
    recovered = restarted.recover_session(grant.recovery_token)
    state = restarted.request_state(recovered.access_token, KEY)
    assert state.state == "accepted" and state.task_id == created.task_id
    assert queue.queue_counts() == (0, 1)
    assert len(store.list_tasks(TENANT_ID)) == 1
    with pytest.raises(MiniAppAuthenticationError):
        service.request_state(grant.access_token, KEY)
    with pytest.raises(MiniAppTaskConflictError):
        asyncio.run(restarted.create_task(recovered.access_token, "Другая задача.", KEY))
    with pytest.raises(MiniAppTaskNotFoundError):
        restarted.request_state(recovered.access_token, "c4-request-never-issued")
    with sqlite3.connect(store._path) as connection:
        stored = connection.execute("SELECT payload FROM miniapp_requests").fetchone()[0]
    for secret in (grant.access_token, grant.recovery_token, signed_init_data(), "Кратко объясни структуру задачи."):
        assert secret.encode() not in stored
    foreign = MiniAppCore(store=store, task_admission=admission, bot_token=OTHER_BOT_TOKEN,
                         owner_user_id=OWNER_ID, tenant_id=TENANT_ID, clock=clock)
    foreign_grant = foreign.authenticate(signed_init_data(bot_token=OTHER_BOT_TOKEN, query_id="other-bot"))
    with pytest.raises(MiniAppTaskNotFoundError):
        foreign.request_state(foreign_grant.access_token, KEY)


def test_unknown_before_admission_never_replays_compiler_or_claims_not_accepted(tmp_path, monkeypatch):
    store, queue, admission = _miniapp_admission(tmp_path)
    service = service_for(store, admission, Clock())
    grant = service.authenticate(signed_init_data())
    calls = []

    async def unavailable(*args, **kwargs):
        calls.append(1)
        raise OSError("private diagnostic and local path")

    monkeypatch.setattr(admission, "submit_miniapp_task", unavailable)
    for _ in range(2):
        with pytest.raises(MiniAppCoreUnavailableError, match="^core_unavailable$"):
            asyncio.run(service.create_task(grant.access_token, "Синтетическая задача.", KEY))
    assert calls == [1]
    assert service.request_state(grant.access_token, KEY).state == "pending"
    assert queue.queue_counts() == (0, 0)
    assert store.list_tasks(TENANT_ID) == ()


def test_clarification_survives_reload_answers_same_conversation_and_rejects_old_token(tmp_path):
    store, queue, admission = _miniapp_admission(tmp_path)
    clock = Clock(datetime.now(UTC))
    compiler = _Compiler(_security_proposal(("respond",), ambiguous=True))
    admission._enable_semantic_admission = True
    admission._semantic_admission = SemanticAdmissionService(compiler)
    admission._semantic_clarifications = DurableSemanticClarificationStore(queue)
    service = service_for(store, admission, clock)
    grant = service.authenticate(signed_init_data(auth_date=clock.now))
    with pytest.raises(SemanticClarificationRequired) as question:
        asyncio.run(service.create_task(grant.access_token, "Подготовь ответ.", KEY))
    assert queue.queue_counts() == (0, 0) and store.list_tasks(TENANT_ID) == ()
    calls = len(compiler.calls)
    restarted = service_for(SQLiteStore(store._path), admission, clock)
    recovered = restarted.recover_session(grant.recovery_token)
    pending = restarted.request_state(recovered.access_token, KEY)
    assert pending.state == "clarification"
    assert pending.question == question.value.question
    assert pending.clarification_token == question.value.token
    assert len(compiler.calls) == calls
    with sqlite3.connect(store._path) as connection:
        payload = connection.execute("SELECT payload FROM miniapp_requests").fetchone()[0]
    assert question.value.token.encode() not in payload
    with pytest.raises(SemanticClarificationRejected):
        asyncio.run(restarted.create_task(recovered.access_token, "Краткий ответ.", KEY + "-wrong",
                                          clarification_token="x" * 43))
    compiler.value = _security_proposal(("respond",))
    created = asyncio.run(restarted.create_task(recovered.access_token, "Краткий ответ.", KEY + "-answer",
                                                clarification_token=question.value.token))
    assert restarted.request_state(recovered.access_token, KEY + "-answer").task_id == created.task_id
    assert queue.queue_counts() == (0, 1)
    stale = restarted.request_state(recovered.access_token, KEY)
    assert stale.state == "not_accepted" and stale.detail == "clarification_invalid"
    assert stale.clarification_token is None
    context = restarted._auth_context_ref
    stored = store.read_miniapp_request(TENANT_ID, context, KEY)
    assert stored.clarification_token is None and stored.question is None
    with pytest.raises(SemanticClarificationRejected):
        asyncio.run(restarted.create_task(recovered.access_token, "Повтор ответа.", KEY + "-replay",
                                          clarification_token=question.value.token))
    assert queue.queue_counts() == (0, 1)


def test_unavailable_is_durable_closed_outcome_without_task(tmp_path):
    store, queue, admission = _miniapp_admission(tmp_path)
    clock = Clock(datetime.now(UTC))
    compiler = _Compiler(_security_proposal(("write_calendar_event",)))
    admission._enable_semantic_admission = True
    admission._semantic_admission = SemanticAdmissionService(compiler)
    admission._semantic_clarifications = DurableSemanticClarificationStore(queue)
    service = service_for(store, admission, clock)
    grant = service.authenticate(signed_init_data(auth_date=clock.now))
    for _ in range(2):
        with pytest.raises(MiniAppRequestNotAccepted) as stopped:
            asyncio.run(service.create_task(grant.access_token, "Создай событие календаря.", KEY))
        assert stopped.value.state.reason.value == "capability_unavailable"
    assert len(compiler.calls) == 1
    state = service.request_state(grant.access_token, KEY)
    assert state.state == "not_accepted" and state.detail == "capability_unavailable"
    assert queue.queue_counts() == (0, 0) and store.list_tasks(TENANT_ID) == ()


def test_recovery_and_request_rows_fail_closed_when_corrupt(tmp_path):
    database = tmp_path / "task-runtime.sqlite3"
    service = MiniAppCore(store=SQLiteStore(database), bot_token=BOT_TOKEN,
                          owner_user_id=OWNER_ID, tenant_id="owner", clock=Clock())
    grant = service.authenticate(signed_init_data())
    validate_runtime_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE miniapp_session_recovery SET expires_at='not-a-date'")
    with pytest.raises(MiniAppCoreUnavailableError):
        service.list_tasks(grant.access_token)
    with pytest.raises(ValueError):
        validate_runtime_database(database)


def test_store_expiry_extension_or_forged_cookie_never_extends_signed_window(tmp_path):
    clock = Clock()
    service = core(tmp_path, clock)
    grant = service.authenticate(signed_init_data())
    nonce, stamp, signature = grant.recovery_token.split(".")
    with pytest.raises(MiniAppAuthenticationError):
        service.recover_session(f"{nonce}.{int(stamp) + 300}.{signature}")
    with sqlite3.connect(tmp_path / "state.sqlite3") as connection:
        connection.execute("UPDATE miniapp_session_recovery SET expires_at=?", ("2099-01-01T00:00:00+00:00",))
    with pytest.raises(MiniAppCoreUnavailableError):
        service.recover_session(grant.recovery_token)
    clock.advance(minutes=5)
    with pytest.raises(MiniAppAuthenticationError):
        service.recover_session(grant.recovery_token)


def test_journal_payload_corruption_cannot_rebind_task_or_expose_question(tmp_path):
    store, queue, admission = _miniapp_admission(tmp_path)
    service = service_for(store, admission, Clock())
    grant = service.authenticate(signed_init_data())
    asyncio.run(service.create_task(grant.access_token, "Короткая задача.", KEY))
    with sqlite3.connect(store._path) as connection:
        connection.execute("UPDATE miniapp_requests SET payload=?", (b"forged private data",))
    with pytest.raises(MiniAppCoreUnavailableError, match="^core_unavailable$"):
        service.request_state(grant.access_token, KEY)
    with pytest.raises(MiniAppCoreUnavailableError, match="^core_unavailable$"):
        asyncio.run(service.create_task(grant.access_token, "Короткая задача.", KEY))
    assert queue.queue_counts() == (0, 1)


def test_expired_clarification_has_no_token_and_cannot_be_answered(tmp_path):
    store, queue, admission = _miniapp_admission(tmp_path)
    clock = Clock(datetime.now(UTC))
    compiler = _Compiler(_security_proposal(("respond",), ambiguous=True))
    admission._enable_semantic_admission = True
    admission._semantic_admission = SemanticAdmissionService(compiler)
    admission._semantic_clarifications = DurableSemanticClarificationStore(queue)
    service = service_for(store, admission, clock)
    grant = service.authenticate(signed_init_data(auth_date=clock.now))
    with pytest.raises(SemanticClarificationRequired):
        asyncio.run(service.create_task(grant.access_token, "Подготовь ответ.", KEY))
    clock.advance(minutes=31)
    fresh = service.authenticate(signed_init_data(auth_date=clock.now, query_id="after-expiry"))
    result = service.request_state(fresh.access_token, KEY)
    assert result.state == "not_accepted" and result.detail == "clarification_invalid"
    assert result.question is None and result.clarification_token is None
    with pytest.raises(SemanticClarificationRejected):
        asyncio.run(service.create_task(fresh.access_token, "Подготовь ответ.", KEY))
    assert queue.queue_counts() == (0, 0)


def test_session_time_is_rechecked_after_lock_and_store_wait(tmp_path, monkeypatch):
    clock = Clock()
    service = core(tmp_path, clock)
    grant = service.authenticate(signed_init_data())
    original = service._lock

    class DelayedLock:
        def __enter__(self):
            clock.advance(minutes=2)
            original.acquire()

        def __exit__(self, *args):
            original.release()

    service._lock = DelayedLock()
    with pytest.raises(MiniAppAuthenticationError):
        service.list_tasks(grant.access_token)
    service._lock = original
    store = service._store
    replace = store.replace_miniapp_recovery

    def delayed_write(*args, **kwargs):
        result = replace(*args, **kwargs)
        clock.advance(minutes=6)
        return result

    monkeypatch.setattr(store, "replace_miniapp_recovery", delayed_write)
    with pytest.raises(MiniAppAuthenticationError):
        service.authenticate(signed_init_data(auth_date=clock.now, query_id="expires-during-write"))
