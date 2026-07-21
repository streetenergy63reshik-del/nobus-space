"""Actor-bound single-use confirmation for one voice preview."""

from __future__ import annotations

import hashlib
import re
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from src.contracts import TrustedIngressEnvelope
from src.contracts.models import canonical_json_digest
from src.transport.telegram import (
    CallbackQuery,
    IngressStatus,
    TrustedIngressResult,
    VoiceMessage,
)

from .base import VoicePreview


DEFAULT_CONFIRMATION_TTL_SECONDS = 300
MAX_CONFIRMATION_TTL_SECONDS = 900
MAX_CONFIRMATION_ENTRIES = 1_000
CONFIRMED_RETENTION_SECONDS = 3_600
MAX_TRANSCRIPT_LENGTH = 4_096

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_LANGUAGE_RE = re.compile(r"^[a-z]{2,8}(?:-[a-z0-9]{1,8}){0,3}$")


def _utc(value: datetime, field_name: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _token_digest(token: str) -> str:
    return f"sha256:{hashlib.sha256(token.encode('utf-8')).hexdigest()}"


def _new_token() -> str:
    return secrets.token_urlsafe(32)


class VoiceConfirmationModel(BaseModel):
    """Strict immutable base for confirmation-boundary values."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class VoiceConfirmationChallenge(VoiceConfirmationModel):
    """Short-lived callback capability; representation masks the raw token."""

    callback_token: SecretStr
    preview_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    issued_at: datetime
    expires_at: datetime

    @field_validator("issued_at", "expires_at")
    @classmethod
    def validate_time(cls, value: datetime, info: Any) -> datetime:
        return _utc(value, info.field_name)

    @model_validator(mode="after")
    def validate_lifetime(self) -> "VoiceConfirmationChallenge":
        seconds = (self.expires_at - self.issued_at).total_seconds()
        if not 0 < seconds <= MAX_CONFIRMATION_TTL_SECONDS:
            raise ValueError("confirmation challenge lifetime is invalid")
        token = self.callback_token.get_secret_value()
        if _TOKEN_RE.fullmatch(token) is None:
            raise ValueError("callback token is invalid")
        return self


class ConfirmedVoicePreview(VoiceConfirmationModel):
    """Voice text confirmed by the exact actor who created its preview."""

    tenant_id: str = Field(min_length=1, max_length=128)
    actor_identity: str = Field(min_length=1, max_length=128)
    actor_role: str = Field(min_length=1, max_length=128)
    auth_context_ref: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    user_id: int
    chat_id: int
    voice_envelope_revision: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    voice_content_ref: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    audio_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    transcript: str = Field(min_length=1, max_length=MAX_TRANSCRIPT_LENGTH)
    transcript_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    language: str | None = Field(default=None, max_length=35)
    confidence: float | None = Field(default=None, ge=0, le=1)
    confirmed_at: datetime
    callback_token_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @field_validator("tenant_id", "actor_identity", "actor_role", "transcript")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("required text must not be empty")
        return normalized

    @field_validator("confirmed_at")
    @classmethod
    def validate_confirmed_at(cls, value: datetime) -> datetime:
        return _utc(value, "confirmed_at")


class VoiceConfirmationStatus(str, Enum):
    """Safe public result of a confirmation attempt."""

    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    ALREADY_USED = "already_used"


class VoiceConfirmationResult(VoiceConfirmationModel):
    """Confirmation result without raw token, audio, path, or exception text."""

    status: VoiceConfirmationStatus
    confirmation: ConfirmedVoicePreview | None = None
    message: str

    @model_validator(mode="after")
    def validate_confirmation(self) -> "VoiceConfirmationResult":
        has_confirmation = self.confirmation is not None
        if has_confirmation != (self.status is VoiceConfirmationStatus.CONFIRMED):
            raise ValueError("confirmation payload does not match status")
        return self


class _TokenState(str, Enum):
    ISSUED = "issued"
    CALLBACK_CLAIMED = "callback_claimed"
    CONFIRMED = "confirmed"


@dataclass(frozen=True)
class _PreviewBinding:
    tenant_id: str
    actor_identity: str
    actor_role: str
    auth_context_ref: str
    user_id: int
    chat_id: int
    voice_envelope_revision: str
    voice_content_ref: str
    audio_sha256: str
    transcript: str
    transcript_digest: str
    preview_digest: str
    language: str | None
    confidence: float | None
    issued_at: datetime
    expires_at: datetime


@dataclass
class _Entry:
    binding: _PreviewBinding
    state: _TokenState = _TokenState.ISSUED


@dataclass(frozen=True)
class _Tombstone:
    tenant_id: str
    actor_identity: str
    actor_role: str
    auth_context_ref: str
    user_id: int
    chat_id: int
    preview_digest: str
    replay_until: datetime


class InMemoryVoiceConfirmationStore:
    """Local confirmation store and Telegram ``CallbackTokenStore``.

    The gateway calls :meth:`claim` first. The application then supplies the
    resulting trusted callback to :meth:`confirm`. Both operations share one
    state machine, so there is no second independent token claim.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        token_factory: Callable[[], str] = _new_token,
        max_entries: int = MAX_CONFIRMATION_ENTRIES,
        max_active_entries_per_tenant: int | None = None,
        confirmed_retention_seconds: int = CONFIRMED_RETENTION_SECONDS,
        max_confirmed_entries: int = MAX_CONFIRMATION_ENTRIES,
        max_confirmed_entries_per_tenant: int | None = None,
    ) -> None:
        if type(max_entries) is not int or not 1 <= max_entries <= 100_000:
            raise ValueError("max_entries must be between 1 and 100000")
        active_tenant_limit = (
            min(100, max_entries)
            if max_active_entries_per_tenant is None
            else max_active_entries_per_tenant
        )
        if (
            type(active_tenant_limit) is not int
            or not 1 <= active_tenant_limit <= max_entries
        ):
            raise ValueError("tenant active limit is invalid")
        if (
            type(confirmed_retention_seconds) is not int
            or not 1 <= confirmed_retention_seconds <= 86_400
        ):
            raise ValueError("confirmed retention must be between 1 and 86400")
        if (
            type(max_confirmed_entries) is not int
            or not 1 <= max_confirmed_entries <= 100_000
        ):
            raise ValueError("max_confirmed_entries must be between 1 and 100000")
        confirmed_tenant_limit = (
            min(100, max_confirmed_entries)
            if max_confirmed_entries_per_tenant is None
            else max_confirmed_entries_per_tenant
        )
        if (
            type(confirmed_tenant_limit) is not int
            or not 1 <= confirmed_tenant_limit <= max_confirmed_entries
        ):
            raise ValueError("tenant tombstone limit is invalid")
        self._clock = clock
        self._token_factory = token_factory
        self._max_entries = max_entries
        self._max_active_per_tenant = active_tenant_limit
        self._confirmed_retention = timedelta(seconds=confirmed_retention_seconds)
        self._max_confirmed_entries = max_confirmed_entries
        self._max_confirmed_per_tenant = confirmed_tenant_limit
        self._entries: dict[str, _Entry] = {}
        self._tombstones: dict[str, _Tombstone] = {}
        self._last_seen_at: datetime | None = None
        self._lock = threading.Lock()

    def issue(
        self,
        *,
        message: VoiceMessage,
        envelope: TrustedIngressEnvelope,
        preview: VoicePreview,
        ttl_seconds: int = DEFAULT_CONFIRMATION_TTL_SECONDS,
    ) -> VoiceConfirmationChallenge:
        """Issue one capability bound to an exact trusted voice preview."""
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= MAX_CONFIRMATION_TTL_SECONDS:
            raise ValueError("ttl_seconds must be between 1 and 900")
        validation_failed = False
        try:
            validated_message = VoiceMessage.model_validate(
                message.model_dump(mode="json")
            )
            validated_envelope = TrustedIngressEnvelope.model_validate(
                envelope.model_dump(mode="json")
            )
            trusted = TrustedIngressResult(
                status=IngressStatus.ACCEPTED,
                update_id=validated_message.update_id,
                payload=validated_message,
                envelope=validated_envelope,
            )
            validated_preview = VoicePreview.model_validate(preview.model_dump())
        except Exception:
            validation_failed = True
        if validation_failed:
            raise ValueError("trusted voice preview is invalid")
        if not isinstance(trusted.payload, VoiceMessage):  # pragma: no cover
            raise ValueError("trusted voice preview is invalid")
        transcript = validated_preview.transcript
        if (
            not transcript
            or transcript != transcript.strip()
            or len(transcript) > MAX_TRANSCRIPT_LENGTH
        ):
            raise ValueError("preview transcript is invalid")
        if _SHA256_RE.fullmatch(validated_preview.sha256) is None:
            raise ValueError("preview audio digest is invalid")
        language = validated_preview.language
        if language is not None:
            language = language.strip().lower()
            if _LANGUAGE_RE.fullmatch(language) is None:
                raise ValueError("preview language is invalid")
        transcript_digest = canonical_json_digest({"transcript": transcript})
        preview_digest = canonical_json_digest(
            {
                "audio_sha256": validated_preview.sha256,
                "language": language,
                "confidence": validated_preview.confidence,
                "size": validated_preview.size,
                "transcript_digest": transcript_digest,
                "voice_content_ref": validated_envelope.content_ref,
                "voice_envelope_revision": validated_envelope.envelope_revision,
            }
        )
        with self._lock:
            now = self._now_locked()
            if now < validated_envelope.received_at.astimezone(UTC):
                raise ValueError("clock moved backwards")
            self._sweep_locked(now)
            if any(
                entry.binding.preview_digest == preview_digest
                for entry in self._entries.values()
            ) or any(
                tombstone.preview_digest == preview_digest
                for tombstone in self._tombstones.values()
            ):
                raise RuntimeError("voice confirmation already issued")
            active_for_tenant = sum(
                entry.binding.tenant_id == validated_message.tenant_id
                for entry in self._entries.values()
            )
            retained_for_tenant = active_for_tenant + sum(
                tombstone.tenant_id == validated_message.tenant_id
                for tombstone in self._tombstones.values()
            )
            if active_for_tenant >= self._max_active_per_tenant:
                raise RuntimeError("tenant voice confirmation capacity exceeded")
            if len(self._entries) >= self._max_entries:
                raise RuntimeError("voice confirmation capacity exceeded")
            if (
                len(self._entries) + len(self._tombstones)
                >= self._max_confirmed_entries
                or retained_for_tenant >= self._max_confirmed_per_tenant
            ):
                raise RuntimeError("voice confirmation retention capacity exceeded")
            binding = _PreviewBinding(
                tenant_id=validated_message.tenant_id,
                actor_identity=validated_message.actor_identity,
                actor_role=validated_message.actor_role,
                auth_context_ref=validated_message.auth_context_ref,
                user_id=validated_message.user_id,
                chat_id=validated_message.chat_id,
                voice_envelope_revision=validated_envelope.envelope_revision,
                voice_content_ref=validated_envelope.content_ref,
                audio_sha256=validated_preview.sha256,
                transcript=transcript,
                transcript_digest=transcript_digest,
                preview_digest=preview_digest,
                language=language,
                confidence=validated_preview.confidence,
                issued_at=now,
                expires_at=now + timedelta(seconds=ttl_seconds),
            )
            for _ in range(3):
                token_failed = False
                token: object | None = None
                try:
                    token = self._token_factory()
                except Exception:
                    token_failed = True
                if token_failed:
                    raise RuntimeError("voice confirmation token factory failed")
                if not isinstance(token, str) or _TOKEN_RE.fullmatch(token) is None:
                    raise RuntimeError("voice confirmation token factory failed")
                digest = _token_digest(token)
                if digest not in self._entries and digest not in self._tombstones:
                    self._entries[digest] = _Entry(binding=binding)
                    return VoiceConfirmationChallenge(
                        callback_token=SecretStr(token),
                        preview_digest=preview_digest,
                        issued_at=now,
                        expires_at=binding.expires_at,
                    )
            raise RuntimeError("voice confirmation token collision")

    def claim(self, token: str, user_id: int, chat_id: int) -> bool:
        """Atomically reserve an issued token for one gateway callback."""
        if (
            not isinstance(token, str)
            or _TOKEN_RE.fullmatch(token) is None
            or type(user_id) is not int
            or type(chat_id) is not int
        ):
            return False
        with self._lock:
            now = self._safe_now_locked()
            if now is None:
                return False
            self._sweep_locked(now)
            entry = self._entries.get(_token_digest(token))
            if (
                entry is None
                or entry.state is not _TokenState.ISSUED
                or entry.binding.user_id != user_id
                or entry.binding.chat_id != chat_id
                or not entry.binding.issued_at <= now < entry.binding.expires_at
            ):
                return False
            entry.state = _TokenState.CALLBACK_CLAIMED
            return True

    def confirm(
        self,
        *,
        callback: CallbackQuery,
        envelope: TrustedIngressEnvelope,
    ) -> VoiceConfirmationResult:
        """Confirm a gateway-claimed callback once with exact actor binding."""
        try:
            callback = CallbackQuery.model_validate(callback.model_dump(mode="json"))
            envelope = TrustedIngressEnvelope.model_validate(
                envelope.model_dump(mode="json")
            )
            trusted = TrustedIngressResult(
                status=IngressStatus.ACCEPTED,
                update_id=callback.update_id,
                payload=callback,
                envelope=envelope,
            )
        except Exception:
            return self._rejected()
        if not isinstance(trusted.payload, CallbackQuery):  # pragma: no cover
            return self._rejected()
        digest = _token_digest(callback.callback_token)
        with self._lock:
            now = self._safe_now_locked()
            if now is None:
                return self._rejected()
            self._sweep_locked(now)
            tombstone = self._tombstones.get(digest)
            if tombstone is not None:
                if (
                    envelope.received_at.astimezone(UTC) <= now
                    and self._actor_matches(tombstone, callback, envelope)
                ):
                    return VoiceConfirmationResult(
                        status=VoiceConfirmationStatus.ALREADY_USED,
                        message="Voice preview was already confirmed.",
                    )
                return self._rejected()
            entry = self._entries.get(digest)
            if entry is None or not self._actor_matches(
                entry.binding, callback, envelope
            ):
                return self._rejected()
            binding = entry.binding
            if not binding.issued_at <= envelope.received_at.astimezone(UTC) <= now:
                return self._rejected()
            if not binding.issued_at <= now < binding.expires_at:
                return self._rejected()
            if entry.state is not _TokenState.CALLBACK_CLAIMED:
                return self._rejected()
            confirmed = ConfirmedVoicePreview(
                tenant_id=binding.tenant_id,
                actor_identity=binding.actor_identity,
                actor_role=binding.actor_role,
                auth_context_ref=binding.auth_context_ref,
                user_id=binding.user_id,
                chat_id=binding.chat_id,
                voice_envelope_revision=binding.voice_envelope_revision,
                voice_content_ref=binding.voice_content_ref,
                audio_sha256=binding.audio_sha256,
                transcript=binding.transcript,
                transcript_digest=binding.transcript_digest,
                language=binding.language,
                confidence=binding.confidence,
                confirmed_at=now,
                callback_token_digest=digest,
            )
            del self._entries[digest]
            self._add_tombstone_locked(digest, binding, now)
            return VoiceConfirmationResult(
                status=VoiceConfirmationStatus.CONFIRMED,
                confirmation=confirmed,
                message="Voice preview confirmed.",
            )

    def sweep_expired(self, now: datetime | None = None) -> int:
        """Remove expired active entries and bounded replay tombstones."""
        with self._lock:
            timestamp = (
                self._observe_time_locked(now)
                if now is not None
                else self._now_locked()
            )
            return self._sweep_locked(timestamp)

    def _now_locked(self) -> datetime:
        clock_failed = False
        value: datetime | None = None
        try:
            value = self._clock()
        except Exception:
            clock_failed = True
        if clock_failed or value is None:
            raise ValueError("voice confirmation clock is invalid")
        return self._observe_time_locked(value)

    def _safe_now_locked(self) -> datetime | None:
        try:
            return self._observe_time_locked(self._clock())
        except Exception:
            return None

    def _observe_time_locked(self, value: datetime) -> datetime:
        timestamp = _utc(value, "clock")
        if self._last_seen_at is not None and timestamp < self._last_seen_at:
            raise ValueError("clock moved backwards")
        self._last_seen_at = timestamp
        return timestamp

    def _sweep_locked(self, now: datetime) -> int:
        removed = 0
        for digest, entry in tuple(self._entries.items()):
            if now >= entry.binding.expires_at:
                del self._entries[digest]
                removed += 1
        for digest, tombstone in tuple(self._tombstones.items()):
            if now >= tombstone.replay_until:
                del self._tombstones[digest]
                removed += 1
        return removed

    def _add_tombstone_locked(
        self, digest: str, binding: _PreviewBinding, confirmed_at: datetime
    ) -> None:
        tenant_count = sum(
            tombstone.tenant_id == binding.tenant_id
            for tombstone in self._tombstones.values()
        )
        if (
            digest in self._tombstones
            or len(self._tombstones) >= self._max_confirmed_entries
            or tenant_count >= self._max_confirmed_per_tenant
        ):
            raise RuntimeError("voice confirmation retention invariant failed")
        self._tombstones[digest] = _Tombstone(
            tenant_id=binding.tenant_id,
            actor_identity=binding.actor_identity,
            actor_role=binding.actor_role,
            auth_context_ref=binding.auth_context_ref,
            user_id=binding.user_id,
            chat_id=binding.chat_id,
            preview_digest=binding.preview_digest,
            replay_until=confirmed_at + self._confirmed_retention,
        )

    @staticmethod
    def _actor_matches(
        binding: _PreviewBinding | _Tombstone,
        callback: CallbackQuery,
        envelope: TrustedIngressEnvelope,
    ) -> bool:
        return (
            binding.tenant_id == callback.tenant_id == envelope.tenant_id
            and binding.actor_identity
            == callback.actor_identity
            == envelope.actor_identity
            and binding.actor_role == callback.actor_role
            and binding.auth_context_ref
            == callback.auth_context_ref
            == envelope.auth_context_ref
            and binding.user_id == callback.user_id
            and binding.chat_id == callback.chat_id
        )

    @staticmethod
    def _rejected() -> VoiceConfirmationResult:
        return VoiceConfirmationResult(
            status=VoiceConfirmationStatus.REJECTED,
            message="Voice confirmation is invalid or expired.",
        )
