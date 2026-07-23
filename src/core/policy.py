"""Deterministic state, idempotency and completion rules for Nobus Core."""

from __future__ import annotations

import threading
from collections.abc import Collection, Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Any
from uuid import UUID

from src.contracts import (
    HumanApprovalRecord,
    RiskLevel,
    TaskContract,
    TrustedIngressEnvelope,
    VerificationBundle,
    VerificationBundleStatus,
    VerificationLevel,
    VerificationLevelStatus,
    WorkerEvent,
)
from src.contracts.models import canonical_json_digest as _canonical_json_digest
from src.models.task import TaskStatus


class PolicyViolation(ValueError):
    """Base error for a rejected Core policy decision."""


class DuplicateIdempotencyKeyError(PolicyViolation):
    """Raised when a task reuses an accepted idempotency key."""


class EventSequenceError(PolicyViolation):
    """Raised when worker events are repeated or out of order."""


class EventBindingError(PolicyViolation):
    """Raised when an event does not match its trusted task/worker binding."""


class TrustedVerifierRegistry:
    """Injected allowlist of verifier identities by L1/L2/L3 role.

    The registry is trusted configuration, not proof that a caller is
    authenticated. A future ingress boundary must authenticate an identity
    before invoking Core with it.
    """

    def __init__(self, assignments: Mapping[int, Collection[str]]) -> None:
        normalized: dict[int, frozenset[str]] = {}
        for level in (1, 2, 3):
            identities = frozenset(
                identity.strip().casefold()
                for identity in assignments.get(level, ())
                if isinstance(identity, str) and identity.strip()
            )
            normalized[level] = identities
        self._assignments = MappingProxyType(normalized)

    def require(self, level: int, identity: str) -> None:
        """Reject identities not assigned to the requested verifier role."""
        if identity.strip().casefold() not in self._assignments[level]:
            raise PolicyViolation(f"identity is not trusted for L{level}")


ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.PARSING, TaskStatus.REJECTED}),
    TaskStatus.PARSING: frozenset(
        {TaskStatus.ROUTING, TaskStatus.DRAFT, TaskStatus.FAILED}
    ),
    TaskStatus.ROUTING: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.FAILED}),
    TaskStatus.IN_PROGRESS: frozenset(
        {TaskStatus.DRAFT, TaskStatus.WAITING_INPUT, TaskStatus.FAILED}
    ),
    TaskStatus.WAITING_INPUT: frozenset(
        {TaskStatus.IN_PROGRESS, TaskStatus.FAILED}
    ),
    TaskStatus.DRAFT: frozenset(
        {
            TaskStatus.L1_VALIDATED,
            TaskStatus.REJECTED,
            TaskStatus.REWORK,
            TaskStatus.DEFERRED,
            TaskStatus.ESCALATE,
        }
    ),
    TaskStatus.L1_VALIDATED: frozenset(
        {
            TaskStatus.L2_VERIFIED,
            TaskStatus.REJECTED,
            TaskStatus.REWORK,
            TaskStatus.ESCALATE,
        }
    ),
    TaskStatus.L2_VERIFIED: frozenset(
        {
            TaskStatus.L3_APPROVED,
            TaskStatus.ANSWERED,
            TaskStatus.REJECTED,
            TaskStatus.REWORK,
            TaskStatus.ESCALATE,
        }
    ),
    TaskStatus.L3_APPROVED: frozenset(
        {
            TaskStatus.COMPLETED,
            TaskStatus.WAITING_HUMAN,
            TaskStatus.REJECTED,
            TaskStatus.ESCALATE,
        }
    ),
    TaskStatus.WAITING_HUMAN: frozenset(
        {TaskStatus.HUMAN_APPROVED, TaskStatus.REJECTED, TaskStatus.ESCALATE}
    ),
    TaskStatus.HUMAN_APPROVED: frozenset(
        {TaskStatus.COMPLETED, TaskStatus.EXECUTING, TaskStatus.REJECTED}
    ),
    TaskStatus.EXECUTING: frozenset(
        {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ESCALATE}
    ),
    TaskStatus.REJECTED: frozenset({TaskStatus.REWORK}),
    TaskStatus.REWORK: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.DRAFT}),
    TaskStatus.DEFERRED: frozenset({TaskStatus.IN_PROGRESS}),
    TaskStatus.ESCALATE: frozenset(),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.ANSWERED: frozenset(),
    TaskStatus.FAILED: frozenset(),
}

VERIFICATION_STAGE_LEVELS: dict[TaskStatus, int] = {
    TaskStatus.L1_VALIDATED: 1,
    TaskStatus.L2_VERIFIED: 2,
    TaskStatus.L3_APPROVED: 3,
    TaskStatus.WAITING_HUMAN: 3,
    TaskStatus.HUMAN_APPROVED: 3,
    TaskStatus.COMPLETED: 3,
    TaskStatus.ANSWERED: 3,
}

_FAILED_STAGE_BY_SOURCE: dict[TaskStatus, int] = {
    TaskStatus.DRAFT: 1,
    TaskStatus.L1_VALIDATED: 2,
    TaskStatus.L2_VERIFIED: 3,
}


def canonical_json_digest(value: Any) -> str:
    """Return a deterministic SHA-256 digest for strict JSON-compatible data."""
    try:
        return _canonical_json_digest(value)
    except ValueError as exc:
        raise PolicyViolation("value is not strict JSON") from exc


def task_contract_digest(contract: TaskContract) -> str:
    """Digest a validated public contract without accepting caller metadata."""
    validated = TaskContract.model_validate(contract.model_dump())
    return canonical_json_digest(validated.model_dump(mode="json"))


class InMemoryPolicyStore:
    """Minimal in-memory guards used until persistent Core storage exists."""

    def __init__(self) -> None:
        self._idempotency_keys: set[tuple[str, str]] = set()
        self._task_contracts: dict[UUID, tuple[str, str]] = {}
        self._attempt_bindings: dict[
            tuple[str, UUID, UUID], tuple[str, str]
        ] = {}
        self._event_ids: set[UUID] = set()
        self._last_sequences: dict[tuple[str, UUID, UUID], int] = {}
        self._trusted_ingress: dict[str, UUID] = {}
        self._registration_lock = threading.Lock()

    def register_contract(
        self,
        contract: TaskContract,
        envelope: TrustedIngressEnvelope,
    ) -> None:
        """Accept a tenant task once and reject duplicate or conflicting bindings."""
        validated = TaskContract.model_validate(contract.model_dump())
        trusted = TrustedIngressEnvelope.model_validate(envelope.model_dump())
        if (
            validated.source != trusted.source.value
            or validated.tenant_id != trusted.tenant_id
            or validated.idempotency_key != trusted.idempotency_key
            or validated.ingress_digest != trusted.envelope_revision
        ):
            raise EventBindingError("contract/ingress binding mismatch")

        key = (validated.tenant_id, validated.idempotency_key)
        with self._registration_lock:
            if key in self._idempotency_keys:
                raise DuplicateIdempotencyKeyError("duplicate idempotency key")
            existing = self._task_contracts.get(validated.task_id)
            if existing is not None:
                if existing[0] != validated.tenant_id:
                    raise EventBindingError("task is already bound to another tenant")
                raise EventBindingError("task is already registered")
            if trusted.envelope_revision in self._trusted_ingress:
                raise EventBindingError("trusted ingress is already registered")
            self._idempotency_keys.add(key)
            self._task_contracts[validated.task_id] = (
                validated.tenant_id,
                task_contract_digest(validated),
            )
            self._trusted_ingress[trusted.envelope_revision] = validated.task_id

    def bind_worker(
        self,
        task_id: UUID,
        tenant_id: str,
        attempt_id: UUID,
        contract_digest: str,
        worker_identity: str,
    ) -> None:
        """Bind one worker and exact contract to one trusted attempt."""
        normalized_worker = worker_identity.strip().casefold()
        if not normalized_worker:
            raise EventBindingError("worker identity must not be empty")
        if self._task_contracts.get(task_id) != (tenant_id, contract_digest):
            raise EventBindingError("worker binding does not match registered task")
        key = (tenant_id, task_id, attempt_id)
        existing = self._attempt_bindings.get(key)
        binding = (contract_digest, normalized_worker)
        if existing is not None and existing != binding:
            raise EventBindingError("attempt is already bound to another worker")
        self._attempt_bindings[key] = binding

    def accept_event(self, event: WorkerEvent) -> None:
        """Accept a validated event only for its registered tenant and worker."""
        validated = WorkerEvent.model_validate(event.model_dump())
        if validated.event_id in self._event_ids:
            raise EventSequenceError("WorkerEvent event_id replay")
        task_binding = (validated.tenant_id, validated.contract_digest)
        if self._task_contracts.get(validated.task_id) != task_binding:
            raise EventBindingError("WorkerEvent tenant/task/contract binding mismatch")
        key = (validated.tenant_id, validated.task_id, validated.attempt_id)
        expected = (
            validated.contract_digest,
            validated.worker_identity.casefold(),
        )
        if self._attempt_bindings.get(key) != expected:
            raise EventBindingError("WorkerEvent attempt/worker binding mismatch")
        previous = self._last_sequences.get(key)
        if previous is not None and validated.sequence <= previous:
            raise EventSequenceError("WorkerEvent sequence must strictly increase")
        self._event_ids.add(validated.event_id)
        self._last_sequences[key] = validated.sequence


def _validate_bundle_binding(
    bundle: VerificationBundle,
    *,
    task_id: UUID,
    tenant_id: str,
    contract_digest: str,
    result_revision: int,
    result_digest: str | None,
    executor_identity: str | None,
) -> None:
    if bundle.task_id != task_id or bundle.tenant_id != tenant_id:
        raise PolicyViolation("VerificationBundle task/tenant binding mismatch")
    if bundle.contract_digest != contract_digest:
        raise PolicyViolation("VerificationBundle contract binding mismatch")
    if (
        result_digest is None
        or bundle.result_revision != result_revision
        or bundle.result_digest != result_digest
    ):
        raise PolicyViolation("VerificationBundle result revision binding mismatch")
    if (
        not executor_identity
        or bundle.executor_identity.casefold() != executor_identity.casefold()
    ):
        raise PolicyViolation("VerificationBundle executor does not match the task")


def _validate_level_set(
    bundle: VerificationBundle,
    *,
    required_count: int,
    verifier_registry: TrustedVerifierRegistry | None,
    failed_level: int | None = None,
) -> None:
    if verifier_registry is None:
        raise PolicyViolation("trusted verifier registry is required")
    levels = (bundle.l1, bundle.l2, bundle.l3)
    used_identities: set[str] = set()
    used_methods: set[str] = set()
    used_refs: set[str] = set()
    used_digests: set[str] = set()
    previous_time: datetime | None = None

    for index, level in enumerate(levels, start=1):
        if index > required_count:
            if level is not None:
                raise PolicyViolation("verification levels must be added sequentially")
            continue
        if level is None:
            raise PolicyViolation(f"verification requires L{index}")
        expected = (
            VerificationLevelStatus.FAILED
            if failed_level == index
            else VerificationLevelStatus.PASSED
        )
        if level.status != expected:
            raise PolicyViolation(f"L{index} has an invalid status for this transition")
        verifier_registry.require(index, level.verifier_identity)
        identity = level.verifier_identity.casefold()
        method = level.method.casefold()
        if identity == bundle.executor_identity.casefold():
            raise PolicyViolation("executor cannot verify its own result")
        if identity in used_identities:
            raise PolicyViolation("required verifiers must be independent")
        if method in used_methods:
            raise PolicyViolation("each verification level requires its own method")
        if used_refs.intersection(level.evidence_refs):
            raise PolicyViolation("verification evidence cannot be reused across levels")
        if level.evidence_digest in used_digests:
            raise PolicyViolation("verification evidence digest cannot be reused")
        if previous_time is not None and level.verified_at < previous_time:
            raise PolicyViolation("verification timestamps must be sequential")
        used_identities.add(identity)
        used_methods.add(method)
        used_refs.update(level.evidence_refs)
        used_digests.add(level.evidence_digest)
        previous_time = level.verified_at


def validate_verification_stage(
    bundle: VerificationBundle | None,
    *,
    task_id: UUID,
    tenant_id: str,
    contract_digest: str,
    result_revision: int,
    result_digest: str | None,
    executor_identity: str | None,
    target: TaskStatus,
    verifier_registry: TrustedVerifierRegistry | None,
) -> None:
    """Prove evidence for one immutable result revision and target state."""
    required_count = VERIFICATION_STAGE_LEVELS[target]
    if bundle is None:
        raise PolicyViolation(f"{target.value} requires a VerificationBundle")
    validated = VerificationBundle.model_validate(bundle.model_dump())
    _validate_bundle_binding(
        validated,
        task_id=task_id,
        tenant_id=tenant_id,
        contract_digest=contract_digest,
        result_revision=result_revision,
        result_digest=result_digest,
        executor_identity=executor_identity,
    )
    _validate_level_set(
        validated,
        required_count=required_count,
        verifier_registry=verifier_registry,
    )
    expected_status = (
        VerificationBundleStatus.APPROVED
        if required_count == 3
        else VerificationBundleStatus.DRAFT
    )
    if validated.status != expected_status:
        raise PolicyViolation("VerificationBundle aggregate status is invalid")


def validate_rejected_verification(
    bundle: VerificationBundle | None,
    *,
    current: TaskStatus,
    task_id: UUID,
    tenant_id: str,
    contract_digest: str,
    result_revision: int,
    result_digest: str | None,
    executor_identity: str | None,
    verifier_registry: TrustedVerifierRegistry | None,
) -> None:
    """Require and preserve evidence for the verification level that failed."""
    failed_level = _FAILED_STAGE_BY_SOURCE[current]
    if bundle is None:
        raise PolicyViolation("rejected verification requires failure evidence")
    validated = VerificationBundle.model_validate(bundle.model_dump())
    _validate_bundle_binding(
        validated,
        task_id=task_id,
        tenant_id=tenant_id,
        contract_digest=contract_digest,
        result_revision=result_revision,
        result_digest=result_digest,
        executor_identity=executor_identity,
    )
    _validate_level_set(
        validated,
        required_count=failed_level,
        verifier_registry=verifier_registry,
        failed_level=failed_level,
    )
    if validated.status != VerificationBundleStatus.REJECTED:
        raise PolicyViolation("failed verification bundle must be rejected")


def validate_completion(
    bundle: VerificationBundle | None,
    *,
    task_id: UUID,
    tenant_id: str,
    contract_digest: str,
    result_revision: int,
    result_digest: str | None,
    executor_identity: str | None,
    verifier_registry: TrustedVerifierRegistry | None,
) -> None:
    validate_verification_stage(
        bundle,
        task_id=task_id,
        tenant_id=tenant_id,
        contract_digest=contract_digest,
        result_revision=result_revision,
        result_digest=result_digest,
        executor_identity=executor_identity,
        target=TaskStatus.COMPLETED,
        verifier_registry=verifier_registry,
    )


def _validate_human_approval(
    approval: HumanApprovalRecord | None,
    *,
    task_id: UUID,
    tenant_id: str,
    contract_digest: str,
    result_revision: int,
    result_digest: str | None,
    executor_identity: str | None,
    bundle: VerificationBundle | None,
) -> None:
    if (
        approval is None
        or approval.task_id != task_id
        or approval.tenant_id != tenant_id
        or approval.contract_digest != contract_digest
        or approval.result_revision != result_revision
        or approval.result_digest != result_digest
    ):
        raise PolicyViolation("HUMAN_APPROVED requires a result-bound L4 record")
    if not executor_identity or bundle is None:
        raise PolicyViolation("L4 approval requires executor and verifier identities")
    excluded = {
        executor_identity.casefold(),
        *(
            level.verifier_identity.casefold()
            for level in (bundle.l1, bundle.l2, bundle.l3)
            if level is not None
        ),
    }
    if approval.approver_identity.casefold() in excluded:
        raise PolicyViolation("L4 approver must be independent from executor and verifiers")


def ensure_transition(
    current: TaskStatus,
    target: TaskStatus,
    *,
    task_id: UUID,
    tenant_id: str,
    contract_digest: str,
    result_revision: int,
    result_digest: str | None,
    risk: RiskLevel,
    bundle: VerificationBundle | None = None,
    executor_identity: str | None = None,
    verifier_registry: TrustedVerifierRegistry | None = None,
    human_approval: HumanApprovalRecord | None = None,
    approval_window_start: datetime | None = None,
    approval_window_end: datetime | None = None,
) -> None:
    """Validate one explicit state transition before mutating state."""
    if target not in ALLOWED_TRANSITIONS[current]:
        raise PolicyViolation(f"invalid task transition: {current.value} -> {target.value}")
    if (
        current == TaskStatus.L3_APPROVED
        and target == TaskStatus.COMPLETED
        and risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}
    ):
        raise PolicyViolation("high-risk completion requires HUMAN_APPROVED")
    if target in VERIFICATION_STAGE_LEVELS:
        validate_verification_stage(
            bundle,
            task_id=task_id,
            tenant_id=tenant_id,
            contract_digest=contract_digest,
            result_revision=result_revision,
            result_digest=result_digest,
            executor_identity=executor_identity,
            target=target,
            verifier_registry=verifier_registry,
        )
    if target == TaskStatus.REJECTED and current in _FAILED_STAGE_BY_SOURCE:
        validate_rejected_verification(
            bundle,
            current=current,
            task_id=task_id,
            tenant_id=tenant_id,
            contract_digest=contract_digest,
            result_revision=result_revision,
            result_digest=result_digest,
            executor_identity=executor_identity,
            verifier_registry=verifier_registry,
        )
    if target == TaskStatus.HUMAN_APPROVED:
        _validate_human_approval(
            human_approval,
            task_id=task_id,
            tenant_id=tenant_id,
            contract_digest=contract_digest,
            result_revision=result_revision,
            result_digest=result_digest,
            executor_identity=executor_identity,
            bundle=bundle,
        )
        assert human_approval is not None
        if (
            approval_window_start is None
            or approval_window_end is None
            or not (
                approval_window_start
                <= human_approval.approved_at
                <= approval_window_end
            )
        ):
            raise PolicyViolation("L4 approval timestamp is outside the approval window")
    if target == TaskStatus.EXECUTING or (
        target == TaskStatus.COMPLETED
        and (
            current in {TaskStatus.HUMAN_APPROVED, TaskStatus.EXECUTING}
            or risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}
        )
    ):
        _validate_human_approval(
            human_approval,
            task_id=task_id,
            tenant_id=tenant_id,
            contract_digest=contract_digest,
            result_revision=result_revision,
            result_digest=result_digest,
            executor_identity=executor_identity,
            bundle=bundle,
        )
