"""In-memory state manager for the orchestrator sandbox."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

from src.contracts import (
    HumanApprovalRecord,
    RiskLevel,
    TaskContract,
    VerificationBundle,
)
from src.core.policy import (
    PolicyViolation,
    TrustedVerifierRegistry,
    VERIFICATION_STAGE_LEVELS,
    canonical_json_digest,
    ensure_transition,
    task_contract_digest,
    validate_verification_stage,
)
from src.models.task import Task, TaskSource, TaskStatus


EXECUTOR_LOCKED_STATUSES = frozenset(
    {
        TaskStatus.DRAFT,
        TaskStatus.L1_VALIDATED,
        TaskStatus.L2_VERIFIED,
        TaskStatus.L3_APPROVED,
        TaskStatus.WAITING_HUMAN,
        TaskStatus.HUMAN_APPROVED,
        TaskStatus.EXECUTING,
    }
)
BUNDLE_LOCKED_STATUSES = frozenset(
    {
        TaskStatus.L3_APPROVED,
        TaskStatus.WAITING_HUMAN,
        TaskStatus.HUMAN_APPROVED,
        TaskStatus.EXECUTING,
    }
)


class StateManager:
    """Manage task state in memory behind deterministic Core policy."""

    def __init__(
        self, verifier_registry: TrustedVerifierRegistry | None = None
    ) -> None:
        self._tasks: dict[UUID, Task] = {}
        self._verifier_registry = verifier_registry

    async def create(
        self,
        source: str,
        external_chat_id: str | None,
        intent: str,
        payload: dict[str, Any],
        risk: RiskLevel = RiskLevel.LOW,
        tenant_id: str = "local",
    ) -> Task:
        """Create a task and seal the immutable local contract projection."""
        normalized_source = TaskSource(source)
        contract_digest = canonical_json_digest(
            {
                "tenant_id": tenant_id,
                "source": normalized_source.value,
                "external_chat_id": external_chat_id,
                "intent": intent,
                "payload": payload,
                "risk": RiskLevel(risk).value,
            }
        )
        task = Task(
            id=uuid4(),
            tenant_id=tenant_id,
            contract_digest=contract_digest,
            source=normalized_source,
            external_chat_id=external_chat_id,
            intent=intent,
            payload=deepcopy(payload),
            risk=risk,
            status=TaskStatus.PENDING,
        )
        self._tasks[task.id] = task
        return task.model_copy(deep=True)

    async def create_from_contract(
        self,
        contract: TaskContract,
        *,
        before_commit: Callable[[Task], None] | None = None,
    ) -> Task:
        """Create one runtime task with the exact accepted contract binding."""
        validated = TaskContract.model_validate(contract.model_dump())
        if validated.task_id in self._tasks:
            raise PolicyViolation("task is already registered")
        task = Task(
            id=validated.task_id,
            tenant_id=validated.tenant_id,
            contract_digest=task_contract_digest(validated),
            source=TaskSource(validated.source),
            intent=validated.instruction,
            payload={
                "acceptance_criteria": list(validated.acceptance_criteria),
                "allowed_paths": list(validated.allowed_paths),
                "ingress_digest": validated.ingress_digest,
                "ingress_idempotency_key": validated.idempotency_key,
                "permissions": list(validated.permissions),
                "quality_profile": validated.quality_profile,
                "timeout_seconds": validated.timeout_seconds,
            },
            risk=validated.risk,
            status=TaskStatus.PENDING,
        )
        if before_commit is not None:
            before_commit(task.model_copy(deep=True))
        self._tasks[task.id] = task
        return task.model_copy(deep=True)

    async def update(
        self,
        task_id: UUID,
        status: TaskStatus | None = None,
        agent_id: str | None = None,
        result: dict[str, Any] | None = None,
        verification_bundle: VerificationBundle | None = None,
        human_approval: HumanApprovalRecord | None = None,
        error_message: str | None = None,
        context: dict[str, Any] | None = None,
        before_commit: Callable[[Task], None] | None = None,
    ) -> Task | None:
        """Validate and atomically store one task update."""
        task = self._tasks.get(task_id)
        if task is None:
            return None

        supplied_values = (
            status,
            agent_id,
            result,
            verification_bundle,
            human_approval,
            error_message,
            context,
        )
        if task.status in {
            TaskStatus.COMPLETED,
            TaskStatus.ANSWERED,
            TaskStatus.FAILED,
            TaskStatus.ESCALATE,
        }:
            if any(value is not None for value in supplied_values):
                raise PolicyViolation("terminal task audit record is immutable")
            return task.model_copy(deep=True)

        entering_rework = status == TaskStatus.REWORK
        non_status_values = (
            agent_id,
            result,
            verification_bundle,
            human_approval,
            error_message,
            context,
        )
        if task.status == TaskStatus.REJECTED and (
            not entering_rework
            or any(value is not None for value in non_status_values)
        ):
            raise PolicyViolation("REJECTED audit record only permits a clean REWORK")
        if entering_rework and any(value is not None for value in non_status_values):
            raise PolicyViolation("REWORK reset cannot replace audit fields")

        entering_draft = status == TaskStatus.DRAFT and task.status != TaskStatus.DRAFT
        if entering_draft and not result:
            raise PolicyViolation("DRAFT requires a non-empty result")

        candidate_data = deepcopy(task.model_dump())
        candidate_data["updated_at"] = datetime.now(UTC)
        if entering_rework:
            if task.verification_bundle is not None:
                candidate_data["verification_history"] = (
                    *task.verification_history,
                    task.verification_bundle,
                )
            if task.human_approval is not None:
                candidate_data["approval_history"] = (
                    *task.approval_history,
                    task.human_approval,
                )
            candidate_data["verification_bundle"] = None
            candidate_data["human_approval"] = None
            candidate_data["result_digest"] = None

        if agent_id is not None:
            candidate_data["agent_id"] = deepcopy(agent_id)
        if result is not None:
            candidate_data["result"] = deepcopy(result)
        if verification_bundle is not None:
            candidate_data["verification_bundle"] = deepcopy(verification_bundle)
        if human_approval is not None:
            candidate_data["human_approval"] = deepcopy(human_approval)
        if error_message is not None:
            candidate_data["error_message"] = deepcopy(error_message)
        if context is not None:
            if isinstance(context, dict):
                candidate_data["context"].update(deepcopy(context))
            else:
                candidate_data["context"] = deepcopy(context)
        if status is not None:
            candidate_data["status"] = deepcopy(status)

        candidate = Task.model_validate(candidate_data)
        if entering_draft and candidate.agent_id is None:
            raise PolicyViolation("DRAFT requires a frozen executor identity")
        if (
            task.result_digest is not None
            and not entering_rework
            and (candidate.result != task.result or candidate.context != task.context)
        ):
            raise PolicyViolation("sealed result and context are immutable until REWORK")

        if entering_draft and task.result_digest is None:
            candidate_data = candidate.model_dump()
            candidate_data["result_revision"] = task.result_revision + 1
            candidate_data["result_digest"] = canonical_json_digest(
                {"context": candidate.context, "result": candidate.result}
            )
            candidate = Task.model_validate(candidate_data)

        if (
            agent_id is not None
            and candidate.agent_id != task.agent_id
            and task.status in EXECUTOR_LOCKED_STATUSES
        ):
            raise PolicyViolation("executor is locked after DRAFT")

        if (
            candidate.status is TaskStatus.ANSWERED
            and (
                not isinstance(candidate.result, dict)
                or candidate.result.get("result_kind") != "answer"
            )
        ):
            raise PolicyViolation("ANSWERED requires a sealed answer result")

        bundle = candidate.verification_bundle
        if bundle is not None:
            if bundle.task_id != task.id or bundle.tenant_id != task.tenant_id:
                raise PolicyViolation("VerificationBundle task/tenant binding mismatch")
            if bundle.contract_digest != task.contract_digest:
                raise PolicyViolation("VerificationBundle contract binding mismatch")
            if (
                bundle.result_revision != candidate.result_revision
                or bundle.result_digest != candidate.result_digest
            ):
                raise PolicyViolation("VerificationBundle result revision binding mismatch")
            if (
                candidate.agent_id is None
                or bundle.executor_identity.casefold()
                != candidate.agent_id.casefold()
            ):
                raise PolicyViolation("VerificationBundle executor does not match the task")

        if (
            verification_bundle is not None
            and task.status in BUNDLE_LOCKED_STATUSES
            and candidate.verification_bundle != task.verification_bundle
        ):
            raise PolicyViolation("VerificationBundle is audit-locked after L3")
        if (
            candidate.status in {TaskStatus.COMPLETED, TaskStatus.ANSWERED}
            and task.verification_bundle is None
        ):
            raise PolicyViolation("VerificationBundle must be stored before completion")

        previous_bundle = task.verification_bundle
        completed_levels = {
            TaskStatus.L1_VALIDATED: 1,
            TaskStatus.L2_VERIFIED: 2,
            TaskStatus.L3_APPROVED: 3,
            TaskStatus.WAITING_HUMAN: 3,
            TaskStatus.HUMAN_APPROVED: 3,
            TaskStatus.EXECUTING: 3,
        }.get(task.status, 0)
        if verification_bundle is not None and previous_bundle is not None:
            previous_levels = (previous_bundle.l1, previous_bundle.l2, previous_bundle.l3)
            candidate_levels = (bundle.l1, bundle.l2, bundle.l3) if bundle else ()
            if (
                previous_bundle.tenant_id != bundle.tenant_id
                or previous_bundle.task_id != bundle.task_id
                or previous_bundle.contract_digest != bundle.contract_digest
                or previous_bundle.result_revision != bundle.result_revision
                or previous_bundle.result_digest != bundle.result_digest
                or previous_bundle.executor_identity.casefold()
                != bundle.executor_identity.casefold()
                or previous_levels[:completed_levels]
                != candidate_levels[:completed_levels]
            ):
                raise PolicyViolation(
                    "VerificationBundle may only add the next verification level"
                )

        if verification_bundle is not None and status is None:
            next_stage = {
                TaskStatus.DRAFT: TaskStatus.L1_VALIDATED,
                TaskStatus.L1_VALIDATED: TaskStatus.L2_VERIFIED,
                TaskStatus.L2_VERIFIED: TaskStatus.L3_APPROVED,
            }.get(task.status)
            if next_stage is None:
                raise PolicyViolation(
                    "VerificationBundle can only be stored during verification"
                )
            validate_verification_stage(
                bundle,
                task_id=task.id,
                tenant_id=task.tenant_id,
                contract_digest=task.contract_digest,
                result_revision=candidate.result_revision,
                result_digest=candidate.result_digest,
                executor_identity=candidate.agent_id,
                target=next_stage,
                verifier_registry=self._verifier_registry,
            )
        elif (
            verification_bundle is not None
            and candidate.status not in VERIFICATION_STAGE_LEVELS
            and candidate.status != TaskStatus.REJECTED
        ):
            raise PolicyViolation(
                "VerificationBundle can only be stored during verification"
            )

        approval = candidate.human_approval
        if approval is not None and (
            approval.task_id != task.id
            or approval.tenant_id != task.tenant_id
            or approval.contract_digest != task.contract_digest
            or approval.result_revision != candidate.result_revision
            or approval.result_digest != candidate.result_digest
        ):
            raise PolicyViolation("L4 record result binding mismatch")
        if human_approval is not None:
            if task.status == TaskStatus.HUMAN_APPROVED:
                raise PolicyViolation("L4 record is audit-locked after approval")
            if not (
                task.status == TaskStatus.WAITING_HUMAN
                and candidate.status == TaskStatus.HUMAN_APPROVED
                and task.human_approval is None
            ):
                raise PolicyViolation(
                    "L4 record may only be supplied during human approval"
                )

        if status is not None:
            ensure_transition(
                task.status,
                candidate.status,
                task_id=task.id,
                tenant_id=task.tenant_id,
                contract_digest=task.contract_digest,
                result_revision=candidate.result_revision,
                result_digest=candidate.result_digest,
                risk=task.risk,
                bundle=bundle,
                executor_identity=candidate.agent_id,
                verifier_registry=self._verifier_registry,
                human_approval=approval,
                approval_window_start=task.updated_at,
                approval_window_end=candidate.updated_at,
            )

        if before_commit is not None:
            before_commit(candidate.model_copy(deep=True))
        self._tasks[task.id] = candidate
        return candidate.model_copy(deep=True)

    async def get(self, task_id: UUID) -> Task | None:
        """Retrieve a deep copy of a task by id."""
        task = self._tasks.get(task_id)
        return task.model_copy(deep=True) if task is not None else None
