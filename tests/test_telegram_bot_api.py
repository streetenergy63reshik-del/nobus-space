"""Offline adversarial tests for the Telegram Bot API boundaries."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from src.models.task import TaskStatus
from src.storage.outbox import (
    OutboxMessage,
    OutboxStatus,
    artifact_for_message,
    message_fingerprint,
    message_id_for,
)
from src.transport.telegram.bot_api import (
    TelegramBotApi,
    TelegramBotApiError,
    TelegramBotIdentity,
    PollingLease,
    TelegramPollingBoundary,
    TelegramStatusSender,
)


TOKEN = "123456:" + "A" * 32
DESTINATION_REF = "sha256:" + "d" * 64


class Checkpoint:
    def __init__(self, offset: int | None = None) -> None:
        self.offset = offset
        self.lease: PollingLease | None = None
        self.advances: list[tuple[int | None, int]] = []

    @property
    def owned(self) -> bool:
        return self.lease is not None

    def acquire(
        self, owner_id: UUID, acquired_at: datetime
    ) -> PollingLease | None:
        if self.lease is not None:
            return None
        self.lease = PollingLease(
            lease_id=uuid4(),
            owner_id=owner_id,
            expires_at=acquired_at + timedelta(seconds=60),
        )
        return self.lease

    def load(self, lease: PollingLease) -> int | None:
        if lease != self.lease:
            raise RuntimeError("stale lease")
        return self.offset

    def advance(
        self, *, lease: PollingLease, expected: int | None, next_offset: int
    ) -> bool:
        if lease != self.lease or self.offset != expected:
            return False
        self.advances.append((expected, next_offset))
        self.offset = next_offset
        return True

    def release(self, lease: PollingLease) -> bool:
        if lease != self.lease:
            return False
        self.lease = None
        return True

def api_for(handler: Any, **options: Any) -> TelegramBotApi:
    return TelegramBotApi(
        token=TOKEN, transport=httpx.MockTransport(handler), **options
    )


def response(result: Any, **options: Any) -> httpx.Response:
    return httpx.Response(200, json={"ok": True, "result": result}, **options)


@pytest.mark.asyncio
async def test_get_me_returns_strict_bot_identity() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return response(
            {
                "id": 123,
                "is_bot": True,
                "username": "Nobusspacebot",
                "first_name": "Nobus",
            }
        )

    api = api_for(handler)
    try:
        identity = await api.get_me()
    finally:
        await api.aclose()
    assert identity == TelegramBotIdentity(123, "Nobusspacebot", "Nobus")
    assert str(calls[0].url) == f"https://api.telegram.org/bot{TOKEN}/getMe"
    assert json.loads(calls[0].content) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [
        {"id": True, "is_bot": True, "username": "bot", "first_name": "Nobus"},
        {"id": 1, "is_bot": False, "username": "bot", "first_name": "Nobus"},
        {"id": 1, "is_bot": True, "username": "", "first_name": "Nobus"},
        {"id": 1, "is_bot": True, "username": "bot", "first_name": ""},
    ],
)
async def test_get_me_rejects_malformed_identity(result: Any) -> None:
    api = api_for(lambda request: response(result))
    try:
        with pytest.raises(TelegramBotApiError) as caught:
            await api.get_me()
    finally:
        await api.aclose()
    assert caught.value.code == "telegram_protocol_error"


@pytest.mark.asyncio
async def test_answer_callback_query_can_show_ephemeral_progress() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return response(True)

    api = api_for(handler)
    try:
        await api.answer_callback_query("query-1", text="Обрабатываю…")
    finally:
        await api.aclose()

    assert str(calls[0].url) == (
        f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"
    )
    assert json.loads(calls[0].content) == {
        "callback_query_id": "query-1",
        "text": "Обрабатываю…",
    }

@pytest.mark.asyncio
async def test_delete_message_uses_exact_source_message() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return response(True)

    api = api_for(handler)
    try:
        await api.delete_message(42, 101)
    finally:
        await api.aclose()

    assert str(calls[0].url) == (
        f"https://api.telegram.org/bot{TOKEN}/deleteMessage"
    )
    assert json.loads(calls[0].content) == {
        "chat_id": 42,
        "message_id": 101,
    }


@pytest.mark.asyncio
async def test_edit_message_text_keeps_exact_progress_identity() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return response({"message_id": 101, "chat": {"id": 42}})

    api = api_for(handler)
    try:
        await api.edit_message_text(42, 101, "Выполняю…")
    finally:
        await api.aclose()

    assert str(calls[0].url) == (
        f"https://api.telegram.org/bot{TOKEN}/editMessageText"
    )
    assert json.loads(calls[0].content) == {
        "chat_id": 42,
        "message_id": 101,
        "text": "Выполняю…",
    }


@pytest.mark.asyncio
async def test_send_document_uses_bounded_multipart_and_validates_binding() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request.read()
        calls.append(request)
        return response(
            {
                "message_id": 12,
                "chat": {"id": 42},
                "document": {
                    "file_id": "telegram-file-id",
                    "file_unique_id": "telegram-unique-id",
                },
            }
        )

    api = api_for(handler)
    try:
        message_id = await api.send_document(
            42, "roadmap.html", b"<html>safe</html>"
        )
    finally:
        await api.aclose()

    assert message_id == 12
    request = calls[0]
    assert str(request.url) == f"https://api.telegram.org/bot{TOKEN}/sendDocument"
    assert request.method == "POST"
    assert request.headers["content-type"].startswith(
        "multipart/form-data; boundary="
    )
    assert b'name="chat_id"' in request.content
    assert b"\r\n\r\n42\r\n" in request.content
    assert b'filename="roadmap.html"' in request.content
    assert b"<html>safe</html>" in request.content


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "content", "code"),
    [
        ("../secret.pdf", b"safe", "telegram_configuration_invalid"),
        ("folder\\secret.pdf", b"safe", "telegram_configuration_invalid"),
        ("safe.pdf", b"", "telegram_configuration_invalid"),
    ],
)
async def test_send_document_rejects_unsafe_input_without_network(
    filename: str, content: bytes, code: str
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response({})

    api = api_for(handler)
    try:
        with pytest.raises(TelegramBotApiError) as caught:
            await api.send_document(42, filename, content)
    finally:
        await api.aclose()
    assert caught.value.code == code
    assert calls == 0


@pytest.mark.asyncio
async def test_send_document_enforces_upload_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.transport.telegram.bot_api._MAX_UPLOAD_LIMIT", 4
    )
    api = api_for(lambda request: response({}))
    try:
        with pytest.raises(TelegramBotApiError) as caught:
            await api.send_document(42, "safe.pdf", b"12345")
    finally:
        await api.aclose()
    assert caught.value.code == "telegram_upload_too_large"


@pytest.mark.asyncio
async def test_get_updates_uses_fixed_endpoint_and_bounded_payload() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return response([{"update_id": 10}, {"update_id": 11, "message": {}}])

    api = api_for(handler)
    try:
        updates = await api.get_updates(offset=10, timeout=20, limit=2)
    finally:
        await api.aclose()
    assert [item["update_id"] for item in updates] == [10, 11]
    request = calls[0]
    assert request.method == "POST"
    assert request.headers["accept-encoding"] == "identity"
    assert str(request.url) == f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    assert json.loads(request.content) == {
        "allowed_updates": ["message", "callback_query"],
        "limit": 2,
        "offset": 10,
        "timeout": 20,
    }


@pytest.mark.asyncio
async def test_peek_updates_has_no_server_side_filter_or_ack() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return response([{"update_id": 10}])

    api = api_for(handler)
    try:
        updates = await api.peek_updates(limit=7)
    finally:
        await api.aclose()
    assert updates == ({"update_id": 10},)
    assert str(calls[0].url) == f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    assert json.loads(calls[0].content) == {"limit": 7, "timeout": 0}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [
        [{"update_id": 2}, {"update_id": 2}],
        [{"update_id": True}],
        [{"update_id": -1}],
        {"update_id": 1},
    ],
)
async def test_get_updates_rejects_malformed_or_out_of_order_batches(result: Any) -> None:
    api = api_for(lambda request: response(result))
    try:
        with pytest.raises(TelegramBotApiError) as caught:
            await api.get_updates()
    finally:
        await api.aclose()
    assert caught.value.code == "telegram_protocol_error"


@pytest.mark.asyncio
async def test_duplicate_json_key_oversize_and_compression_fail_closed() -> None:
    cases = [
        (httpx.Response(200, content=b'{"ok":true,"result":[],"result":[]}'), "telegram_protocol_error"),
        (httpx.Response(200, content=b"x", headers={"content-length": "9999"}), "telegram_response_too_large"),
        (
            httpx.Response(
                200,
                stream=httpx.ByteStream(b"gzip"),
                headers={"content-encoding": "gzip"},
            ),
            "telegram_protocol_error",
        ),
    ]
    for raw, code in cases:
        api = api_for(lambda request, raw=raw: raw, response_limit=100)
        try:
            with pytest.raises(TelegramBotApiError) as caught:
                await api.get_updates()
        finally:
            await api.aclose()
        assert caught.value.code == code


@pytest.mark.asyncio
async def test_transport_and_handler_failures_have_no_exception_chain() -> None:
    def transport_failure(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"secret {TOKEN} at {request.url}", request=request)

    api = api_for(transport_failure)
    try:
        with pytest.raises(TelegramBotApiError) as caught:
            await api.get_updates()
    finally:
        await api.aclose()
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert TOKEN not in str(caught.value)

    api = api_for(lambda request: response([{"update_id": 10, "secret": TOKEN}]))

    async def bad_handler(update: dict[str, Any]) -> bool:
        raise RuntimeError(f"raw {update}")

    boundary = TelegramPollingBoundary(api, bad_handler, Checkpoint(10))
    try:
        with pytest.raises(TelegramBotApiError) as caught:
            await boundary.poll_once()
    finally:
        await api.aclose()
    assert caught.value.code == "telegram_handler_failed"
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.asyncio
async def test_redirect_is_not_followed() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(307, headers={"location": "https://example.invalid"})

    api = api_for(handler)
    try:
        with pytest.raises(TelegramBotApiError) as caught:
            await api.get_updates()
    finally:
        await api.aclose()
    assert caught.value.code == "telegram_unavailable"
    assert calls == 1


@pytest.mark.asyncio
async def test_download_checks_path_metadata_and_actual_stream_limit() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/getFile"):
            return response({"file_id": "voice", "file_path": "voice/file.oga"})
        return httpx.Response(200, content=b"123456")

    api = api_for(handler)
    try:
        with pytest.raises(TelegramBotApiError) as caught:
            await api.download_file("voice", size_limit=5)
    finally:
        await api.aclose()
    assert caught.value.code == "telegram_download_too_large"
    assert len(calls) == 2

    for unsafe in ("../secret", ".", "a/.", "/absolute"):
        unsafe_calls = 0

        def unsafe_handler(request: httpx.Request) -> httpx.Response:
            nonlocal unsafe_calls
            unsafe_calls += 1
            return response({"file_id": "voice", "file_path": unsafe})

        api = api_for(unsafe_handler)
        try:
            with pytest.raises(TelegramBotApiError):
                await api.download_file("voice", size_limit=1024)
        finally:
            await api.aclose()
        assert unsafe_calls == 1


@pytest.mark.asyncio
async def test_send_message_requires_strict_returned_chat_id() -> None:
    api = api_for(lambda request: response({"message_id": 1, "chat": {"id": True}}))
    try:
        with pytest.raises(TelegramBotApiError) as caught:
            await api.send_message(1, "status")
    finally:
        await api.aclose()
    assert caught.value.code == "telegram_protocol_error"


@pytest.mark.asyncio
async def test_polling_freezes_update_id_and_persists_before_next_update() -> None:
    api = api_for(
        lambda request: response([{"update_id": 10}, {"update_id": 11}])
    )
    checkpoint = Checkpoint(10)
    snapshots: list[list[tuple[int | None, int]]] = []

    async def handler(update: dict[str, Any]) -> bool:
        snapshots.append(list(checkpoint.advances))
        update["update_id"] = 999_999
        return True

    boundary = TelegramPollingBoundary(api, handler, checkpoint)
    try:
        result = await boundary.poll_once()
    finally:
        await api.aclose()
    assert snapshots == [[], [(10, 11)]]
    assert checkpoint.advances == [(10, 11), (11, 12)]
    assert result == result.__class__(12, 2, False)


@pytest.mark.asyncio
async def test_polling_is_single_flight_and_checkpoint_lease_is_released() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    api = api_for(lambda request: response([{"update_id": 1}]))
    checkpoint = Checkpoint(1)

    async def handler(update: dict[str, Any]) -> bool:
        entered.set()
        await release.wait()
        return True

    boundary = TelegramPollingBoundary(api, handler, checkpoint)
    first = asyncio.create_task(boundary.poll_once())
    await entered.wait()
    with pytest.raises(TelegramBotApiError) as caught:
        await boundary.poll_once()
    assert caught.value.code == "telegram_consumer_busy"
    release.set()
    await first
    assert not checkpoint.owned
    await api.aclose()


def outbox_message(status: TaskStatus = TaskStatus.COMPLETED) -> OutboxMessage:
    task_id = uuid4()
    projection_digest = "sha256:" + "a" * 64
    contract_digest = "sha256:" + "b" * 64
    result_digest = "sha256:" + "c" * 64
    user_message = "Проверенный пользовательский ответ." if status is TaskStatus.ANSWERED else None
    fingerprint = message_fingerprint(
        tenant_id="tenant-a",
        task_id=task_id,
        task_revision=2,
        task_projection_digest=projection_digest,
        contract_digest=contract_digest,
        result_revision=1,
        result_digest=result_digest,
        destination_ref=DESTINATION_REF,
        task_status=status,
        user_message=user_message,
    )
    now = datetime(2026, 7, 22, tzinfo=UTC)
    return OutboxMessage(
        message_id=message_id_for(fingerprint),
        message_fingerprint=fingerprint,
        tenant_id="tenant-a",
        task_id=task_id,
        task_revision=2,
        task_projection_digest=projection_digest,
        contract_digest=contract_digest,
        result_revision=1,
        result_digest=result_digest,
        destination_ref=DESTINATION_REF,
        template_id="task_status",
        task_status=status,
        user_message=user_message,
        status=OutboxStatus.LEASED,
        attempt_count=1,
        max_attempts=3,
        lease_id=uuid4(),
        lease_owner=uuid4(),
        lease_expires_at=datetime(2026, 7, 22, 0, 1, tzinfo=UTC),
        state_revision=2,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_release_failure_does_not_replace_cancellation() -> None:
    entered = asyncio.Event()
    api = api_for(lambda request: response([{"update_id": 1}]))

    class ReleaseFailure(Checkpoint):
        def release(self, lease: PollingLease) -> bool:
            return False

    checkpoint = ReleaseFailure(1)

    async def handler(update: dict[str, Any]) -> bool:
        entered.set()
        await asyncio.Event().wait()
        return True

    boundary = TelegramPollingBoundary(api, handler, checkpoint)
    task = asyncio.create_task(boundary.poll_once())
    await entered.wait()
    task.cancel()
    try:
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        await api.aclose()
    assert checkpoint.owned


def test_checkpoint_generation_rejects_stale_advance_and_release() -> None:
    checkpoint = Checkpoint(10)
    now = datetime.now(UTC)
    first = checkpoint.acquire(uuid4(), now)
    assert isinstance(first, PollingLease)
    assert checkpoint.release(first)
    second = checkpoint.acquire(uuid4(), now)
    assert isinstance(second, PollingLease)
    assert second.lease_id != first.lease_id
    assert not checkpoint.advance(
        lease=first, expected=10, next_offset=11
    )
    assert not checkpoint.release(first)
    assert checkpoint.load(second) == 10


@pytest.mark.asyncio
async def test_polling_rejects_expired_or_unbounded_lease() -> None:
    now = datetime(2026, 7, 22, tzinfo=UTC)

    class BadCheckpoint(Checkpoint):
        def __init__(self, seconds: int) -> None:
            super().__init__(1)
            self.seconds = seconds

        def acquire(
            self, owner_id: UUID, acquired_at: datetime
        ) -> PollingLease:
            return PollingLease(
                lease_id=uuid4(),
                owner_id=owner_id,
                expires_at=acquired_at + timedelta(seconds=self.seconds),
            )

    for seconds in (0, 301):
        api = api_for(lambda request: response([]))
        boundary = TelegramPollingBoundary(
            api,
            lambda update: asyncio.sleep(0, result=True),
            BadCheckpoint(seconds),
            clock=lambda: now,
        )
        try:
            with pytest.raises(TelegramBotApiError) as caught:
                await boundary.poll_once()
        finally:
            await api.aclose()
        assert caught.value.code == "telegram_checkpoint_failed"


@pytest.mark.asyncio
async def test_expired_lease_never_reaches_handler() -> None:
    now = datetime(2026, 7, 22, tzinfo=UTC)
    clock_values = iter((now, now + timedelta(seconds=61)))
    api = api_for(lambda request: response([{"update_id": 1}]))
    checkpoint = Checkpoint(1)
    handler_calls = 0

    async def handler(update: dict[str, Any]) -> bool:
        nonlocal handler_calls
        handler_calls += 1
        return True

    boundary = TelegramPollingBoundary(
        api, handler, checkpoint, clock=lambda: next(clock_values)
    )
    try:
        with pytest.raises(TelegramBotApiError) as caught:
            await boundary.poll_once()
    finally:
        await api.aclose()
    assert caught.value.code == "telegram_checkpoint_failed"
    assert handler_calls == 0
    assert checkpoint.offset == 1
    assert not checkpoint.owned


@pytest.mark.asyncio
async def test_polling_cancellation_releases_exact_lease() -> None:
    entered = asyncio.Event()
    api = api_for(lambda request: response([{"update_id": 1}]))
    checkpoint = Checkpoint(1)

    async def handler(update: dict[str, Any]) -> bool:
        entered.set()
        await asyncio.Event().wait()
        return True

    boundary = TelegramPollingBoundary(api, handler, checkpoint)
    task = asyncio.create_task(boundary.poll_once())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not checkpoint.owned
    await api.aclose()


@pytest.mark.asyncio
async def test_status_sender_rejects_tenant_collision_and_mismatch() -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return response({"message_id": 1, "chat": {"id": 42}})

    api = api_for(handler)
    with pytest.raises(TelegramBotApiError):
        TelegramStatusSender(api, None)  # type: ignore[arg-type]
    with pytest.raises(TelegramBotApiError):
        TelegramStatusSender(
            api,
            {
                "tenant-a": (DESTINATION_REF, 42),
                " tenant-a ": ("sha256:" + "e" * 64, 99),
            },
        )
    sender = TelegramStatusSender(api, {"tenant-a": (DESTINATION_REF, 42)})
    message = outbox_message()
    try:
        assert await sender(message)
        mismatched = message.model_copy(update={"destination_ref": "sha256:" + "e" * 64})
        assert await sender(mismatched) is False
    finally:
        await api.aclose()
    assert len(sent) == 1


@pytest.mark.parametrize(
    "options",
    [
        {"token": "bad"},
        {"request_timeout": True},
        {"request_timeout": float("inf")},
        {"request_timeout": 61},
        {"response_limit": 0},
        {"response_limit": 9 * 1024 * 1024},
    ],
)
def test_configuration_rejects_ambiguous_or_unbounded_values(options: dict[str, Any]) -> None:
    values = {
        "token": TOKEN,
        "transport": httpx.MockTransport(lambda request: response([])),
        **options,
    }
    with pytest.raises(TelegramBotApiError) as caught:
        TelegramBotApi(**values)
    assert caught.value.code == "telegram_configuration_invalid"


@pytest.mark.asyncio
async def test_product_status_sender_never_exposes_internal_identifiers() -> None:
    sent: list[dict[str, Any]] = []
    documents: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("/sendDocument"):
            request.read()
            documents.append(request.content)
            return response(
                {
                    "message_id": 2,
                    "chat": {"id": 42},
                    "document": {"file_id": "id", "file_unique_id": "unique"},
                }
            )
        sent.append(json.loads(request.content))
        return response({"message_id": 1, "chat": {"id": 42}})

    api = api_for(handler)
    sender = TelegramStatusSender(
        api,
        {"tenant-a": (DESTINATION_REF, 42)},
        technical_details=False,
    )
    completed = outbox_message()
    failed = outbox_message(TaskStatus.FAILED)
    answered = outbox_message(TaskStatus.ANSWERED)
    try:
        assert await sender(completed)
        assert await sender(failed)
        assert await sender(answered)
    finally:
        await api.aclose()

    assert len(sent) == 3
    visible = "\n".join(item["text"] for item in sent)
    assert "Изменение проверено" in visible
    assert "Не удалось выполнить задачу" in visible
    assert "Проверенный пользовательский ответ." in visible
    assert len(documents) == 1
    assert "Проверенный пользовательский ответ.".encode("utf-8") in documents[0]
    for marker in ("Task:", "Event:", "Revision:", str(failed.task_id)):
        assert marker not in visible


@pytest.mark.asyncio
async def test_product_status_sender_projects_verified_artifact_once(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if str(request.url).endswith("/sendDocument"):
            return response(
                {
                    "message_id": 2,
                    "chat": {"id": 42},
                    "document": {"file_id": "id", "file_unique_id": "unique"},
                }
            )
        return response({"message_id": 1, "chat": {"id": 42}})

    artifact_root = tmp_path / "Проекты Telegram"
    artifact_root.mkdir()
    api = api_for(handler)
    sender = TelegramStatusSender(
        api,
        {"tenant-a": (DESTINATION_REF, 42)},
        technical_details=False,
        artifact_directory=artifact_root,
    )
    message = outbox_message(TaskStatus.ANSWERED)
    artifact = artifact_for_message(message)
    assert artifact is not None
    try:
        assert await sender(message)
        assert await sender(message)
    finally:
        await api.aclose()

    target = artifact_root / artifact.filename
    assert target.read_bytes() == artifact.content_bytes()
    assert tuple(path.name for path in artifact_root.iterdir()) == (artifact.filename,)
    assert len(calls) == 4


@pytest.mark.asyncio
async def test_product_status_sender_rejects_conflicting_local_artifact(
    tmp_path: Path,
) -> None:
    calls: list[httpx.Request] = []
    artifact_root = tmp_path / "Проекты Telegram"
    artifact_root.mkdir()
    message = outbox_message(TaskStatus.ANSWERED)
    artifact = artifact_for_message(message)
    assert artifact is not None
    (artifact_root / artifact.filename).write_bytes(b"conflict")
    api = api_for(lambda request: (calls.append(request), response({}))[1])
    sender = TelegramStatusSender(
        api,
        {"tenant-a": (DESTINATION_REF, 42)},
        technical_details=False,
        artifact_directory=artifact_root,
    )
    try:
        with pytest.raises(TelegramBotApiError) as caught:
            await sender(message)
    finally:
        await api.aclose()

    assert caught.value.code == "telegram_artifact_projection_failed"
    assert calls == []
    assert (artifact_root / artifact.filename).read_bytes() == b"conflict"


def test_product_status_sender_requires_existing_artifact_directory(
    tmp_path: Path,
) -> None:
    api = api_for(lambda request: response({}))
    try:
        with pytest.raises(TelegramBotApiError) as caught:
            TelegramStatusSender(
                api,
                {"tenant-a": (DESTINATION_REF, 42)},
                artifact_directory=tmp_path / "missing",
            )
    finally:
        asyncio.run(api.aclose())

    assert caught.value.code == "telegram_configuration_invalid"


@pytest.mark.asyncio
async def test_product_status_sender_delivers_long_verified_answer_in_chunks() -> None:
    sent: list[dict[str, Any]] = []
    documents: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("/sendDocument"):
            request.read()
            documents.append(request.content)
            return response(
                {
                    "message_id": len(sent) + 1,
                    "chat": {"id": 42},
                    "document": {"file_id": "id", "file_unique_id": "unique"},
                }
            )
        sent.append(json.loads(request.content))
        return response({"message_id": len(sent), "chat": {"id": 42}})

    api = api_for(handler)
    sender = TelegramStatusSender(
        api,
        {"tenant-a": (DESTINATION_REF, 42)},
        technical_details=False,
    )
    original = outbox_message(TaskStatus.ANSWERED)
    answer = "\n".join(
        f"Раздел {index}: " + "x" * 120 for index in range(80)
    )
    fingerprint = message_fingerprint(
        tenant_id=original.tenant_id,
        task_id=original.task_id,
        task_revision=original.task_revision,
        task_projection_digest=original.task_projection_digest,
        contract_digest=original.contract_digest,
        result_revision=original.result_revision,
        result_digest=original.result_digest,
        destination_ref=original.destination_ref,
        task_status=original.task_status,
        user_message=answer,
    )
    message = original.model_copy(
        update={
            "message_fingerprint": fingerprint,
            "message_id": message_id_for(fingerprint),
            "user_message": answer,
        }
    )
    try:
        assert await sender(message)
    finally:
        await api.aclose()

    assert len(sent) > 1
    assert all(len(item["text"]) <= 3_400 for item in sent)
    assert "".join(item["text"] for item in sent).replace("\n", "") == answer.replace(
        "\n", ""
    )
    assert len(documents) == 1
    assert answer.encode("utf-8") in documents[0]


@pytest.mark.asyncio
async def test_product_status_sender_requires_strict_mode_flag() -> None:
    api = api_for(lambda request: response({"message_id": 1, "chat": {"id": 42}}))
    try:
        with pytest.raises(TelegramBotApiError):
            TelegramStatusSender(
                api,
                {"tenant-a": (DESTINATION_REF, 42)},
                technical_details=1,  # type: ignore[arg-type]
            )
    finally:
        await api.aclose()


def test_product_rejected_status_does_not_claim_owner_cancelled() -> None:
    from src.transport.telegram.bot_api import _status_text

    visible = _status_text(
        outbox_message(TaskStatus.REJECTED),
        technical_details=False,
    )

    assert "Не удалось подтвердить качество результата" in visible
    assert "Задача отменена" not in visible


@pytest.mark.parametrize(
    "status",
    tuple(TaskStatus),
)
def test_product_sender_uses_channel_neutral_status(status: TaskStatus) -> None:
    from src.application.product_status import product_task_state
    from src.transport.telegram.bot_api import _status_text

    visible = _status_text(outbox_message(status), technical_details=False)

    if status is TaskStatus.ANSWERED:
        assert visible == "Проверенный пользовательский ответ."
        assert product_task_state(status).label not in visible
    else:
        assert product_task_state(status).label in visible


@pytest.mark.asyncio
async def test_polling_accepts_long_handler_with_bounded_240_second_lease() -> None:
    now = datetime(2026, 7, 23, tzinfo=UTC)
    clock_values = iter(
        (now, now + timedelta(seconds=120), now + timedelta(seconds=121))
    )

    class LongHandlerCheckpoint(Checkpoint):
        def acquire(
            self, owner_id: UUID, acquired_at: datetime
        ) -> PollingLease | None:
            if self.lease is not None:
                return None
            self.lease = PollingLease(
                lease_id=uuid4(),
                owner_id=owner_id,
                expires_at=acquired_at + timedelta(seconds=240),
            )
            return self.lease

    api = api_for(lambda request: response([{"update_id": 1}]))
    checkpoint = LongHandlerCheckpoint()
    boundary = TelegramPollingBoundary(
        api,
        lambda update: asyncio.sleep(0, result=True),
        checkpoint,
        clock=lambda: next(clock_values),
    )
    try:
        result = await boundary.poll_once(timeout=30)
    finally:
        await api.aclose()

    assert result.next_offset == 2
    assert checkpoint.advances == [(None, 2)]


@pytest.mark.asyncio
async def test_delete_message_treats_exact_not_found_as_idempotent_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "ok": False,
                "error_code": 400,
                "description": "Bad Request: message to delete not found",
            },
        )

    api = api_for(handler)
    try:
        await api.delete_message(42, 101)
    finally:
        await api.aclose()


@pytest.mark.asyncio
async def test_send_message_binds_exact_forum_topic() -> None:
    payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        value = json.loads(request.content)
        assert isinstance(value, dict)
        payloads.append(value)
        return response({
            "message_id": 5,
            "message_thread_id": 77,
            "chat": {"id": -1001},
        })

    api = api_for(handler)
    try:
        assert await api.send_message(
            -1001,
            "Резюме темы",
            message_thread_id=77,
        ) == 5
        with pytest.raises(TelegramBotApiError):
            await api.send_message(
                -1001,
                "bad",
                message_thread_id=0,
            )
    finally:
        await api.aclose()

    for returned in (None, 76, True, 77.0):
        def mismatch_handler(_: httpx.Request) -> httpx.Response:
            result: dict[str, object] = {
                "message_id": 5,
                "chat": {"id": -1001},
            }
            if returned is not None:
                result["message_thread_id"] = returned
            return response(result)

        mismatch_api = api_for(mismatch_handler)
        try:
            with pytest.raises(
                TelegramBotApiError, match="invalid response"
            ):
                await mismatch_api.send_message(
                    -1001, "bad topic", message_thread_id=77
                )
        finally:
            await mismatch_api.aclose()

    assert payloads == [
        {
            "chat_id": -1001,
            "text": "Резюме темы",
            "message_thread_id": 77,
        }
    ]
