"""Authenticated Telegram owner control-plane for Nobus MVP-1."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any, Protocol

from src.application.durable_runtime import DurableFakeRuntime, StatusDeliveryBoundary
from src.application.fake_vertical import FakeVerticalStatus
from src.application.task_confirmation import (
    MAX_TASK_INSTRUCTION_LENGTH,
    InMemoryTaskConfirmationStore,
    TaskConfirmationChallenge,
    TaskConfirmationStatus,
)
from src.contracts import TrustedIngressEnvelope
from src.transport.telegram import (
    IngressStatus,
    TelegramGateway,
    TextMessage,
    VoiceMessage,
)


class TelegramReplyApi(Protocol):
    async def send_message(self, chat_id: int, text: str) -> int: ...


class TelegramControlPlane:
    """Handle bounded owner commands after TelegramGateway authentication."""

    _STATUS_BASIC = (
        "Nobus Space MVP-1\n"
        "Telegram: online\n"
        "Owner binding: active\n"
        "Task executor: pre-live"
    )
    _STATUS_TASKS = (
        "Nobus Space MVP-1\n"
        "Telegram: online\n"
        "Owner binding: active\n"
        "Task executor: local fake (confirmation required)"
    )
    _HELP_BASIC = (
        "Доступные команды:\n"
        "/status — состояние оркестратора\n"
        "/help — список команд\n"
        "Выполнение задач подключается следующим этапом."
    )
    _HELP_TASKS = (
        "Доступные команды:\n"
        "/status — состояние оркестратора\n"
        "/task <задача> — создать локальный черновик\n"
        "/confirm <код> — подтвердить запуск fake-worker\n"
        "/cancel <код> — отменить черновик\n"
        "/help — список команд\n"
        "Live Codex не подключён."
    )
    _VOICE_PENDING = (
        "Голосовое сообщение принято доверенной границей, "
        "но live-транскрибация ещё не активирована."
    )
    _UNSUPPORTED = (
        "Команда пока не поддерживается. Используйте /status или /help."
    )
    _TASK_USAGE = (
        f"Формат: /task <задача>. Длина задачи: "
        f"1–{MAX_TASK_INSTRUCTION_LENGTH} символов."
    )
    _TOKEN_USAGE = (
        "Укажите одноразовый код из сообщения с предпросмотром."
    )

    def __init__(
        self,
        gateway: TelegramGateway,
        api: TelegramReplyApi,
        *,
        task_runtime: DurableFakeRuntime | None = None,
        task_confirmations: InMemoryTaskConfirmationStore | None = None,
        task_tenants: Iterable[str] = (),
        task_status_sender: StatusDeliveryBoundary | None = None,
    ) -> None:
        if not isinstance(gateway, TelegramGateway) or not callable(
            getattr(api, "send_message", None)
        ):
            raise ValueError("Telegram control-plane configuration is invalid")
        task_parts = (task_runtime, task_confirmations, task_status_sender)
        configured = all(part is not None for part in task_parts)
        if any(part is not None for part in task_parts) and not configured:
            raise ValueError("Telegram task configuration is incomplete")
        tenants = tuple(
            dict.fromkeys(
                tenant.strip()
                for tenant in task_tenants
                if isinstance(tenant, str) and tenant.strip()
            )
        )
        if configured and not tenants:
            raise ValueError("Telegram task tenants are required")
        if not configured and tenants:
            raise ValueError("Telegram task configuration is incomplete")
        self._gateway = gateway
        self._api = api
        self._task_runtime = task_runtime
        self._task_confirmations = task_confirmations
        self._task_tenants = tenants
        self._task_status_sender = task_status_sender

    @property
    def tasks_enabled(self) -> bool:
        return self._task_runtime is not None

    async def handle(self, update: dict[str, Any]) -> bool:
        """Acknowledge every bounded update; reply only after exact binding."""

        ingress = self._gateway.process_update(update)
        if (
            ingress.status is not IngressStatus.ACCEPTED
            or ingress.payload is None
            or ingress.envelope is None
        ):
            return True
        await self._expire_task_drafts()
        payload = ingress.payload
        if isinstance(payload, TextMessage):
            command = _command(payload.text)
            if command == "/status":
                response = (
                    self._STATUS_TASKS if self.tasks_enabled else self._STATUS_BASIC
                )
                await self._api.send_message(payload.chat_id, response)
            elif command in {"/help", "/start"}:
                response = self._HELP_TASKS if self.tasks_enabled else self._HELP_BASIC
                await self._api.send_message(payload.chat_id, response)
            elif command == "/task" and self.tasks_enabled:
                await self._create_task(payload, ingress.envelope)
            elif command in {"/confirm", "/cancel"} and self.tasks_enabled:
                await self._resolve_task(
                    payload,
                    ingress.envelope,
                    TaskConfirmationStatus.CONFIRMED
                    if command == "/confirm"
                    else TaskConfirmationStatus.CANCELLED,
                )
            else:
                await self._api.send_message(payload.chat_id, self._UNSUPPORTED)
        elif isinstance(payload, VoiceMessage):
            await self._api.send_message(payload.chat_id, self._VOICE_PENDING)
        return True

    async def deliver_pending(self) -> int:
        """Deliver durable content-free statuses after a successful poll cycle."""
        if self._task_runtime is None or self._task_status_sender is None:
            return 0
        delivered = 0
        for tenant_id in self._task_tenants:
            outcomes = await self._task_runtime.deliver_pending(
                tenant_id,
                self._task_status_sender,
            )
            delivered += sum(message.status.value == "acked" for message in outcomes)
        return delivered

    async def _create_task(
        self,
        message: TextMessage,
        envelope: TrustedIngressEnvelope,
    ) -> None:
        assert self._task_runtime is not None
        assert self._task_confirmations is not None
        instruction = _argument(message.text)
        if (
            not instruction
            or len(instruction) > MAX_TASK_INSTRUCTION_LENGTH
            or "\x00" in instruction
        ):
            await self._api.send_message(message.chat_id, self._TASK_USAGE)
            return
        challenge = self._task_confirmations.challenge_for(message, envelope)
        if challenge is None:
            prepared = None
            try:
                prepared = await self._task_runtime.prepare_instruction(
                    instruction,
                    envelope,
                )
                challenge = self._task_confirmations.issue(
                    message=message,
                    envelope=envelope,
                    prepared=prepared,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                if prepared is not None:
                    await self._task_runtime.cancel_prepared(prepared)
                await self._api.send_message(
                    message.chat_id,
                    "Черновик задачи не создан. Отправьте новую команду /task.",
                )
                return
        await self._api.send_message(message.chat_id, _preview_text(challenge))

    async def _resolve_task(
        self,
        message: TextMessage,
        envelope: TrustedIngressEnvelope,
        action: TaskConfirmationStatus,
    ) -> None:
        assert self._task_runtime is not None
        assert self._task_confirmations is not None
        token = _argument(message.text)
        if not token or any(character.isspace() for character in token):
            await self._api.send_message(message.chat_id, self._TOKEN_USAGE)
            return
        result = self._task_confirmations.consume(
            token=token,
            action=action,
            message=message,
            envelope=envelope,
        )
        if result.status is TaskConfirmationStatus.ALREADY_USED:
            await self._api.send_message(
                message.chat_id,
                "Этот одноразовый код уже использован.",
            )
            return
        if result.prepared is None:
            await self._api.send_message(
                message.chat_id,
                "Код недействителен, истёк или принадлежит другому запросу.",
            )
            return
        if result.status is TaskConfirmationStatus.CONFIRMED:
            outcome = await self._task_runtime.execute_prepared(result.prepared)
            response = (
                "Подтверждение принято. Итоговый статус задачи "
                "будет отправлен отдельно."
                if outcome.status is FakeVerticalStatus.COMPLETED
                else "Задачу не удалось выполнить локальным fake-worker."
            )
        else:
            outcome = await self._task_runtime.cancel_prepared(result.prepared)
            response = (
                "Черновик задачи отменён."
                if outcome.status is FakeVerticalStatus.REJECTED
                else "Черновик задачи уже недоступен."
            )
        await self._api.send_message(message.chat_id, response)

    async def _expire_task_drafts(self) -> None:
        if self._task_runtime is None or self._task_confirmations is None:
            return
        for prepared in self._task_confirmations.sweep_expired():
            await self._task_runtime.cancel_prepared(prepared)


def _preview_text(challenge: TaskConfirmationChallenge) -> str:
    token = challenge.confirmation_token.get_secret_value()
    return (
        "Предпросмотр локальной задачи (fake-worker):\n"
        f"{challenge.instruction_preview}\n\n"
        f"Task: {challenge.task_id}\n"
        f"Подтвердить: /confirm {token}\n"
        f"Отменить: /cancel {token}\n"
        "Код одноразовый и действует 5 минут. Live Codex не запускается."
    )


def _command(text: str) -> str:
    parts = text.split(maxsplit=1)
    token = parts[0].casefold() if parts else ""
    return token.split("@", 1)[0]


def _argument(text: str) -> str:
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) == 2 else ""
