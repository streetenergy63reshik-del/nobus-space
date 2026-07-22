"""Minimal authenticated Telegram control-plane for MVP-1 activation."""

from __future__ import annotations

from typing import Any, Protocol

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

    _STATUS = (
        "Nobus Space MVP-1\n"
        "Telegram: online\n"
        "Owner binding: active\n"
        "Task executor: pre-live"
    )
    _HELP = (
        "Доступные команды:\n"
        "/status — состояние оркестратора\n"
        "/help — список команд\n"
        "Голосовые команды и выполнение задач подключаются следующим этапом."
    )
    _VOICE_PENDING = (
        "Голосовое сообщение принято доверенной границей, "
        "но live-транскрибация ещё не активирована."
    )
    _UNSUPPORTED = "Команда пока не поддерживается. Используйте /status или /help."

    def __init__(self, gateway: TelegramGateway, api: TelegramReplyApi) -> None:
        if not isinstance(gateway, TelegramGateway) or not callable(
            getattr(api, "send_message", None)
        ):
            raise ValueError("Telegram control-plane configuration is invalid")
        self._gateway = gateway
        self._api = api

    async def handle(self, update: dict[str, Any]) -> bool:
        """Acknowledge every bounded update; reply only after exact binding."""

        ingress = self._gateway.process_update(update)
        if ingress.status is not IngressStatus.ACCEPTED or ingress.payload is None:
            return True
        payload = ingress.payload
        if isinstance(payload, TextMessage):
            command = _command(payload.text)
            if command == "/status":
                response = self._STATUS
            elif command in {"/help", "/start"}:
                response = self._HELP
            else:
                response = self._UNSUPPORTED
            await self._api.send_message(payload.chat_id, response)
        elif isinstance(payload, VoiceMessage):
            await self._api.send_message(payload.chat_id, self._VOICE_PENDING)
        return True


def _command(text: str) -> str:
    token = text.split(maxsplit=1)[0].casefold() if text.split(maxsplit=1) else ""
    return token.split("@", 1)[0]
