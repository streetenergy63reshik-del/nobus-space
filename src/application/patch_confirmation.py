"""Actor-bound second confirmation for one exact model-generated patch."""

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

from src.contracts import TrustedIngressEnvelope
from src.contracts.models import canonical_json_digest
from src.transport.telegram import (
    CallbackQuery,
    IngressStatus,
    TextMessage,
    TrustedIngressResult,
)


PatchActionMessage = TextMessage | CallbackQuery


PATCH_CONFIRMATION_TTL_SECONDS = 600
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")


class PatchProposal(BaseModel):
    """In-memory exact patch binding created after read-only Codex execution."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    tenant_id: str = Field(min_length=1, max_length=128)
    task_id: UUID
    contract_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    result_revision: int = Field(ge=1)
    result_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    output_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    base_revision: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    summary: str = Field(min_length=1, max_length=1_500)
    patch: str = Field(min_length=1, max_length=16 * 1024)
    paths: tuple[str, ...] = Field(min_length=1, max_length=20)
    patch_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_digest(self) -> "PatchProposal":
        expected = canonical_json_digest(
            {
                "base_revision": self.base_revision,
                "contract_digest": self.contract_digest,
                "output_digest": self.output_digest,
                "patch": self.patch,
                "paths": self.paths,
                "result_digest": self.result_digest,
                "result_revision": self.result_revision,
                "summary": self.summary,
                "task_id": str(self.task_id),
                "tenant_id": self.tenant_id,
            }
        )
        if self.patch_digest != expected:
            raise ValueError("patch proposal digest mismatch")
        return self


class PatchConfirmationChallenge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    confirmation_token: SecretStr
    proposal: PatchProposal
    issued_at: datetime
    expires_at: datetime


class PatchConfirmationStatus(str, Enum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    ALREADY_USED = "already_used"
    REJECTED = "rejected"


@dataclass(frozen=True, repr=False)
class PatchConfirmationResult:
    status: PatchConfirmationStatus
    proposal: PatchProposal | None = None


@dataclass(frozen=True, repr=False)
class _Entry:
    proposal: PatchProposal
    token: SecretStr
    tenant_id: str
    actor_identity: str
    actor_role: str
    auth_context_ref: str
    user_id: int
    chat_id: int
    request_key: tuple[str, str]
    request_digest: str
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True, repr=False)
class _Tombstone:
    tenant_id: str
    actor_identity: str
    actor_role: str
    auth_context_ref: str
    user_id: int
    chat_id: int
    replay_until: datetime


class InMemoryPatchConfirmationStore:
    """Hold exact patch bytes only until owner apply/cancel or expiry."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        token_factory: Callable[[], str] = lambda: secrets.token_urlsafe(32),
        max_entries: int = 100,
    ) -> None:
        if not callable(clock) or not callable(token_factory) or not 1 <= max_entries <= 1_000:
            raise ValueError("patch confirmation configuration is invalid")
        self._clock = clock
        self._token_factory = token_factory
        self._max_entries = max_entries
        self._entries: dict[str, _Entry] = {}
        self._requests: dict[tuple[str, str], str] = {}
        self._tombstones: dict[str, _Tombstone] = {}
        self._lock = threading.Lock()

    def challenge_for(
        self, message: PatchActionMessage, envelope: TrustedIngressEnvelope
    ) -> PatchConfirmationChallenge | None:
        if not _trusted(message, envelope):
            return None
        with self._lock:
            now = self._now()
            self._sweep(now)
            digest = self._requests.get((message.tenant_id, envelope.idempotency_key))
            entry = self._entries.get(digest or "")
            return (
                self._challenge(entry)
                if entry and now < entry.expires_at and _actor_matches(entry, message)
                else None
            )

    def issue(
        self,
        *,
        message: PatchActionMessage,
        envelope: TrustedIngressEnvelope,
        proposal: PatchProposal,
    ) -> PatchConfirmationChallenge:
        if not _trusted(message, envelope):
            raise ValueError("patch confirmation ingress is invalid")
        proposal = PatchProposal.model_validate(proposal.model_dump(mode="python"))
        if proposal.tenant_id != message.tenant_id:
            raise ValueError("patch confirmation tenant mismatch")
        request_key = (message.tenant_id, envelope.idempotency_key)
        request_digest = canonical_json_digest(
            {
                "auth_context_ref": message.auth_context_ref,
                "patch_digest": proposal.patch_digest,
                "request_key": request_key,
                "task_id": str(proposal.task_id),
                "user_id": message.user_id,
                "chat_id": message.chat_id,
            }
        )
        with self._lock:
            now = self._now()
            self._sweep(now)
            existing = self._entries.get(self._requests.get(request_key, ""))
            if existing is not None:
                if now >= existing.expires_at:
                    raise RuntimeError("patch confirmation awaits expiry cleanup")
                if existing.request_digest != request_digest:
                    raise RuntimeError("patch confirmation request conflicts")
                return self._challenge(existing)
            if len(self._entries) + len(self._tombstones) >= self._max_entries:
                raise RuntimeError("patch confirmation capacity exceeded")
            for _ in range(3):
                token = self._token_factory()
                if not isinstance(token, str) or _TOKEN_RE.fullmatch(token) is None:
                    raise RuntimeError("patch confirmation token factory failed")
                digest = _token_digest(token)
                if digest in self._entries or digest in self._tombstones:
                    continue
                entry = _Entry(
                    proposal=proposal,
                    token=SecretStr(token),
                    tenant_id=message.tenant_id,
                    actor_identity=message.actor_identity,
                    actor_role=message.actor_role,
                    auth_context_ref=message.auth_context_ref,
                    user_id=message.user_id,
                    chat_id=message.chat_id,
                    request_key=request_key,
                    request_digest=request_digest,
                    issued_at=now,
                    expires_at=now + timedelta(seconds=PATCH_CONFIRMATION_TTL_SECONDS),
                )
                self._entries[digest] = entry
                self._requests[request_key] = digest
                return self._challenge(entry)
            raise RuntimeError("patch confirmation token collision")

    def consume(
        self,
        *,
        token: str,
        action: PatchConfirmationStatus,
        message: PatchActionMessage,
        envelope: TrustedIngressEnvelope,
    ) -> PatchConfirmationResult:
        if (
            type(action) is not PatchConfirmationStatus
            or action not in {PatchConfirmationStatus.CONFIRMED, PatchConfirmationStatus.CANCELLED}
            or not isinstance(token, str)
            or _TOKEN_RE.fullmatch(token) is None
            or not _trusted(message, envelope)
        ):
            return PatchConfirmationResult(PatchConfirmationStatus.REJECTED)
        digest = _token_digest(token)
        with self._lock:
            now = self._now()
            tombstone = self._tombstones.get(digest)
            if tombstone is not None:
                return PatchConfirmationResult(
                    PatchConfirmationStatus.ALREADY_USED
                    if _actor_matches(tombstone, message)
                    else PatchConfirmationStatus.REJECTED
                )
            entry = self._entries.get(digest)
            if entry is None or not _actor_matches(entry, message):
                return PatchConfirmationResult(PatchConfirmationStatus.REJECTED)
            if now >= entry.expires_at:
                return PatchConfirmationResult(PatchConfirmationStatus.EXPIRED)
            self._consume(digest, entry, now)
            return PatchConfirmationResult(action, entry.proposal)

    def sweep_expired(self) -> tuple[PatchProposal, ...]:
        """Return expired proposals so the runtime can reject and discard them."""
        with self._lock:
            now = self._now()
            expired = tuple(
                entry.proposal
                for entry in self._entries.values()
                if now >= entry.expires_at
            )
            self._sweep(now)
            return expired
    def acknowledge_expired(self, proposal: PatchProposal) -> bool:
        proposal = PatchProposal.model_validate(proposal.model_dump(mode="python"))
        with self._lock:
            now = self._now()
            for digest, entry in tuple(self._entries.items()):
                if entry.proposal == proposal and now >= entry.expires_at:
                    self._consume(digest, entry, now)
                    return True
            return False
    def _consume(self, digest: str, entry: _Entry, now: datetime) -> None:
        self._entries.pop(digest, None)
        self._requests.pop(entry.request_key, None)
        self._tombstones[digest] = _Tombstone(
            tenant_id=entry.tenant_id,
            actor_identity=entry.actor_identity,
            actor_role=entry.actor_role,
            auth_context_ref=entry.auth_context_ref,
            user_id=entry.user_id,
            chat_id=entry.chat_id,
            replay_until=now + timedelta(hours=1),
        )

    def _sweep(self, now: datetime) -> None:
        for digest, tombstone in tuple(self._tombstones.items()):
            if now >= tombstone.replay_until:
                del self._tombstones[digest]

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("patch confirmation clock is invalid")
        return value.astimezone(UTC)

    @staticmethod
    def _challenge(entry: _Entry) -> PatchConfirmationChallenge:
        return PatchConfirmationChallenge(
            confirmation_token=entry.token,
            proposal=entry.proposal,
            issued_at=entry.issued_at,
            expires_at=entry.expires_at,
        )


def patch_proposal_digest(values: dict[str, object]) -> str:
    return canonical_json_digest(values)


def _token_digest(token: str) -> str:
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def _trusted(message: PatchActionMessage, envelope: TrustedIngressEnvelope) -> bool:
    try:
        if type(message) is TextMessage:
            payload = TextMessage.model_validate(message.model_dump(mode="json"))
        elif type(message) is CallbackQuery:
            payload = CallbackQuery.model_validate(message.model_dump(mode="json"))
        else:
            return False
        TrustedIngressResult(
            status=IngressStatus.ACCEPTED,
            update_id=message.update_id,
            payload=payload,
            envelope=TrustedIngressEnvelope.model_validate(envelope.model_dump(mode="json")),
        )
    except Exception:
        return False
    return True


def _actor_matches(entry: _Entry | _Tombstone, message: PatchActionMessage) -> bool:
    return (
        entry.tenant_id == message.tenant_id
        and entry.actor_identity == message.actor_identity
        and entry.actor_role == message.actor_role
        and entry.auth_context_ref == message.auth_context_ref
        and entry.user_id == message.user_id
        and entry.chat_id == message.chat_id
    )
