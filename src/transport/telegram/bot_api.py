"""Offline-testable Telegram Bot API, polling and status boundaries."""

from __future__ import annotations

import asyncio
import json
import math
import re
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any, Protocol
from uuid import UUID, uuid4

import httpx
from pydantic import SecretStr

from src.models.task import TaskStatus
from src.storage.outbox import OutboxMessage, OutboxStatus


_API_ROOT = "https://api.telegram.org"
_TOKEN_RE = re.compile(r"^[1-9][0-9]{4,15}:[A-Za-z0-9_-]{20,128}$")
_FILE_PATH_RE = re.compile(r"^[A-Za-z0-9_./-]{1,512}$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_REQUEST_TIMEOUT = 60.0
_MAX_RESPONSE_LIMIT = 8 * 1024 * 1024
_MAX_DOWNLOAD_LIMIT = 20 * 1024 * 1024
_MAX_POLL_LEASE_SECONDS = 300
_ERROR_MESSAGES = {
    "telegram_configuration_invalid": "Telegram configuration is invalid.",
    "telegram_unavailable": "Telegram is unavailable.",
    "telegram_protocol_error": "Telegram returned an invalid response.",
    "telegram_response_too_large": "Telegram response is too large.",
    "telegram_download_too_large": "Telegram file is too large.",
    "telegram_handler_failed": "Telegram update handling failed.",
    "telegram_checkpoint_failed": "Telegram checkpoint operation failed.",
    "telegram_consumer_busy": "Telegram polling consumer is already active.",
}


class TelegramBotApiError(RuntimeError):
    """Stable public failure containing no token, URL or raw payload."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(_ERROR_MESSAGES[code])


@dataclass(frozen=True)
class TelegramBotIdentity:
    bot_id: int
    username: str
    first_name: str


@dataclass(frozen=True)
class PollingLease:
    lease_id: UUID
    owner_id: UUID
    expires_at: datetime


class PollingCheckpointStore(Protocol):
    """Synchronous durable lease/checkpoint boundary with ABA protection."""

    def acquire(
        self, owner_id: UUID, acquired_at: datetime
    ) -> PollingLease | None: ...

    def load(self, lease: PollingLease) -> int | None: ...

    def advance(
        self, *, lease: PollingLease, expected: int | None, next_offset: int
    ) -> bool: ...

    def release(self, lease: PollingLease) -> bool: ...

@dataclass(frozen=True)
class PollBatchResult:
    next_offset: int | None
    acknowledged: int
    retry_required: bool


class TelegramBotApi:
    """Bounded client owning an injected transport and no ambient authority."""

    def __init__(
        self,
        *,
        token: str,
        transport: httpx.AsyncBaseTransport,
        request_timeout: float = 60.0,
        response_limit: int = 2 * 1024 * 1024,
    ) -> None:
        if (
            not isinstance(token, str)
            or _TOKEN_RE.fullmatch(token) is None
            or not isinstance(transport, httpx.AsyncBaseTransport)
            or not _bounded_number(request_timeout, _MAX_REQUEST_TIMEOUT)
            or not _bounded_int(response_limit, _MAX_RESPONSE_LIMIT)
        ):
            raise TelegramBotApiError("telegram_configuration_invalid")
        self._token = SecretStr(token)
        self._request_timeout = float(request_timeout)
        self._response_limit = response_limit
        self._client = httpx.AsyncClient(
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=self._request_timeout,
            headers={"Accept-Encoding": "identity"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_me(self) -> TelegramBotIdentity:
        result = await self._call("getMe", {})
        if (
            type(result) is not dict
            or not _positive_int(result.get("id"))
            or result.get("is_bot") is not True
            or not _bounded_text(result.get("username"), 64)
            or not _bounded_text(result.get("first_name"), 128)
        ):
            raise TelegramBotApiError("telegram_protocol_error")
        return TelegramBotIdentity(
            bot_id=result["id"],
            username=result["username"].strip(),
            first_name=result["first_name"].strip(),
        )

    async def configure_profile(
        self,
        *,
        name: str,
        description: str,
        short_description: str,
        commands: tuple[tuple[str, str], ...],
    ) -> None:
        """Apply one validated, idempotent default-language bot profile."""
        valid_commands: list[dict[str, str]] = []
        seen: set[str] = set()
        valid = (
            _bounded_text(name, 64)
            and _bounded_text(description, 512)
            and _bounded_text(short_description, 120)
            and type(commands) is tuple
            and 1 <= len(commands) <= 100
        )
        for item in commands if type(commands) is tuple else ():
            if (
                type(item) is not tuple
                or len(item) != 2
                or not isinstance(item[0], str)
                or re.fullmatch(r"[a-z0-9_]{1,32}", item[0]) is None
                or item[0] in seen
                or not _bounded_text(item[1], 256)
            ):
                valid = False
                break
            seen.add(item[0])
            valid_commands.append(
                {"command": item[0], "description": item[1].strip()}
            )
        if not valid:
            raise TelegramBotApiError("telegram_configuration_invalid")
        operations = (
            ("setMyName", {"name": name.strip()}),
            ("setMyDescription", {"description": description.strip()}),
            (
                "setMyShortDescription",
                {"short_description": short_description.strip()},
            ),
            ("setMyCommands", {"commands": valid_commands}),
        )
        for method, payload in operations:
            if await self._call(method, payload) is not True:
                raise TelegramBotApiError("telegram_protocol_error")
    async def get_updates(
        self,
        *,
        offset: int | None = None,
        timeout: int = 30,
        limit: int = 100,
    ) -> tuple[dict[str, Any], ...]:
        if (
            (offset is not None and not _non_negative_int(offset))
            or not _non_negative_int(timeout)
            or timeout > 50
            or not _positive_int(limit)
            or limit > 100
        ):
            raise TelegramBotApiError("telegram_configuration_invalid")
        payload: dict[str, Any] = {
            "allowed_updates": ["message", "callback_query"],
            "limit": limit,
            "timeout": timeout,
        }
        if offset is not None:
            payload["offset"] = offset
        return await self._receive_updates(payload, offset=offset, limit=limit)

    async def peek_updates(self, *, limit: int = 100) -> tuple[dict[str, Any], ...]:
        """Read pending updates without changing offset or allowed_updates."""

        if not _positive_int(limit) or limit > 100:
            raise TelegramBotApiError("telegram_configuration_invalid")
        return await self._receive_updates(
            {"limit": limit, "timeout": 0}, offset=None, limit=limit
        )

    async def _receive_updates(
        self,
        payload: Mapping[str, Any],
        *,
        offset: int | None,
        limit: int,
    ) -> tuple[dict[str, Any], ...]:
        result = await self._call("getUpdates", payload)
        if type(result) is not list or len(result) > limit:
            raise TelegramBotApiError("telegram_protocol_error")
        updates: list[dict[str, Any]] = []
        previous: int | None = None
        for update in result:
            if type(update) is not dict or not _non_negative_int(update.get("update_id")):
                raise TelegramBotApiError("telegram_protocol_error")
            update_id = update["update_id"]
            if (previous is not None and update_id <= previous) or (
                offset is not None and update_id < offset
            ):
                raise TelegramBotApiError("telegram_protocol_error")
            updates.append(update)
            previous = update_id
        return tuple(updates)

    async def download_file(self, file_id: str, *, size_limit: int) -> bytes:
        if not _bounded_text(file_id, 512) or not _bounded_int(
            size_limit, _MAX_DOWNLOAD_LIMIT
        ):
            raise TelegramBotApiError("telegram_configuration_invalid")
        normalized_id = file_id.strip()
        result = await self._call("getFile", {"file_id": normalized_id})
        if type(result) is not dict:
            raise TelegramBotApiError("telegram_protocol_error")
        file_path = result.get("file_path")
        file_size = result.get("file_size")
        if (
            result.get("file_id") != normalized_id
            or not _safe_file_path(file_path)
            or (file_size is not None and not _non_negative_int(file_size))
        ):
            raise TelegramBotApiError("telegram_protocol_error")
        if file_size is not None and file_size > size_limit:
            raise TelegramBotApiError("telegram_download_too_large")
        assert isinstance(file_path, str)
        return await self._download(file_path, size_limit)

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        buttons: tuple[tuple[str, str], ...] = (),
    ) -> int:
        valid_buttons = (
            type(buttons) is tuple
            and len(buttons) <= 8
            and all(
                type(button) is tuple
                and len(button) == 2
                and _bounded_text(button[0], 64)
                and _bounded_text(button[1], 64)
                and len(button[1].encode("utf-8")) <= 64
                for button in buttons
            )
        )
        if (
            type(chat_id) is not int
            or not _bounded_text(text, 4096)
            or not valid_buttons
        ):
            raise TelegramBotApiError("telegram_configuration_invalid")
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text.strip()}
        if buttons:
            payload["reply_markup"] = {
                "inline_keyboard": [[
                    {"text": label.strip(), "callback_data": token.strip()}
                    for label, token in buttons
                ]]
            }
        result = await self._call("sendMessage", payload)
        if type(result) is not dict or not _non_negative_int(result.get("message_id")):
            raise TelegramBotApiError("telegram_protocol_error")
        chat = result.get("chat")
        if (
            type(chat) is not dict
            or type(chat.get("id")) is not int
            or chat["id"] != chat_id
        ):
            raise TelegramBotApiError("telegram_protocol_error")
        return result["message_id"]

    async def answer_callback_query(
        self, query_id: str, *, text: str | None = None
    ) -> None:
        if not _bounded_text(query_id, 256) or (
            text is not None and not _bounded_text(text, 200)
        ):
            raise TelegramBotApiError("telegram_configuration_invalid")
        payload = {"callback_query_id": query_id.strip()}
        if text is not None:
            payload["text"] = text.strip()
        result = await self._call("answerCallbackQuery", payload)
        if result is not True:
            raise TelegramBotApiError("telegram_protocol_error")

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        if type(chat_id) is not int or not _non_negative_int(message_id):
            raise TelegramBotApiError("telegram_configuration_invalid")
        result = await self._call(
            "deleteMessage",
            {"chat_id": chat_id, "message_id": message_id},
        )
        if result is not True:
            raise TelegramBotApiError("telegram_protocol_error")

    async def _call(self, method: str, payload: Mapping[str, Any]) -> Any:
        failure: str | None = None
        raw: bytes | None = None
        try:
            async with self._client.stream(
                "POST",
                self._method_url(method),
                json=dict(payload),
                timeout=self._request_timeout,
                follow_redirects=False,
            ) as response:
                if response.status_code != 200:
                    failure = "telegram_unavailable"
                else:
                    raw = await _read_response(response, self._response_limit)
        except asyncio.CancelledError:
            raise
        except TelegramBotApiError as error:
            failure = error.code
        except BaseException:
            failure = "telegram_unavailable"
        if failure is not None or raw is None:
            raise TelegramBotApiError(failure or "telegram_unavailable")

        value: Any = None
        try:
            value = json.loads(raw, object_pairs_hook=_unique_object)
        except BaseException:
            failure = "telegram_protocol_error"
        if failure is not None:
            raise TelegramBotApiError(failure)
        if type(value) is not dict or set(value) - {
            "ok",
            "result",
            "description",
            "error_code",
            "parameters",
        }:
            raise TelegramBotApiError("telegram_protocol_error")
        if value.get("ok") is not True or "result" not in value:
            raise TelegramBotApiError("telegram_unavailable")
        return value["result"]

    async def _download(self, file_path: str, size_limit: int) -> bytes:
        failure: str | None = None
        data: bytes | None = None
        try:
            async with self._client.stream(
                "GET",
                self._file_url(file_path),
                timeout=self._request_timeout,
                follow_redirects=False,
            ) as response:
                if response.status_code != 200:
                    failure = "telegram_unavailable"
                else:
                    data = await _read_response(
                        response,
                        size_limit,
                        too_large="telegram_download_too_large",
                    )
        except asyncio.CancelledError:
            raise
        except TelegramBotApiError as error:
            failure = error.code
        except BaseException:
            failure = "telegram_protocol_error"
        if failure is not None or not data:
            raise TelegramBotApiError(failure or "telegram_protocol_error")
        return data

    def _method_url(self, method: str) -> str:
        if method not in {
            "answerCallbackQuery",
            "deleteMessage",
            "getFile",
            "getMe",
            "getUpdates",
            "sendMessage",
            "setMyCommands",
            "setMyDescription",
            "setMyName",
            "setMyShortDescription",
        }:
            raise TelegramBotApiError("telegram_configuration_invalid")
        return f"{_API_ROOT}/bot{self._token.get_secret_value()}/{method}"

    def _file_url(self, file_path: str) -> str:
        if not _safe_file_path(file_path):
            raise TelegramBotApiError("telegram_protocol_error")
        return f"{_API_ROOT}/file/bot{self._token.get_secret_value()}/{file_path}"


class TelegramPollingBoundary:
    """Single-consumer polling with a durable generation-bound checkpoint."""

    def __init__(
        self,
        api: TelegramBotApi,
        handler: Callable[[dict[str, Any]], Awaitable[bool]],
        checkpoint: PollingCheckpointStore,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if (
            not isinstance(api, TelegramBotApi)
            or not callable(handler)
            or (clock is not None and not callable(clock))
            or not all(
                callable(getattr(checkpoint, name, None))
                for name in ("acquire", "load", "advance", "release")
            )
        ):
            raise TelegramBotApiError("telegram_configuration_invalid")
        self._api = api
        self._handler = handler
        self._checkpoint = checkpoint
        self._clock = clock or _utc_now
        self._owner_id = uuid4()
        self._single_flight = asyncio.Lock()

    async def poll_once(
        self, *, timeout: int = 30, limit: int = 100
    ) -> PollBatchResult:
        if self._single_flight.locked():
            raise TelegramBotApiError("telegram_consumer_busy")
        async with self._single_flight:
            acquired_at = self._now()
            lease = self._checkpoint_call(
                lambda: self._checkpoint.acquire(self._owner_id, acquired_at)
            )
            if lease is None:
                raise TelegramBotApiError("telegram_consumer_busy")
            if not isinstance(lease, PollingLease):
                raise TelegramBotApiError("telegram_checkpoint_failed")
            try:
                if not self._valid_lease(lease, acquired_at):
                    raise TelegramBotApiError("telegram_checkpoint_failed")
                current = self._checkpoint_call(
                    lambda: self._checkpoint.load(lease)
                )
                if current is not None and not _non_negative_int(current):
                    raise TelegramBotApiError("telegram_checkpoint_failed")
                updates = await self._api.get_updates(
                    offset=current, timeout=timeout, limit=limit
                )
                acknowledged = 0
                for update in updates:
                    update_id = update["update_id"]
                    remaining = self._lease_remaining(lease, self._now())
                    if remaining <= 0:
                        raise TelegramBotApiError("telegram_checkpoint_failed")
                    handler_failure: str | None = None
                    try:
                        accepted = await asyncio.wait_for(
                            self._handler(update), timeout=remaining
                        )
                    except asyncio.CancelledError:
                        raise
                    except TimeoutError:
                        handler_failure = "telegram_checkpoint_failed"
                        accepted = False
                    except BaseException:
                        handler_failure = "telegram_handler_failed"
                        accepted = False
                    if handler_failure is not None:
                        raise TelegramBotApiError(handler_failure)
                    if type(accepted) is not bool:
                        raise TelegramBotApiError("telegram_handler_failed")
                    if not accepted:
                        return PollBatchResult(current, acknowledged, True)
                    next_offset = update_id + 1
                    if not self._valid_lease(lease, self._now()):
                        raise TelegramBotApiError("telegram_checkpoint_failed")
                    advanced = self._checkpoint_call(
                        lambda: self._checkpoint.advance(
                            lease=lease,
                            expected=current,
                            next_offset=next_offset,
                        )
                    )
                    if advanced is not True:
                        raise TelegramBotApiError("telegram_checkpoint_failed")
                    current = next_offset
                    acknowledged += 1
                return PollBatchResult(current, acknowledged, False)
            finally:
                active_error = sys.exception()
                released = self._release_lease(lease)
                if not released and active_error is None:
                    raise TelegramBotApiError("telegram_checkpoint_failed")

    def _now(self) -> datetime:
        value = self._clock()
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise TelegramBotApiError("telegram_checkpoint_failed")
        return value.astimezone(UTC)

    def _valid_lease(self, lease: object, now: datetime) -> bool:
        if (
            not isinstance(lease, PollingLease)
            or lease.owner_id != self._owner_id
            or not isinstance(lease.lease_id, UUID)
            or not isinstance(lease.expires_at, datetime)
            or lease.expires_at.tzinfo is None
            or lease.expires_at.utcoffset() is None
        ):
            return False
        remaining = self._lease_remaining(lease, now)
        return 0 < remaining <= _MAX_POLL_LEASE_SECONDS

    @staticmethod
    def _lease_remaining(lease: PollingLease, now: datetime) -> float:
        return (lease.expires_at.astimezone(UTC) - now).total_seconds()

    def _release_lease(self, lease: PollingLease) -> bool:
        failed = False
        released = False
        try:
            released = self._checkpoint.release(lease)
        except Exception:
            failed = True
        return not failed and released is True

    @staticmethod
    def _checkpoint_call(operation: Callable[[], Any]) -> Any:
        failed = False
        result: Any = None
        try:
            result = operation()
        except Exception:
            failed = True
        if failed:
            raise TelegramBotApiError("telegram_checkpoint_failed")
        return result

class TelegramStatusSender:
    """Render one content-free outbox record for an exact tenant destination."""

    def __init__(
        self,
        api: TelegramBotApi,
        destinations: Mapping[str, tuple[str, int]],
        *,
        technical_details: bool = True,
    ) -> None:
        normalized: dict[str, tuple[str, int]] = {}
        valid = (
            isinstance(api, TelegramBotApi)
            and isinstance(destinations, Mapping)
            and type(technical_details) is bool
        )
        entries = destinations.items() if isinstance(destinations, Mapping) else ()
        for tenant_id, binding in entries:
            tenant = tenant_id.strip() if isinstance(tenant_id, str) else ""
            if (
                not tenant
                or tenant in normalized
                or type(binding) is not tuple
                or len(binding) != 2
                or not isinstance(binding[0], str)
                or _DIGEST_RE.fullmatch(binding[0]) is None
                or type(binding[1]) is not int
            ):
                valid = False
                break
            normalized[tenant] = binding
        if not valid or not normalized:
            raise TelegramBotApiError("telegram_configuration_invalid")
        self._api = api
        self._destinations = MappingProxyType(normalized)
        self._technical_details = technical_details

    async def __call__(self, message: OutboxMessage) -> bool:
        invalid = False
        validated: OutboxMessage | None = None
        try:
            validated = OutboxMessage.model_validate(message.model_dump(mode="json"))
        except BaseException:
            invalid = True
        if invalid or validated is None:
            return False
        binding = self._destinations.get(validated.tenant_id)
        if (
            validated.status is not OutboxStatus.LEASED
            or binding is None
            or binding[0] != validated.destination_ref
        ):
            return False
        text = _status_text(validated, technical_details=self._technical_details)
        await self._api.send_message(binding[1], text)
        return True


def _status_text(
    message: OutboxMessage, *, technical_details: bool = True
) -> str:
    if technical_details:
        return (
            f"Task: {message.task_id}\n"
            f"Status: {message.task_status.value}\n"
            f"Revision: {message.task_revision}\n"
            f"Event: {message.message_id}"
        )
    if message.task_status is TaskStatus.ANSWERED:
        assert message.user_message is not None
        return message.user_message
    if message.task_status is TaskStatus.COMPLETED:
        return (
            "✅ Изменение проверено и сохранено в рабочей ветке. "
            "Merge и push не выполнялись."
        )
    if message.task_status is TaskStatus.REJECTED:
        return (
            "⚠️ Не удалось подтвердить качество результата. Уточните задачу."
        )
    if message.task_status is TaskStatus.FAILED:
        return "⚠️ Не удалось выполнить задачу. Попробуйте ещё раз."
    if message.task_status is TaskStatus.ESCALATE:
        return "⚠️ Задача остановлена безопасно и требует проверки в Codex."
    return "Статус задачи обновлён."


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def _non_negative_int(value: object) -> bool:
    return type(value) is int and value >= 0


def _bounded_int(value: object, maximum: int) -> bool:
    return type(value) is int and 0 < value <= maximum


def _bounded_number(value: object, maximum: float) -> bool:
    return type(value) in {int, float} and math.isfinite(value) and 0 < value <= maximum


def _bounded_text(value: object, limit: int) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= limit
        and "\x00" not in value
    )


def _safe_file_path(value: object) -> bool:
    if not isinstance(value, str) or _FILE_PATH_RE.fullmatch(value) is None:
        return False
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and value not in {".", ".."}
        and bool(path.parts)
        and str(path) == value
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


async def _read_response(
    response: httpx.Response,
    limit: int,
    *,
    too_large: str = "telegram_response_too_large",
) -> bytes:
    encoding = response.headers.get("content-encoding", "identity").strip().lower()
    if encoding not in {"", "identity"}:
        raise TelegramBotApiError("telegram_protocol_error")
    content_length = response.headers.get("content-length")
    if content_length is not None:
        invalid_length = False
        try:
            declared = int(content_length)
        except ValueError:
            invalid_length = True
            declared = 0
        if invalid_length or declared < 0:
            raise TelegramBotApiError("telegram_protocol_error")
        if declared > limit:
            raise TelegramBotApiError(too_large)
    body = bytearray()
    async for chunk in response.aiter_bytes():
        if len(chunk) > limit - len(body):
            raise TelegramBotApiError(too_large)
        body.extend(chunk)
    return bytes(body)
