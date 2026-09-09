"""Owner-bound Core authentication and read-only Mini App projection."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol, get_args
from urllib.parse import parse_qsl
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from src.application.task_confirmation import MAX_TASK_INSTRUCTION_LENGTH
from src.application.product_status import (
    ProductAction, ProductAdmissionStopped, ProductReason, ProductTaskStatus,
    product_event_label, product_reason_state, product_task_state,
)
from src.application.semantic_admission import (
    SemanticAdmissionError,
    SemanticClarificationRejected,
    SemanticClarificationRequired,
)
from src.contracts import (
    IngressKind,
    IngressSource,
    TrustedIngressEnvelope,
    WorkerEventType,
)
from src.contracts.models import canonical_json_digest
from src.core.policy import DuplicateIdempotencyKeyError
from src.models.task import TaskStatus
from src.storage import (
    DurableTaskProjection,
    IngressClaimConflictError,
    OutboxArtifact,
    OutboxMessage,
    SQLiteStore,
    SnapshotConflictError,
    StoreCorruptionError,
    StoredTaskSnapshot,
    artifact_for_message,
)
from src.storage.sqlite_store import (
    MiniAppAdmissionClosedError, MiniAppCancelledRequest, MiniAppRequestRecord,
    MiniAppRequestDetail, MiniAppFailureCode, MiniAppRequestPhase,
)
from src.storage.outbox import OutboxStatus


_IDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9._~-]{16,128}")
_CLARIFICATION_TOKEN = re.compile(r"[A-Za-z0-9_-]{32,128}")
MAX_TASK_DISPLAY_TITLE_LENGTH = 120


class MiniAppAuthenticationError(ValueError):
    """Authentication failed without exposing which check rejected it."""


class MiniAppTaskNotFoundError(LookupError):
    """A task is absent from the server-derived session scope."""


class MiniAppCoreUnavailableError(RuntimeError):
    """The authoritative local state cannot be read safely."""


class MiniAppTaskConflictError(ValueError):
    """One request id was rebound to another trusted request."""


class MiniAppTaskRequestError(ValueError):
    """A task mutation request is syntactically invalid."""


class MiniAppRequestCancelled(ValueError):
    """An absent request key was durably cancelled before admission."""


class MiniAppRequestNotAccepted(RuntimeError):
    def __init__(self, detail: str) -> None:
        self.state = product_reason_state(ProductReason(detail))
        super().__init__(self.state.reason.value)


class MiniAppTaskMaterial(BaseModel):
    """One bounded UTF-8 material; its metadata is part of request identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    filename: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    media_type: Literal["text/plain; charset=utf-8"]
    size: StrictInt = Field(ge=1, le=MAX_TASK_INSTRUCTION_LENGTH * 4)
    content_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    text: str = Field(min_length=1, max_length=MAX_TASK_INSTRUCTION_LENGTH)

    def checked_instruction(self, instruction: str) -> str:
        raw = self.text.encode("utf-8", errors="strict")
        if (
            len(raw) != self.size
            or "sha256:" + hashlib.sha256(raw).hexdigest() != self.content_digest
            or "\x00" in self.text
            or not self.text.strip()
        ):
            raise MiniAppTaskRequestError("invalid_request")
        # C1's existing explicit colon boundary marks the entire suffix inert.
        return f"{instruction}\n\nМатериал:\n{self.text}"


class MiniAppSessionGrant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    access_token: str = Field(min_length=32, max_length=128)
    expires_in: StrictInt = Field(ge=1, le=900)
    recovery_token: str | None = Field(default=None, exclude=True, repr=False)
    recovery_expires_in: int = Field(default=0, exclude=True, repr=False)


class MiniAppRequestState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str
    state: Literal["pending", "accepted", "clarification", "not_accepted"]
    task_id: UUID | None = None
    status: ProductTaskStatus | None = None
    question: str | None = None
    clarification_token: str | None = Field(default=None, repr=False)
    detail: MiniAppRequestDetail | None = None
    request_ref: str | None = None
    received_at: datetime | None = None
    updated_at: datetime | None = None
    deadline_at: datetime | None = None
    phase: MiniAppRequestPhase | None = None
    failure_code: MiniAppFailureCode | None = None
    failure_phase: MiniAppRequestPhase | None = None
    elapsed_seconds: float | None = None
    legacy_timing: bool = False


class MiniAppTaskSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: UUID
    description: str = Field(min_length=1, max_length=120)
    description_available: bool
    status: ProductTaskStatus
    status_label: str = Field(min_length=1, max_length=64)
    reason: ProductReason
    reason_label: str
    action: ProductAction
    terminal: bool
    source: str
    risk: str
    created_at: datetime
    updated_at: datetime


class MiniAppTaskDetail(MiniAppTaskSummary):
    instruction: str | None = Field(
        default=None, min_length=1, max_length=MAX_TASK_INSTRUCTION_LENGTH
    )
    instruction_available: bool
    task_revision: StrictInt = Field(ge=1)
    result_revision: StrictInt = Field(ge=0)
    result_digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    has_result: bool
    has_verified_answer: bool
    has_artifact: bool = False
    delivery_pending: bool = False
    delivery_label: str | None = None


class MiniAppTaskCreation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: UUID
    status: ProductTaskStatus


class MiniAppTaskArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: UUID
    filename: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    media_type: Literal["text/plain; charset=utf-8"]
    size: StrictInt = Field(ge=1, le=1024 * 1024)
    content_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class MiniAppTaskResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: UUID
    task_revision: StrictInt = Field(ge=1)
    product_status: ProductTaskStatus
    result_revision: StrictInt = Field(ge=1)
    result_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    answer: str = Field(min_length=1, max_length=128 * 1024)
    artifact: MiniAppTaskArtifact | None = None


class MiniAppTaskEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal[
        "started",
        "progress",
        "waiting_input",
        "artifact_ready",
        "result_ready",
        "failed",
        "stopped",
    ]
    label: str
    emitted_at: datetime


_SAFE_EVENT_KIND = {
    WorkerEventType.STARTED: "started",
    WorkerEventType.PROGRESS: "progress",
    WorkerEventType.WAITING_INPUT: "waiting_input",
    WorkerEventType.ARTIFACT_READY: "artifact_ready",
    WorkerEventType.RESULT_READY: "result_ready",
    WorkerEventType.USAGE: "progress",
    WorkerEventType.FAILED: "failed",
    WorkerEventType.CANCELLED: "stopped",
}


class MiniAppTaskAdmission(Protocol):
    def miniapp_clarification_current(self, envelope: TrustedIngressEnvelope, token: str) -> bool: ...

    async def submit_miniapp_task(
        self,
        instruction: str,
        envelope: TrustedIngressEnvelope,
        *,
        clarification_token: str | None = None,
    ) -> UUID: ...

    def miniapp_task_submitted(
        self, tenant_id: str, task_id: UUID, contract_digest: str
    ) -> bool: ...


@dataclass(frozen=True)
class _Session:
    owner_user_id: int
    tenant_id: str
    auth_context_ref: str
    recovery_digest: str
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True, repr=False)
class MiniAppTaskArtifactDownload:
    artifact: MiniAppTaskArtifact
    content: bytes


class MiniAppCore:
    """Core-owned Telegram verification, sessions and safe task reads."""

    def __init__(
        self,
        *,
        store: SQLiteStore,
        task_admission: MiniAppTaskAdmission | None = None,
        bot_token: str,
        owner_user_id: int,
        tenant_id: str,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        init_data_ttl: timedelta = timedelta(minutes=5),
        session_ttl: timedelta = timedelta(minutes=2),
        future_skew: timedelta = timedelta(seconds=30),
        max_init_data_bytes: int = 4096,
    ) -> None:
        if not isinstance(store, SQLiteStore):
            raise ValueError("store must be SQLiteStore")
        if not isinstance(bot_token, str) or not bot_token or len(bot_token) > 512:
            raise ValueError("bot_token is invalid")
        if (
            isinstance(owner_user_id, bool)
            or not isinstance(owner_user_id, int)
            or owner_user_id < 1
        ):
            raise ValueError("owner_user_id must be an integer")
        tenant = tenant_id.strip() if isinstance(tenant_id, str) else ""
        if not tenant or len(tenant) > 128:
            raise ValueError("tenant_id is invalid")
        for name, value, ceiling in (
            ("init_data_ttl", init_data_ttl, 900),
            ("session_ttl", session_ttl, 900),
            ("future_skew", future_skew, 120),
        ):
            seconds = value.total_seconds() if isinstance(value, timedelta) else -1
            if seconds < (0 if name == "future_skew" else 1) or seconds > ceiling:
                raise ValueError(f"{name} is invalid")
        if (
            isinstance(max_init_data_bytes, bool)
            or not isinstance(max_init_data_bytes, int)
            or not 256 <= max_init_data_bytes <= 8192
        ):
            raise ValueError("max_init_data_bytes is invalid")
        self._store = store
        self._task_admission = task_admission
        self._bot_token = bot_token.encode("utf-8")
        self._bot_ref = canonical_json_digest({"bot_token": bot_token})
        self._owner_user_id = owner_user_id
        self._tenant_id = tenant
        self._clock = clock
        self._init_data_ttl = init_data_ttl
        self._session_ttl = session_ttl
        self._future_skew = future_skew
        self._max_init_data_bytes = max_init_data_bytes
        self._auth_context_ref = canonical_json_digest(
            {"bot_ref": self._bot_ref, "owner_user_id": owner_user_id, "tenant_id": tenant}
        )
        self._sessions: dict[str, _Session] = {}
        self._lock = threading.Lock()
        # ponytail: one owner, so one mutation lock is enough until measured concurrency needs more.

    def authenticate(self, raw_init_data: str) -> MiniAppSessionGrant:
        now = self._now()
        auth_date, owner_user_id, replay_digest = self._verify_init_data(
            raw_init_data, now=now
        )
        try:
            if self._store.restore_reconciliation_required():
                raise MiniAppCoreUnavailableError("core_unavailable")
            cutoff = self._store.miniapp_restore_cutoff()
        except StoreCorruptionError:
            raise MiniAppCoreUnavailableError("core_unavailable") from None
        if cutoff is not None and auth_date <= cutoff:
            raise MiniAppAuthenticationError("unauthorized")
        try:
            claimed = self._store.claim_miniapp_auth_replay(
                self._tenant_id,
                replay_digest,
                auth_expires_at=auth_date + self._init_data_ttl,
                claimed_at=now,
            )
        except StoreCorruptionError:
            raise MiniAppCoreUnavailableError("core_unavailable") from None
        if not claimed:
            raise MiniAppAuthenticationError("unauthorized")
        with self._lock:
            recovery = self._recovery_token(auth_date + self._init_data_ttl)
            try:
                deadline = self._store.replace_miniapp_recovery(
                    self._tenant_id, self._auth_context_ref,
                    "sha256:" + self._token_digest(recovery), now=now,
                    expires_at=auth_date + self._init_data_ttl,
                )
            except StoreCorruptionError:
                raise MiniAppCoreUnavailableError("core_unavailable") from None
            assert deadline is not None
            return self._grant(recovery, deadline=deadline, now=now)

    def recover_session(self, recovery_token: str) -> MiniAppSessionGrant:
        now = self._now()
        deadline = self._verify_recovery_token(recovery_token, now=now)
        with self._lock:
            recovery = self._recovery_token(deadline)
            try:
                stored_deadline = self._store.replace_miniapp_recovery(
                    self._tenant_id, self._auth_context_ref,
                    "sha256:" + self._token_digest(recovery), now=now,
                    previous_digest="sha256:" + self._token_digest(recovery_token),
                    expected_deadline=deadline,
                )
            except StoreCorruptionError:
                raise MiniAppCoreUnavailableError("core_unavailable") from None
            if stored_deadline is None:
                raise MiniAppAuthenticationError("unauthorized")
            if stored_deadline != deadline:
                raise MiniAppCoreUnavailableError("core_unavailable")
            return self._grant(recovery, deadline=deadline, now=now)

    def _recovery_token(self, deadline: datetime) -> str:
        stamp = (deadline - datetime(1970, 1, 1, tzinfo=UTC)) // timedelta(microseconds=1)
        value = f"{secrets.token_urlsafe(32)}.{stamp}"
        signature = hmac.new(self._bot_token,
            f"miniapp-recovery:v1:{self._auth_context_ref}:{value}".encode(), hashlib.sha256).hexdigest()
        return f"{value}.{signature}"

    def _verify_recovery_token(self, token: str, *, now: datetime) -> datetime:
        if not isinstance(token, str) or re.fullmatch(r"[A-Za-z0-9_-]{43}\.[0-9]{15,17}\.[0-9a-f]{64}", token) is None:
            raise MiniAppAuthenticationError("unauthorized")
        value, signature = token.rsplit(".", 1)
        expected = hmac.new(self._bot_token,
            f"miniapp-recovery:v1:{self._auth_context_ref}:{value}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise MiniAppAuthenticationError("unauthorized")
        try:
            deadline = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=int(value.split(".")[1]))
        except (ValueError, OSError, OverflowError):
            raise MiniAppAuthenticationError("unauthorized") from None
        if deadline <= now:
            raise MiniAppAuthenticationError("unauthorized")
        return deadline

    def _grant(self, recovery: str, *, deadline: datetime, now: datetime) -> MiniAppSessionGrant:
        now = self._now()
        if deadline <= now:
            raise MiniAppAuthenticationError("unauthorized")
        token = secrets.token_urlsafe(32)
        expires_at = min(now + self._session_ttl, deadline)
        self._sessions = {self._token_digest(token): _Session(
            owner_user_id=self._owner_user_id, tenant_id=self._tenant_id,
            auth_context_ref=self._auth_context_ref,
            recovery_digest="sha256:" + self._token_digest(recovery),
            issued_at=now, expires_at=expires_at,
        )}
        return MiniAppSessionGrant(
            access_token=token, expires_in=max(1, int((expires_at - now).total_seconds())),
            recovery_token=recovery, recovery_expires_in=max(1, int((deadline - now).total_seconds())),
        )

    def list_tasks(
        self, bearer: str, *, limit: int = 20
    ) -> tuple[MiniAppTaskSummary, ...]:
        session = self._session(bearer)
        try:
            snapshots = self._store.list_tasks(session.tenant_id, limit=limit)
        except StoreCorruptionError:
            raise MiniAppCoreUnavailableError("core_unavailable") from None
        return tuple(self._summary(item) for item in snapshots)

    def task_detail(self, bearer: str, task_id: UUID) -> MiniAppTaskDetail:
        session = self._session(bearer)
        if not isinstance(task_id, UUID):
            raise MiniAppTaskNotFoundError("task_not_found")
        try:
            snapshot = self._store.read_task(session.tenant_id, task_id)
        except StoreCorruptionError:
            raise MiniAppCoreUnavailableError("core_unavailable") from None
        if snapshot is None or snapshot.projection.tenant_id != session.tenant_id:
            raise MiniAppTaskNotFoundError("task_not_found")
        projection = snapshot.projection
        state = product_task_state(projection.status)
        has_verified_answer = False
        artifact: OutboxArtifact | None = None
        delivery_pending = False
        delivery_label = None
        if projection.status is TaskStatus.ANSWERED:
            message = self._verified_answer(snapshot)
            has_verified_answer = message is not None
            if not has_verified_answer:
                raise MiniAppCoreUnavailableError("core_unavailable")
            assert message is not None
            artifact = artifact_for_message(message)
            delivery_pending = message.status in {OutboxStatus.PENDING, OutboxStatus.LEASED}
            if delivery_pending:
                delivery_label = product_reason_state(ProductReason.DELIVERY_PENDING).reason_label
            elif message.status is OutboxStatus.FAILED:
                delivery_label = "Доставку в Telegram не удалось подтвердить. Результат доступен здесь."
            else:
                delivery_label = "Доставка в Telegram подтверждена."
        return MiniAppTaskDetail(
            **self._summary(snapshot).model_dump(),
            instruction=snapshot.display_instruction,
            instruction_available=snapshot.display_instruction is not None,
            task_revision=snapshot.revision,
            result_revision=(
                projection.result_revision
                if state.status is ProductTaskStatus.READY
                else 0
            ),
            result_digest=(
                projection.result_digest
                if state.status is ProductTaskStatus.READY
                else None
            ),
            has_result=(
                state.status is ProductTaskStatus.READY
                and projection.result_digest is not None
            ),
            has_verified_answer=has_verified_answer,
            has_artifact=artifact is not None,
            delivery_pending=delivery_pending,
            delivery_label=delivery_label,
        )

    def task_result(
        self, bearer: str, task_id: UUID, *, result_revision: int
    ) -> MiniAppTaskResult:
        session = self._session(bearer)
        if (
            not isinstance(task_id, UUID)
            or isinstance(result_revision, bool)
            or not isinstance(result_revision, int)
            or result_revision < 1
        ):
            raise MiniAppTaskNotFoundError("task_not_found")
        try:
            snapshot = self._store.read_task(session.tenant_id, task_id)
        except StoreCorruptionError:
            raise MiniAppCoreUnavailableError("core_unavailable") from None
        if (
            snapshot is None
            or snapshot.projection.tenant_id != session.tenant_id
            or snapshot.projection.status is not TaskStatus.ANSWERED
            or snapshot.projection.result_revision != result_revision
            or snapshot.projection.result_digest is None
        ):
            raise MiniAppTaskNotFoundError("task_not_found")
        message = self._verified_answer(snapshot)
        if message is None or message.user_message is None:
            raise MiniAppCoreUnavailableError("core_unavailable")
        artifact = artifact_for_message(message)
        return MiniAppTaskResult(
            task_id=task_id,
            task_revision=snapshot.revision,
            product_status=product_task_state(snapshot.projection.status).status,
            result_revision=snapshot.projection.result_revision,
            result_digest=snapshot.projection.result_digest,
            answer=message.user_message,
            artifact=(
                self._artifact_summary(artifact) if artifact is not None else None
            ),
        )

    def task_artifact(
        self,
        bearer: str,
        task_id: UUID,
        artifact_id: UUID,
        *,
        result_revision: int,
    ) -> MiniAppTaskArtifactDownload:
        session = self._session(bearer)
        if (
            not isinstance(task_id, UUID)
            or not isinstance(artifact_id, UUID)
            or isinstance(result_revision, bool)
            or not isinstance(result_revision, int)
            or result_revision < 1
        ):
            raise MiniAppTaskNotFoundError("task_not_found")
        try:
            snapshot = self._store.read_task(session.tenant_id, task_id)
        except StoreCorruptionError:
            raise MiniAppCoreUnavailableError("core_unavailable") from None
        if (
            snapshot is None
            or snapshot.projection.tenant_id != session.tenant_id
            or snapshot.projection.status is not TaskStatus.ANSWERED
            or snapshot.projection.result_revision != result_revision
            or snapshot.projection.result_digest is None
        ):
            raise MiniAppTaskNotFoundError("task_not_found")
        message = self._verified_answer(snapshot)
        artifact = None if message is None else artifact_for_message(message)
        if artifact is None or artifact.artifact_id != artifact_id:
            raise MiniAppTaskNotFoundError("task_not_found")
        try:
            content = artifact.content_bytes()
        except ValueError:
            raise MiniAppCoreUnavailableError("core_unavailable") from None
        return MiniAppTaskArtifactDownload(
            artifact=self._artifact_summary(artifact),
            content=content,
        )

    def task_events(
        self, bearer: str, task_id: UUID, *, limit: int = 20
    ) -> tuple[MiniAppTaskEvent, ...]:
        session = self._session(bearer)
        if not isinstance(task_id, UUID):
            raise MiniAppTaskNotFoundError("task_not_found")
        try:
            snapshot = self._store.read_task(session.tenant_id, task_id)
            if snapshot is None or snapshot.projection.tenant_id != session.tenant_id:
                raise MiniAppTaskNotFoundError("task_not_found")
            events = self._store.read_task_events(
                session.tenant_id, task_id, limit=limit
            )
        except MiniAppTaskNotFoundError:
            raise
        except (StoreCorruptionError, ValueError):
            raise MiniAppCoreUnavailableError("core_unavailable") from None
        return tuple(
            MiniAppTaskEvent(
                kind=_SAFE_EVENT_KIND[event.event_type],
                label=product_event_label(_SAFE_EVENT_KIND[event.event_type]),
                emitted_at=event.emitted_at,
            )
            for event in events
        )

    async def create_task(
        self,
        bearer: str,
        instruction: str,
        idempotency_key: str,
        *,
        display_title: str | None = None,
        clarification_token: str | None = None,
        material: MiniAppTaskMaterial | None = None,
    ) -> MiniAppTaskCreation:
        normalized = instruction.strip() if isinstance(instruction, str) else ""
        if material is not None:
            if not isinstance(material, MiniAppTaskMaterial) or not normalized:
                raise MiniAppTaskRequestError("invalid_request")
            try:
                material = MiniAppTaskMaterial.model_validate(material.model_dump())
                normalized = material.checked_instruction(normalized)
            except (UnicodeError, ValueError):
                raise MiniAppTaskRequestError("invalid_request") from None
        normalized_title = (
            display_title.strip() if isinstance(display_title, str) else None
        )
        if (
            not normalized
            or len(normalized) > MAX_TASK_INSTRUCTION_LENGTH
            or "\x00" in normalized
            or (
                display_title is not None
                and (
                    not normalized_title
                    or len(normalized_title) > MAX_TASK_DISPLAY_TITLE_LENGTH
                    or "\x00" in normalized_title
                )
            )
            or not isinstance(idempotency_key, str)
            or _IDEMPOTENCY_KEY.fullmatch(idempotency_key) is None
            or (
                clarification_token is not None
                and (
                    not isinstance(clarification_token, str)
                    or _CLARIFICATION_TOKEN.fullmatch(clarification_token) is None
                )
            )
        ):
            raise MiniAppTaskRequestError("invalid_request")
        session = self._session(bearer)
        return await self._create_task(
            session, instruction=normalized, idempotency_key=idempotency_key,
            display_title=normalized_title, clarification_token=clarification_token,
            material=material,
        )

    async def _create_task(
        self,
        session: _Session,
        *,
        instruction: str,
        idempotency_key: str,
        display_title: str | None,
        clarification_token: str | None,
        material: MiniAppTaskMaterial | None,
    ) -> MiniAppTaskCreation:
        admission = self._task_admission
        if admission is None:
            raise MiniAppCoreUnavailableError("core_unavailable")
        envelope = self._task_envelope(
            session,
            instruction=instruction,
            idempotency_key=idempotency_key,
            display_title=display_title,
            material=material,
            clarification_token=clarification_token,
        )
        try:
            claimed, record = self._store.write_miniapp_request(
                MiniAppRequestRecord(envelope=envelope), claim=True
            )
        except IngressClaimConflictError:
            raise MiniAppTaskConflictError("request_conflict") from None
        except StoreCorruptionError:
            raise MiniAppCoreUnavailableError("core_unavailable") from None
        if isinstance(record, MiniAppCancelledRequest):
            raise MiniAppRequestCancelled("request_cancelled")
        # Content/auth identity was checked by the store; repeats use the first envelope bytes.
        envelope = record.envelope
        existing = self._existing_creation(envelope, admission,
            display_title=display_title, instruction=instruction)
        if existing is not None:
            return existing
        if not claimed:
            self._raise_request_outcome(record)
        outcome = None
        try:
            if clarification_token is None:
                task_id = await admission.submit_miniapp_task(instruction, envelope)
            else:
                task_id = await admission.submit_miniapp_task(
                    instruction, envelope, clarification_token=clarification_token)
        except SemanticClarificationRequired as error:
            outcome = dict(state="clarification", question=error.question,
                clarification_token=error.token, expires_at=self._now() + timedelta(minutes=30),
                phase="semantic")
        except SemanticClarificationRejected:
            outcome = dict(state="not_accepted", detail="clarification_invalid", phase="semantic")
        except ProductAdmissionStopped as error:
            outcome = dict(state="not_accepted", detail=error.state.reason.value, phase="semantic")
        except SemanticAdmissionError as error:
            # These errors are before admission; still reconcile against a concurrent accepted claim.
            code = error.code if error.code in get_args(MiniAppFailureCode) else "SEMANTIC_FAILED"
            outcome = dict(state="not_accepted", detail="semantic_unavailable", phase="semantic", failure_code=code)
        except asyncio.CancelledError:
            self._store.reconcile_miniapp_request(envelope.tenant_id, envelope.auth_context_ref,
                envelope.idempotency_key, detail="request_interrupted", failure_code="TRANSPORT_CANCELLED")
            raise
        except (MiniAppAdmissionClosedError, DuplicateIdempotencyKeyError, IngressClaimConflictError):
            outcome = dict(state="pending", phase="reconciliation", failure_code="ADMISSION_UNKNOWN")
        except Exception:
            # An arbitrary exception does not prove refusal. Retain UNKNOWN until atomic reconciliation.
            outcome = dict(state="pending", phase="reconciliation", failure_code="ADMISSION_UNKNOWN")
        if outcome is not None:
            record = self._finish_request(record, **outcome)
            existing = self._existing_creation(envelope, admission,
                display_title=display_title, instruction=instruction)
            if existing is not None:
                return existing
            self._raise_request_outcome(record)
        try:
            snapshot = self._store.read_task(session.tenant_id, task_id)
        except StoreCorruptionError:
            raise MiniAppCoreUnavailableError("core_unavailable") from None
        if snapshot is None or snapshot.projection.tenant_id != session.tenant_id:
            raise MiniAppCoreUnavailableError("core_unavailable")
        snapshot = self._bind_display_title(snapshot, display_title, instruction=instruction)
        return self._creation(snapshot, admission)

    def _raise_request_outcome(self, record: MiniAppRequestRecord | MiniAppCancelledRequest) -> None:
        if isinstance(record, MiniAppCancelledRequest) or record.detail == "request_cancelled":
            raise MiniAppRequestCancelled("request_cancelled")
        if record.state == "clarification":
            if not self._clarification_current(record):
                self._finish_request(record, state="not_accepted", detail="clarification_invalid",
                    question=None, clarification_token=None, expires_at=None)
                raise SemanticClarificationRejected("clarification_invalid")
            raise SemanticClarificationRequired(record.question, record.clarification_token)
        if record.detail == "clarification_invalid":
            raise SemanticClarificationRejected("clarification_invalid")
        if record.state == "not_accepted":
            raise MiniAppRequestNotAccepted(record.detail)
        raise MiniAppCoreUnavailableError("core_unavailable")

    def _finish_request(self, record: MiniAppRequestRecord, **outcome: object) -> MiniAppRequestRecord | MiniAppCancelledRequest:
        try:
            return self._store.write_miniapp_request(
                MiniAppRequestRecord.model_validate(record.model_dump() | outcome)
            )[1]
        except (StoreCorruptionError, ValueError):
            raise MiniAppCoreUnavailableError("core_unavailable") from None

    def _clarification_current(self, record: MiniAppRequestRecord) -> bool:
        if record.expires_at is None or record.expires_at <= self._now():
            return False
        check = getattr(self._task_admission, "miniapp_clarification_current", None)
        if not callable(check):
            raise MiniAppCoreUnavailableError("core_unavailable")
        try:
            return check(record.envelope, record.clarification_token)
        except Exception:
            raise MiniAppCoreUnavailableError("core_unavailable") from None

    def request_state(self, bearer: str, idempotency_key: str) -> MiniAppRequestState:
        session = self._session(bearer)
        if not isinstance(idempotency_key, str) or _IDEMPOTENCY_KEY.fullmatch(idempotency_key) is None:
            raise MiniAppTaskNotFoundError("task_not_found")
        try:
            record, snapshot = self._store.reconcile_miniapp_request(
                session.tenant_id, session.auth_context_ref, idempotency_key
            )
            if record is None:
                raise MiniAppTaskNotFoundError("task_not_found")
            if isinstance(record, MiniAppCancelledRequest):
                return MiniAppRequestState(request_id=idempotency_key, state="not_accepted",
                                           detail="request_cancelled")
            if snapshot is not None:
                if self._task_admission is None:
                    raise MiniAppCoreUnavailableError("core_unavailable")
                creation = self._creation(snapshot, self._task_admission)
                return MiniAppRequestState(request_id=idempotency_key, state="accepted",
                                           task_id=creation.task_id, status=creation.status)
        except (StoreCorruptionError, IngressClaimConflictError):
            raise MiniAppCoreUnavailableError("core_unavailable") from None
        if record.state == "clarification" and not self._clarification_current(record):
            self._finish_request(record, state="not_accepted", detail="clarification_invalid",
                question=None, clarification_token=None, expires_at=None)
            return MiniAppRequestState(request_id=idempotency_key, state="not_accepted",
                                       detail="clarification_invalid")
        return MiniAppRequestState(
            request_id=idempotency_key, state=record.state,
            question=record.question, clarification_token=record.clarification_token,
            detail=record.detail,
            request_ref=hashlib.sha256(idempotency_key.encode()).hexdigest()[:16],
            received_at=record.received_at, updated_at=record.updated_at,
            deadline_at=record.admission_deadline, phase=record.phase,
            failure_code=record.failure_code, failure_phase=record.failure_phase,
            elapsed_seconds=(round((record.updated_at - record.received_at).total_seconds(), 3)
                if record.received_at is not None and record.updated_at is not None else None),
            legacy_timing=record.received_at is None,
        )

    async def cancel_absent_request(self, bearer: str, idempotency_key: str) -> MiniAppRequestState:
        if not isinstance(idempotency_key, str) or _IDEMPOTENCY_KEY.fullmatch(idempotency_key) is None:
            raise MiniAppTaskRequestError("invalid_request")
        session = self._session(bearer)
        try:
            record = self._store.cancel_absent_miniapp_request(MiniAppCancelledRequest(
                tenant_id=session.tenant_id, auth_context_ref=session.auth_context_ref,
                idempotency_key=idempotency_key,
            ))
        except IngressClaimConflictError:
            raise MiniAppTaskNotFoundError("task_not_found") from None
        except StoreCorruptionError:
            raise MiniAppCoreUnavailableError("core_unavailable") from None
        if record is None:
            # A legacy ingress claim without a journal is not proof of rejection.
            return MiniAppRequestState(request_id=idempotency_key, state="pending")
        return self.request_state(bearer, idempotency_key)

    def _existing_creation(
        self,
        envelope: TrustedIngressEnvelope,
        admission: MiniAppTaskAdmission,
        *,
        display_title: str | None,
        instruction: str,
    ) -> MiniAppTaskCreation | None:
        try:
            snapshot = self._store.read_ingress_claim(envelope)
        except IngressClaimConflictError:
            raise MiniAppTaskConflictError("request_conflict") from None
        except StoreCorruptionError:
            raise MiniAppCoreUnavailableError("core_unavailable") from None
        if snapshot is None:
            return None
        return self._creation(
            self._bind_display_title(
                snapshot, display_title, instruction=instruction
            ),
            admission,
        )

    def _bind_display_title(
        self,
        snapshot: StoredTaskSnapshot,
        display_title: str | None,
        *,
        instruction: str,
    ) -> StoredTaskSnapshot:
        if display_title is None:
            return snapshot
        try:
            return self._store.bind_task_display_text(
                snapshot.projection.tenant_id,
                snapshot.projection.task_id,
                display_title,
                display_instruction=instruction,
            )
        except SnapshotConflictError:
            raise MiniAppTaskConflictError("request_conflict") from None
        except StoreCorruptionError:
            raise MiniAppCoreUnavailableError("core_unavailable") from None

    @staticmethod
    def _creation(
        snapshot: StoredTaskSnapshot,
        admission: MiniAppTaskAdmission,
    ) -> MiniAppTaskCreation:
        projection = snapshot.projection
        if projection.status is TaskStatus.PENDING:
            try:
                submitted = admission.miniapp_task_submitted(
                    projection.tenant_id,
                    projection.task_id,
                    projection.contract_digest,
                )
            except Exception:
                raise MiniAppCoreUnavailableError("core_unavailable") from None
            if not submitted:
                raise MiniAppCoreUnavailableError("core_unavailable")
        return MiniAppTaskCreation(
            task_id=projection.task_id,
            status=product_task_state(projection.status).status,
        )

    def _task_envelope(
        self,
        session: _Session,
        *,
        instruction: str,
        idempotency_key: str,
        display_title: str | None,
        material: MiniAppTaskMaterial | None = None,
        clarification_token: str | None = None,
    ) -> TrustedIngressEnvelope:
        content: dict[str, object] = {"instruction": instruction}
        if display_title is not None:
            content["display_title"] = display_title
        if material is not None:
            content["material"] = material.model_dump(exclude={"text"})
        if clarification_token is not None:
            content["clarification_token"] = clarification_token
        content_ref = canonical_json_digest(content)
        ingress_binding = canonical_json_digest(
            {
                "auth_context_ref": session.auth_context_ref,
                "idempotency_key": idempotency_key,
                "kind": IngressKind.TEXT.value,
                "source": IngressSource.API.value,
                "tenant_id": session.tenant_id,
                "content_ref": content_ref,
            }
        )
        values = {
            "schema_version": "1",
            "ingress_id": UUID(hex=ingress_binding[7:39], version=4),
            "tenant_id": session.tenant_id,
            "source": IngressSource.API,
            "actor_identity": "telegram:owner",
            "external_message_id": f"miniapp:task.create:{idempotency_key}",
            "idempotency_key": idempotency_key,
            "received_at": self._now(),
            "kind": IngressKind.TEXT,
            "content_ref": content_ref,
            "auth_context_ref": session.auth_context_ref,
        }
        revision = canonical_json_digest(
            TrustedIngressEnvelope.model_construct(
                **values,
                envelope_revision="sha256:" + "0" * 64,
            ).model_dump(mode="json", exclude={"envelope_revision"})
        )
        return TrustedIngressEnvelope(**values, envelope_revision=revision)

    def _verify_init_data(
        self, raw_init_data: str, *, now: datetime
    ) -> tuple[datetime, int, str]:
        try:
            if not isinstance(raw_init_data, str):
                raise ValueError
            encoded = raw_init_data.encode("utf-8")
            if not encoded or len(encoded) > self._max_init_data_bytes:
                raise ValueError
            pairs = parse_qsl(
                raw_init_data,
                keep_blank_values=True,
                strict_parsing=True,
                max_num_fields=64,
            )
            if len({key for key, _ in pairs}) != len(pairs):
                raise ValueError
            fields = dict(pairs)
            supplied_hash = fields.pop("hash")
            if len(supplied_hash) != 64 or any(
                character not in "0123456789abcdef" for character in supplied_hash
            ):
                raise ValueError
            check = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
            replay_digest = "sha256:" + hashlib.sha256(
                check.encode("utf-8")
            ).hexdigest()
            secret = hmac.new(b"WebAppData", self._bot_token, hashlib.sha256).digest()
            expected_hash = hmac.new(
                secret, check.encode("utf-8"), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(expected_hash, supplied_hash):
                raise ValueError
            auth_value = fields["auth_date"]
            if not auth_value.isascii() or not auth_value.isdigit():
                raise ValueError
            auth_date = datetime.fromtimestamp(int(auth_value), tz=UTC)
            if auth_date > now + self._future_skew:
                raise ValueError
            if now - auth_date >= self._init_data_ttl:
                raise ValueError
            user = json.loads(fields["user"])
            owner_user_id = user["id"] if isinstance(user, dict) else None
            if (
                isinstance(owner_user_id, bool)
                or not isinstance(owner_user_id, int)
                or owner_user_id != self._owner_user_id
            ):
                raise ValueError
            return auth_date, owner_user_id, replay_digest
        except (
            KeyError,
            OSError,
            OverflowError,
            TypeError,
            UnicodeError,
            ValueError,
        ):
            raise MiniAppAuthenticationError("unauthorized") from None

    def _session(self, bearer: str) -> _Session:
        if (
            not isinstance(bearer, str)
            or not 32 <= len(bearer) <= 128
            or any(character.isspace() for character in bearer)
        ):
            raise MiniAppAuthenticationError("unauthorized")
        with self._lock:
            now = self._now()
            self._expire(now)
            session = self._sessions.get(self._token_digest(bearer))
            if (
                session is None
                or session.owner_user_id != self._owner_user_id
                or session.tenant_id != self._tenant_id
                or session.expires_at <= now
            ):
                raise MiniAppAuthenticationError("unauthorized")
            try:
                current = self._store.miniapp_recovery_current(
                    session.tenant_id, session.auth_context_ref, session.recovery_digest, now=now
                )
            except StoreCorruptionError:
                raise MiniAppCoreUnavailableError("core_unavailable") from None
            if not current or session.expires_at <= self._now():
                raise MiniAppAuthenticationError("unauthorized")
            return session

    def _expire(self, now: datetime) -> None:
        self._sessions = {
            key: value for key, value in self._sessions.items() if value.expires_at > now
        }

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise MiniAppCoreUnavailableError("core_unavailable")
        return value.astimezone(UTC)

    @staticmethod
    def _token_digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _verified_answer(
        self, snapshot: StoredTaskSnapshot
    ) -> OutboxMessage | None:
        projection = snapshot.projection
        try:
            return self._store.read_verified_answer(
                projection.tenant_id,
                projection.task_id,
                task_revision=snapshot.revision,
                task_projection_digest=snapshot.snapshot_digest,
                contract_digest=projection.contract_digest,
                result_revision=projection.result_revision,
                result_digest=projection.result_digest,
            )
        except (StoreCorruptionError, ValueError):
            raise MiniAppCoreUnavailableError("core_unavailable") from None

    @staticmethod
    def _artifact_summary(artifact: OutboxArtifact) -> MiniAppTaskArtifact:
        return MiniAppTaskArtifact(
            artifact_id=artifact.artifact_id,
            filename="nobus-result.txt",
            media_type=artifact.media_type,
            size=artifact.size,
            content_digest=artifact.content_digest,
        )

    def _summary(self, snapshot: StoredTaskSnapshot) -> MiniAppTaskSummary:
        projection = snapshot.projection
        state = product_task_state(projection.status)
        try:
            number = self._store.task_display_number(projection.tenant_id, projection.task_id)
        except StoreCorruptionError:
            raise MiniAppCoreUnavailableError("core_unavailable") from None
        return MiniAppTaskSummary(
            task_id=projection.task_id,
            description=snapshot.display_text or f"Задача №{number}",
            description_available=snapshot.display_text is not None,
            status=state.status,
            status_label=state.label,
            reason=state.reason,
            reason_label=state.reason_label,
            action=state.action,
            terminal=state.terminal,
            source=projection.source.value,
            risk=projection.risk.value,
            created_at=projection.created_at,
            updated_at=projection.updated_at,
        )
