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
from typing import Protocol
from urllib.parse import parse_qsl
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from src.application.task_confirmation import MAX_TASK_INSTRUCTION_LENGTH
from src.contracts import IngressKind, IngressSource, TrustedIngressEnvelope
from src.contracts.models import canonical_json_digest
from src.core.policy import DuplicateIdempotencyKeyError
from src.models.task import TaskStatus
from src.storage import (
    DurableTaskProjection,
    IngressClaimConflictError,
    SQLiteStore,
    StoreCorruptionError,
    StoredTaskSnapshot,
)


_IDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9._~-]{16,128}")


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


class MiniAppSessionGrant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    access_token: str = Field(min_length=32, max_length=128)
    expires_in: StrictInt = Field(ge=1, le=900)


class MiniAppTaskSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: UUID
    status: str
    source: str
    risk: str
    created_at: datetime
    updated_at: datetime


class MiniAppTaskDetail(MiniAppTaskSummary):
    result_revision: StrictInt = Field(ge=0)
    has_result: bool


class MiniAppTaskCreation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: UUID
    status: str


class MiniAppTaskAdmission(Protocol):
    async def submit_miniapp_task(
        self, instruction: str, envelope: TrustedIngressEnvelope
    ) -> UUID: ...

    def miniapp_task_submitted(
        self, tenant_id: str, task_id: UUID, contract_digest: str
    ) -> bool: ...


@dataclass(frozen=True)
class _Session:
    owner_user_id: int
    tenant_id: str
    auth_context_ref: str
    expires_at: datetime


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
        self._sessions: dict[str, _Session] = {}
        self._lock = threading.Lock()
        # ponytail: one owner, so one mutation lock is enough until measured concurrency needs more.
        self._mutation_lock = asyncio.Lock()

    def authenticate(self, raw_init_data: str) -> MiniAppSessionGrant:
        now = self._now()
        auth_date, owner_user_id, replay_digest = self._verify_init_data(
            raw_init_data, now=now
        )
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
            self._expire(now)
            token = secrets.token_urlsafe(32)
            token_digest = self._token_digest(token)
            while token_digest in self._sessions:
                token = secrets.token_urlsafe(32)
                token_digest = self._token_digest(token)
            expires_at = now + self._session_ttl
            self._sessions[token_digest] = _Session(
                owner_user_id=owner_user_id,
                tenant_id=self._tenant_id,
                auth_context_ref=canonical_json_digest(
                    {
                        "bot_ref": self._bot_ref,
                        "owner_user_id": owner_user_id,
                        "session_nonce": secrets.token_hex(16),
                    }
                ),
                expires_at=expires_at,
            )
        return MiniAppSessionGrant(
            access_token=token,
            expires_in=int(self._session_ttl.total_seconds()),
        )

    def list_tasks(
        self, bearer: str, *, limit: int = 20
    ) -> tuple[MiniAppTaskSummary, ...]:
        session = self._session(bearer)
        try:
            snapshots = self._store.list_tasks(session.tenant_id, limit=limit)
        except StoreCorruptionError:
            raise MiniAppCoreUnavailableError("core_unavailable") from None
        return tuple(self._summary(item.projection) for item in snapshots)

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
        return MiniAppTaskDetail(
            **self._summary(projection).model_dump(),
            result_revision=projection.result_revision,
            has_result=projection.result_digest is not None,
        )

    async def create_task(
        self, bearer: str, instruction: str, idempotency_key: str
    ) -> MiniAppTaskCreation:
        normalized = instruction.strip() if isinstance(instruction, str) else ""
        if (
            not normalized
            or len(normalized) > MAX_TASK_INSTRUCTION_LENGTH
            or "\x00" in normalized
            or not isinstance(idempotency_key, str)
            or _IDEMPOTENCY_KEY.fullmatch(idempotency_key) is None
        ):
            raise MiniAppTaskRequestError("invalid_request")
        async with self._mutation_lock:
            session = self._session(bearer)
            return await self._create_task(
                session,
                instruction=normalized,
                idempotency_key=idempotency_key,
            )

    async def _create_task(
        self,
        session: _Session,
        *,
        instruction: str,
        idempotency_key: str,
    ) -> MiniAppTaskCreation:
        admission = self._task_admission
        if admission is None:
            raise MiniAppCoreUnavailableError("core_unavailable")
        envelope = self._task_envelope(
            session,
            instruction=instruction,
            idempotency_key=idempotency_key,
        )
        existing = self._existing_creation(envelope, admission)
        if existing is not None:
            return existing
        try:
            task_id = await admission.submit_miniapp_task(instruction, envelope)
        except (DuplicateIdempotencyKeyError, IngressClaimConflictError):
            existing = self._existing_creation(envelope, admission)
            if existing is not None:
                return existing
            raise MiniAppTaskConflictError("request_conflict") from None
        except Exception:
            existing = self._existing_creation(envelope, admission)
            if existing is not None:
                return existing
            raise MiniAppCoreUnavailableError("core_unavailable") from None
        try:
            snapshot = self._store.read_task(session.tenant_id, task_id)
        except StoreCorruptionError:
            raise MiniAppCoreUnavailableError("core_unavailable") from None
        if snapshot is None or snapshot.projection.tenant_id != session.tenant_id:
            raise MiniAppCoreUnavailableError("core_unavailable")
        return self._creation(snapshot, admission)

    def _existing_creation(
        self,
        envelope: TrustedIngressEnvelope,
        admission: MiniAppTaskAdmission,
    ) -> MiniAppTaskCreation | None:
        try:
            snapshot = self._store.read_ingress_claim(envelope)
        except IngressClaimConflictError:
            raise MiniAppTaskConflictError("request_conflict") from None
        except StoreCorruptionError:
            raise MiniAppCoreUnavailableError("core_unavailable") from None
        return None if snapshot is None else self._creation(snapshot, admission)

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
            status=projection.status.value,
        )

    def _task_envelope(
        self,
        session: _Session,
        *,
        instruction: str,
        idempotency_key: str,
    ) -> TrustedIngressEnvelope:
        content_ref = canonical_json_digest({"instruction": instruction})
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
            "received_at": session.expires_at - self._session_ttl,
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
        now = self._now()
        with self._lock:
            self._expire(now)
            session = self._sessions.get(self._token_digest(bearer))
            if (
                session is None
                or session.owner_user_id != self._owner_user_id
                or session.tenant_id != self._tenant_id
                or session.expires_at <= now
            ):
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

    @staticmethod
    def _summary(projection: DurableTaskProjection) -> MiniAppTaskSummary:
        return MiniAppTaskSummary(
            task_id=projection.task_id,
            status=projection.status.value,
            source=projection.source.value,
            risk=projection.risk.value,
            created_at=projection.created_at,
            updated_at=projection.updated_at,
        )
