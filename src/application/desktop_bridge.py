"""Durable Telegram tunnel to the owner of a running Codex Desktop task."""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import os
import re
import stat
import subprocess
from contextlib import contextmanager
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from src.application.desktop_bridge_state import (
    BridgeRequest,
    BridgeRequestStatus,
    DesktopBridgeStateError,
    InteractionKind,
    PendingDesktopInteraction,
    SQLiteDesktopBridgeState,
)
from src.application.desktop_artifact_refs import extract_artifact_references
from src.application.desktop_interaction_view import render_interaction
from src.application.desktop_output import format_final_blocks
from src.contracts import TrustedIngressEnvelope
from src.contracts.models import canonical_json_digest
from src.integrations.codex_desktop_ipc import (
    CodexDesktopIpcClient,
    DesktopConversationProjection,
    DesktopIpcError,
    DesktopIpcTimeoutError,
    DesktopIpcUnknownOutcome,
    DesktopIpcUnavailableError,
    DesktopPendingRequest,
    DesktopTurnState,
    OwnerBinding,
    project_desktop_conversation,
)
from src.integrations.codex_desktop_uia import (
    CodexDesktopUiAutomation,
    DesktopUiAutomationError,
)
from src.transport.telegram.models import TextMessage, VoiceMessage


_COMMAND = re.compile(r"^/codex(?:@(?P<username>[A-Za-z0-9_]+))?(?:\s+|$)", re.IGNORECASE)
_MENTION = re.compile(r"^@(?P<username>[A-Za-z0-9_]+)(?:\s+|$)", re.IGNORECASE)
_NAME_ADDRESS = re.compile(r"^(?:Нобус(?:\s+Спейс)?|Nobus(?:\s+Space)?)\s*[,!:]\s*", re.IGNORECASE)
_NATURAL_CREATE = re.compile(
    r"^(?:создай|создать|начни|заведи)\s+(?:новую\s+)?задачу"
    r"(?:\s+в\s+проекте\s+(?P<project>[^:\r\n]+))?\s*[:\r\n]\s*"
    r"(?P<instruction>.+)$", re.IGNORECASE | re.DOTALL,
)
_PARTICIPANT_BIND_MARKER = re.compile(
    r"^@Nobusspacebot #NOBUS-BIND-PARTICIPANT:[A-Za-z0-9_-]{12,80}$",
    re.IGNORECASE,
)
_WINDOWS_PATH = re.compile(
    r"(?<![A-Za-z0-9_])(?P<path>[A-Za-z]:\\[^\r\n<>\"|?*]+)"
)
_REQUEST_MARKER_PREFIX = "NOBUS-BRIDGE-REQUEST:"
_NOTIFIER_MARKER = re.compile(
    r"(?:\r?\n)?<!--\s*nobus-notify:complete\|[^\r\n]*-->\s*\Z"
)
_TEXT_PART_BYTES = 3_600
_ARTIFACT_PART_BYTES = 45 * 1024 * 1024
_MAX_ARTIFACT_BYTES = 400 * 1024 * 1024
_ARTIFACT_SLOT_WIDTH = (_MAX_ARTIFACT_BYTES + _ARTIFACT_PART_BYTES - 1) // _ARTIFACT_PART_BYTES
_SENSITIVE_ARTIFACT_NAME = re.compile(
    r"(?i)(?:^|[._-])(?:\.env|credentials?|secrets?|private[-_]?key|"
    r"id_(?:rsa|dsa|ecdsa|ed25519)|cookies?)(?:$|[._-])|"
    r"\.(?:pem|pfx|p12|key|kdbx)$"
)
_SENSITIVE_OUTPUT = re.compile(
    r"(?i)(?:-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----|"
    r"\b(?:authorization\s*:\s*)?bearer\s+[A-Za-z0-9._~+/-]{8,}|"
    r"\b(?:password|passwd|api[_ -]?key|client[_ -]?secret|"
    r"access[_ -]?token|refresh[_ -]?token|cookie|telegram[_ -]?bot[_ -]?token)"
    r"\s*[:=]\s*\S{4,}|"
    r"\b(?:sk|ghp|gho|xox[baprs])[-_][A-Za-z0-9_-]{8,}\b|"
    r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b)"
)
_INTERACTION_TTL = timedelta(hours=12)
# requestUserInput is not a proof that Desktop asks for a mere clarification:
# Apps and agents can phrase a permission as a question. Ambiguous consent or
# side-effect prompts go to the owner for manual handling in Desktop.
_OWNER_REVIEW_QUESTION = re.compile(
    r"\b(?:разреш(?:аете|ите|аю|ение)|одобр(?:яете|ите|ение)|"
    r"подтвержда(?:ете|ете ли)|соглас(?:ны|ие)|дать\s+доступ|"
    r"предоставить\s+прав[ао]|можно\s+(?:ли\s+)?(?:мне\s+)?"
    r"(?:удал|измен|запис|установ|публи|отправ|запуст|выполн|оплат)|"
    r"могу\s+ли\s+(?:я\s+)?(?:удал|измен|запис|установ|публи|отправ|запуст|выполн|оплат)|"
    r"(?:approve|permission|consent|grant|allow|can\s+i))",
    re.IGNORECASE,
)
_BOT_REQUEST_WINDOW = timedelta(minutes=10)
_BOT_REQUEST_LIMIT = 4
_RUNNING_STATUSES = frozenset(
    {
        BridgeRequestStatus.DISPATCHING,
        BridgeRequestStatus.RUNNING,
        BridgeRequestStatus.WAITING_AUTHOR,
        BridgeRequestStatus.WAITING_OWNER,
        BridgeRequestStatus.EXECUTION_COMPLETED,
        BridgeRequestStatus.DELIVERING,
        BridgeRequestStatus.WAITING_PC,
    }
)
_RECOVERABLE_STATUSES = _RUNNING_STATUSES | frozenset({BridgeRequestStatus.RECEIVED})


class DesktopBridgeApi(Protocol):
    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        buttons: tuple[tuple[str, str], ...] = (),
        message_thread_id: int | None = None,
        reply_to_message_id: int | None = None,
        parse_mode: str | None = None,
    ) -> int: ...

    async def download_file(self, file_id: str, *, size_limit: int) -> bytes: ...

    async def send_document(
        self,
        chat_id: int,
        filename: str,
        content: bytes,
        *,
        message_thread_id: int | None = None,
        reply_to_message_id: int | None = None,
    ) -> int: ...


class DesktopVoicePreview(Protocol):
    async def preview_from_bytes(self, audio: bytes) -> Any: ...


class DesktopDocumentDelivery(Protocol):
    async def deliver(
        self,
        *,
        api: object,
        request_id: UUID,
        operation_id: str,
        tenant_id: str,
        chat_id: int,
        topic_id: int | None,
        filename: str,
        content: bytes,
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class DesktopProject:
    name: str
    cwd: Path


@dataclass(frozen=True, slots=True)
class ParsedDesktopCommand:
    operation: str
    project_name: str | None
    thread_id: str | None
    instruction: str
    task_title: str | None = None


class DesktopBridgeService:
    """One in-process bridge; Telegram polling and sending stay with MVP1."""

    def __init__(
        self,
        *,
        api: DesktopBridgeApi,
        state: SQLiteDesktopBridgeState,
        uia: CodexDesktopUiAutomation,
        projects: Mapping[str, Path],
        owner_user_id: int,
        owner_private_chat_id: int,
        bot_username: str,
        voice_service: DesktopVoicePreview | None = None,
        document_delivery: DesktopDocumentDelivery | None = None,
        artifact_roots: tuple[Path, ...] = (),
        ipc_factory: Callable[[], CodexDesktopIpcClient] = CodexDesktopIpcClient,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        max_concurrency: int = 4,
    ) -> None:
        normalized_projects: dict[str, DesktopProject] = {}
        project_paths: set[Path] = set()
        for name, cwd in projects.items():
            clean_name = _bounded_text(name, 256)
            path = Path(cwd).resolve()
            if (
                clean_name.casefold() in normalized_projects
                or path in project_paths
                or not path.is_dir()
            ):
                raise ValueError("desktop bridge project configuration is invalid")
            normalized_projects[clean_name.casefold()] = DesktopProject(clean_name, path)
            project_paths.add(path)
        username = _bounded_text(bot_username.removeprefix("@"), 64)
        if (
            not normalized_projects
            or type(owner_user_id) is not int
            or owner_user_id <= 0
            or type(owner_private_chat_id) is not int
            or owner_private_chat_id <= 0
            or type(max_concurrency) is not int
            or not 1 <= max_concurrency <= 8
        ):
            raise ValueError("desktop bridge configuration is invalid")
        self._api = api
        self._state = state
        self._uia = uia
        self._projects = normalized_projects
        self._owner_user_id = owner_user_id
        self._owner_private_chat_id = owner_private_chat_id
        self._bot_username = username.casefold()
        self._voice_service = voice_service
        self._document_delivery = document_delivery
        self._artifact_roots = tuple(Path(root).resolve() for root in artifact_roots)
        if any(not root.is_dir() for root in self._artifact_roots):
            raise ValueError("desktop artifact root is invalid")
        self._ipc_factory = ipc_factory
        self._clock = clock
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._ui_bootstrap_lock = asyncio.Lock()
        self._ui_bootstrap_lock_path = state._path.with_name("desktop-bootstrap.lock")
        self._tasks: dict[UUID, asyncio.Task[None]] = {}
        self._expiry_task: asyncio.Task[None] | None = None
        self._worker_error: BaseException | None = None
        self._closed = False

    async def start(self) -> None:
        if self._closed:
            raise RuntimeError("desktop bridge is closed")
        if self._worker_error is not None:
            raise RuntimeError("desktop bridge worker stopped") from self._worker_error
        await self._expire_interactions()
        for request in self._state.list_requests(statuses=_RECOVERABLE_STATUSES):
            self._schedule(request.request_id)
        if self._expiry_task is None:
            self._expiry_task = asyncio.create_task(
                self._expiry_watchdog(), name="desktop-bridge-expiry"
            )

    async def close(self) -> None:
        self._closed = True
        expiry_task = self._expiry_task
        self._expiry_task = None
        if expiry_task is not None:
            expiry_task.cancel()
        tasks = tuple(self._tasks.values())
        for task in tasks:
            task.cancel()
        awaiting = tasks + (() if expiry_task is None else (expiry_task,))
        if awaiting:
            await asyncio.gather(*awaiting, return_exceptions=True)
        self._tasks.clear()

    def assert_healthy(self) -> None:
        if self._closed:
            raise RuntimeError("desktop bridge is closed")
        if self._worker_error is not None:
            raise RuntimeError("desktop bridge worker stopped") from self._worker_error
        if (
            self._expiry_task is not None
            and self._expiry_task.done()
            and not self._expiry_task.cancelled()
            and self._expiry_task.exception() is not None
        ):
            raise RuntimeError("desktop bridge expiry worker stopped")
        failed = [
            task
            for task in self._tasks.values()
            if task.done()
            and not task.cancelled()
            and task.exception() is not None
        ]
        if failed:
            raise RuntimeError("desktop bridge worker stopped")

    async def handle(
        self,
        message: TextMessage | VoiceMessage,
        envelope: TrustedIngressEnvelope,
    ) -> bool:
        """Consume only explicit bridge commands or replies to bridge prompts."""
        await self._expire_interactions()
        if message.reply_to_message_id is not None and isinstance(message, TextMessage):
            interaction = self._state.pending_interaction_for_reply(
                chat_id=message.chat_id,
                telegram_message_id=message.reply_to_message_id,
            )
            if interaction is not None:
                await self._answer_interaction(message, interaction, envelope)
                return True
        if message.binding_purpose != "business_notes":
            return False
        if isinstance(message, VoiceMessage):
            return await self._handle_voice(message, envelope)
        parsed = self._parse_command(message)
        if parsed is None:
            return False
        if parsed.operation == "help":
            await self._api.send_message(
                message.chat_id,
                "Codex Desktop:\n"
                "/codex new <проект> — затем с новой строки задача;\n"
                "/codex continue <thread-id> — затем с новой строки продолжение;\n"
                "/codex continue <thread-id> | <проект> | <точный заголовок> — "
                "если прежняя задача выгружена из Desktop;\n"
                "/codex <текст> — уточнить создание или продолжение перед запуском.",
                message_thread_id=message.message_thread_id,
                reply_to_message_id=message.message_id,
            )
            return True
        if parsed.operation == "redeliver":
            await self._redeliver_known_partial(message, parsed.thread_id)
            return True
        if parsed.operation == "route":
            await self._request_route(message, envelope, parsed)
            return True
        await self._admit(message, envelope, parsed)
        return True

    def _parse_command(self, message: TextMessage) -> ParsedDesktopCommand | None:
        text = message.text.strip()
        if _PARTICIPANT_BIND_MARKER.fullmatch(text) is not None:
            return None
        command = _COMMAND.match(text)
        addressed = command is not None
        if command is not None:
            if command.group("username") is not None and command.group("username").casefold() != self._bot_username:
                return None
            body = text[command.end() :].strip()
        else:
            mention = _MENTION.match(text)
            if mention is not None:
                if mention.group("username").casefold() != self._bot_username:
                    return None
                addressed = True
                body = text[mention.end() :].strip()
            else:
                address = _NAME_ADDRESS.match(text)
                if address is not None:
                    addressed = True
                    body = text[address.end() :].strip()
                elif message.reply_to_message_id is not None and self._topic_predecessor(message) is not None:
                    body = text
                else:
                    return None
        if not body or body.casefold() in {"help", "помощь"}:
            return ParsedDesktopCommand("help", None, None, "")
        natural_create = _NATURAL_CREATE.match(body)
        if natural_create is not None:
            return ParsedDesktopCommand(
                "create", (natural_create.group("project") or "").strip() or None,
                None, natural_create.group("instruction").strip(),
            )
        if re.match(r"^(?:создай|создать|начни|заведи)\s+(?:новую\s+)?задачу\b", body, re.I):
            return ParsedDesktopCommand("create", None, None, body)
        first, separator, remainder = body.partition("\n")
        fields = first.split(maxsplit=2)
        verb = fields[0].casefold()
        if verb in {"new", "новая"}:
            tail = first[len(fields[0]):].strip()
            project = next(
                (
                    item for item in sorted(self._projects.values(), key=lambda p: len(p.name), reverse=True)
                    if tail.casefold() == item.name.casefold()
                    or tail.casefold().startswith(item.name.casefold() + " ")
                ),
                None,
            )
            if project is None:
                if separator and tail:
                    return ParsedDesktopCommand("create", tail, None, remainder.strip())
                if len(fields) < 2:
                    return ParsedDesktopCommand("help", None, None, "")
                return ParsedDesktopCommand(
                    "create", fields[1], None,
                    fields[2].strip() if len(fields) == 3 else "",
                )
            inline = tail[len(project.name):].strip()
            instruction = (inline + ("\n" + remainder if separator else "")).strip()
            return ParsedDesktopCommand("create", project.name, None, instruction)
        if verb in {"continue", "продолжить"}:
            if len(fields) < 2:
                return ParsedDesktopCommand("help", None, None, "")
            if " | " in first:
                parts = [part.strip() for part in first[len(fields[0]):].split(" | ", 2)]
                if len(parts) == 3 and all(parts) and separator:
                    return ParsedDesktopCommand(
                        "continue", parts[1], parts[0], remainder.strip(), parts[2]
                    )
                return ParsedDesktopCommand("help", None, None, "")
            instruction = ((fields[2] if len(fields) == 3 else "") + ("\n" + remainder if separator else "")).strip()
            return ParsedDesktopCommand("continue", None, fields[1], instruction)
        if verb in {"redeliver", "доставить"}:
            return ParsedDesktopCommand(
                "redeliver", None, fields[1] if len(fields) >= 2 else None, ""
            )
        return ParsedDesktopCommand(
            "topic" if message.reply_to_message_id is not None and not addressed else "route",
            None, None, body,
        )

    async def _request_route(
        self, message: TextMessage, envelope: TrustedIngressEnvelope,
        parsed: ParsedDesktopCommand,
    ) -> None:
        """Persist ambiguous natural language before choosing a Desktop effect."""
        if message.is_forwarded or not parsed.instruction or len(parsed.instruction) > 12_000:
            await self._reply(message, "Не удалось безопасно определить поручение Desktop.")
            return
        if (
            message.is_bot
            and self._state.recent_author_request_count(
                author_user_id=message.user_id,
                since=self._now() - _BOT_REQUEST_WINDOW,
            ) >= _BOT_REQUEST_LIMIT
        ):
            await self._reply(message, "Лимит агента: не более четырёх новых запросов за 10 минут.")
            return
        previous = self._topic_predecessor(message)
        try:
            request = self._state.create_request(
                request_id=_request_uuid(envelope.idempotency_key),
                ingress_key=envelope.idempotency_key, tenant_id=message.tenant_id,
                author_user_id=message.user_id, author_identity=message.actor_identity,
                chat_id=message.chat_id, topic_id=message.message_thread_id,
                source_message_id=message.message_id, operation="create",
                project_name=None,
                payload={
                    "instruction": parsed.instruction,
                    "route_thread_id": previous.desktop_thread_id if previous else None,
                },
            )
        except DesktopBridgeStateError as error:
            if str(error) != "desktop_bridge_queue_full":
                raise
            await self._reply(message, "Очередь задач Codex Desktop заполнена. Повторите запрос позже.")
            return
        if not self._state.transition(
            request.request_id, expected=frozenset({BridgeRequestStatus.RECEIVED}),
            status=BridgeRequestStatus.NEEDS_TARGET,
        ):
            return
        await self._publish_route_card(message, request)

    async def _publish_route_card(
        self, message: TextMessage, request: BridgeRequest,
    ) -> None:
        interaction = self._state.put_interaction(
            interaction_id=_interaction_id(request.request_id, "route"),
            request_id=request.request_id, kind=InteractionKind.QUESTION,
            desktop_request_id="route", desktop_turn_id="route",
            target_user_id=message.user_id, generation=1,
            payload={"method": "bridge/route"},
            expires_at=self._now() + _INTERACTION_TTL,
        )
        if not self._state.claim_interaction_delivery(interaction.interaction_id):
            return
        try:
            card_id = await self._api.send_message(
                message.chat_id,
                f'<a href="tg://user?id={message.user_id}">Автор запроса</a>, '
                "уточните действие с этим поручением: ответьте «создать» для новой "
                "задачи или «продолжить» для задачи, связанной с темой. "
                "Для другой задачи ответьте «продолжить <ID>». "
                "До ответа Codex Desktop не запускается.",
                message_thread_id=message.message_thread_id,
                reply_to_message_id=message.message_id, parse_mode="HTML",
            )
        except Exception:
            return  # Lost Telegram ACK: do not duplicate the card.
        self._state.finish_interaction_delivery(
            interaction.interaction_id, telegram_chat_id=message.chat_id,
            telegram_message_id=card_id,
        )

    async def _redeliver_known_partial(
        self, message: TextMessage, request_ref: str | None
    ) -> None:
        try:
            request_id = UUID(_bounded_text(request_ref, 64))
        except (ValueError, TypeError):
            await self._reply(message, "Укажите точный ID запроса для восстановления доставки.")
            return
        request = self._state.read_request(request_id)
        if (
            request is None
            or request.chat_id != message.chat_id
            or request.topic_id != message.message_thread_id
            or message.user_id not in {request.author_user_id, self._owner_user_id}
            or message.is_forwarded
        ):
            await self._reply(message, "Запрос для восстановления в этой теме не найден.")
            return
        if request.status is not BridgeRequestStatus.DELIVERY_PARTIAL:
            await self._reply(
                message,
                "Автоматическая повторная доставка возможна только для известных недоставленных частей; неизвестный исход требует сверки квитанции.",
            )
            return
        if request.desktop_thread_id is None or request.desktop_turn_id is None:
            await self._reply(message, "Нет подтверждённого завершённого turn для повторной доставки.")
            return
        self._schedule(request.request_id)
        await self._reply(message, "Проверяю только недоставленные части прежнего ответа; новый turn не создаётся.")

    def _topic_predecessor(
        self, message: TextMessage | VoiceMessage
    ) -> BridgeRequest | None:
        if message.reply_to_message_id is not None:
            return self._state.request_for_reply(
                chat_id=message.chat_id, topic_id=message.message_thread_id,
                telegram_message_id=message.reply_to_message_id,
            )
        if self._state.topic_thread_count(
            chat_id=message.chat_id, topic_id=message.message_thread_id
        ) != 1:
            return None
        return self._state.latest_topic_request(
            chat_id=message.chat_id, topic_id=message.message_thread_id
        )

    async def _admit(
        self,
        message: TextMessage,
        envelope: TrustedIngressEnvelope,
        parsed: ParsedDesktopCommand,
    ) -> None:
        if message.is_forwarded:
            await self._reply(
                message,
                "Пересланное или анонимное сообщение не создаёт задачу Codex Desktop.",
            )
            return
        if not parsed.instruction or len(parsed.instruction) > 12_000:
            await self._reply(message, "Задача пуста или превышает 12 000 символов.")
            return
        if (
            message.is_bot
            and self._state.recent_author_request_count(
                author_user_id=message.user_id,
                since=self._now() - _BOT_REQUEST_WINDOW,
            )
            >= _BOT_REQUEST_LIMIT
        ):
            await self._reply(
                message,
                "Лимит агента: не более четырёх новых запросов за 10 минут.",
            )
            return
        operation = parsed.operation
        project_name = parsed.project_name
        thread_id = parsed.thread_id
        if operation == "create":
            project = self._projects.get((project_name or "").casefold())
            if project is None:
                await self._request_project_target(message, envelope, parsed)
                return
            project_name = project.name
        elif operation == "topic":
            previous = self._topic_predecessor(message)
            if previous is None or previous.desktop_thread_id is None:
                await self._reply(
                    message,
                    "Задача для продолжения не определена. Ответьте на исходное поручение или итог, либо укажите /codex continue <ID>.",
                )
                return
            operation = "continue"
            thread_id = previous.desktop_thread_id
            project_name = previous.project_name
        elif operation == "continue":
            try:
                thread_id = _parse_thread_ref(thread_id)
            except (ValueError, TypeError):
                await self._reply(message, "Некорректный идентификатор задачи Desktop.")
                return
            if parsed.task_title is not None:
                project = self._projects.get((project_name or "").casefold())
                if project is None or not 0 < len(parsed.task_title.strip()) <= 256:
                    await self._reply(message, "Укажите точный существующий проект и заголовок задачи Desktop.")
                    return
                project_name = project.name
        request_id = _request_uuid(envelope.idempotency_key)
        try:
            request = self._state.create_request(
                request_id=request_id,
                ingress_key=envelope.idempotency_key,
                tenant_id=message.tenant_id,
                author_user_id=message.user_id,
                author_identity=message.actor_identity,
                chat_id=message.chat_id,
                topic_id=message.message_thread_id,
                source_message_id=message.message_id,
                operation=operation,
                project_name=project_name,
                payload={
                    "instruction": parsed.instruction,
                    "requested_thread_id": thread_id,
                    "requested_task_title": parsed.task_title,
                },
            )
        except DesktopBridgeStateError as error:
            if str(error) != "desktop_bridge_queue_full":
                raise
            await self._reply(
                message,
                "Очередь задач Codex Desktop заполнена. Завершите ожидающие задачи и повторите запрос.",
            )
            return
        if operation == "continue" and request.desktop_thread_id is None:
            assert thread_id is not None
            request = self._state.bind_desktop(
                request.request_id,
                thread_id=thread_id,
                turn_id=None,
                client_message_id=f"nobus:{request.request_id}",
                status=BridgeRequestStatus.RECEIVED,
            )
        if request.status is BridgeRequestStatus.RECEIVED:
            await self._reply(
                message,
                f"Задача принята и передаётся в Codex Desktop. ID запроса: {request.request_id}",
            )
            self._schedule(request.request_id)

    async def _request_project_target(
        self, message: TextMessage, envelope: TrustedIngressEnvelope,
        parsed: ParsedDesktopCommand,
    ) -> None:
        request_id = _request_uuid(envelope.idempotency_key)
        request = self._state.create_request(
            request_id=request_id, ingress_key=envelope.idempotency_key,
            tenant_id=message.tenant_id, author_user_id=message.user_id,
            author_identity=message.actor_identity, chat_id=message.chat_id,
            topic_id=message.message_thread_id, source_message_id=message.message_id,
            operation="create", project_name=None,
            payload={"instruction": parsed.instruction,
                     "requested_project": parsed.project_name},
        )
        if not self._state.transition(
            request.request_id, expected=frozenset({BridgeRequestStatus.RECEIVED}),
            status=BridgeRequestStatus.NEEDS_TARGET,
        ):
            return
        await self._publish_project_target(message, request)

    async def _publish_project_target(
        self, message: TextMessage, request: BridgeRequest,
    ) -> None:
        projects = tuple(project.name for project in self._projects.values())
        interaction = self._state.put_interaction(
            interaction_id=_interaction_id(request.request_id, "target"),
            request_id=request.request_id, kind=InteractionKind.QUESTION,
            desktop_request_id="target", desktop_turn_id="target",
            target_user_id=message.user_id, generation=1,
            payload={"method": "bridge/target", "projects": projects},
            expires_at=self._now() + _INTERACTION_TTL,
        )
        if not self._state.claim_interaction_delivery(interaction.interaction_id):
            return
        mention = f'<a href="tg://user?id={message.user_id}">Автор запроса</a>'
        requested_project = request.payload.get("requested_project")
        requested = f" (запрошено: {html.escape(str(requested_project))})" if requested_project else ""
        try:
            card_id = await self._api.send_message(
                message.chat_id,
                f"{mention}, выберите существующий проект{requested}. "
                "Ответьте на эту карточку точным названием:\n"
                + "\n".join(html.escape(name) for name in projects),
                message_thread_id=message.message_thread_id,
                reply_to_message_id=message.message_id, parse_mode="HTML",
            )
        except Exception:
            return  # Unknown Telegram ACK: never send a second card automatically.
        self._state.finish_interaction_delivery(
            interaction.interaction_id,
            telegram_chat_id=message.chat_id, telegram_message_id=card_id,
        )

    async def _handle_voice(
        self, message: VoiceMessage, envelope: TrustedIngressEnvelope
    ) -> bool:
        if message.is_forwarded:
            await self._reply(
                message,
                "Пересланное или анонимное сообщение не создаёт задачу Codex Desktop.",
            )
            return True
        previous = self._topic_predecessor(message)
        if self._voice_service is None:
            if message.reply_to_message_id is None and previous is None:
                return False
            await self._reply(message, "Голосовой ввод для Desktop сейчас недоступен.")
            return True
        try:
            audio = await self._api.download_file(message.file_id, size_limit=10 * 1024 * 1024)
            preview = await self._voice_service.preview_from_bytes(audio)
            transcript = _bounded_text(getattr(preview, "transcript", None), 12_000)
        except Exception:
            await self._reply(message, "Не удалось распознать голосовую задачу.")
            return True
        parsed = self._parse_voice_command(message, transcript)
        operation = parsed.operation
        project_name = parsed.project_name
        thread_id = parsed.thread_id
        instruction = parsed.instruction
        if operation == "create":
            project = self._projects.get((project_name or "").casefold())
            if project is None:
                project_name = None
            else:
                project_name = project.name
        elif operation == "route":
            operation = "create"  # The pending route is inert until confirmed.
            project_name = None
            thread_id = None
        elif operation == "continue":
            try:
                thread_id = _parse_thread_ref(thread_id)
            except (ValueError, TypeError):
                await self._reply(
                    message,
                    "Некорректный идентификатор задачи Desktop.",
                )
                return True
        else:
            if previous is None or previous.desktop_thread_id is None:
                if message.reply_to_message_id is None:
                    return False
                await self._reply(
                    message,
                    "В этой теме ещё нет связанной задачи. "
                    "Надиктуйте: «новая <проект> <задача>».",
                )
                return True
            operation = "continue"
            thread_id = previous.desktop_thread_id
            project_name = previous.project_name
            instruction = transcript
        if not instruction or len(instruction) > 12_000:
            await self._reply(message, "Задача пуста или превышает 12 000 символов.")
            return True
        if (
            message.is_bot
            and self._state.recent_author_request_count(
                author_user_id=message.user_id,
                since=self._now() - _BOT_REQUEST_WINDOW,
            )
            >= _BOT_REQUEST_LIMIT
        ):
            await self._reply(
                message,
                "Лимит агента: не более четырёх новых запросов за 10 минут.",
            )
            return True
        request_id = _request_uuid(envelope.idempotency_key)
        try:
            request = self._state.create_request(
                request_id=request_id,
                ingress_key=envelope.idempotency_key,
                tenant_id=message.tenant_id,
                author_user_id=message.user_id,
                author_identity=message.actor_identity,
                chat_id=message.chat_id,
                topic_id=message.message_thread_id,
                source_message_id=message.message_id,
                operation=operation,
                project_name=project_name,
                payload={
                    "instruction": instruction,
                    "requested_thread_id": thread_id,
                    "requested_project": parsed.project_name,
                    "route_required": parsed.operation == "route",
                    "route_thread_id": previous.desktop_thread_id if previous else None,
                    "voice": True,
                },
            )
        except DesktopBridgeStateError as error:
            if str(error) != "desktop_bridge_queue_full":
                raise
            await self._reply(
                message,
                "Очередь задач Codex Desktop заполнена. Завершите ожидающие задачи и повторите запрос.",
            )
            return True
        if operation == "continue":
            assert thread_id is not None
            request = self._state.bind_desktop(
                request.request_id,
                thread_id=thread_id,
                turn_id=None,
                client_message_id=f"nobus:{request.request_id}",
                status=BridgeRequestStatus.RECEIVED,
            )
        if not self._state.transition(
            request.request_id,
            expected=frozenset({BridgeRequestStatus.RECEIVED}),
            status=BridgeRequestStatus.NEEDS_VOICE_CONFIRMATION,
        ):
            return True
        interaction_id = _interaction_id(request.request_id, "voice")
        interaction = self._state.put_interaction(
            interaction_id=interaction_id, request_id=request.request_id,
            kind=InteractionKind.VOICE_CONFIRMATION, desktop_request_id="voice",
            desktop_turn_id="voice", target_user_id=message.user_id, generation=1,
            payload={"transcript": transcript}, expires_at=self._now() + _INTERACTION_TTL,
        )
        if not self._state.claim_interaction_delivery(interaction.interaction_id):
            return True
        try:
            sent = await self._api.send_message(
                message.chat_id,
                f"Распознано:\n\n{transcript}\n\nID запроса: {request.request_id}. Ответьте на это сообщение «да» для запуска или «отмена».",
                message_thread_id=message.message_thread_id,
                reply_to_message_id=message.message_id,
            )
        except Exception:
            return True  # Unknown Telegram ACK: do not resend the preview blindly.
        self._state.finish_interaction_delivery(
            interaction.interaction_id,
            telegram_chat_id=message.chat_id,
            telegram_message_id=sent,
        )
        return True

    def _parse_voice_command(
        self, message: VoiceMessage, transcript: str
    ) -> ParsedDesktopCommand:
        normalized = transcript.strip()
        first = normalized.split(maxsplit=1)[0].casefold() if normalized else ""
        if first in {"new", "новая", "continue", "продолжить", "создай", "создать", "начни", "заведи"}:
            text = "/codex " + normalized
        elif _COMMAND.match(normalized) or _MENTION.match(normalized) or _NAME_ADDRESS.match(normalized):
            text = normalized
        else:
            return ParsedDesktopCommand("topic", None, None, normalized)
        synthetic = TextMessage(
            update_id=message.update_id,
            tenant_id=message.tenant_id,
            actor_identity=message.actor_identity,
            actor_role=message.actor_role,
            auth_context_ref=message.auth_context_ref,
            user_id=message.user_id,
            is_bot=message.is_bot,
            is_forwarded=message.is_forwarded,
            chat_id=message.chat_id,
            message_thread_id=message.message_thread_id,
            reply_to_message_id=message.reply_to_message_id,
            binding_purpose=message.binding_purpose,
            message_id=message.message_id,
            text=text,
        )
        return self._parse_command(synthetic) or ParsedDesktopCommand(
            "route" if message.reply_to_message_id is None else "topic",
            None, None, normalized,
        )

    async def _answer_interaction(
        self, message: TextMessage, interaction: PendingDesktopInteraction,
        envelope: TrustedIngressEnvelope | None = None,
    ) -> None:
        if message.user_id != interaction.target_user_id:
            await self._reply(message, "Этот ответ может дать только назначенный адресат.")
            return
        if message.is_forwarded or (
            interaction.kind
            not in {InteractionKind.QUESTION, InteractionKind.VOICE_CONFIRMATION}
            and message.is_bot
        ):
            await self._reply(
                message,
                "Пересланное сообщение или ответ бота не подтверждает это действие.",
            )
            return
        request = self._state.read_request(interaction.request_id)
        if request is None:
            await self._reply(message, "Связанный запрос больше не найден.")
            return
        if message.chat_id != request.chat_id or message.message_thread_id != request.topic_id:
            await self._reply(message, "Ответ принимается только в исходной теме запроса.")
            return
        answer = message.text.strip()
        if interaction.payload.get("method") == "bridge/route":
            normalized = answer.casefold()
            if normalized in {"создать", "новая", "create"}:
                chosen = ParsedDesktopCommand(
                    "create", None, None, str(request.payload["instruction"])
                )
            elif normalized in {"продолжить", "continue"}:
                thread = request.payload.get("route_thread_id")
                if not isinstance(thread, str):
                    await self._reply(message, "Укажите «продолжить <ID>» или выберите создание.")
                    return
                chosen = ParsedDesktopCommand(
                    "continue", None, thread, str(request.payload["instruction"])
                )
            elif normalized.startswith(("продолжить ", "continue ")):
                thread = answer.split(maxsplit=1)[1]
                try:
                    _parse_thread_ref(thread)
                except (ValueError, TypeError):
                    await self._reply(message, "Некорректный идентификатор задачи Desktop.")
                    return
                chosen = ParsedDesktopCommand(
                    "continue", None, thread, str(request.payload["instruction"])
                )
            else:
                await self._reply(message, "Ответьте «создать» или «продолжить <ID>».")
                return
            if request.status is not BridgeRequestStatus.NEEDS_TARGET or envelope is None:
                await self._reply(message, "Уточнение уже закрыто или не связано с этим сообщением.")
                return
            if not self._state.resolve_interaction(
                interaction.interaction_id, responder_user_id=message.user_id,
            ):
                await self._reply(message, "Выбор уже обработан или истёк.")
                return
            self._state.transition(
                request.request_id, expected=frozenset({BridgeRequestStatus.NEEDS_TARGET}),
                status=BridgeRequestStatus.CANCELLED,
            )
            await self._admit(message, envelope, chosen)
            return
        if interaction.payload.get("method") == "bridge/target":
            project = self._projects.get(answer.casefold())
            if project is None or project.name not in interaction.payload.get("projects", ()):
                await self._reply(message, "Выберите точное название проекта из карточки.")
                return
            if request.status is not BridgeRequestStatus.NEEDS_TARGET or envelope is None:
                await self._reply(message, "Уточнение уже закрыто или не связано с этим сообщением.")
                return
            if not self._state.resolve_interaction(
                interaction.interaction_id, responder_user_id=message.user_id,
            ):
                await self._reply(message, "Выбор проекта уже обработан или истёк.")
                return
            self._state.transition(
                request.request_id, expected=frozenset({BridgeRequestStatus.NEEDS_TARGET}),
                status=BridgeRequestStatus.CANCELLED,
            )
            await self._admit(
                message, envelope,
                ParsedDesktopCommand("create", project.name, None,
                                     str(request.payload["instruction"])),
            )
            return
        if interaction.kind is InteractionKind.VOICE_CONFIRMATION:
            normalized = answer.casefold()
            if normalized in {"отмена", "нет", "cancel"}:
                self._state.resolve_interaction(interaction.interaction_id, responder_user_id=message.user_id)
                self._state.transition(
                    request.request_id,
                    expected=frozenset({BridgeRequestStatus.NEEDS_VOICE_CONFIRMATION}),
                    status=BridgeRequestStatus.CANCELLED,
                )
                await self._reply(message, "Голосовая задача отменена.")
                return
            if normalized not in {"да", "yes", "подтверждаю", "запускай"}:
                await self._reply(message, "Ответьте «да» или «отмена».")
                return
            if not self._state.resolve_interaction(interaction.interaction_id, responder_user_id=message.user_id):
                await self._reply(message, "Подтверждение уже обработано или истекло.")
                return
            needs_route = request.payload.get("route_required") is True
            needs_target = request.operation == "create" and request.project_name is None
            if self._state.transition(
                request.request_id,
                expected=frozenset({BridgeRequestStatus.NEEDS_VOICE_CONFIRMATION}),
                status=(BridgeRequestStatus.NEEDS_TARGET if needs_route or needs_target
                        else BridgeRequestStatus.RECEIVED),
            ):
                if needs_route:
                    await self._publish_route_card(message, request)
                    await self._reply(message, "Распознанная задача подтверждена; уточните создание или продолжение. До выбора Desktop не запускается.")
                elif needs_target:
                    await self._publish_project_target(message, request)
                    await self._reply(message, "Распознанная задача подтверждена; выберите проект в карточке. До выбора Desktop не запускается.")
                else:
                    self._schedule(request.request_id)
                    await self._reply(message, "Голосовая задача подтверждена.")
            return
        if request.desktop_thread_id is None:
            await self._reply(message, "Связь с задачей Desktop потеряна; ответ не отправлен.")
            return
        client = self._ipc_factory()
        claimed = False
        try:
            owner = await self._find_or_open_owner(client, request)
            snapshot = await client.load_complete_history_snapshot(request.desktop_thread_id, owner=owner)
            projection = project_desktop_conversation(snapshot)
            pending = [item for item in projection.pending_requests if str(item.request_id) == interaction.desktop_request_id]
            if len(pending) != 1:
                self._state.close_interaction(interaction.interaction_id, status="superseded")
                self._state.transition(
                    request.request_id,
                    expected=frozenset(
                        {
                            BridgeRequestStatus.WAITING_AUTHOR,
                            BridgeRequestStatus.WAITING_OWNER,
                        }
                    ),
                    status=BridgeRequestStatus.RUNNING,
                )
                self._schedule(request.request_id)
                await self._reply(message, "Запрос уже закрыт в Desktop; ответ не повторён.")
                return
            if interaction.kind is InteractionKind.UNKNOWN:
                await self._reply(
                    message,
                    "Этот тип запроса нельзя безопасно подтвердить через Telegram. Ответьте в Codex Desktop.",
                )
                return
            if not _pending_matches_interaction(
                pending[0], interaction, request.desktop_thread_id
            ):
                self._state.close_interaction(interaction.interaction_id, status="unknown")
                self._state.transition(
                    request.request_id,
                    expected=frozenset({
                        BridgeRequestStatus.WAITING_AUTHOR,
                        BridgeRequestStatus.WAITING_OWNER,
                    }),
                    status=BridgeRequestStatus.UNKNOWN_DISPATCH,
                )
                await self._reply(
                    message,
                    "Параметры запроса в Desktop изменились. Ответ из Telegram остановлен; проверьте задачу в Desktop.",
                )
                return
            _prevalidate_interaction_answer(interaction.kind, pending[0], answer)
            if not self._state.claim_interaction_answer(
                interaction, responder_user_id=message.user_id
            ):
                await self._reply(message, "Ответ уже обрабатывается или истёк.")
                return
            claimed = True
            if self._now() >= interaction.expires_at:
                self._state.finish_interaction_answer(
                    interaction.interaction_id, status="expired"
                )
                self._state.transition(
                    request.request_id,
                    expected=frozenset({
                        BridgeRequestStatus.WAITING_AUTHOR,
                        BridgeRequestStatus.WAITING_OWNER,
                    }),
                    status=BridgeRequestStatus.FAILED,
                )
                await self._reply(message, "Срок ответа истёк; решение не отправлено.")
                return
            try:
                await self._submit_interaction_answer(
                    client, owner, request, interaction, pending[0], answer,
                    desktop_cwd=projection.cwd,
                )
            except DesktopIpcUnknownOutcome:
                check = project_desktop_conversation(
                    await client.load_complete_history_snapshot(request.desktop_thread_id, owner=owner)
                )
                still_pending = any(str(item.request_id) == interaction.desktop_request_id for item in check.pending_requests)
                if still_pending:
                    self._state.finish_interaction_answer(
                        interaction.interaction_id, status="unknown"
                    )
                    self._state.transition(
                        request.request_id,
                        expected=frozenset(
                            {
                                BridgeRequestStatus.WAITING_AUTHOR,
                                BridgeRequestStatus.WAITING_OWNER,
                            }
                        ),
                        status=BridgeRequestStatus.UNKNOWN_DISPATCH,
                    )
                    await self._reply(message, "Desktop не подтвердил получение ответа. Повтор автоматически не отправлен.")
                    return
                self._state.finish_interaction_answer(
                    interaction.interaction_id,
                    status="superseded",
                )
                self._state.transition(
                    request.request_id,
                    expected=frozenset(
                        {
                            BridgeRequestStatus.WAITING_AUTHOR,
                            BridgeRequestStatus.WAITING_OWNER,
                        }
                    ),
                    status=BridgeRequestStatus.RUNNING,
                )
                self._schedule(request.request_id)
                await self._reply(
                    message,
                    "Запрос уже закрыт в Desktop. Ответ автоматически не повторён.",
                )
                return
            self._state.finish_interaction_answer(
                interaction.interaction_id, status="answered"
            )
            await self._reply(message, "Ответ передан в Codex Desktop.")
            self._schedule(request.request_id)
        except DesktopIpcError as error:
            if claimed:
                self._state.finish_interaction_answer(
                    interaction.interaction_id, status="unknown"
                )
                self._state.transition(
                    request.request_id,
                    expected=frozenset({
                        BridgeRequestStatus.WAITING_AUTHOR,
                        BridgeRequestStatus.WAITING_OWNER,
                    }),
                    status=BridgeRequestStatus.UNKNOWN_DISPATCH,
                )
            if str(error) in {
                "approval-answer-invalid",
                "multi-question-answer-needs-json",
                "mcp-elicitation-answer-needs-json",
            }:
                await self._reply(
                    message,
                    "Формат ответа не подходит. Для разрешения ответьте «разрешаю» или «отказать»; для нескольких полей — JSON-объект.",
                )
            else:
                await self._reply(
                    message,
                    "Desktop не подтвердил ответ. Повтор через Telegram остановлен; проверьте запрос в Desktop.",
                )
        finally:
            await client.close()

    async def _submit_interaction_answer(
        self,
        client: CodexDesktopIpcClient,
        owner: OwnerBinding,
        request: BridgeRequest,
        interaction: PendingDesktopInteraction,
        pending: DesktopPendingRequest,
        answer: str,
        *,
        desktop_cwd: str | None = None,
    ) -> None:
        thread_id = request.desktop_thread_id
        assert thread_id is not None
        if interaction.kind is InteractionKind.QUESTION:
            if pending.method == "item/tool/requestUserInputAsync":
                project = self._projects.get((request.project_name or "").casefold())
                if (
                    project is None or not desktop_cwd
                    or not await asyncio.to_thread(
                        _desktop_cwd_belongs_to_project, desktop_cwd, project.cwd
                    )
                ):
                    raise DesktopIpcError("async-question-project-context-invalid")
                reply_text = _async_question_reply_text(pending.payload, answer)
                message_id = f"nobus:question:{interaction.interaction_id}"
                restore_message = {
                    "id": message_id,
                    "text": answer,
                    "createdAt": int(self._now().timestamp() * 1000),
                    "cwd": desktop_cwd,
                    "context": {
                        "prompt": answer,
                        "turnTrigger": "send_user_message_async_question",
                        "addedFiles": [],
                        "fileAttachments": [],
                        "ideContext": None,
                        "imageAttachments": [],
                    },
                }
                await client.steer_turn(
                    thread_id,
                    owner=owner,
                    input_items=[{"type": "text", "text": reply_text, "text_elements": []}],
                    client_user_message_id=message_id,
                    restore_message=restore_message,
                )
            else:
                question_ids = _question_ids(pending.payload)
                answers = _question_answers(question_ids, answer)
                await client.submit_user_input(
                    thread_id, pending.request_id,
                    {"answers": answers}, owner=owner,
                )
            return
        if interaction.kind is InteractionKind.MCP_ELICITATION:
            decision = _approval_decision(answer)
            if decision == "decline":
                response: Mapping[str, Any] = {"action": "decline"}
            else:
                try:
                    content = json.loads(answer)
                except json.JSONDecodeError as exc:
                    raise DesktopIpcError("mcp-elicitation-answer-needs-json") from exc
                if not isinstance(content, dict):
                    raise DesktopIpcError("mcp-elicitation-answer-needs-json")
                response = {"action": "accept", "content": content}
            await client.submit_mcp_elicitation_response(
                thread_id, pending.request_id, response, owner=owner
            )
            return
        decision = _approval_decision(answer)
        if decision is None:
            raise DesktopIpcError("approval-answer-invalid")
        if interaction.kind is InteractionKind.COMMAND_APPROVAL:
            await client.answer_command_approval(
                thread_id, pending.request_id,
                _command_approval_decision(pending.payload, answer), owner=owner,
            )
        elif interaction.kind is InteractionKind.FILE_APPROVAL:
            await client.answer_file_approval(thread_id, pending.request_id, decision, owner=owner)
        elif interaction.kind is InteractionKind.PERMISSIONS_APPROVAL:
            params = pending.payload.get("params")
            permissions = params.get("permissions") if isinstance(params, Mapping) else None
            if not isinstance(permissions, Mapping):
                raise DesktopIpcError("permissions-request-invalid")
            await client.answer_permissions_request(
                thread_id,
                pending.request_id,
                {
                    "permissions": dict(permissions) if decision == "accept" else {},
                    "scope": "turn",
                    "strictAutoReview": False,
                },
                owner=owner,
            )
        else:
            raise DesktopIpcError("unsupported-approval-family")

    def _schedule(self, request_id: UUID) -> None:
        existing = self._tasks.get(request_id)
        if existing is not None and existing.done():
            self._tasks.pop(request_id, None)
            existing = None
        if self._closed or existing is not None:
            return
        task = asyncio.create_task(self._run_request(request_id), name=f"desktop-bridge-{request_id}")
        self._tasks[request_id] = task
        task.add_done_callback(
            lambda finished, key=request_id: self._worker_finished(key, finished)
        )

    def _worker_finished(
        self, request_id: UUID, task: asyncio.Task[None]
    ) -> None:
        if self._tasks.get(request_id) is task:
            self._tasks.pop(request_id, None)
        if task.cancelled():
            return
        try:
            error = task.exception()
        except asyncio.CancelledError:
            return
        if error is not None and self._worker_error is None:
            self._worker_error = error

    async def _expiry_watchdog(self) -> None:
        while not self._closed:
            await asyncio.sleep(60)
            await self._expire_interactions()
            for request in self._state.list_requests(
                statuses=frozenset(
                    {
                        BridgeRequestStatus.WAITING_AUTHOR,
                        BridgeRequestStatus.WAITING_OWNER,
                        BridgeRequestStatus.WAITING_PC,
                    }
                )
            ):
                self._schedule(request.request_id)

    async def _expire_interactions(self) -> None:
        expired = self._state.expire_interactions()
        notified: set[UUID] = set()
        for interaction in expired:
            if interaction.request_id in notified:
                continue
            notified.add(interaction.request_id)
            request = self._state.read_request(interaction.request_id)
            if request is None:
                continue
            if interaction.kind is InteractionKind.VOICE_CONFIRMATION:
                text = (
                    "Срок подтверждения голосовой задачи истёк. "
                    "Задача в Codex Desktop не запускалась."
                )
                chat_id = request.chat_id
                topic_id = request.topic_id
                reply_id = request.source_message_id
            elif interaction.payload.get("method") in {"bridge/target", "bridge/route"}:
                text = (
                    "Срок выбора действия или проекта истёк. Задача в Codex Desktop "
                    "не запускалась; отправьте новое поручение."
                )
                chat_id = request.chat_id
                topic_id = request.topic_id
                reply_id = request.source_message_id
            elif interaction.kind is InteractionKind.QUESTION:
                text = (
                    "Срок ответа на уточнение истёк. Автоматический ответ не отправлен; "
                    "задача остаётся ожидающей в Codex Desktop."
                )
                chat_id = request.chat_id
                topic_id = request.topic_id
                reply_id = request.source_message_id
            else:
                text = (
                    "Срок ответа на запрос разрешения истёк. Разрешение не выдано; "
                    "задача остаётся ожидающей в Codex Desktop."
                )
                chat_id = request.chat_id
                topic_id = request.topic_id
                reply_id = request.source_message_id
            await self._api.send_message(
                chat_id,
                text,
                message_thread_id=topic_id,
                reply_to_message_id=reply_id,
            )

    async def _run_request(self, request_id: UUID) -> None:
        async with self._semaphore:
            request = self._state.read_request(request_id)
            if request is None or request.status in {BridgeRequestStatus.DELIVERED, BridgeRequestStatus.CANCELLED, BridgeRequestStatus.FAILED, BridgeRequestStatus.UNKNOWN_DISPATCH, BridgeRequestStatus.DELIVERY_UNKNOWN}:
                return
            if self._state.has_prior_thread_request(request):
                return
            client = self._ipc_factory()
            try:
                await client.start()
                if request.desktop_thread_id is None:
                    request, owner = await self._create_desktop_task(client, request)
                else:
                    owner = await self._find_or_open_owner(client, request)
                if request.desktop_turn_id is None or request.status in {BridgeRequestStatus.RECEIVED, BridgeRequestStatus.DISPATCHING, BridgeRequestStatus.WAITING_PC}:
                    request = await self._start_desktop_turn(client, owner, request)
                await self._monitor(client, owner, request)
            except DesktopIpcUnknownOutcome:
                self._state.transition(
                    request_id,
                    expected=_RUNNING_STATUSES | frozenset({BridgeRequestStatus.RECEIVED}),
                    status=BridgeRequestStatus.UNKNOWN_DISPATCH,
                )
                await self._notify_request(request, "Desktop получил команду, но подтверждение потеряно. Повтор не выполнен; нужна сверка истории.")
            except DesktopUiAutomationError as exc:
                self._state.transition(
                    request_id,
                    expected=_RUNNING_STATUSES | frozenset({BridgeRequestStatus.RECEIVED}),
                    status=BridgeRequestStatus.UNKNOWN_DISPATCH,
                )
                if exc.reason == "desktop-uia-existing-draft":
                    await self._notify_request(
                        request,
                        "В Codex Desktop уже есть несохранённый черновик. "
                        "Он не изменён, задача не отправлена автоматически. "
                        "Сохраните или очистите черновик в Desktop; повтор требует сверки запроса.",
                    )
                else:
                    await self._notify_request(request, "UI Automation не подтвердил исход создания задачи. Повтор не выполнен, чтобы не создать дубль.")
            except (DesktopIpcUnavailableError, DesktopIpcTimeoutError) as exc:
                self._state.transition(
                    request_id,
                    expected=_RUNNING_STATUSES | frozenset({BridgeRequestStatus.RECEIVED}),
                    status=BridgeRequestStatus.WAITING_PC,
                )
                if request.status is not BridgeRequestStatus.WAITING_PC:
                    await self._notify_request(
                        request,
                        (
                            "Задача выгружена из Codex Desktop. Откройте её в приложении; "
                            "запрос сохранён и будет восстановлен без повторной отправки."
                            if isinstance(exc, DesktopIpcUnavailableError)
                            and exc.reason == "no-client-found"
                            else "Codex Desktop сейчас недоступен. Запрос сохранён и будет восстановлен после запуска."
                        ),
                    )
            except DesktopIpcError:
                self._state.transition(
                    request_id,
                    expected=_RUNNING_STATUSES
                    | frozenset({BridgeRequestStatus.RECEIVED}),
                    status=BridgeRequestStatus.FAILED,
                )
                await self._notify_request(
                    request,
                    "Codex Desktop отклонил безопасное продолжение задачи. "
                    "Повторное исполнение не запускалось.",
                )
            except Exception:
                self._state.transition(
                    request_id,
                    expected=_RUNNING_STATUSES | frozenset({BridgeRequestStatus.RECEIVED}),
                    status=BridgeRequestStatus.FAILED,
                )
                await self._notify_request(request, "Не удалось безопасно продолжить задачу Desktop. Повторное исполнение не запускалось.")
            finally:
                await client.close()
                refreshed = self._state.read_request(request_id)
                if (
                    refreshed is not None
                    and refreshed.desktop_thread_id is not None
                    and refreshed.status
                    not in {
                        BridgeRequestStatus.RECEIVED,
                        BridgeRequestStatus.NEEDS_VOICE_CONFIRMATION,
                        BridgeRequestStatus.DISPATCHING,
                        BridgeRequestStatus.RUNNING,
                        BridgeRequestStatus.WAITING_AUTHOR,
                        BridgeRequestStatus.WAITING_OWNER,
                        BridgeRequestStatus.WAITING_PC,
                        BridgeRequestStatus.UNKNOWN_DISPATCH,
                    }
                ):
                    queued = self._state.next_received_for_thread(
                        refreshed.desktop_thread_id
                    )
                    if queued is not None:
                        self._schedule(queued.request_id)

    async def _find_or_open_owner(
        self, client: CodexDesktopIpcClient, request: BridgeRequest
    ) -> OwnerBinding:
        """Load a known task in Desktop UI before retrying owner discovery once."""
        thread_id = request.desktop_thread_id
        if thread_id is None:
            raise DesktopIpcError("desktop-thread-missing")
        try:
            return await client.find_thread_owner(thread_id)
        except DesktopIpcUnavailableError as exc:
            if exc.reason != "no-client-found":
                raise
        title = self._state.known_thread_title(thread_id)
        if title is None:
            candidate = request.payload.get("requested_task_title")
            if (
                request.project_name is not None
                and request.project_name.casefold() in self._projects
                and isinstance(candidate, str)
                and 0 < len(candidate.strip()) <= 256
            ):
                # Telegram supplies only a UI selector, not task identity.
                # The exact thread owner and project cwd must still be proven
                # through IPC before a turn can be sent.
                title = candidate.strip()
        if title is None:
            raise DesktopIpcUnavailableError("no-client-found")
        async with self._ui_bootstrap_lock:
            with _interprocess_bootstrap_lock(self._ui_bootstrap_lock_path):
                try:
                    await self._uia.open_existing(
                        project_name=request.project_name or "snapshot",
                        task_title=title,
                    )
                except DesktopUiAutomationError as exc:
                    raise DesktopIpcUnavailableError("desktop-uia-open-unavailable") from exc
                # The title is only a UI selector. The IPC owner for the exact
                # requested thread ID remains mandatory before any mutation.
                for attempt in range(6):
                    try:
                        return await client.find_thread_owner(thread_id)
                    except DesktopIpcUnavailableError as exc:
                        if exc.reason != "no-client-found" or attempt == 5:
                            raise
                        await asyncio.sleep(0.5)
        raise DesktopIpcUnavailableError("no-client-found")

    async def _create_desktop_task(
        self, client: CodexDesktopIpcClient, request: BridgeRequest
    ) -> tuple[BridgeRequest, OwnerBinding]:
        async with self._ui_bootstrap_lock:
            with _interprocess_bootstrap_lock(self._ui_bootstrap_lock_path):
                return await self._create_desktop_task_locked(client, request)

    async def _create_desktop_task_locked(
        self, client: CodexDesktopIpcClient, request: BridgeRequest
    ) -> tuple[BridgeRequest, OwnerBinding]:
        if request.project_name is None:
            raise DesktopIpcError("desktop-project-missing")
        project = self._projects.get(request.project_name.casefold())
        if project is None:
            raise DesktopIpcError("desktop-project-not-allowed")
        if not self._state.transition(
            request.request_id,
            expected=frozenset({BridgeRequestStatus.RECEIVED, BridgeRequestStatus.WAITING_PC}),
            status=BridgeRequestStatus.DISPATCHING,
        ):
            refreshed = self._state.read_request(request.request_id)
            if refreshed is None:
                raise DesktopIpcError("desktop-request-missing")
            if refreshed.desktop_thread_id is None:
                raise DesktopIpcUnknownOutcome(
                    method="desktop-uia-create",
                    request_id=str(request.request_id),
                    request_digest=hashlib.sha256(str(request.request_id).encode()).hexdigest(),
                    reason="dispatching-create-needs-readback",
                )
            return refreshed, await client.find_thread_owner(refreshed.desktop_thread_id)
        marker = _REQUEST_MARKER_PREFIX + str(request.request_id)
        bootstrap = (
            f"{marker}\nСоздай пустую задачу Nobus Space, не выполняй инструменты "
            "и внешние действия. Ответь только DESKTOP-BRIDGE-READY."
        )
        await _drain_events(client)
        await self._uia.create_and_submit(project_name=project.name, prompt=bootstrap)
        candidates: set[str] = set()
        deadline = asyncio.get_running_loop().time() + 30
        while asyncio.get_running_loop().time() < deadline:
            try:
                event = await client.next_event(timeout_ms=2_000)
            except DesktopIpcTimeoutError:
                continue
            if event.method == "thread-stream-following-status-requested":
                candidates.update(_conversation_ids(event.params))
        matches: list[tuple[OwnerBinding, DesktopConversationProjection, DesktopTurnState]] = []
        for candidate in sorted(candidates):
            try:
                owner = await client.find_thread_owner(candidate)
                projection = project_desktop_conversation(
                    await client.load_complete_history_snapshot(candidate, owner=owner)
                )
            except DesktopIpcError:
                continue
            turns = [turn for turn in projection.turns if any(marker in text for text in turn.user_text)]
            if len(turns) == 1 and await asyncio.to_thread(
                _desktop_cwd_belongs_to_project, projection.cwd, project.cwd,
            ):
                matches.append((owner, projection, turns[0]))
        if len(matches) != 1:
            raise DesktopIpcUnknownOutcome(
                method="desktop-uia-create", request_id=str(request.request_id),
                request_digest=hashlib.sha256(bootstrap.encode()).hexdigest(),
                reason="created-thread-correlation-ambiguous",
            )
        owner, projection, bootstrap_turn = matches[0]
        bound = self._state.bind_desktop(
            request.request_id, thread_id=projection.conversation_id,
            turn_id=None, client_message_id=f"nobus:{request.request_id}",
            status=BridgeRequestStatus.RECEIVED,
        )
        if not self._state.bind_bootstrap_turn(
            request.request_id,
            thread_id=projection.conversation_id,
            turn_id=bootstrap_turn.turn_id,
        ):
            raise DesktopIpcUnknownOutcome(
                method="desktop-uia-create", request_id=str(request.request_id),
                request_digest=hashlib.sha256(bootstrap.encode()).hexdigest(),
                reason="bootstrap-turn-binding-conflict",
            )
        self._remember_title(bound, projection)
        return bound, owner

    def _remember_title(
        self, request: BridgeRequest, projection: DesktopConversationProjection
    ) -> None:
        if (
            request.desktop_thread_id == projection.conversation_id
            and 0 < len(projection.title) <= 256
        ):
            self._state.remember_thread_title(
                request.request_id,
                thread_id=projection.conversation_id,
                title=projection.title,
            )

    async def _start_desktop_turn(
        self,
        client: CodexDesktopIpcClient,
        owner: OwnerBinding,
        request: BridgeRequest,
    ) -> BridgeRequest:
        thread_id = request.desktop_thread_id or str(request.payload.get("requested_thread_id") or "")
        if not thread_id:
            raise DesktopIpcError("desktop-thread-missing")
        before = await client.load_complete_history_snapshot(thread_id, owner=owner)
        projection = project_desktop_conversation(before)
        projects = tuple(self._projects.values())
        actual_projects = await asyncio.to_thread(
            lambda: tuple(
                project for project in projects
                if _desktop_cwd_belongs_to_project(projection.cwd, project.cwd)
            )
        )
        if len(actual_projects) != 1:
            raise DesktopIpcError("desktop-project-context-not-allowed")
        if request.project_name is not None:
            project = self._projects.get(request.project_name.casefold())
            if project is None or actual_projects[0] != project:
                raise DesktopIpcError("desktop-project-context-mismatch")
        self._remember_title(request, projection)
        client_message_id = request.client_message_id or f"nobus:{request.request_id}"
        existing = projection.turn_by_client_message_id(client_message_id)
        if existing is not None:
            return self._state.bind_desktop(
                request.request_id, thread_id=thread_id, turn_id=existing.turn_id,
                client_message_id=client_message_id, status=BridgeRequestStatus.RUNNING,
            )
        execution_settings = _desktop_execution_settings(before.conversation_state)
        instruction = _bridge_turn_text(request)
        try:
            receipt = await client.start_turn(
                thread_id, owner=owner, client_user_message_id=client_message_id,
                input_items=[
                    {
                        "type": "text",
                        "text": instruction,
                        "text_elements": [],
                    }
                ],
                request_values=execution_settings,
            )
        except DesktopIpcUnknownOutcome:
            recovered = project_desktop_conversation(
                await client.load_complete_history_snapshot(thread_id, owner=owner)
            ).turn_by_client_message_id(client_message_id)
            if recovered is None:
                raise
            return self._state.bind_desktop(
                request.request_id, thread_id=thread_id, turn_id=recovered.turn_id,
                client_message_id=client_message_id, status=BridgeRequestStatus.RUNNING,
            )
        return self._state.bind_desktop(
            request.request_id, thread_id=thread_id, turn_id=receipt.turn_id,
            client_message_id=client_message_id, status=BridgeRequestStatus.RUNNING,
        )

    async def _monitor(
        self, client: CodexDesktopIpcClient, owner: OwnerBinding, request: BridgeRequest
    ) -> None:
        assert request.desktop_thread_id is not None
        deadline = asyncio.get_running_loop().time() + 24 * 60 * 60
        while asyncio.get_running_loop().time() < deadline:
            projection = project_desktop_conversation(
                await client.load_complete_history_snapshot(request.desktop_thread_id, owner=owner)
            )
            self._remember_title(request, projection)
            turn = projection.turn_by_client_message_id(request.client_message_id or "")
            if turn is None:
                raise DesktopIpcError("desktop-turn-readback-missing")
            pending = [item for item in projection.pending_requests if _pending_turn_id(item) in {None, turn.turn_id}]
            if pending:
                await self._publish_interactions(request, turn, pending, client.generation)
                return
            if turn.status == "completed":
                self._state.transition(
                    request.request_id,
                    expected=frozenset({BridgeRequestStatus.RUNNING, BridgeRequestStatus.WAITING_AUTHOR, BridgeRequestStatus.WAITING_OWNER, BridgeRequestStatus.EXECUTION_COMPLETED, BridgeRequestStatus.DELIVERY_PARTIAL}),
                    status=BridgeRequestStatus.EXECUTION_COMPLETED,
                )
                await self._deliver(request, projection, turn)
                return
            if turn.status in {"failed", "cancelled", "interrupted"}:
                self._state.transition(request.request_id, expected=_RUNNING_STATUSES, status=BridgeRequestStatus.FAILED)
                await self._notify_request(request, "Задача завершилась в Desktop без готового итогового ответа.")
                return
            await asyncio.sleep(1)

    async def _publish_interactions(
        self,
        request: BridgeRequest,
        turn: DesktopTurnState,
        pending: list[DesktopPendingRequest],
        generation: int,
    ) -> None:
        kinds = tuple(
            _interaction_kind(item.method, item.payload) for item in pending
        )
        has_owner_interaction = any(
            kind is not InteractionKind.QUESTION for kind in kinds
        )
        for item, kind in zip(pending, kinds, strict=True):
            target = (
                request.author_user_id
                if kind is InteractionKind.QUESTION
                else self._owner_user_id
            )
            interaction = self._state.put_interaction(
                interaction_id=_interaction_id(request.request_id, str(item.request_id)),
                request_id=request.request_id, kind=kind,
                desktop_request_id=item.request_id, desktop_turn_id=turn.turn_id,
                target_user_id=target, generation=generation,
                payload=dict(item.payload), expires_at=self._now() + _INTERACTION_TTL,
            )
            if interaction.status == "unknown" and interaction.telegram_message_id is None:
                self._state.transition(
                    request.request_id,
                    expected=frozenset({BridgeRequestStatus.RUNNING, BridgeRequestStatus.WAITING_AUTHOR, BridgeRequestStatus.WAITING_OWNER}),
                    status=BridgeRequestStatus.UNKNOWN_DISPATCH,
                )
                return
            if interaction.status != "pending" or interaction.telegram_message_id is not None:
                continue
            view_kind = "user_input" if kind is InteractionKind.QUESTION else kind.value
            view = render_interaction(view_kind, item.payload)
            card = "\n\n".join(view.blocks)
            manual_review = view.requires_manual_review
            if len(card.encode("utf-8")) > 64 * 1024:
                card = "Запрос Desktop слишком велик для безопасной карточки Telegram. Откройте его в Desktop."
                manual_review = True
            intro = (
                "Ответьте на последнюю карточку сообщения."
                if not manual_review
                else "Автоматический ответ остановлен: проверьте запрос в Codex Desktop."
            )
            label = "Автор запроса" if kind is InteractionKind.QUESTION else "Владелец"
            mention = f'<a href="tg://user?id={target}">{label}</a>'
            if view.reply_example is not None and not manual_review:
                card += "\n\nПример ответа: " + view.reply_example
            if not self._state.claim_interaction_delivery(interaction.interaction_id):
                continue
            try:
                message_id = await self._api.send_message(
                    request.chat_id,
                    f"{mention}: {html.escape(intro)}",
                    message_thread_id=request.topic_id,
                    reply_to_message_id=request.source_message_id,
                    parse_mode="HTML",
                )
                for part in telegram_text_parts(card):
                    message_id = await self._api.send_message(
                        request.chat_id, part,
                        message_thread_id=request.topic_id,
                        reply_to_message_id=message_id,
                    )
            except Exception:
                self._state.transition(
                    request.request_id,
                    expected=frozenset({BridgeRequestStatus.RUNNING, BridgeRequestStatus.WAITING_AUTHOR, BridgeRequestStatus.WAITING_OWNER}),
                    status=BridgeRequestStatus.UNKNOWN_DISPATCH,
                )
                return
            if not self._state.finish_interaction_delivery(
                interaction.interaction_id,
                telegram_chat_id=request.chat_id,
                telegram_message_id=message_id,
            ):
                self._state.transition(
                    request.request_id,
                    expected=frozenset({BridgeRequestStatus.RUNNING, BridgeRequestStatus.WAITING_AUTHOR, BridgeRequestStatus.WAITING_OWNER}),
                    status=BridgeRequestStatus.UNKNOWN_DISPATCH,
                )
                return
            if manual_review:
                self._state.close_interaction(interaction.interaction_id, status="unknown")
        waiting = (
            BridgeRequestStatus.WAITING_OWNER
            if has_owner_interaction
            else BridgeRequestStatus.WAITING_AUTHOR
        )
        self._state.transition(
            request.request_id,
            expected=frozenset({BridgeRequestStatus.RUNNING, BridgeRequestStatus.WAITING_AUTHOR, BridgeRequestStatus.WAITING_OWNER}),
            status=waiting,
        )

    async def _deliver(
        self,
        request: BridgeRequest,
        projection: DesktopConversationProjection,
        turn: DesktopTurnState,
    ) -> None:
        self._state.transition(
            request.request_id,
            expected=frozenset({BridgeRequestStatus.EXECUTION_COMPLETED, BridgeRequestStatus.DELIVERY_PARTIAL}),
            status=BridgeRequestStatus.DELIVERING,
        )
        final_blocks = _desktop_final_blocks(turn)
        full_text = "\n\n".join(final_blocks)
        if _SENSITIVE_OUTPUT.search(full_text) is not None:
            raise ValueError("desktop-final-output-sensitive")
        inspection = await asyncio.to_thread(
            inspect_artifacts, full_text, allowed_root=Path(projection.cwd),
            additional_roots=self._artifact_roots,
        )
        references = [
            {"index": index, "kind": item.kind,
             "path_digest": "sha256:" + hashlib.sha256((item.path or item.raw).encode()).hexdigest()}
            for index, item in enumerate(extract_artifact_references(full_text).references)
        ]
        snapshots = [
            {"index": item.reference_index, "digest": item.sha256,
             "size": len(item.content),
             "parts": (len(item.content) + _ARTIFACT_PART_BYTES - 1) // _ARTIFACT_PART_BYTES}
            for item in inspection.snapshots
        ]
        try:
            self._state.record_delivery_plan(
                request.request_id,
                final_digest="sha256:" + hashlib.sha256(full_text.encode()).hexdigest(),
                references=references, snapshots=snapshots,
            )
        except DesktopBridgeStateError:
            self._mark_delivery_unknown(request)
            return
        formatted = format_final_blocks(final_blocks)
        parts = formatted.parts
        destination = _destination_ref(request)
        for index, part in enumerate(parts):
            digest = "sha256:" + hashlib.sha256(part.text.encode("utf-8")).hexdigest()
            claim = self._state.claim_delivery(
                request_id=request.request_id, kind="text", ordinal=index,
                source_digest=digest, destination_ref=destination,
                payload={"part_count": len(parts), "text": part.text, "parse_mode": part.parse_mode},
            )
            if claim.status == "sent":
                continue
            if claim.status == "unknown":
                self._mark_delivery_unknown(request)
                return
            try:
                message_id = await self._api.send_message(
                    request.chat_id, part.text, message_thread_id=request.topic_id,
                    reply_to_message_id=request.source_message_id if index == 0 else None,
                    parse_mode=part.parse_mode,
                )
            except Exception:
                self._state.finish_delivery(claim.operation_key, telegram_message_id=None, status="unknown")
                self._mark_delivery_unknown(request)
                return
            if not self._state.finish_delivery(
                claim.operation_key,
                telegram_message_id=message_id,
                status="sent",
            ):
                self._mark_delivery_unknown(request)
                return
        if len(parts) > 1:
            if not await self._deliver_artifact(
                request,
                destination,
                0,
                "answer.md",
                full_text.encode("utf-8"),
            ):
                return
        artifacts = inspection.snapshots
        for artifact in artifacts:
            chunks = tuple(
                artifact.content[offset : offset + _ARTIFACT_PART_BYTES]
                for offset in range(0, len(artifact.content), _ARTIFACT_PART_BYTES)
            )
            manifest = None
            if len(chunks) > 1:
                manifest = json.dumps(
                    {
                        "filename": artifact.filename,
                        "sha256": artifact.sha256,
                        "bytes": len(artifact.content),
                        "parts": len(chunks),
                        "assembly": (
                            "Соедините части .part001, .part002 и далее "
                            "по порядку без преобразования bytes."
                        ),
                    },
                    ensure_ascii=False,
                    indent=2,
                ).encode("utf-8")
            for chunk_index, content in enumerate(chunks):
                filename = artifact.filename if len(chunks) == 1 else f"{artifact.filename}.part{chunk_index + 1:03d}"
                slot = 1 + artifact.reference_index * _ARTIFACT_SLOT_WIDTH + chunk_index
                if not await self._deliver_artifact(
                    request, destination, slot, filename, content,
                    source_file_digest=artifact.sha256, part_count=len(chunks),
                ):
                    return
            if manifest is not None:
                if not await self._deliver_artifact(request, destination, 1 + artifact.reference_index, artifact.filename + ".manifest.json", manifest, kind="manifest"):
                    return
        if inspection.failures:
            failure_manifest = json.dumps(
                {
                    "status": "partial",
                    "files": [
                        {"filename": item.filename, "reason": item.reason}
                        for item in inspection.failures
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8")
            if self._state.delivery_slot_status(
                request.request_id, kind="manifest", ordinal=0
            ) != "sent" and not await self._deliver_artifact(
                request,
                destination,
                0,
                "artifact-delivery-manifest.json",
                failure_manifest,
                kind="manifest",
            ):
                return
            self._state.transition(
                request.request_id,
                expected=frozenset({BridgeRequestStatus.DELIVERING}),
                status=BridgeRequestStatus.DELIVERY_PARTIAL,
            )
            return
        self._state.transition(
            request.request_id,
            expected=frozenset({BridgeRequestStatus.DELIVERING}),
            status=BridgeRequestStatus.DELIVERED,
        )

    async def _deliver_artifact(
        self,
        request: BridgeRequest,
        destination: str,
        ordinal: int,
        filename: str,
        content: bytes,
        *,
        kind: str = "artifact",
        source_file_digest: str | None = None,
        part_count: int | None = None,
    ) -> bool:
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        payload = {"filename": filename, "bytes": len(content)}
        if source_file_digest is not None:
            payload.update(source_file_digest=source_file_digest, part_count=part_count)
        try:
            claim = self._state.claim_delivery(
                request_id=request.request_id, kind=kind, ordinal=ordinal,
                source_digest=digest, destination_ref=destination,
                payload=payload,
            )
        except DesktopBridgeStateError:
            self._mark_delivery_unknown(request)
            return False
        if claim.status == "sent":
            return True
        if claim.status == "unknown":
            self._mark_delivery_unknown(request)
            return False
        if self._document_delivery is None:
            self._state.finish_delivery(claim.operation_key, telegram_message_id=None, status="failed")
            self._state.transition(
                request.request_id,
                expected=frozenset({BridgeRequestStatus.DELIVERING}),
                status=BridgeRequestStatus.DELIVERY_PARTIAL,
            )
            return False
        try:
            receipt = await self._document_delivery.deliver(
                api=self._api,
                request_id=request.request_id,
                operation_id=claim.operation_key,
                tenant_id=request.tenant_id,
                chat_id=request.chat_id,
                topic_id=request.topic_id,
                filename=_safe_filename(filename),
                content=content,
            )
        except Exception:
            self._state.finish_delivery(claim.operation_key, telegram_message_id=None, status="unknown")
            self._mark_delivery_unknown(request)
            return False
        if receipt.status not in {"sent", "sent_existing"} or type(receipt.message_id) is not int:
            self._state.finish_delivery(claim.operation_key, telegram_message_id=None, status="unknown")
            self._mark_delivery_unknown(request)
            return False
        message_id = receipt.message_id
        if not self._state.finish_delivery(
            claim.operation_key,
            telegram_message_id=message_id,
            status="sent",
        ):
            self._mark_delivery_unknown(request)
            return False
        return True

    def _mark_delivery_unknown(self, request: BridgeRequest) -> None:
        self._state.transition(
            request.request_id,
            expected=frozenset({BridgeRequestStatus.DELIVERING, BridgeRequestStatus.DELIVERY_PARTIAL}),
            status=BridgeRequestStatus.DELIVERY_UNKNOWN,
        )

    async def _reply(self, message: TextMessage | VoiceMessage, text: str) -> int:
        return await self._api.send_message(
            message.chat_id, text, message_thread_id=message.message_thread_id,
            reply_to_message_id=message.message_id,
        )

    async def _notify_request(self, request: BridgeRequest, text: str) -> int:
        return await self._api.send_message(
            request.chat_id, text, message_thread_id=request.topic_id,
            reply_to_message_id=request.source_message_id,
        )

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeError("desktop bridge clock unavailable")
        return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class ArtifactSnapshot:
    filename: str
    content: bytes
    sha256: str
    reference_index: int = 0


@dataclass(frozen=True, slots=True)
class ArtifactFailure:
    filename: str
    reason: str


@dataclass(frozen=True, slots=True)
class ArtifactInspection:
    snapshots: tuple[ArtifactSnapshot, ...]
    failures: tuple[ArtifactFailure, ...]


def telegram_text_parts(text: str, *, max_bytes: int = _TEXT_PART_BYTES) -> tuple[str, ...]:
    """Split every Unicode codepoint exactly once, preferring line boundaries."""
    if not isinstance(text, str) or not text or type(max_bytes) is not int or not 256 <= max_bytes <= 4096:
        raise ValueError("Telegram text projection is invalid")
    parts: list[str] = []
    remaining = text
    while remaining:
        encoded = remaining.encode("utf-8")
        if len(encoded) <= max_bytes:
            parts.append(remaining)
            break
        byte_cut = max_bytes
        while byte_cut > 0:
            try:
                candidate = encoded[:byte_cut].decode("utf-8")
                break
            except UnicodeDecodeError:
                byte_cut -= 1
        if byte_cut <= 0:
            raise ValueError("Telegram text projection cannot make progress")
        newline = candidate.rfind("\n")
        if newline >= max(1, len(candidate) // 2):
            candidate = candidate[: newline + 1]
        parts.append(candidate)
        remaining = remaining[len(candidate) :]
    if "".join(parts) != text:
        raise RuntimeError("Telegram text projection lost content")
    return tuple(parts)


def telegram_visible_final(text: str) -> str:
    """Remove only the private notifier directive at the end of a final answer."""
    if not isinstance(text, str):
        raise ValueError("Desktop final output is invalid")
    visible = _NOTIFIER_MARKER.sub("", text)
    if not visible.strip():
        raise ValueError("Desktop final output is empty")
    return visible


def _desktop_final_text(turn: DesktopTurnState) -> str:
    return "\n\n".join(_desktop_final_blocks(turn))


def _desktop_final_blocks(turn: DesktopTurnState) -> tuple[str, ...]:
    finals = tuple(
        telegram_visible_final(item.text)
        for item in turn.agent_messages
        if item.phase == "final_answer"
        and not (item.delivery == "async" and item.questions)
    )
    if not finals:
        raise DesktopIpcError("desktop-final-output-missing")
    return finals


@contextmanager
def _interprocess_bootstrap_lock(path: Path):
    """One creator across bridge processes until Desktop thread correlation ends."""
    try:
        with path.open("a+b") as handle:
            handle.seek(0)
            if handle.read(1) == b"":
                handle.seek(0)
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    raise DesktopIpcUnavailableError("desktop-ui-bootstrap-busy") from exc
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    raise DesktopIpcUnavailableError("desktop-ui-bootstrap-busy") from exc
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        raise DesktopIpcUnavailableError("desktop-ui-bootstrap-lock-unavailable") from exc


def _bridge_turn_text(request: BridgeRequest) -> str:
    """Bind one Desktop turn to the durable Telegram request for notifier routing."""
    instruction = request.payload.get("instruction")
    if not isinstance(instruction, str) or not instruction.strip():
        raise DesktopIpcError("desktop-instruction-missing")
    return (
        f"{_REQUEST_MARKER_PREFIX}{request.request_id}\n"
        "Nobus Space Bridge доставит ваш итог и файлы в исходную тему Telegram. "
        "Не вызывай nobus-send-results и не отправляй Telegram-сообщения из этой "
        "задачи: у доставки один владелец — Bridge.\n"
        f"{instruction}"
    )


def _desktop_execution_settings(state: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve Desktop mode/policy, but route bridge approvals to the owner."""
    settings = state.get("latestThreadSettings")
    mode = settings.get("collaborationMode") if isinstance(settings, dict) else None
    if not isinstance(settings, dict) or not isinstance(mode, dict):
        raise DesktopIpcError("desktop-thread-settings-missing")
    mode_settings = mode.get("settings")
    if (
        mode.get("mode") not in {"default", "plan"}
        or not isinstance(mode_settings, dict)
        or not isinstance(mode_settings.get("model"), str)
        or not mode_settings["model"]
        or (mode_settings.get("reasoning_effort") is not None
            and not isinstance(mode_settings["reasoning_effort"], str))
        or (mode_settings.get("developer_instructions") is not None
            and not isinstance(mode_settings["developer_instructions"], str))
    ):
        raise DesktopIpcError("desktop-collaboration-mode-unsupported")
    approval_policy = settings.get("approvalPolicy")
    approvals_reviewer = settings.get("approvalsReviewer")
    if (
        not isinstance(approval_policy, str) or not approval_policy
        or approvals_reviewer not in {"auto_review", "user"}
        or not isinstance(settings.get("sandboxPolicy"), dict)
    ):
        raise DesktopIpcError("desktop-permission-settings-missing")
    return {
        "approvalPolicy": approval_policy,
        # The installed Desktop auto-reviewer can decide before Telegram sees
        # a pending approval. Bridge turns need the normal user-review path so
        # only the verified numeric Telegram owner can answer that request.
        "approvalsReviewer": "user",
        "collaborationMode": mode,
    }


def snapshot_artifacts(text: str, *, allowed_root: Path) -> tuple[ArtifactSnapshot, ...]:
    """Snapshot only explicit regular files below the confirmed project cwd."""
    return inspect_artifacts(text, allowed_root=allowed_root).snapshots


def _desktop_cwd_belongs_to_project(cwd: str, project_root: Path) -> bool:
    """Accept only the saved root or a Git-registered worktree of that root."""
    try:
        candidate = Path(cwd)
        resolved = candidate.resolve(strict=True)
        if not resolved.is_dir() or resolved != candidate.absolute():
            return False
        if resolved == project_root:
            return True
        def git(at: Path, *args: str) -> str:
            result = subprocess.run(
                ["git", "-C", str(at), *args], capture_output=True,
                text=True, encoding="utf-8", timeout=5, check=True,
            )
            return result.stdout.strip()
        if Path(git(project_root, "rev-parse", "--show-toplevel")).resolve() != project_root:
            return False
        if Path(git(resolved, "rev-parse", "--show-toplevel")).resolve() != resolved:
            return False
        original_common = (project_root / git(project_root, "rev-parse", "--git-common-dir")).resolve()
        candidate_common = (resolved / git(resolved, "rev-parse", "--git-common-dir")).resolve()
        if original_common != candidate_common:
            return False
        registered = git(project_root, "worktree", "list", "--porcelain", "-z")
        return any(
            Path(record[9:]).resolve() == resolved
            for record in registered.split("\0")
            if record.startswith("worktree ")
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def inspect_artifacts(
    text: str, *, allowed_root: Path, additional_roots: tuple[Path, ...] = ()
) -> ArtifactInspection:
    """Return immutable snapshots plus bounded reasons for every explicit path."""
    root = Path(allowed_root).resolve()
    roots = (root, *(Path(item).resolve() for item in additional_roots))
    found: list[ArtifactSnapshot] = []
    failures: list[ArtifactFailure] = []
    seen: set[Path] = set()
    parsed = extract_artifact_references(text)
    for issue in parsed.issues:
        failures.append(ArtifactFailure("artifact-reference", issue))
    for reference_index, reference in enumerate(parsed.references):
        if reference.kind == "remote_url":
            continue
        if reference.kind != "windows_absolute" or reference.path is None:
            failures.append(ArtifactFailure("artifact-reference", "unsupported_local"))
            continue
        path = Path(reference.path)
        filename = _safe_filename(path.name or "artifact")
        try:
            resolved = path.resolve(strict=True)
            metadata = resolved.stat()
            if resolved in seen:
                continue
            seen.add(resolved)
            allowed = next((item for item in roots if resolved.is_relative_to(item)), None)
            if allowed is None:
                failures.append(ArtifactFailure(filename, "outside_allowed_roots"))
                continue
            if _has_reparse_component(path, allowed):
                failures.append(ArtifactFailure(filename, "reparse_path"))
                continue
            if (
                not stat.S_ISREG(metadata.st_mode)
                or getattr(metadata, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
                or metadata.st_nlink != 1
            ):
                failures.append(ArtifactFailure(filename, "not_regular_file"))
                continue
            if metadata.st_size <= 0:
                failures.append(ArtifactFailure(filename, "empty_file"))
                continue
            if metadata.st_size > _MAX_ARTIFACT_BYTES:
                failures.append(ArtifactFailure(filename, "file_too_large"))
                continue
            content = resolved.read_bytes()
            after = resolved.stat()
            if (metadata.st_size, metadata.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                failures.append(ArtifactFailure(filename, "file_changed_during_snapshot"))
                continue
            if _artifact_is_sensitive(filename, content):
                failures.append(ArtifactFailure(filename, "sensitive_file"))
                continue
        except FileNotFoundError:
            failures.append(ArtifactFailure(filename, "file_missing"))
            continue
        except (OSError, ValueError):
            failures.append(ArtifactFailure(filename, "file_unavailable"))
            continue
        found.append(
            ArtifactSnapshot(
                filename=resolved.name,
                content=content,
                sha256="sha256:" + hashlib.sha256(content).hexdigest(),
                reference_index=reference_index,
            )
        )
    return ArtifactInspection(tuple(found), tuple(failures))


def _has_reparse_component(path: Path, root: Path) -> bool:
    """Reject symlink/junction components even when their target stays allowed."""
    current = path
    while current != root and current != current.parent:
        metadata = current.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or getattr(metadata, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        ):
            return True
        current = current.parent
    return False


def _artifact_is_sensitive(filename: str, content: bytes) -> bool:
    if _SENSITIVE_ARTIFACT_NAME.search(filename) is not None:
        return True
    sample = content if len(content) <= 2 * 1024 * 1024 else content[: 1024 * 1024] + content[-1024 * 1024 :]
    try:
        text = sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return _SENSITIVE_OUTPUT.search(text) is not None


async def _drain_events(client: CodexDesktopIpcClient) -> None:
    while True:
        try:
            await client.next_event(timeout_ms=1)
        except DesktopIpcTimeoutError:
            return


def _conversation_ids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in {"conversationId", "threadId"} and isinstance(child, str):
                found.add(child)
            found.update(_conversation_ids(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_conversation_ids(child))
    return found


def _request_uuid(digest: str) -> UUID:
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("desktop bridge ingress digest is invalid")
    return UUID(hex=digest[7:39], version=4)


def _interaction_id(request_id: UUID, desktop_request_id: str) -> str:
    return hashlib.sha256(f"desktop-interaction-v1:{request_id}:{desktop_request_id}".encode()).hexdigest()


def _interaction_kind(
    method: str, payload: Mapping[str, Any]
) -> InteractionKind:
    if method in {"item/tool/requestUserInput", "item/tool/requestUserInputAsync"}:
        params = payload.get("params")
        if (
            not isinstance(params, Mapping)
            or not isinstance(params.get("questions"), list)
            or not params["questions"]
            or not set(params).issubset(
                {"questions", "threadId", "turnId", "itemId"}
            )
        ):
            return InteractionKind.UNKNOWN
        # There is no trusted origin/authority field in this pinned IPC shape.
        # Never turn a consent-like question into a member-addressed approval.
        if set(payload) - {"id", "method", "params"} or _OWNER_REVIEW_QUESTION.search(
            json.dumps(params["questions"], ensure_ascii=False)
        ):
            return InteractionKind.UNKNOWN
        return InteractionKind.QUESTION
    return {
        "item/commandExecution/requestApproval": InteractionKind.COMMAND_APPROVAL,
        "item/fileChange/requestApproval": InteractionKind.FILE_APPROVAL,
        "item/permissions/requestApproval": InteractionKind.PERMISSIONS_APPROVAL,
        "mcpServer/elicitation/request": InteractionKind.MCP_ELICITATION,
    }.get(method, InteractionKind.UNKNOWN)


def _pending_turn_id(request: DesktopPendingRequest) -> str | None:
    params = request.payload.get("params")
    if isinstance(params, Mapping) and isinstance(params.get("turnId"), str):
        return params["turnId"]
    return None


def _pending_matches_interaction(
    pending: DesktopPendingRequest,
    interaction: PendingDesktopInteraction,
    thread_id: str,
) -> bool:
    """Bind the displayed approval to the current Desktop request bytes."""
    params = pending.payload.get("params")
    return (
        str(pending.request_id) == interaction.desktop_request_id
        and pending.method == interaction.payload.get("method")
        and canonical_json_digest(dict(pending.payload)) == interaction.payload_digest
        and isinstance(params, Mapping)
        and params.get("threadId") in {None, thread_id}
        and params.get("turnId") == interaction.desktop_turn_id
        and _interaction_kind(pending.method, pending.payload) is interaction.kind
    )


def _prevalidate_interaction_answer(
    kind: InteractionKind, pending: DesktopPendingRequest, answer: str
) -> None:
    """Reject malformed replies before reserving the one response attempt."""
    if kind is InteractionKind.QUESTION:
        if pending.method == "item/tool/requestUserInputAsync":
            _async_question_reply_text(pending.payload, answer)
        else:
            _question_answers(_question_ids(pending.payload), answer)
        return
    if kind is InteractionKind.MCP_ELICITATION:
        if _approval_decision(answer) == "decline":
            return
        try:
            value = json.loads(answer)
        except json.JSONDecodeError as exc:
            raise DesktopIpcError("mcp-elicitation-answer-needs-json") from exc
        if not isinstance(value, dict):
            raise DesktopIpcError("mcp-elicitation-answer-needs-json")
        return
    if _approval_decision(answer) is None:
        raise DesktopIpcError("approval-answer-invalid")
    if kind is InteractionKind.COMMAND_APPROVAL:
        _command_approval_decision(pending.payload, answer)
    if kind is InteractionKind.PERMISSIONS_APPROVAL:
        params = pending.payload.get("params")
        if not isinstance(params, Mapping) or not isinstance(
            params.get("permissions"), Mapping
        ):
            raise DesktopIpcError("permissions-request-invalid")


def _question_ids(payload: Mapping[str, Any]) -> tuple[str, ...]:
    params = payload.get("params")
    questions = params.get("questions") if isinstance(params, Mapping) else None
    if not isinstance(questions, list):
        return ()
    ids = []
    for question in questions:
        if isinstance(question, Mapping) and isinstance(question.get("id"), str):
            ids.append(question["id"])
    return tuple(ids)


def _question_text(payload: Mapping[str, Any]) -> str:
    params = payload.get("params")
    questions = params.get("questions") if isinstance(params, Mapping) else None
    lines = ["Codex Desktop просит уточнение. Ответьте на это сообщение."]
    if isinstance(questions, list):
        for question in questions[:8]:
            if not isinstance(question, Mapping):
                continue
            text = question.get("question")
            if isinstance(text, str):
                lines.append("\n" + text[:800])
            options = question.get("options")
            if isinstance(options, list):
                for option in options[:12]:
                    if isinstance(option, Mapping) and isinstance(option.get("label"), str):
                        lines.append("— " + option["label"][:200])
    return "\n".join(lines)[:4000]


def _question_answers(question_ids: tuple[str, ...], answer: str) -> dict[str, dict[str, list[str]]]:
    if not question_ids:
        raise DesktopIpcError("question-request-invalid")
    if len(question_ids) == 1:
        return {question_ids[0]: {"answers": [answer]}}
    try:
        decoded = json.loads(answer)
    except json.JSONDecodeError as exc:
        raise DesktopIpcError("multi-question-answer-needs-json") from exc
    if not isinstance(decoded, dict) or set(decoded) != set(question_ids):
        raise DesktopIpcError("multi-question-answer-needs-json")
    result: dict[str, dict[str, list[str]]] = {}
    for question_id in question_ids:
        value = decoded[question_id]
        values = value if isinstance(value, list) else [value]
        if not values or not all(isinstance(item, str) and item.strip() for item in values):
            raise DesktopIpcError("multi-question-answer-needs-json")
        result[question_id] = {"answers": [item.strip() for item in values]}
    return result


def _async_question_reply_text(payload: Mapping[str, Any], answer: str) -> str:
    """Build the installed Desktop's exact steered async-question envelope."""
    params = payload.get("params")
    questions = params.get("questions") if isinstance(params, Mapping) else None
    item_id = params.get("itemId") if isinstance(params, Mapping) else None
    if (
        not isinstance(item_id, str) or not item_id
        or not isinstance(questions, list) or not 1 <= len(questions) <= 3
    ):
        raise DesktopIpcError("async-question-shape-invalid")
    ids = _question_ids(payload)
    if len(ids) != len(questions):
        raise DesktopIpcError("async-question-shape-invalid")
    answers = _question_answers(ids, answer)
    reply_records = []
    for index, question in enumerate(questions):
        if not isinstance(question, Mapping):
            raise DesktopIpcError("async-question-shape-invalid")
        expected_id = json.dumps(
            ["request_user_input_async", item_id, index], separators=(",", ":")
        )
        title = question.get("question")
        if question.get("id") != expected_id or not isinstance(title, str) or not title:
            raise DesktopIpcError("async-question-shape-invalid")
        chosen = answers[expected_id]["answers"]
        if len(chosen) != 1:
            raise DesktopIpcError("async-question-answer-invalid")
        reply_records.append({
            "questionItemId": expected_id,
            "question": title,
            "answer": chosen[0],
        })
    return (
        "<send_user_message_question_reply>\n"
        + json.dumps(reply_records, ensure_ascii=False, separators=(",", ":"))
        + "\n</send_user_message_question_reply>"
    )


def _approval_text(payload: Mapping[str, Any]) -> str:
    params = payload.get("params")
    lines = ["Codex Desktop запрашивает разрешение. Ответьте «разрешаю» или «отказать». "]
    if isinstance(params, Mapping):
        for key in ("command", "cwd", "reason", "path"):
            value = params.get(key)
            if isinstance(value, str) and value.strip():
                lines.append(f"{key}: {value.strip()[:1000]}")
    return "\n".join(lines)[:4000]


def _approval_decision(answer: str) -> str | None:
    value = answer.strip().casefold()
    if value in {"разрешаю", "разрешить", "да", "approve", "accept"}:
        return "accept"
    if value in {"отказать", "отклонить", "нет", "deny", "decline"}:
        return "decline"
    return None


def _command_approval_decision(payload: Mapping[str, Any], answer: str) -> str:
    """Use a decision advertised by this exact Desktop approval request."""
    decision = _approval_decision(answer)
    if decision is None:
        raise DesktopIpcError("approval-answer-invalid")
    params = payload.get("params")
    available = params.get("availableDecisions") if isinstance(params, Mapping) else None
    if available is None:
        return decision  # Older owner protocol, previously proven with decline.
    if not isinstance(available, list):
        raise DesktopIpcError("approval-decisions-invalid")
    allowed = {item for item in available if isinstance(item, str)}
    if decision == "accept" and "accept" in allowed:
        return "accept"
    if decision == "decline":
        if "decline" in allowed:
            return "decline"
        if "cancel" in allowed:
            return "cancel"
    raise DesktopIpcError("approval-decision-unavailable")


def _destination_ref(request: BridgeRequest) -> str:
    return f"telegram:{request.chat_id}:topic:{request.topic_id or 0}:reply:{request.source_message_id}"


def _safe_filename(value: str) -> str:
    cleaned = re.sub(
        r"[^A-Za-zА-Яа-яЁё0-9._() -]", "_", Path(value).name
    ).strip(" ")
    if cleaned in {"", ".", ".."} or len(cleaned.encode("utf-8")) > 240:
        digest = hashlib.sha256(value.encode()).hexdigest()[:12]
        return f"artifact-{digest}.bin"
    return cleaned


def _parse_thread_ref(value: object) -> str:
    raw = _bounded_text(value, 256)
    if raw.startswith("codex://threads/"):
        raw = raw.removeprefix("codex://threads/").split("?", 1)[0]
    return str(UUID(raw))


def _bounded_text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        raise ValueError("desktop bridge text is invalid")
    normalized = value.strip()
    if not normalized or len(normalized) > limit or "\x00" in normalized:
        raise ValueError("desktop bridge text is invalid")
    return normalized
