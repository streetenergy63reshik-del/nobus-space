"""Actor-bound one-shot confirmation for an in-memory text task preview."""

from __future__ import annotations

import hashlib
import re
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from src.application.durable_runtime import PreparedTask
from src.contracts import TrustedIngressEnvelope
from src.contracts.models import canonical_json_digest
from src.core.policy import task_contract_digest
from src.transport.telegram import (
    CallbackQuery,
    IngressStatus,
    TextMessage,
    TrustedIngressResult,
    VoiceMessage,
)


TaskRequestMessage = TextMessage | VoiceMessage
TaskActionMessage = TextMessage | CallbackQuery
TaskBoundMessage = TaskRequestMessage | CallbackQuery


DEFAULT_TASK_CONFIRMATION_TTL_SECONDS = 300
MAX_TASK_CONFIRMATION_TTL_SECONDS = 900
MAX_TASK_CONFIRMATION_ENTRIES = 1_000
TASK_CONFIRMATION_RETENTION_SECONDS = 3_600
MAX_TASK_INSTRUCTION_LENGTH = 2_000
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")


def _token_digest(token: str) -> str:
    return f"sha256:{hashlib.sha256(token.encode('utf-8')).hexdigest()}"


class TaskConfirmationChallenge(BaseModel):
    """Short-lived capability shown only in the bound owner chat."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    confirmation_token: SecretStr
    task_id: UUID
    contract_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    instruction_preview: str = Field(min_length=1, max_length=MAX_TASK_INSTRUCTION_LENGTH)
    issued_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def validate_challenge(self) -> "TaskConfirmationChallenge":
        for value in (self.issued_at, self.expires_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("confirmation timestamps must be timezone-aware")
        if not 0 < (self.expires_at - self.issued_at).total_seconds() <= MAX_TASK_CONFIRMATION_TTL_SECONDS:
            raise ValueError("confirmation lifetime is invalid")
        if _TOKEN_RE.fullmatch(self.confirmation_token.get_secret_value()) is None:
            raise ValueError("confirmation token is invalid")
        return self


class TaskConfirmationStatus(str, Enum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    ALREADY_USED = "already_used"
    REJECTED = "rejected"


@dataclass(frozen=True, repr=False)
class TaskConfirmationResult:
    status: TaskConfirmationStatus
    prepared: PreparedTask | None
    envelope: TrustedIngressEnvelope | None


@dataclass(frozen=True, repr=False)
class _Binding:
    prepared: PreparedTask
    envelope: TrustedIngressEnvelope
    tenant_id: str
    actor_identity: str
    actor_role: str
    auth_context_ref: str
    user_id: int
    chat_id: int
    request_key: tuple[str, str]
    request_digest: str
    instruction: str
    token: SecretStr
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class _Tombstone:
    tenant_id: str
    actor_identity: str
    actor_role: str
    auth_context_ref: str
    user_id: int
    chat_id: int
    replay_until: datetime


class InMemoryTaskConfirmationStore:
    """Bounded capability store; raw instruction/token never reach SQLite."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        token_factory: Callable[[], str] = lambda: secrets.token_urlsafe(32),
        max_entries: int = MAX_TASK_CONFIRMATION_ENTRIES,
        max_entries_per_tenant: int = 100,
        retention_seconds: int = TASK_CONFIRMATION_RETENTION_SECONDS,
    ) -> None:
        if type(max_entries) is not int or not 1 <= max_entries <= 100_000:
            raise ValueError("max_entries is invalid")
        if (
            type(max_entries_per_tenant) is not int
            or not 1 <= max_entries_per_tenant <= max_entries
        ):
            raise ValueError("tenant entry limit is invalid")
        if type(retention_seconds) is not int or not 1 <= retention_seconds <= 86_400:
            raise ValueError("retention_seconds is invalid")
        self._clock = clock
        self._token_factory = token_factory
        self._max_entries = max_entries
        self._max_entries_per_tenant = max_entries_per_tenant
        self._retention = timedelta(seconds=retention_seconds)
        self._entries: dict[str, _Binding] = {}
        self._requests: dict[tuple[str, str], str] = {}
        self._tombstones: dict[str, _Tombstone] = {}
        self._last_seen_at: datetime | None = None
        self._lock = threading.Lock()

    def challenge_for(
        self, message: TaskRequestMessage, envelope: TrustedIngressEnvelope
    ) -> TaskConfirmationChallenge | None:
        trusted = self._trusted(message, envelope)
        if trusted is None:
            return None
        with self._lock:
            now = self._safe_now_locked()
            if now is None:
                return None
            self._sweep_locked(now)
            digest = self._requests.get((message.tenant_id, envelope.idempotency_key))
            binding = self._entries.get(digest or "")
            if binding is None or not self._actor_matches(binding, message, envelope):
                return None
            return self._challenge(binding)

    def issue(
        self,
        *,
        message: TaskRequestMessage,
        envelope: TrustedIngressEnvelope,
        prepared: PreparedTask,
        ttl_seconds: int = DEFAULT_TASK_CONFIRMATION_TTL_SECONDS,
    ) -> TaskConfirmationChallenge:
        if (
            type(ttl_seconds) is not int
            or not 1 <= ttl_seconds <= MAX_TASK_CONFIRMATION_TTL_SECONDS
        ):
            raise ValueError("ttl_seconds is invalid")
        trusted = self._trusted(message, envelope)
        if trusted is None:
            raise ValueError("trusted task preview is invalid")
        try:
            prepared = PreparedTask.validate(prepared)
            contract = prepared.contract
            instruction = contract.instruction
            valid = (
                0 < len(instruction) <= MAX_TASK_INSTRUCTION_LENGTH
                and instruction == instruction.strip()
                and "\x00" not in instruction
                and contract.tenant_id == message.tenant_id == envelope.tenant_id
                and contract.idempotency_key == envelope.idempotency_key
                and contract.ingress_digest == envelope.envelope_revision
                and prepared.envelope_revision == envelope.envelope_revision
            )
        except Exception:
            valid = False
        if not valid:
            raise ValueError("trusted task preview is invalid")
        contract_digest = task_contract_digest(contract)
        request_key = (message.tenant_id, envelope.idempotency_key)
        request_digest = canonical_json_digest(
            {
                "auth_context_ref": message.auth_context_ref,
                "contract_digest": contract_digest,
                "request_key": request_key,
                "user_id": message.user_id,
                "chat_id": message.chat_id,
            }
        )
        with self._lock:
            now = self._now_locked()
            if now < envelope.received_at.astimezone(UTC):
                raise ValueError("clock moved backwards")
            self._sweep_locked(now)
            existing_digest = self._requests.get(request_key)
            existing = self._entries.get(existing_digest or "")
            if existing is not None:
                if existing.request_digest != request_digest:
                    raise RuntimeError("task confirmation request conflicts")
                return self._challenge(existing)
            retained = len(self._entries) + len(self._tombstones)
            retained_for_tenant = sum(
                item.tenant_id == message.tenant_id
                for item in (*self._entries.values(), *self._tombstones.values())
            )
            if retained >= self._max_entries:
                raise RuntimeError("task confirmation capacity exceeded")
            if retained_for_tenant >= self._max_entries_per_tenant:
                raise RuntimeError("tenant task confirmation capacity exceeded")
            for _ in range(3):
                try:
                    token = self._token_factory()
                except Exception:
                    raise RuntimeError("task confirmation token factory failed") from None
                if not isinstance(token, str) or _TOKEN_RE.fullmatch(token) is None:
                    raise RuntimeError("task confirmation token factory failed")
                digest = _token_digest(token)
                if digest in self._entries or digest in self._tombstones:
                    continue
                binding = _Binding(
                    prepared=prepared,
                    envelope=TrustedIngressEnvelope.model_validate(
                        envelope.model_dump(mode="json")
                    ),
                    tenant_id=message.tenant_id,
                    actor_identity=message.actor_identity,
                    actor_role=message.actor_role,
                    auth_context_ref=message.auth_context_ref,
                    user_id=message.user_id,
                    chat_id=message.chat_id,
                    request_key=request_key,
                    request_digest=request_digest,
                    instruction=instruction,
                    token=SecretStr(token),
                    issued_at=now,
                    expires_at=now + timedelta(seconds=ttl_seconds),
                )
                self._entries[digest] = binding
                self._requests[request_key] = digest
                return self._challenge(binding)
            raise RuntimeError("task confirmation token collision")

    def consume(
        self,
        *,
        token: str,
        action: TaskConfirmationStatus,
        message: TaskActionMessage,
        envelope: TrustedIngressEnvelope,
    ) -> TaskConfirmationResult:
        if (
            type(action) is not TaskConfirmationStatus
            or action not in {
                TaskConfirmationStatus.CONFIRMED,
                TaskConfirmationStatus.CANCELLED,
            }
            or not isinstance(token, str)
            or _TOKEN_RE.fullmatch(token) is None
        ):
            return self._result(TaskConfirmationStatus.REJECTED)
        if self._trusted(message, envelope) is None:
            return self._result(TaskConfirmationStatus.REJECTED)
        digest = _token_digest(token)
        with self._lock:
            now = self._safe_now_locked()
            if now is None:
                return self._result(TaskConfirmationStatus.REJECTED)
            tombstone = self._tombstones.get(digest)
            if tombstone is not None:
                if self._actor_matches(tombstone, message, envelope):
                    return self._result(TaskConfirmationStatus.ALREADY_USED)
                return self._result(TaskConfirmationStatus.REJECTED)
            binding = self._entries.get(digest)
            if binding is None or not self._actor_matches(binding, message, envelope):
                return self._result(TaskConfirmationStatus.REJECTED)
            received_at = envelope.received_at.astimezone(UTC)
            if not binding.issued_at <= received_at <= now:
                return self._result(TaskConfirmationStatus.REJECTED)
            if now >= binding.expires_at:
                self._consume_locked(digest, binding, now)
                return TaskConfirmationResult(
                    TaskConfirmationStatus.EXPIRED,
                    binding.prepared,
                    binding.envelope,
                )
            self._consume_locked(digest, binding, now)
            return TaskConfirmationResult(
                action, binding.prepared, binding.envelope
            )

    def sweep_expired(self) -> tuple[PreparedTask, ...]:
        with self._lock:
            now = self._safe_now_locked()
            if now is None:
                return ()
            return tuple(self._sweep_locked(now))

    def _consume_locked(self, digest: str, binding: _Binding, now: datetime) -> None:
        self._entries.pop(digest, None)
        self._requests.pop(binding.request_key, None)
        self._tombstones[digest] = _Tombstone(
            tenant_id=binding.tenant_id,
            actor_identity=binding.actor_identity,
            actor_role=binding.actor_role,
            auth_context_ref=binding.auth_context_ref,
            user_id=binding.user_id,
            chat_id=binding.chat_id,
            replay_until=now + self._retention,
        )

    def _sweep_locked(self, now: datetime) -> list[PreparedTask]:
        expired: list[PreparedTask] = []
        for digest, binding in tuple(self._entries.items()):
            if now >= binding.expires_at:
                expired.append(binding.prepared)
                self._consume_locked(digest, binding, now)
        for digest, tombstone in tuple(self._tombstones.items()):
            if now >= tombstone.replay_until:
                del self._tombstones[digest]
        return expired

    def _now_locked(self) -> datetime:
        try:
            value = self._clock()
        except Exception:
            raise ValueError("task confirmation clock is unavailable") from None
        if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("task confirmation clock is unavailable")
        value = value.astimezone(UTC)
        if self._last_seen_at is not None and value < self._last_seen_at:
            raise ValueError("task confirmation clock moved backwards")
        self._last_seen_at = value
        return value

    def _safe_now_locked(self) -> datetime | None:
        try:
            return self._now_locked()
        except ValueError:
            return None

    @staticmethod
    def _trusted(
        message: TaskBoundMessage, envelope: TrustedIngressEnvelope
    ) -> TrustedIngressResult | None:
        try:
            if type(message) is TextMessage:
                payload = TextMessage.model_validate(message.model_dump(mode="json"))
            elif type(message) is VoiceMessage:
                payload = VoiceMessage.model_validate(message.model_dump(mode="json"))
            elif type(message) is CallbackQuery:
                payload = CallbackQuery.model_validate(message.model_dump(mode="json"))
            else:
                return None
            return TrustedIngressResult(
                status=IngressStatus.ACCEPTED,
                update_id=message.update_id,
                payload=payload,
                envelope=TrustedIngressEnvelope.model_validate(
                    envelope.model_dump(mode="json")
                ),
            )
        except Exception:
            return None

    @staticmethod
    def _actor_matches(
        binding: _Binding | _Tombstone,
        message: TaskActionMessage,
        envelope: TrustedIngressEnvelope,
    ) -> bool:
        return (
            binding.tenant_id == message.tenant_id == envelope.tenant_id
            and binding.actor_identity == message.actor_identity == envelope.actor_identity
            and binding.actor_role == message.actor_role
            and binding.auth_context_ref == message.auth_context_ref == envelope.auth_context_ref
            and binding.user_id == message.user_id
            and binding.chat_id == message.chat_id
        )

    @staticmethod
    def _challenge(binding: _Binding) -> TaskConfirmationChallenge:
        return TaskConfirmationChallenge(
            confirmation_token=binding.token,
            task_id=binding.prepared.contract.task_id,
            contract_digest=task_contract_digest(binding.prepared.contract),
            instruction_preview=binding.instruction,
            issued_at=binding.issued_at,
            expires_at=binding.expires_at,
        )

    @staticmethod
    def _result(status: TaskConfirmationStatus) -> TaskConfirmationResult:
        return TaskConfirmationResult(status, None, None)
