"""Small durable SQLite boundary for trusted ingress, tasks and worker events."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from src.contracts import (
    HumanApprovalRecord,
    RiskLevel,
    TaskContract,
    TrustedIngressEnvelope,
    VerificationBundle,
    WorkerEvent,
)
from src.contracts.models import canonical_json_digest
from src.core.policy import (
    TrustedVerifierRegistry,
    ensure_transition,
    task_contract_digest,
)
from src.models.task import Task, TaskSource, TaskStatus
from src.storage.outbox import (
    DeliveryReceipt,
    OutboxEnqueueResult,
    OutboxMessage,
    OutboxStatus,
    ReceiptType,
    message_fingerprint,
    message_id_for,
)


class StoreCorruptionError(RuntimeError):
    """Stored state failed its integrity or schema checks."""


class IngressClaimConflictError(ValueError):
    """An idempotency key or ingress id was reused for different content."""


class SnapshotConflictError(ValueError):
    """A task snapshot compare-and-swap precondition failed."""


class AuditEventConflictError(ValueError):
    """A worker event identifier or sequence was already used."""


class AuditEventOrderError(ValueError):
    """A worker event did not immediately follow the stored sequence."""


class OutboxConflictError(ValueError):
    """An outbox idempotency binding was reused for different state."""


class OutboxLeaseError(ValueError):
    """A receipt did not match the current unexpired lease."""


class OutboxReceiptConflictError(ValueError):
    """A receipt identifier was already recorded."""


class OutboxCorruptionError(StoreCorruptionError):
    """Stored outbox state failed its row/JSON/digest checks."""


class DurableTaskProjection(BaseModel):
    """Recovery-safe Task metadata; raw operational content is never persisted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: UUID
    tenant_id: str = Field(min_length=1)
    contract_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source: TaskSource
    risk: RiskLevel
    status: TaskStatus
    agent_id: str | None = Field(default=None, min_length=1, max_length=128)
    result_revision: StrictInt = Field(ge=0)
    result_digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    output_digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    verification_bundle: VerificationBundle | None = None
    verification_history: tuple[VerificationBundle, ...] = ()
    human_approval: HumanApprovalRecord | None = None
    approval_history: tuple[HumanApprovalRecord, ...] = ()
    created_at: datetime
    updated_at: datetime


    @model_validator(mode="after")
    def validate_projection(self) -> "DurableTaskProjection":
        for field_name in ("created_at", "updated_at"):
            value = getattr(self, field_name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field_name} must be timezone-aware")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        if self.result_revision == 0:
            if self.result_digest is not None or self.output_digest is not None:
                raise ValueError("an unstarted result cannot have digests")
        elif self.result_digest is None and self.output_digest is not None:
            raise ValueError("output digest requires an active result digest")
        return self


class StoredTaskSnapshot(BaseModel):
    """Validated durable projection plus its compare-and-swap revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    revision: StrictInt = Field(ge=1)
    updated_at: datetime
    snapshot_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    projection: DurableTaskProjection


    @model_validator(mode="after")
    def validate_binding(self) -> "StoredTaskSnapshot":
        if self.updated_at.tzinfo is None or self.updated_at.utcoffset() is None:
            raise ValueError("updated_at must be timezone-aware")
        if self.updated_at != self.projection.updated_at:
            raise ValueError("updated_at must match the durable projection")
        expected = canonical_json_digest(self.projection.model_dump(mode="json"))
        if self.snapshot_digest != expected:
            raise ValueError("snapshot_digest does not match the durable projection")
        return self


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("value is not strict JSON") from exc


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _strict_revision(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("expected_revision must be a positive integer")
    return value


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _validate_task_projection(
    task: Task,
) -> tuple[DurableTaskProjection, str, str]:
    """Create a strict allowlist projection; raw Task content is discarded."""
    validated = Task.model_validate(task.model_dump(mode="json"))
    output_digest: object | None = None
    if validated.result_digest is not None:
        if not isinstance(validated.result, dict) or not validated.result:
            raise ValueError("sealed result requires a non-empty result object")
        output_digest = validated.result.get("output_digest")
        if validated.result_digest != canonical_json_digest(
            {"context": validated.context, "result": validated.result}
        ):
            raise ValueError("result digest does not match the runtime result")
    projection = DurableTaskProjection(
        task_id=validated.id,
        tenant_id=validated.tenant_id,
        contract_digest=validated.contract_digest,
        source=validated.source,
        risk=validated.risk,
        status=validated.status,
        agent_id=validated.agent_id,
        result_revision=validated.result_revision,
        result_digest=validated.result_digest,
        output_digest=output_digest,
        verification_bundle=validated.verification_bundle,
        verification_history=validated.verification_history,
        human_approval=validated.human_approval,
        approval_history=validated.approval_history,
        created_at=validated.created_at,
        updated_at=validated.updated_at,
    )
    data = projection.model_dump(mode="json")
    return projection, _canonical_json(data), canonical_json_digest(data)


def _stable_ingress_fingerprint(envelope: TrustedIngressEnvelope) -> str:
    """Bind retries to stable trusted facts, excluding UUID/time/revision."""
    return canonical_json_digest(
        {
            "tenant_id": envelope.tenant_id,
            "source": envelope.source.value,
            "actor_identity": envelope.actor_identity,
            "external_message_id": envelope.external_message_id,
            "idempotency_key": envelope.idempotency_key,
            "kind": envelope.kind.value,
            "content_ref": envelope.content_ref,
            "auth_context_ref": envelope.auth_context_ref,
        }
    )


def _claim_binding_digest(
    fingerprint: str,
    *,
    tenant_id: str,
    idempotency_key: str,
    task_id: UUID,
    contract_digest: str,
) -> str:
    return canonical_json_digest(
        {
            "ingress_fingerprint": fingerprint,
            "tenant_id": tenant_id,
            "idempotency_key": idempotency_key,
            "task_id": str(task_id),
            "contract_digest": contract_digest,
        }
    )


class SQLiteStore:
    """File-backed stdlib SQLite store with explicit atomic transactions."""

    def __init__(
        self,
        path: str | Path,
        *,
        busy_timeout_ms: int = 5_000,
        verifier_registry: TrustedVerifierRegistry | None = None,
    ) -> None:
        self._path = Path(path)
        self._verifier_registry = verifier_registry
        if str(path) == ":memory:":
            raise ValueError("SQLiteStore requires a durable file path")
        if isinstance(busy_timeout_ms, bool) or not isinstance(busy_timeout_ms, int):
            raise ValueError("busy_timeout_ms must be an integer")
        if busy_timeout_ms < 1:
            raise ValueError("busy_timeout_ms must be positive")
        self._busy_timeout_ms = busy_timeout_ms
        try:
            self._initialize()
        except (OSError, sqlite3.DatabaseError):
            raise StoreCorruptionError("durable store is invalid") from None

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self._path,
            isolation_level=None,
            timeout=self._busy_timeout_ms / 1_000,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS task_snapshots (
                    tenant_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    contract_digest TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK (revision >= 1),
                    updated_at TEXT NOT NULL,
                    projection_digest TEXT NOT NULL,
                    projection_json TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, task_id)
                );

                CREATE TABLE IF NOT EXISTS ingress_claims (
                    tenant_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    ingress_id TEXT NOT NULL,
                    ingress_fingerprint TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    claim_binding_digest TEXT NOT NULL,
                    claimed_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, idempotency_key),
                    UNIQUE (tenant_id, ingress_id),
                    FOREIGN KEY (tenant_id, task_id)
                        REFERENCES task_snapshots (tenant_id, task_id)
                        ON DELETE RESTRICT
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    tenant_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL CHECK (sequence >= 1),
                    event_id TEXT NOT NULL,
                    contract_digest TEXT NOT NULL,
                    worker_identity TEXT NOT NULL,
                    event_digest TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, task_id, attempt_id, sequence),
                    UNIQUE (tenant_id, event_id),
                    FOREIGN KEY (tenant_id, task_id)
                        REFERENCES task_snapshots (tenant_id, task_id)
                        ON DELETE RESTRICT
                );

                CREATE TABLE IF NOT EXISTS outbox_messages (
                    tenant_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    message_fingerprint TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    task_revision INTEGER NOT NULL CHECK (task_revision >= 2),
                    task_projection_digest TEXT NOT NULL,
                    status TEXT NOT NULL
                        CHECK (status IN ('pending','leased','acked','failed')),
                    attempt_count INTEGER NOT NULL CHECK (attempt_count >= 0),
                    max_attempts INTEGER NOT NULL CHECK (max_attempts BETWEEN 1 AND 10),
                    next_attempt_at TEXT,
                    lease_id TEXT,
                    lease_owner TEXT,
                    lease_expires_at TEXT,
                    state_revision INTEGER NOT NULL CHECK (state_revision >= 1),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    message_digest TEXT NOT NULL,
                    message_json TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, message_id),
                    UNIQUE (tenant_id, message_fingerprint),
                    FOREIGN KEY (tenant_id, task_id)
                        REFERENCES task_snapshots (tenant_id, task_id)
                        ON DELETE RESTRICT
                );

                CREATE TABLE IF NOT EXISTS outbox_receipts (
                    tenant_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    receipt_id TEXT NOT NULL,
                    lease_id TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL CHECK (attempt_count >= 1),
                    receipt_type TEXT NOT NULL
                        CHECK (receipt_type IN ('ack','nack','timeout')),
                    received_at TEXT NOT NULL,
                    receipt_digest TEXT NOT NULL,
                    receipt_json TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, message_id, receipt_id),
                    FOREIGN KEY (tenant_id, message_id)
                        REFERENCES outbox_messages (tenant_id, message_id)
                        ON DELETE RESTRICT
                );

                CREATE INDEX IF NOT EXISTS idx_outbox_pending
                    ON outbox_messages (tenant_id, next_attempt_at, created_at)
                    WHERE status = 'pending';

                CREATE INDEX IF NOT EXISTS idx_outbox_expired
                    ON outbox_messages (tenant_id, lease_expires_at)
                    WHERE status = 'leased';

                CREATE INDEX IF NOT EXISTS idx_outbox_receipts
                    ON outbox_receipts (tenant_id, message_id, received_at);
                """
            )

    @staticmethod
    def _snapshot_from_row(
        row: sqlite3.Row, *, tenant_id: str, task_id: UUID
    ) -> StoredTaskSnapshot:
        projection = DurableTaskProjection.model_validate_json(
            row["projection_json"]
        )
        updated_at = datetime.fromisoformat(row["updated_at"])
        expected_digest = canonical_json_digest(projection.model_dump(mode="json"))
        if (
            row["tenant_id"] != tenant_id
            or row["task_id"] != str(task_id)
            or projection.tenant_id != tenant_id
            or projection.task_id != task_id
            or row["contract_digest"] != projection.contract_digest
            or updated_at != projection.updated_at
            or row["projection_digest"] != expected_digest
        ):
            raise ValueError("task snapshot binding mismatch")
        return StoredTaskSnapshot(
            revision=row["revision"],
            updated_at=updated_at,
            snapshot_digest=row["projection_digest"],
            projection=projection,
        )

    @staticmethod
    def _select_task(
        connection: sqlite3.Connection, tenant_id: str, task_id: UUID
    ) -> StoredTaskSnapshot | None:
        row = connection.execute(
            """SELECT tenant_id, task_id, contract_digest, revision, updated_at,
                      projection_digest, projection_json
               FROM task_snapshots WHERE tenant_id = ? AND task_id = ?""",
            (tenant_id, str(task_id)),
        ).fetchone()
        if row is None:
            return None
        return SQLiteStore._snapshot_from_row(
            row, tenant_id=tenant_id, task_id=task_id
        )

    @staticmethod
    def _insert_projection(
        connection: sqlite3.Connection,
        projection: DurableTaskProjection,
        projection_json: str,
        digest: str,
    ) -> StoredTaskSnapshot:
        connection.execute(
            """INSERT INTO task_snapshots
               (tenant_id, task_id, contract_digest, revision, updated_at,
                projection_digest, projection_json)
               VALUES (?, ?, ?, 1, ?, ?, ?)""",
            (
                projection.tenant_id,
                str(projection.task_id),
                projection.contract_digest,
                projection.updated_at.isoformat(),
                digest,
                projection_json,
            ),
        )
        return StoredTaskSnapshot(
            revision=1,
            updated_at=projection.updated_at,
            snapshot_digest=digest,
            projection=projection,
        )

    def read_ingress_claim(
        self,
        envelope: TrustedIngressEnvelope,
    ) -> StoredTaskSnapshot | None:
        """Resolve an existing stable ingress claim without creating state."""
        validated = TrustedIngressEnvelope.model_validate(
            envelope.model_dump(mode="json")
        )
        fingerprint = _stable_ingress_fingerprint(validated)
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    """SELECT ingress_fingerprint, task_id, claim_binding_digest
                       FROM ingress_claims
                       WHERE tenant_id = ? AND idempotency_key = ?""",
                    (validated.tenant_id, validated.idempotency_key),
                ).fetchone()
                if row is None:
                    return None
                if (
                    not _is_digest(row["ingress_fingerprint"])
                    or row["ingress_fingerprint"] != fingerprint
                ):
                    raise IngressClaimConflictError(
                        "trusted ingress claim conflict"
                    )
                stored = self._select_task(
                    connection,
                    validated.tenant_id,
                    UUID(row["task_id"]),
                )
                if stored is None:
                    raise ValueError("ingress claim has no task snapshot")
                expected_binding = _claim_binding_digest(
                    fingerprint,
                    tenant_id=validated.tenant_id,
                    idempotency_key=validated.idempotency_key,
                    task_id=stored.projection.task_id,
                    contract_digest=stored.projection.contract_digest,
                )
                if row["claim_binding_digest"] != expected_binding:
                    raise ValueError("ingress claim binding mismatch")
                return stored
        except IngressClaimConflictError:
            raise
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise StoreCorruptionError("durable store is invalid") from None

    def claim_ingress_with_task(
        self,
        envelope: TrustedIngressEnvelope,
        contract: TaskContract,
        task: Task,
    ) -> tuple[bool, StoredTaskSnapshot]:
        """Atomically claim ingress and persist its initial task snapshot."""
        validated_envelope = TrustedIngressEnvelope.model_validate(
            envelope.model_dump(mode="json")
        )
        validated_contract = TaskContract.model_validate(
            contract.model_dump(mode="json")
        )
        validated_task = Task.model_validate(task.model_dump(mode="json"))
        fingerprint = _stable_ingress_fingerprint(validated_envelope)

        try:
            with self._transaction() as connection:
                row = connection.execute(
                    """SELECT ingress_fingerprint, task_id, claim_binding_digest
                       FROM ingress_claims
                       WHERE tenant_id = ? AND idempotency_key = ?""",
                    (
                        validated_envelope.tenant_id,
                        validated_envelope.idempotency_key,
                    ),
                ).fetchone()
                if row is not None:
                    if not _is_digest(row["ingress_fingerprint"]):
                        raise ValueError("invalid ingress fingerprint")
                    if row["ingress_fingerprint"] != fingerprint:
                        raise IngressClaimConflictError(
                            "trusted ingress claim conflict"
                        )
                    stored = self._select_task(
                        connection,
                        validated_envelope.tenant_id,
                        UUID(row["task_id"]),
                    )
                    if stored is None:
                        raise ValueError("ingress claim has no task snapshot")
                    expected_binding = _claim_binding_digest(
                        fingerprint,
                        tenant_id=validated_envelope.tenant_id,
                        idempotency_key=validated_envelope.idempotency_key,
                        task_id=stored.projection.task_id,
                        contract_digest=stored.projection.contract_digest,
                    )
                    if row["claim_binding_digest"] != expected_binding:
                        raise ValueError("ingress claim binding mismatch")
                    return False, stored

                contract_digest = task_contract_digest(validated_contract)
                if (
                    validated_contract.tenant_id != validated_envelope.tenant_id
                    or validated_contract.source != validated_envelope.source.value
                    or validated_contract.idempotency_key
                    != validated_envelope.idempotency_key
                    or validated_contract.ingress_digest
                    != validated_envelope.envelope_revision
                    or validated_task.id != validated_contract.task_id
                    or validated_task.tenant_id != validated_contract.tenant_id
                    or validated_task.source.value != validated_contract.source
                    or validated_task.contract_digest != contract_digest
                    or validated_task.risk != validated_contract.risk
                    or validated_task.intent != validated_contract.instruction
                    or validated_task.payload
                    != {
                        "acceptance_criteria": list(
                            validated_contract.acceptance_criteria
                        ),
                        "allowed_paths": list(validated_contract.allowed_paths),
                        "ingress_digest": validated_contract.ingress_digest,
                        "ingress_idempotency_key": (
                            validated_contract.idempotency_key
                        ),
                        "permissions": list(validated_contract.permissions),
                        "quality_profile": validated_contract.quality_profile,
                        "timeout_seconds": validated_contract.timeout_seconds,
                    }
                    or validated_task.status != TaskStatus.PENDING
                    or validated_task.external_chat_id is not None
                    or validated_task.agent_id is not None
                    or validated_task.result is not None
                    or validated_task.result_revision != 0
                    or validated_task.result_digest is not None
                    or validated_task.verification_bundle is not None
                    or validated_task.verification_history
                    or validated_task.human_approval is not None
                    or validated_task.approval_history
                    or validated_task.context
                    or validated_task.error_message is not None
                ):
                    raise IngressClaimConflictError(
                        "trusted ingress task binding mismatch"
                    )
                try:
                    projection, projection_json, projection_digest = (
                        _validate_task_projection(validated_task)
                    )
                except ValueError:
                    raise IngressClaimConflictError(
                        "trusted ingress task binding mismatch"
                    ) from None
                try:
                    binding_digest = _claim_binding_digest(
                        fingerprint,
                        tenant_id=validated_envelope.tenant_id,
                        idempotency_key=validated_envelope.idempotency_key,
                        task_id=projection.task_id,
                        contract_digest=projection.contract_digest,
                    )
                    stored = self._insert_projection(
                        connection,
                        projection,
                        projection_json,
                        projection_digest,
                    )
                    connection.execute(
                        """INSERT INTO ingress_claims
                           (tenant_id, idempotency_key, ingress_id,
                            ingress_fingerprint, task_id, claim_binding_digest,
                            claimed_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            validated_envelope.tenant_id,
                            validated_envelope.idempotency_key,
                            str(validated_envelope.ingress_id),
                            fingerprint,
                            str(projection.task_id),
                            binding_digest,
                            validated_envelope.received_at.isoformat(),
                        ),
                    )
                except sqlite3.IntegrityError:
                    raise IngressClaimConflictError(
                        "trusted ingress claim conflict"
                    ) from None
                return True, stored
        except IngressClaimConflictError:
            raise
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise StoreCorruptionError("durable store is invalid") from None

    def _save_task_cas(
        self,
        connection: sqlite3.Connection,
        projection: DurableTaskProjection,
        projection_json: str,
        digest: str,
        *,
        expected_revision: int,
    ) -> StoredTaskSnapshot:
        """Persist one already-validated transition inside the caller transaction."""
        next_revision = expected_revision + 1
        existing = self._select_task(
            connection, projection.tenant_id, projection.task_id
        )
        if existing is None or existing.revision != expected_revision:
            raise SnapshotConflictError("task snapshot revision conflict")
        previous = existing.projection
        if (
            projection.task_id != previous.task_id
            or projection.tenant_id != previous.tenant_id
            or projection.contract_digest != previous.contract_digest
            or projection.source != previous.source
            or projection.risk != previous.risk
            or projection.created_at != previous.created_at
            or projection.result_revision < previous.result_revision
            or projection.updated_at < previous.updated_at
        ):
            raise SnapshotConflictError("task snapshot binding mismatch")
        executor_reassigned_on_redraft = (
            previous.status == TaskStatus.REWORK
            and projection.status == TaskStatus.DRAFT
            and projection.result_revision > previous.result_revision
            and projection.result_digest is not None
        )
        if (
            previous.agent_id is not None
            and projection.agent_id != previous.agent_id
            and not executor_reassigned_on_redraft
        ):
            raise SnapshotConflictError("task executor is immutable")
        clearing_result_for_rework = (
            projection.status == TaskStatus.REWORK
            and previous.result_digest is not None
            and projection.result_digest is None
            and projection.output_digest is None
        )
        if projection.result_revision > previous.result_revision and (
            projection.result_revision != previous.result_revision + 1
            or projection.status != TaskStatus.DRAFT
            or projection.result_digest is None
        ):
            raise SnapshotConflictError(
                "a new result revision must be sealed on DRAFT"
            )
        if (
            projection.result_revision == previous.result_revision
            and (
                projection.result_digest != previous.result_digest
                or projection.output_digest != previous.output_digest
            )
            and not clearing_result_for_rework
        ):
            raise SnapshotConflictError("task result binding is immutable")
        if projection.status == TaskStatus.REWORK:
            expected_verification_history = previous.verification_history + (
                (previous.verification_bundle,)
                if previous.verification_bundle is not None
                else ()
            )
            expected_approval_history = previous.approval_history + (
                (previous.human_approval,)
                if previous.human_approval is not None
                else ()
            )
            if (
                projection.verification_bundle is not None
                or projection.human_approval is not None
                or projection.verification_history
                != expected_verification_history
                or projection.approval_history != expected_approval_history
            ):
                raise SnapshotConflictError(
                    "REWORK must archive the exact active evidence"
                )
        elif (
            projection.verification_history != previous.verification_history
            or projection.approval_history != previous.approval_history
        ):
            raise SnapshotConflictError("task audit history is immutable")
        if previous.verification_bundle is not None:
            current_bundle = projection.verification_bundle
            clearing_for_rework = projection.status == TaskStatus.REWORK
            if not clearing_for_rework and (
                current_bundle is None
                or previous.verification_bundle.tenant_id
                != current_bundle.tenant_id
                or previous.verification_bundle.task_id != current_bundle.task_id
                or previous.verification_bundle.contract_digest
                != current_bundle.contract_digest
                or previous.verification_bundle.result_revision
                != current_bundle.result_revision
                or previous.verification_bundle.result_digest
                != current_bundle.result_digest
                or previous.verification_bundle.executor_identity
                != current_bundle.executor_identity
                or any(
                    old is not None and old != new
                    for old, new in zip(
                        (
                            previous.verification_bundle.l1,
                            previous.verification_bundle.l2,
                            previous.verification_bundle.l3,
                        ),
                        (
                            current_bundle.l1,
                            current_bundle.l2,
                            current_bundle.l3,
                        ),
                    )
                )
            ):
                raise SnapshotConflictError(
                    "task verification evidence is immutable"
                )
        if previous.human_approval is not None:
            clearing_approval_for_rework = projection.status == TaskStatus.REWORK
            if (
                not clearing_approval_for_rework
                and projection.human_approval != previous.human_approval
            ):
                raise SnapshotConflictError(
                    "task approval evidence is immutable"
                )
        try:
            ensure_transition(
                previous.status,
                projection.status,
                task_id=projection.task_id,
                tenant_id=projection.tenant_id,
                contract_digest=projection.contract_digest,
                result_revision=projection.result_revision,
                result_digest=projection.result_digest,
                risk=projection.risk,
                bundle=projection.verification_bundle,
                executor_identity=projection.agent_id,
                verifier_registry=self._verifier_registry,
                human_approval=projection.human_approval,
                approval_window_start=previous.updated_at,
                approval_window_end=projection.updated_at,
            )
        except ValueError:
            raise SnapshotConflictError("task transition rejected") from None
        cursor = connection.execute(
            """UPDATE task_snapshots
               SET revision = ?, updated_at = ?, projection_digest = ?, projection_json = ?
               WHERE tenant_id = ? AND task_id = ? AND revision = ?
                 AND contract_digest = ?""",
            (
                next_revision,
                projection.updated_at.isoformat(),
                digest,
                projection_json,
                projection.tenant_id,
                str(projection.task_id),
                expected_revision,
                projection.contract_digest,
            ),
        )
        if cursor.rowcount != 1:
            raise SnapshotConflictError("task snapshot revision conflict")
        return StoredTaskSnapshot(
            revision=next_revision,
            updated_at=projection.updated_at,
            snapshot_digest=digest,
            projection=projection,
        )

    def save_task(self, task: Task, *, expected_revision: int) -> StoredTaskSnapshot:
        """Compare-and-swap an existing recovery-safe task projection."""
        expected = _strict_revision(expected_revision)
        try:
            projection, projection_json, digest = _validate_task_projection(task)
        except ValueError:
            raise SnapshotConflictError("task result projection is invalid") from None
        try:
            with self._transaction() as connection:
                return self._save_task_cas(
                    connection,
                    projection,
                    projection_json,
                    digest,
                    expected_revision=expected,
                )
        except SnapshotConflictError:
            raise
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise StoreCorruptionError("durable store is invalid") from None

    def read_task(self, tenant_id: str, task_id: UUID) -> StoredTaskSnapshot | None:
        """Read one tenant-scoped task snapshot and verify every stored binding."""
        tenant = _required_text(tenant_id, "tenant_id")
        if not isinstance(task_id, UUID):
            raise ValueError("task_id must be a UUID")
        try:
            with closing(self._connect()) as connection:
                return self._select_task(connection, tenant, task_id)
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise StoreCorruptionError("durable store is invalid") from None

    def _append_event_row(
        self,
        connection: sqlite3.Connection,
        event: WorkerEvent,
        event_json: str,
        event_digest: str,
    ) -> None:
        task_snapshot = self._select_task(
            connection, event.tenant_id, event.task_id
        )
        if (
            task_snapshot is None
            or task_snapshot.projection.contract_digest != event.contract_digest
        ):
            raise AuditEventConflictError("worker event task binding mismatch")

        existing_id = connection.execute(
            """SELECT event_digest FROM audit_events
               WHERE tenant_id = ? AND event_id = ?""",
            (event.tenant_id, str(event.event_id)),
        ).fetchone()
        if existing_id is not None:
            raise AuditEventConflictError("worker event id already exists")

        previous = connection.execute(
            """SELECT sequence, worker_identity FROM audit_events
               WHERE tenant_id = ? AND task_id = ? AND attempt_id = ?
               ORDER BY sequence DESC LIMIT 1""",
            (
                event.tenant_id,
                str(event.task_id),
                str(event.attempt_id),
            ),
        ).fetchone()
        expected = 1 if previous is None else previous["sequence"] + 1
        if event.sequence != expected:
            raise AuditEventOrderError(
                f"worker event sequence must be {expected}"
            )
        if (
            previous is not None
            and previous["worker_identity"].casefold()
            != event.worker_identity.casefold()
        ):
            raise AuditEventConflictError("worker attempt identity mismatch")

        try:
            connection.execute(
                """INSERT INTO audit_events
                   (tenant_id, task_id, attempt_id, sequence, event_id,
                    contract_digest, worker_identity, event_digest, event_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.tenant_id,
                    str(event.task_id),
                    str(event.attempt_id),
                    event.sequence,
                    str(event.event_id),
                    event.contract_digest,
                    event.worker_identity,
                    event_digest,
                    event_json,
                ),
            )
        except sqlite3.IntegrityError:
            raise AuditEventConflictError("worker event conflict") from None

    def append_event(self, event: WorkerEvent) -> None:
        """Append one strictly ordered, task-bound worker audit event."""
        validated = WorkerEvent.model_validate(event.model_dump(mode="json"))
        event_data = validated.model_dump(mode="json")
        event_json = _canonical_json(event_data)
        event_digest = canonical_json_digest(event_data)

        try:
            with self._transaction() as connection:
                self._append_event_row(
                    connection, validated, event_json, event_digest
                )
        except (AuditEventConflictError, AuditEventOrderError):
            raise
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise StoreCorruptionError("durable store is invalid") from None

    def save_task_and_append_event(
        self,
        task: Task,
        event: WorkerEvent,
        *,
        expected_revision: int,
    ) -> StoredTaskSnapshot:
        """Atomically persist one Task transition and its worker audit event."""
        expected = _strict_revision(expected_revision)
        try:
            projection, projection_json, projection_digest = (
                _validate_task_projection(task)
            )
            validated_event = WorkerEvent.model_validate(
                event.model_dump(mode="json")
            )
        except ValueError:
            raise SnapshotConflictError("task or event projection is invalid") from None
        if (
            validated_event.tenant_id != projection.tenant_id
            or validated_event.task_id != projection.task_id
            or validated_event.contract_digest != projection.contract_digest
        ):
            raise AuditEventConflictError("worker event task binding mismatch")
        event_data = validated_event.model_dump(mode="json")
        event_json = _canonical_json(event_data)
        event_digest = canonical_json_digest(event_data)

        try:
            with self._transaction() as connection:
                snapshot = self._save_task_cas(
                    connection,
                    projection,
                    projection_json,
                    projection_digest,
                    expected_revision=expected,
                )
                self._append_event_row(
                    connection, validated_event, event_json, event_digest
                )
                return snapshot
        except (
            SnapshotConflictError,
            AuditEventConflictError,
            AuditEventOrderError,
        ):
            raise
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise StoreCorruptionError("durable store is invalid") from None

    def read_events(
        self, tenant_id: str, task_id: UUID, attempt_id: UUID
    ) -> tuple[WorkerEvent, ...]:
        """Return an attempt only after verifying every row and JSON binding."""
        tenant = _required_text(tenant_id, "tenant_id")
        if not isinstance(task_id, UUID) or not isinstance(attempt_id, UUID):
            raise ValueError("task_id and attempt_id must be UUID values")
        try:
            with closing(self._connect()) as connection:
                task_snapshot = self._select_task(connection, tenant, task_id)
                if task_snapshot is None:
                    return ()
                rows = connection.execute(
                    """SELECT tenant_id, task_id, attempt_id, sequence, event_id,
                              contract_digest, worker_identity, event_digest, event_json
                       FROM audit_events
                       WHERE tenant_id = ? AND task_id = ? AND attempt_id = ?
                       ORDER BY sequence""",
                    (tenant, str(task_id), str(attempt_id)),
                ).fetchall()
                events: list[WorkerEvent] = []
                worker_identity: str | None = None
                for expected_sequence, row in enumerate(rows, start=1):
                    parsed = WorkerEvent.model_validate_json(row["event_json"])
                    digest = canonical_json_digest(parsed.model_dump(mode="json"))
                    if (
                        row["tenant_id"] != tenant
                        or row["task_id"] != str(task_id)
                        or row["attempt_id"] != str(attempt_id)
                        or row["sequence"] != expected_sequence
                        or row["event_id"] != str(parsed.event_id)
                        or parsed.tenant_id != tenant
                        or parsed.task_id != task_id
                        or parsed.attempt_id != attempt_id
                        or parsed.sequence != expected_sequence
                        or row["contract_digest"] != parsed.contract_digest
                        or parsed.contract_digest
                        != task_snapshot.projection.contract_digest
                        or row["worker_identity"] != parsed.worker_identity
                        or row["event_digest"] != digest
                        or (
                            worker_identity is not None
                            and worker_identity.casefold()
                            != parsed.worker_identity.casefold()
                        )
                    ):
                        raise ValueError("worker event binding mismatch")
                    worker_identity = parsed.worker_identity
                    events.append(parsed)
                return tuple(events)
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise StoreCorruptionError("durable store is invalid") from None

    @staticmethod
    def _outbox_from_row(
        row: sqlite3.Row, *, tenant_id: str, message_id: UUID
    ) -> OutboxMessage:
        try:
            message = OutboxMessage.model_validate_json(row["message_json"])
            digest = canonical_json_digest(message.model_dump(mode="json"))
        except (ValueError, TypeError):
            raise OutboxCorruptionError("outbox message is invalid") from None
        bindings = (
            row["tenant_id"] == tenant_id == message.tenant_id,
            row["message_id"] == str(message_id) == str(message.message_id),
            row["message_fingerprint"] == message.message_fingerprint,
            row["task_id"] == str(message.task_id),
            row["task_revision"] == message.task_revision,
            row["task_projection_digest"] == message.task_projection_digest,
            row["status"] == message.status.value,
            row["attempt_count"] == message.attempt_count,
            row["max_attempts"] == message.max_attempts,
            row["next_attempt_at"]
            == (
                message.next_attempt_at.isoformat()
                if message.next_attempt_at is not None
                else None
            ),
            row["lease_id"]
            == (str(message.lease_id) if message.lease_id is not None else None),
            row["lease_owner"]
            == (
                str(message.lease_owner)
                if message.lease_owner is not None
                else None
            ),
            row["lease_expires_at"]
            == (
                message.lease_expires_at.isoformat()
                if message.lease_expires_at is not None
                else None
            ),
            row["state_revision"] == message.state_revision,
            row["created_at"] == message.created_at.isoformat(),
            row["updated_at"] == message.updated_at.isoformat(),
            row["message_digest"] == digest,
        )
        if not all(bindings):
            raise OutboxCorruptionError("outbox message binding mismatch")
        return message

    @staticmethod
    def _select_outbox_message(
        connection: sqlite3.Connection, tenant_id: str, message_id: UUID
    ) -> OutboxMessage | None:
        row = connection.execute(
            """SELECT tenant_id, message_id, message_fingerprint, task_id,
                      task_revision, task_projection_digest, status, attempt_count, max_attempts,
                      next_attempt_at, lease_id, lease_owner, lease_expires_at,
                      state_revision, created_at, updated_at, message_digest,
                      message_json
               FROM outbox_messages
               WHERE tenant_id = ? AND message_id = ?""",
            (tenant_id, str(message_id)),
        ).fetchone()
        if row is None:
            return None
        return SQLiteStore._outbox_from_row(
            row, tenant_id=tenant_id, message_id=message_id
        )

    @staticmethod
    def _update_outbox_message(
        connection: sqlite3.Connection,
        message: OutboxMessage,
        *,
        previous_state_revision: int,
        previous_digest: str,
    ) -> None:
        data = message.model_dump(mode="json")
        message_json = _canonical_json(data)
        digest = canonical_json_digest(data)
        cursor = connection.execute(
            """UPDATE outbox_messages
               SET status = ?, attempt_count = ?, max_attempts = ?,
                   next_attempt_at = ?, lease_id = ?, lease_owner = ?,
                   lease_expires_at = ?, state_revision = ?, updated_at = ?,
                   message_digest = ?, message_json = ?
               WHERE tenant_id = ? AND message_id = ?
                 AND state_revision = ? AND message_digest = ?""",
            (
                message.status.value,
                message.attempt_count,
                message.max_attempts,
                (
                    message.next_attempt_at.isoformat()
                    if message.next_attempt_at is not None
                    else None
                ),
                str(message.lease_id) if message.lease_id is not None else None,
                (
                    str(message.lease_owner)
                    if message.lease_owner is not None
                    else None
                ),
                (
                    message.lease_expires_at.isoformat()
                    if message.lease_expires_at is not None
                    else None
                ),
                message.state_revision,
                message.updated_at.isoformat(),
                digest,
                message_json,
                message.tenant_id,
                str(message.message_id),
                previous_state_revision,
                previous_digest,
            ),
        )
        if cursor.rowcount != 1:
            raise OutboxCorruptionError("outbox lifecycle CAS failed")

    def save_task_and_enqueue_status(
        self,
        task: Task,
        *,
        expected_revision: int,
        destination_ref: str,
        event: WorkerEvent | None = None,
        max_attempts: int = 3,
        now: datetime | None = None,
    ) -> OutboxEnqueueResult:
        """Atomically persist one Task transition and its safe status notice."""
        expected = _strict_revision(expected_revision)
        if not _is_digest(destination_ref):
            raise ValueError("destination_ref must be a sha256 reference")
        if (
            isinstance(max_attempts, bool)
            or not isinstance(max_attempts, int)
            or not 1 <= max_attempts <= 10
        ):
            raise ValueError("max_attempts must be an integer from 1 to 10")
        timestamp = now or datetime.now(UTC)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        timestamp = timestamp.astimezone(UTC)
        try:
            projection, projection_json, projection_digest = (
                _validate_task_projection(task)
            )
        except ValueError:
            raise SnapshotConflictError("task result projection is invalid") from None

        validated_event: WorkerEvent | None = None
        event_json = ""
        event_digest = ""
        if event is not None:
            try:
                validated_event = WorkerEvent.model_validate(
                    event.model_dump(mode="json")
                )
            except ValueError:
                raise AuditEventConflictError("worker event is invalid") from None
            if (
                validated_event.tenant_id != projection.tenant_id
                or validated_event.task_id != projection.task_id
                or validated_event.contract_digest != projection.contract_digest
            ):
                raise AuditEventConflictError("worker event task binding mismatch")
            event_data = validated_event.model_dump(mode="json")
            event_json = _canonical_json(event_data)
            event_digest = canonical_json_digest(event_data)

        task_revision = expected + 1
        fingerprint = message_fingerprint(
            tenant_id=projection.tenant_id,
            task_id=projection.task_id,
            task_revision=task_revision,
            task_projection_digest=projection_digest,
            contract_digest=projection.contract_digest,
            result_revision=projection.result_revision,
            result_digest=projection.result_digest,
            destination_ref=destination_ref,
            task_status=projection.status,
        )
        message_id = message_id_for(fingerprint)
        pending = OutboxMessage(
            message_id=message_id,
            message_fingerprint=fingerprint,
            tenant_id=projection.tenant_id,
            task_id=projection.task_id,
            task_revision=task_revision,
            task_projection_digest=projection_digest,
            contract_digest=projection.contract_digest,
            result_revision=projection.result_revision,
            result_digest=projection.result_digest,
            destination_ref=destination_ref,
            template_id="task_status",
            task_status=projection.status,
            status=OutboxStatus.PENDING,
            attempt_count=0,
            max_attempts=max_attempts,
            state_revision=1,
            created_at=timestamp,
            updated_at=timestamp,
        )
        try:
            with self._transaction() as connection:
                existing = self._select_outbox_message(
                    connection, projection.tenant_id, message_id
                )
                if existing is not None:
                    if (
                        existing.message_fingerprint != fingerprint
                        or existing.task_id != projection.task_id
                        or existing.task_revision != task_revision
                        or existing.task_projection_digest != projection_digest
                        or existing.contract_digest != projection.contract_digest
                        or existing.result_revision != projection.result_revision
                        or existing.result_digest != projection.result_digest
                        or existing.destination_ref != destination_ref
                        or existing.task_status != projection.status
                        or existing.max_attempts != max_attempts
                    ):
                        raise OutboxConflictError(
                            "outbox idempotency binding mismatch"
                        )
                    return OutboxEnqueueResult(
                        created=False,
                        task_revision=existing.task_revision,
                        message=existing,
                    )

                stored = self._save_task_cas(
                    connection,
                    projection,
                    projection_json,
                    projection_digest,
                    expected_revision=expected,
                )
                if validated_event is not None:
                    self._append_event_row(
                        connection,
                        validated_event,
                        event_json,
                        event_digest,
                    )
                message_data = pending.model_dump(mode="json")
                message_json = _canonical_json(message_data)
                message_digest = canonical_json_digest(message_data)
                connection.execute(
                    """INSERT INTO outbox_messages
                       (tenant_id, message_id, message_fingerprint, task_id,
                        task_revision, task_projection_digest, status, attempt_count, max_attempts,
                        next_attempt_at, lease_id, lease_owner,
                        lease_expires_at, state_revision, created_at,
                        updated_at, message_digest, message_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        pending.tenant_id,
                        str(pending.message_id),
                        pending.message_fingerprint,
                        str(pending.task_id),
                        pending.task_revision,
                        pending.task_projection_digest,
                        pending.status.value,
                        pending.attempt_count,
                        pending.max_attempts,
                        None,
                        None,
                        None,
                        None,
                        pending.state_revision,
                        pending.created_at.isoformat(),
                        pending.updated_at.isoformat(),
                        message_digest,
                        message_json,
                    ),
                )
                return OutboxEnqueueResult(
                    created=True,
                    task_revision=stored.revision,
                    message=pending,
                )
        except (
            SnapshotConflictError,
            OutboxConflictError,
            OutboxCorruptionError,
            AuditEventConflictError,
            AuditEventOrderError,
        ):
            raise
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise StoreCorruptionError("durable store is invalid") from None

    def claim_outbox_messages(
        self,
        tenant_id: str,
        *,
        lease_owner: UUID,
        lease_duration_seconds: int,
        limit: int = 10,
        now: datetime | None = None,
    ) -> tuple[OutboxMessage, ...]:
        """Reclaim expired work and return post-update leased messages."""
        tenant = _required_text(tenant_id, "tenant_id")
        if not isinstance(lease_owner, UUID):
            raise ValueError("lease_owner must be a UUID")
        if (
            isinstance(lease_duration_seconds, bool)
            or not isinstance(lease_duration_seconds, int)
            or lease_duration_seconds < 1
            or lease_duration_seconds > 3600
        ):
            raise ValueError("lease_duration_seconds must be between 1 and 3600")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError("limit must be between 1 and 100")
        timestamp = now or datetime.now(UTC)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        timestamp = timestamp.astimezone(UTC)
        lease_expires_at = timestamp + timedelta(seconds=lease_duration_seconds)

        try:
            with self._transaction() as connection:
                expired_rows = connection.execute(
                    """SELECT tenant_id, message_id, message_fingerprint, task_id,
                              task_revision, task_projection_digest, status, attempt_count, max_attempts,
                              next_attempt_at, lease_id, lease_owner,
                              lease_expires_at, state_revision, created_at,
                              updated_at, message_digest, message_json
                       FROM outbox_messages
                       WHERE tenant_id = ? AND status = 'leased'
                         AND lease_expires_at <= ?
                       ORDER BY lease_expires_at, message_id LIMIT ?""",
                    (tenant, timestamp.isoformat(), limit),
                ).fetchall()
                for row in expired_rows:
                    message = self._outbox_from_row(
                        row,
                        tenant_id=tenant,
                        message_id=UUID(row["message_id"]),
                    )
                    if timestamp < message.updated_at:
                        raise OutboxCorruptionError("outbox clock moved backwards")
                    failed = message.attempt_count >= message.max_attempts
                    reclaimed = message.model_copy(
                        update={
                            "status": (
                                OutboxStatus.FAILED
                                if failed
                                else OutboxStatus.PENDING
                            ),
                            "next_attempt_at": None if failed else timestamp,
                            "lease_id": None,
                            "lease_owner": None,
                            "lease_expires_at": None,
                            "state_revision": message.state_revision + 1,
                            "updated_at": timestamp,
                        }
                    )
                    reclaimed = OutboxMessage.model_validate(
                        reclaimed.model_dump(mode="json")
                    )
                    self._update_outbox_message(
                        connection,
                        reclaimed,
                        previous_state_revision=message.state_revision,
                        previous_digest=row["message_digest"],
                    )

                rows = connection.execute(
                    """SELECT tenant_id, message_id, message_fingerprint, task_id,
                              task_revision, task_projection_digest, status, attempt_count, max_attempts,
                              next_attempt_at, lease_id, lease_owner,
                              lease_expires_at, state_revision, created_at,
                              updated_at, message_digest, message_json
                       FROM outbox_messages
                       WHERE tenant_id = ? AND status = 'pending'
                         AND attempt_count < max_attempts
                         AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                       ORDER BY created_at, message_id LIMIT ?""",
                    (tenant, timestamp.isoformat(), limit),
                ).fetchall()
                leased: list[OutboxMessage] = []
                for row in rows:
                    message = self._outbox_from_row(
                        row,
                        tenant_id=tenant,
                        message_id=UUID(row["message_id"]),
                    )
                    if timestamp < message.updated_at:
                        raise OutboxCorruptionError("outbox clock moved backwards")
                    claimed = message.model_copy(
                        update={
                            "status": OutboxStatus.LEASED,
                            "attempt_count": message.attempt_count + 1,
                            "next_attempt_at": None,
                            "lease_id": uuid4(),
                            "lease_owner": lease_owner,
                            "lease_expires_at": lease_expires_at,
                            "state_revision": message.state_revision + 1,
                            "updated_at": timestamp,
                        }
                    )
                    claimed = OutboxMessage.model_validate(
                        claimed.model_dump(mode="json")
                    )
                    self._update_outbox_message(
                        connection,
                        claimed,
                        previous_state_revision=message.state_revision,
                        previous_digest=row["message_digest"],
                    )
                    leased.append(claimed)
                return tuple(leased)
        except OutboxCorruptionError:
            raise
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise StoreCorruptionError("durable store is invalid") from None

    def record_outbox_receipt(
        self,
        receipt: DeliveryReceipt,
        *,
        lease_owner: UUID,
        now: datetime | None = None,
    ) -> OutboxMessage:
        """Record an outcome only for the exact current unexpired lease."""
        validated = DeliveryReceipt.model_validate(receipt.model_dump(mode="json"))
        if not isinstance(lease_owner, UUID):
            raise ValueError("lease_owner must be a UUID")
        timestamp = now or datetime.now(UTC)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        timestamp = timestamp.astimezone(UTC)
        if validated.received_at > timestamp:
            raise ValueError("receipt time cannot be in the future")

        try:
            with self._transaction() as connection:
                duplicate = connection.execute(
                    """SELECT 1 FROM outbox_receipts
                       WHERE tenant_id = ? AND message_id = ? AND receipt_id = ?""",
                    (
                        validated.tenant_id,
                        str(validated.message_id),
                        str(validated.receipt_id),
                    ),
                ).fetchone()
                if duplicate is not None:
                    raise OutboxReceiptConflictError("receipt already recorded")
                row = connection.execute(
                    """SELECT tenant_id, message_id, message_fingerprint, task_id,
                              task_revision, task_projection_digest, status, attempt_count, max_attempts,
                              next_attempt_at, lease_id, lease_owner,
                              lease_expires_at, state_revision, created_at,
                              updated_at, message_digest, message_json
                       FROM outbox_messages
                       WHERE tenant_id = ? AND message_id = ?""",
                    (validated.tenant_id, str(validated.message_id)),
                ).fetchone()
                if row is None:
                    raise OutboxLeaseError("message is not leased")
                message = self._outbox_from_row(
                    row,
                    tenant_id=validated.tenant_id,
                    message_id=validated.message_id,
                )
                if (
                    message.status is not OutboxStatus.LEASED
                    or message.lease_owner != lease_owner
                    or message.lease_id != validated.lease_id
                    or message.attempt_count != validated.attempt_count
                    or message.lease_expires_at is None
                    or message.lease_expires_at <= timestamp
                    or validated.received_at < message.updated_at
                ):
                    raise OutboxLeaseError("receipt does not match current lease")

                if validated.receipt_type is ReceiptType.ACK:
                    new_status = OutboxStatus.ACKED
                    next_attempt_at = None
                elif message.attempt_count >= message.max_attempts:
                    new_status = OutboxStatus.FAILED
                    next_attempt_at = None
                else:
                    new_status = OutboxStatus.PENDING
                    delay = min(2 ** (message.attempt_count - 1), 300)
                    next_attempt_at = timestamp + timedelta(seconds=delay)
                updated = message.model_copy(
                    update={
                        "status": new_status,
                        "next_attempt_at": next_attempt_at,
                        "lease_id": None,
                        "lease_owner": None,
                        "lease_expires_at": None,
                        "state_revision": message.state_revision + 1,
                        "updated_at": timestamp,
                    }
                )
                updated = OutboxMessage.model_validate(
                    updated.model_dump(mode="json")
                )
                self._update_outbox_message(
                    connection,
                    updated,
                    previous_state_revision=message.state_revision,
                    previous_digest=row["message_digest"],
                )
                receipt_data = validated.model_dump(mode="json")
                connection.execute(
                    """INSERT INTO outbox_receipts
                       (tenant_id, message_id, receipt_id, lease_id,
                        attempt_count, receipt_type, received_at,
                        receipt_digest, receipt_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        validated.tenant_id,
                        str(validated.message_id),
                        str(validated.receipt_id),
                        str(validated.lease_id),
                        validated.attempt_count,
                        validated.receipt_type.value,
                        validated.received_at.isoformat(),
                        canonical_json_digest(receipt_data),
                        _canonical_json(receipt_data),
                    ),
                )
                return updated
        except (
            OutboxCorruptionError,
            OutboxLeaseError,
            OutboxReceiptConflictError,
        ):
            raise
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise StoreCorruptionError("durable store is invalid") from None

    def read_outbox_message(
        self, tenant_id: str, message_id: UUID
    ) -> OutboxMessage | None:
        tenant = _required_text(tenant_id, "tenant_id")
        if not isinstance(message_id, UUID):
            raise ValueError("message_id must be a UUID")
        try:
            with closing(self._connect()) as connection:
                return self._select_outbox_message(connection, tenant, message_id)
        except OutboxCorruptionError:
            raise
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise StoreCorruptionError("durable store is invalid") from None

    def read_outbox_receipts(
        self, tenant_id: str, message_id: UUID
    ) -> tuple[DeliveryReceipt, ...]:
        tenant = _required_text(tenant_id, "tenant_id")
        if not isinstance(message_id, UUID):
            raise ValueError("message_id must be a UUID")
        try:
            with closing(self._connect()) as connection:
                if self._select_outbox_message(connection, tenant, message_id) is None:
                    return ()
                rows = connection.execute(
                    """SELECT tenant_id, message_id, receipt_id, lease_id,
                              attempt_count, receipt_type, received_at,
                              receipt_digest, receipt_json
                       FROM outbox_receipts
                       WHERE tenant_id = ? AND message_id = ?
                       ORDER BY received_at, receipt_id""",
                    (tenant, str(message_id)),
                ).fetchall()
                receipts: list[DeliveryReceipt] = []
                for row in rows:
                    try:
                        receipt = DeliveryReceipt.model_validate_json(
                            row["receipt_json"]
                        )
                        digest = canonical_json_digest(
                            receipt.model_dump(mode="json")
                        )
                    except (ValueError, TypeError):
                        raise OutboxCorruptionError(
                            "outbox receipt is invalid"
                        ) from None
                    if (
                        row["tenant_id"] != tenant
                        or row["message_id"] != str(message_id)
                        or row["receipt_id"] != str(receipt.receipt_id)
                        or row["lease_id"] != str(receipt.lease_id)
                        or row["attempt_count"] != receipt.attempt_count
                        or row["receipt_type"] != receipt.receipt_type.value
                        or row["received_at"] != receipt.received_at.isoformat()
                        or row["receipt_digest"] != digest
                        or receipt.tenant_id != tenant
                        or receipt.message_id != message_id
                    ):
                        raise OutboxCorruptionError(
                            "outbox receipt binding mismatch"
                        )
                    receipts.append(receipt)
                return tuple(receipts)
        except OutboxCorruptionError:
            raise
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise StoreCorruptionError("durable store is invalid") from None
