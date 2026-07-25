"""Isolated Telegram ingress gateway."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Protocol, TypeVar, runtime_checkable
from uuid import UUID, uuid4

from src.contracts import TrustedIngressEnvelope
from src.contracts.models import canonical_json_digest

from .models import (
    ActorBinding,
    CallbackQuery,
    IngressResult,
    IngressStatus,
    TrustedIngressResult,
    TextMessage,
    VoiceMessage,
    VoiceMetadata,
    _telegram_payload_facts,
)


ClaimValue = TypeVar("ClaimValue", int, str)
_CALLBACK_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


def _is_callback_token(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value == value.strip()
        and _CALLBACK_TOKEN_RE.fullmatch(value) is not None
        and len(value.encode("utf-8")) <= 64
    )


@runtime_checkable
class ClaimStore(Protocol[ClaimValue]):
    """Atomically claim an identifier exactly once."""

    def claim(self, value: ClaimValue) -> bool:
        """Return True only for the first successful claim."""
        ...


UpdateIdStore = ClaimStore[int]
@runtime_checkable
class CallbackTokenStore(Protocol):
    """Atomically consume a token issued for one exact actor/chat pair."""

    def claim(self, token: str, user_id: int, chat_id: int) -> bool:
        """Return True once when token and actor binding match."""
        ...


class InMemoryClaimStore(ClaimStore[ClaimValue]):
    """Thread-safe in-memory claim store intended for unit tests."""

    def __init__(self, available: Iterable[ClaimValue] | None = None) -> None:
        self._claimed: set[ClaimValue] = set()
        self._available = frozenset(available) if available is not None else None
        self._lock = threading.Lock()

    def claim(self, value: ClaimValue) -> bool:
        with self._lock:
            if self._available is not None and value not in self._available:
                return False
            if value in self._claimed:
                return False
            self._claimed.add(value)
            return True


class InMemoryUpdateIdStore(InMemoryClaimStore[int]):
    """Atomic update-id claims for tests and the local preview."""


class InMemoryCallbackTokenStore:
    """Atomic pair-bound callback-token claims for tests."""

    def __init__(self, bindings: Mapping[str, tuple[int, int]]) -> None:
        snapshot: dict[str, tuple[int, int]] = {}
        for token, pair in bindings.items():
            if not _is_callback_token(token):
                raise ValueError("callback token configuration is invalid")
            if (
                type(pair) is not tuple
                or len(pair) != 2
                or type(pair[0]) is not int
                or type(pair[1]) is not int
            ):
                raise ValueError("callback token binding must be an integer pair")
            snapshot[token] = pair
        self._bindings = MappingProxyType(snapshot)
        self._claimed: set[str] = set()
        self._lock = threading.Lock()

    def claim(self, token: str, user_id: int, chat_id: int) -> bool:
        with self._lock:
            if (
                not _is_callback_token(token)
                or type(user_id) is not int
                or type(chat_id) is not int
            ):
                return False
            if self._bindings.get(token) != (user_id, chat_id):
                return False
            if token in self._claimed:
                return False
            self._claimed.add(token)
            return True


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_non_negative_int(value: Any) -> bool:
    return _is_int(value) and value >= 0


def _is_dict(value: Any) -> bool:
    return isinstance(value, dict)


def _is_non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _rejected(update_id: int | None, reason: str) -> IngressResult:
    return IngressResult(status=IngressStatus.REJECTED, update_id=update_id, reason=reason)


def _ignored(update_id: int, reason: str) -> IngressResult:
    return IngressResult(status=IngressStatus.IGNORED, update_id=update_id, reason=reason)


class TelegramGateway:
    """Normalize already-authenticated Telegram updates without I/O."""

    def __init__(
        self,
        actor_bindings: Mapping[tuple[int, int], ActorBinding],
        update_id_store: UpdateIdStore,
        callback_token_store: CallbackTokenStore,
        max_text_length: int = 4096,
        max_voice_duration: int = 300,
        ingress_id_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        normalized: dict[tuple[int, int], ActorBinding] = {}
        for pair, binding in actor_bindings.items():
            if (
                not isinstance(pair, tuple)
                or len(pair) != 2
                or not _is_int(pair[0])
                or not _is_int(pair[1])
            ):
                raise ValueError("actor binding keys must be user/chat integer pairs")
            normalized[pair] = ActorBinding.model_validate(binding.model_dump())
        if not normalized:
            raise ValueError("at least one actor binding is required")
        if (
            isinstance(max_text_length, bool)
            or not isinstance(max_text_length, int)
            or max_text_length <= 0
        ):
            raise ValueError("max_text_length must be a positive integer")
        if (
            isinstance(max_voice_duration, bool)
            or not isinstance(max_voice_duration, int)
            or max_voice_duration <= 0
        ):
            raise ValueError("max_voice_duration must be a positive integer")
        self._actor_bindings = MappingProxyType(normalized)
        self._update_id_store = update_id_store
        self._callback_token_store = callback_token_store
        self._max_text_length = max_text_length
        self._max_voice_duration = max_voice_duration
        self._ingress_id_factory = ingress_id_factory
        self._clock = clock

    def replace_actor_bindings(
        self, actor_bindings: Mapping[tuple[int, int], ActorBinding]
    ) -> None:
        """Atomically replace the trusted binding snapshot."""
        normalized: dict[tuple[int, int], ActorBinding] = {}
        for pair, binding in actor_bindings.items():
            if (
                not isinstance(pair, tuple)
                or len(pair) != 2
                or not _is_int(pair[0])
                or not _is_int(pair[1])
            ):
                raise ValueError("actor binding keys must be user/chat integer pairs")
            normalized[pair] = ActorBinding.model_validate(binding.model_dump())
        if not normalized:
            raise ValueError("at least one actor binding is required")
        self._actor_bindings = MappingProxyType(normalized)

    def process_update(self, update: dict[str, Any]) -> TrustedIngressResult:
        """Claim one raw update and atomically mint its trusted envelope."""
        update_id = update.get("update_id") if _is_dict(update) else None
        safe_update_id = update_id if _is_non_negative_int(update_id) else None
        try:
            ingress_id = self._ingress_id_factory()
            received_at = self._clock()
            if type(ingress_id) is not UUID:
                raise ValueError("ingress id must be a UUID")
            if (
                type(received_at) is not datetime
                or received_at.tzinfo is None
                or received_at.utcoffset() is None
            ):
                raise ValueError("received time must be timezone-aware")
            received_at = received_at.astimezone(UTC)
        except Exception:
            return TrustedIngressResult.model_validate(
                _rejected(None, "trusted ingress unavailable").model_dump()
            )

        try:
            normalized = self._normalize_update(update)
            candidate = self._trusted_ingress(normalized, ingress_id, received_at)
            if safe_update_id is None:
                return candidate

            duplicate = TrustedIngressResult.model_validate(
                _rejected(safe_update_id, "duplicate update_id").model_dump()
            )
            invalid_callback = TrustedIngressResult.model_validate(
                _rejected(
                    safe_update_id, "invalid or used callback token"
                ).model_dump()
            )
            callback_claim: tuple[str, int, int] | None = None
            if (
                candidate.status == IngressStatus.ACCEPTED
                and type(candidate.payload) is CallbackQuery
            ):
                callback_claim = (
                    candidate.payload.callback_token,
                    candidate.payload.user_id,
                    candidate.payload.chat_id,
                )
        except Exception:
            return TrustedIngressResult.model_validate(
                _rejected(safe_update_id, "trusted ingress unavailable").model_dump()
            )

        if not self._update_id_store.claim(safe_update_id):
            return duplicate
        if callback_claim is not None:
            token, user_id, chat_id = callback_claim
            if not self._callback_token_store.claim(token, user_id, chat_id):
                return invalid_callback
        return candidate

    @staticmethod
    def _trusted_ingress(
        normalized: IngressResult,
        ingress_id: UUID,
        received_at: datetime,
    ) -> TrustedIngressResult:
        if normalized.status != IngressStatus.ACCEPTED:
            return TrustedIngressResult.model_validate(normalized.model_dump())
        payload = normalized.payload
        if payload is None:  # pragma: no cover - normalization invariant
            return TrustedIngressResult.model_validate(
                _rejected(
                    normalized.update_id, "trusted ingress unavailable"
                ).model_dump()
            )
        facts = _telegram_payload_facts(payload)
        envelope_data = {
            "schema_version": "1",
            "ingress_id": ingress_id,
            "tenant_id": payload.tenant_id,
            "actor_identity": payload.actor_identity,
            "auth_context_ref": payload.auth_context_ref,
            "received_at": received_at,
            **facts,
        }
        revision = canonical_json_digest(
            TrustedIngressEnvelope.model_construct(
                **envelope_data, envelope_revision="sha256:" + "0" * 64
            ).model_dump(mode="json", exclude={"envelope_revision"})
        )
        envelope = TrustedIngressEnvelope(
            **envelope_data, envelope_revision=revision
        )
        return TrustedIngressResult.model_validate(
            {**normalized.model_dump(), "envelope": envelope.model_dump()}
        )

    def _normalize_update(self, update: dict[str, Any]) -> IngressResult:
        """Normalize one raw Telegram update without mutating claim stores."""
        if not _is_dict(update):
            return _rejected(None, "update is not a dict")
        update_id = update.get("update_id")
        if not _is_non_negative_int(update_id):
            return _rejected(None, "missing or invalid update_id")
        has_message = "message" in update
        has_callback = "callback_query" in update
        if has_message and has_callback:
            return _rejected(update_id, "ambiguous update")
        if has_message:
            return self._handle_message(update_id, update["message"])
        if has_callback:
            return self._handle_callback(update_id, update["callback_query"])
        return _ignored(update_id, "unknown update type")

    def _binding(self, user_id: int, chat_id: int) -> ActorBinding | None:
        return self._actor_bindings.get((user_id, chat_id))

    def _handle_message(self, update_id: int, message: Any) -> IngressResult:
        if not _is_dict(message):
            return _rejected(update_id, "malformed message")
        from_obj = message.get("from")
        chat_obj = message.get("chat")
        if not _is_dict(from_obj) or not _is_dict(chat_obj):
            return _rejected(update_id, "malformed message")
        user_id = from_obj.get("id")
        chat_id = chat_obj.get("id")
        if not _is_int(user_id) or not _is_int(chat_id):
            return _rejected(update_id, "missing or invalid user_id/chat_id")
        binding = self._binding(user_id, chat_id)
        if binding is None:
            return _rejected(update_id, "user/chat pair not in allowlist")

        has_text = "text" in message
        has_voice = "voice" in message
        if has_text and has_voice:
            return _rejected(update_id, "ambiguous message")
        if has_text:
            return self._handle_text(update_id, message, user_id, chat_id, binding)
        if has_voice:
            return self._handle_voice(update_id, message, user_id, chat_id, binding)
        return _ignored(update_id, "unsupported message type")

    def _handle_text(
        self,
        update_id: int,
        message: dict[str, Any],
        user_id: int,
        chat_id: int,
        binding: ActorBinding,
    ) -> IngressResult:
        message_id = message.get("message_id")
        thread_id = message.get("message_thread_id")
        if not _is_int(message_id):
            return _rejected(update_id, "missing or invalid message_id")
        if thread_id is not None and (
            not _is_int(thread_id) or thread_id <= 0
        ):
            return _rejected(update_id, "invalid message_thread_id")
        raw_text = message.get("text")
        if not isinstance(raw_text, str):
            return _rejected(update_id, "invalid text type")
        text = raw_text.strip()
        if not text:
            return _rejected(update_id, "empty text")
        if len(text) > self._max_text_length:
            return _rejected(update_id, "text exceeds max length")
        return IngressResult(
            status=IngressStatus.ACCEPTED,
            update_id=update_id,
            payload=TextMessage(
                update_id=update_id,
                tenant_id=binding.tenant_id,
                actor_identity=binding.actor_identity,
                actor_role=binding.role,
                auth_context_ref=binding.auth_context_ref,
                user_id=user_id,
                chat_id=chat_id,
                message_thread_id=thread_id,
                binding_purpose=binding.purpose,
                message_id=message_id,
                text=text,
            ),
        )

    def _handle_voice(
        self,
        update_id: int,
        message: dict[str, Any],
        user_id: int,
        chat_id: int,
        binding: ActorBinding,
    ) -> IngressResult:
        message_id = message.get("message_id")
        thread_id = message.get("message_thread_id")
        if not _is_int(message_id):
            return _rejected(update_id, "missing or invalid message_id")
        if thread_id is not None and (
            not _is_int(thread_id) or thread_id <= 0
        ):
            return _rejected(update_id, "invalid message_thread_id")
        voice = message.get("voice")
        if not _is_dict(voice):
            return _rejected(update_id, "malformed voice")
        file_id = voice.get("file_id")
        if not _is_non_empty_str(file_id):
            return _rejected(update_id, "missing or invalid file_id")
        duration = voice.get("duration")
        if not _is_non_negative_int(duration) or duration > self._max_voice_duration:
            return _rejected(update_id, "voice exceeds max duration or invalid duration")

        file_unique_id = voice.get("file_unique_id")
        mime_type = voice.get("mime_type")
        file_size = voice.get("file_size")
        if file_unique_id is not None and not _is_non_empty_str(file_unique_id):
            return _rejected(update_id, "invalid voice metadata")
        if mime_type is not None and not _is_non_empty_str(mime_type):
            return _rejected(update_id, "invalid voice metadata")
        if file_size is not None and not _is_non_negative_int(file_size):
            return _rejected(update_id, "invalid voice metadata")

        return IngressResult(
            status=IngressStatus.ACCEPTED,
            update_id=update_id,
            payload=VoiceMessage(
                update_id=update_id,
                tenant_id=binding.tenant_id,
                actor_identity=binding.actor_identity,
                actor_role=binding.role,
                auth_context_ref=binding.auth_context_ref,
                user_id=user_id,
                chat_id=chat_id,
                message_thread_id=thread_id,
                binding_purpose=binding.purpose,
                message_id=message_id,
                file_id=file_id.strip(),
                duration=duration,
                metadata=VoiceMetadata(
                    file_unique_id=file_unique_id.strip() if file_unique_id else None,
                    mime_type=mime_type.strip() if mime_type else None,
                    file_size=file_size,
                ),
            ),
        )

    def _handle_callback(self, update_id: int, callback_query: Any) -> IngressResult:
        if not _is_dict(callback_query):
            return _rejected(update_id, "malformed callback_query")
        from_obj = callback_query.get("from")
        message_obj = callback_query.get("message")
        if not _is_dict(from_obj) or not _is_dict(message_obj):
            return _rejected(update_id, "malformed callback_query")
        chat_obj = message_obj.get("chat")
        if not _is_dict(chat_obj):
            return _rejected(update_id, "malformed callback_query")
        user_id = from_obj.get("id")
        chat_id = chat_obj.get("id")
        message_id = message_obj.get("message_id")
        thread_id = message_obj.get("message_thread_id")
        if thread_id is not None and (
            not _is_int(thread_id) or thread_id <= 0
        ):
            return _rejected(update_id, "invalid message_thread_id")
        if (
            not _is_int(user_id)
            or not _is_int(chat_id)
            or not _is_int(message_id)
        ):
            return _rejected(
                update_id, "missing or invalid user_id/chat_id/message_id"
            )
        binding = self._binding(user_id, chat_id)
        if binding is None:
            return _rejected(update_id, "user/chat pair not in allowlist")
        query_id = callback_query.get("id")
        if not _is_non_empty_str(query_id):
            return _rejected(update_id, "missing or invalid query_id")
        if "data" not in callback_query:
            return _ignored(update_id, "unsupported callback data")
        token = callback_query.get("data")
        if not _is_callback_token(token):
            return _rejected(update_id, "malformed callback token")
        return IngressResult(
            status=IngressStatus.ACCEPTED,
            update_id=update_id,
            payload=CallbackQuery(
                update_id=update_id,
                tenant_id=binding.tenant_id,
                actor_identity=binding.actor_identity,
                actor_role=binding.role,
                auth_context_ref=binding.auth_context_ref,
                user_id=user_id,
                chat_id=chat_id,
                message_thread_id=thread_id,
                binding_purpose=binding.purpose,
                message_id=message_id,
                query_id=query_id.strip(),
                callback_token=token,
            ),
        )
