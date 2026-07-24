"""Actor-bound one-shot actions for Telegram inline buttons."""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum

from src.transport.telegram import CallbackQuery


class TelegramAction(str, Enum):
    CONFIRM_VOICE = "confirm_voice"
    CANCEL_VOICE = "cancel_voice"
    APPLY_PATCH = "apply_patch"
    REJECT_PATCH = "reject_patch"
    APPLY_ARTIFACT = "apply_artifact"
    REJECT_ARTIFACT = "reject_artifact"
    APPLY_DOWNLOAD = "apply_download"
    REJECT_DOWNLOAD = "reject_download"
    RUN_NETWORK = "run_network"
    REJECT_NETWORK = "reject_network"


@dataclass(frozen=True)
class ClaimedTelegramAction:
    action: TelegramAction
    capability_token: str


@dataclass(frozen=True)
class _Binding:
    action: TelegramAction
    capability_token: str
    user_id: int
    chat_id: int
    expires_at: datetime


class InMemoryTelegramActionStore:
    """Issue callback tokens and consume them only after gateway validation."""

    def __init__(self) -> None:
        self._issued: dict[str, _Binding] = {}
        self._claimed: set[str] = set()
        self._reserved: set[str] = set()
        self._lock = threading.Lock()

    def issue(
        self,
        *,
        action: TelegramAction,
        capability_token: str,
        user_id: int,
        chat_id: int,
        ttl_seconds: int,
    ) -> str:
        if (
            type(action) is not TelegramAction
            or not isinstance(capability_token, str)
            or not capability_token
            or type(user_id) is not int
            or type(chat_id) is not int
            or type(ttl_seconds) is not int
            or not 1 <= ttl_seconds <= 900
        ):
            raise ValueError("Telegram action configuration is invalid")
        now = datetime.now(UTC)
        with self._lock:
            self._expire(now)
            for _ in range(8):
                token = secrets.token_urlsafe(24)
                if token not in self._issued:
                    self._issued[token] = _Binding(
                        action, capability_token, user_id, chat_id,
                        now + timedelta(seconds=ttl_seconds),
                    )
                    return token
        raise RuntimeError("Telegram action token is unavailable")

    def claim(self, token: str, user_id: int, chat_id: int) -> bool:
        now = datetime.now(UTC)
        with self._lock:
            self._expire(now)
            binding = self._issued.get(token)
            if (
                binding is None
                or binding.user_id != user_id
                or binding.chat_id != chat_id
                or token in self._claimed
            ):
                return False
            self._claimed.add(token)
            return True

    def consume(self, callback: CallbackQuery) -> ClaimedTelegramAction | None:
        if type(callback) is not CallbackQuery:
            return None
        now = datetime.now(UTC)
        with self._lock:
            self._expire(now)
            token = callback.callback_token
            binding = self._issued.get(token)
            if (
                binding is None
                or token not in self._claimed
                or token in self._reserved
                or binding.user_id != callback.user_id
                or binding.chat_id != callback.chat_id
            ):
                return None
            self._reserved.add(token)
            return ClaimedTelegramAction(binding.action, binding.capability_token)

    def commit(self, callback: CallbackQuery) -> bool:
        """Permanently consume an action after its effect is durable."""
        if type(callback) is not CallbackQuery:
            return False
        with self._lock:
            token = callback.callback_token
            binding = self._issued.get(token)
            if (
                binding is None
                or token not in self._reserved
                or binding.user_id != callback.user_id
                or binding.chat_id != callback.chat_id
            ):
                return False
            self._issued.pop(token, None)
            self._claimed.discard(token)
            self._reserved.discard(token)
            return True

    def release(self, callback: CallbackQuery) -> bool:
        """Allow a fresh gateway claim after a pre-durable failure."""
        if type(callback) is not CallbackQuery:
            return False
        with self._lock:
            token = callback.callback_token
            binding = self._issued.get(token)
            if (
                binding is None
                or token not in self._reserved
                or binding.user_id != callback.user_id
                or binding.chat_id != callback.chat_id
            ):
                return False
            self._reserved.discard(token)
            self._claimed.discard(token)
            return True

    def _expire(self, now: datetime) -> None:
        expired = [
            token
            for token, binding in self._issued.items()
            if binding.expires_at <= now and token not in self._reserved
        ]
        for token in expired:
            self._issued.pop(token, None)
            self._claimed.discard(token)
            self._reserved.discard(token)
