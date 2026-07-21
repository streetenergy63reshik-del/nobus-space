"""Fully local fake-only Telegram-to-Core vertical slice."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict

from src.contracts import (
    RiskLevel,
    TaskContract,
    VerificationBundle,
    VerificationBundleStatus,
    VerificationLevel,
    VerificationLevelStatus,
)
from src.core.policy import (
    DuplicateIdempotencyKeyError,
    InMemoryPolicyStore,
    canonical_json_digest,
)
from src.models.task import Task, TaskStatus
from src.orchestrator.state_manager import StateManager
from src.transport.telegram import (
    CallbackQuery,
    IngressStatus,
    TelegramGateway,
    TextMessage,
    VoiceMessage,
)
from src.workers import CodexCliAdapter


@dataclass(frozen=True)
class VerificationInput:
    """Ephemeral immutable result view passed only to verifier boundaries."""

    tenant_id: str
    task_id: UUID
    contract_digest: str
    result_revision: int
    result_digest: str
    output_digest: str
    worker_message: str


class VerifierBoundary(Protocol):
    """Injected verifier; Core still validates identity, evidence and order."""

    async def __call__(self, candidate: VerificationInput) -> VerificationLevel: ...


class FakeVerticalStatus(str, Enum):
    """Safe outcomes exposed by the local demonstration boundary."""

    COMPLETED = "completed"
    DUPLICATE = "duplicate"
    FAILED = "failed"
    NEEDS_VOICE_PREVIEW = "needs_voice_preview"
    REJECTED = "rejected"
    UNSUPPORTED = "unsupported"


class FakeVerticalResponse(BaseModel):
    """Immutable response that never includes worker or exception text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: FakeVerticalStatus
    task_id: UUID | None = None
    result_digest: str | None = None
    message: str


class FakeVertical:
    """Compose existing fake boundaries without network or live processes."""

    _EXECUTOR_IDENTITY = "worker:codex-cli-fake"
    _PERMISSIONS = ("repo.read", "process.run_allowlisted")
    _CRITERIA = ("Return one bounded local result.",)

    def __init__(
        self,
        *,
        gateway: TelegramGateway,
        policy_store: InMemoryPolicyStore,
        state_manager: StateManager,
        worker: CodexCliAdapter,
        verifiers: tuple[VerifierBoundary, VerifierBoundary, VerifierBoundary],
        allowed_path: str | Path,
    ) -> None:
        if len(verifiers) != 3:
            raise ValueError("exactly three verifier boundaries are required")
        self._gateway = gateway
        self._policy_store = policy_store
        self._state = state_manager
        self._worker = worker
        self._verifiers = verifiers
        self._allowed_path = str(allowed_path)

    async def handle(self, update: dict[str, Any]) -> FakeVerticalResponse:
        """Process one raw update through the local text-only vertical."""
        ingress = self._gateway.process_update(update)
        if ingress.status != IngressStatus.ACCEPTED:
            if ingress.reason == "duplicate update_id":
                return self._response(
                    FakeVerticalStatus.DUPLICATE, "Update was already processed."
                )
            return self._response(FakeVerticalStatus.REJECTED, "Update was rejected.")
        if isinstance(ingress.payload, VoiceMessage):
            return self._response(
                FakeVerticalStatus.NEEDS_VOICE_PREVIEW,
                "Voice preview is required before execution.",
            )
        if isinstance(ingress.payload, CallbackQuery):
            return self._response(
                FakeVerticalStatus.UNSUPPORTED,
                "Callback execution is unavailable in the local preview.",
            )
        if not isinstance(ingress.payload, TextMessage):
            return self._response(FakeVerticalStatus.UNSUPPORTED, "Update is unsupported.")

        try:
            contract = self._contract(ingress.payload)
            self._policy_store.register_contract(contract)
        except DuplicateIdempotencyKeyError:
            return self._response(
                FakeVerticalStatus.DUPLICATE, "Update was already processed."
            )
        except Exception:
            return self._response(FakeVerticalStatus.FAILED, "Task could not be created.")

        task: Task | None = None
        try:
            task = await self._state.create_from_contract(contract)
            task = await self._required_update(task.id, status=TaskStatus.PARSING)
            worker_result = await self._worker.execute(contract)
            task = await self._required_update(
                task.id,
                status=TaskStatus.DRAFT,
                agent_id=self._EXECUTOR_IDENTITY,
                result={
                    "output_digest": canonical_json_digest(
                        {"message": worker_result.message}
                    ),
                    "summary": "Worker completed.",
                },
            )
            assert task.result is not None and task.result_digest is not None
            candidate = VerificationInput(
                tenant_id=task.tenant_id,
                task_id=task.id,
                contract_digest=task.contract_digest,
                result_revision=task.result_revision,
                result_digest=task.result_digest,
                output_digest=task.result["output_digest"],
                worker_message=worker_result.message,
            )
            task = await self._verify(task, candidate)
            if task.status != TaskStatus.L3_APPROVED:
                return self._response(
                    FakeVerticalStatus.FAILED,
                    "Task verification failed.",
                    task_id=task.id,
                )
            task = await self._required_update(task.id, status=TaskStatus.COMPLETED)
            return self._response(
                FakeVerticalStatus.COMPLETED,
                "Task completed.",
                task_id=task.id,
                result_digest=task.result_digest,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            if task is not None:
                await self._escalate(task)
            return self._response(
                FakeVerticalStatus.FAILED,
                "Task execution failed.",
                task_id=task.id if task is not None else contract.task_id,
            )

    def _contract(self, message: TextMessage) -> TaskContract:
        return TaskContract(
            task_id=uuid4(),
            idempotency_key=f"telegram:update:{message.update_id}",
            tenant_id=message.tenant_id,
            source="telegram",
            instruction=message.text,
            allowed_paths=(self._allowed_path,),
            permissions=self._PERMISSIONS,
            risk=RiskLevel.LOW,
            acceptance_criteria=self._CRITERIA,
            timeout_seconds=60,
            quality_profile="local-fake@1",
        )

    async def _verify(self, task: Task, candidate: VerificationInput) -> Task:
        levels: list[VerificationLevel | None] = [None, None, None]
        targets = (
            TaskStatus.L1_VALIDATED,
            TaskStatus.L2_VERIFIED,
            TaskStatus.L3_APPROVED,
        )
        for index, (verifier, target) in enumerate(zip(self._verifiers, targets)):
            level = VerificationLevel.model_validate(
                (await verifier(candidate)).model_dump()
            )
            levels[index] = level
            passed = level.status == VerificationLevelStatus.PASSED
            bundle = VerificationBundle(
                tenant_id=task.tenant_id,
                task_id=task.id,
                contract_digest=task.contract_digest,
                result_revision=task.result_revision,
                result_digest=task.result_digest,
                executor_identity=task.agent_id,
                l1=levels[0],
                l2=levels[1],
                l3=levels[2],
                status=(
                    VerificationBundleStatus.APPROVED
                    if passed and index == 2
                    else VerificationBundleStatus.DRAFT
                    if passed
                    else VerificationBundleStatus.REJECTED
                ),
            )
            task = await self._required_update(
                task.id,
                status=target if passed else TaskStatus.REJECTED,
                verification_bundle=bundle,
                error_message=None if passed else f"l{index + 1}_failed",
            )
            if not passed:
                break
        return task

    async def _required_update(self, task_id: UUID, **values: Any) -> Task:
        task = await self._state.update(task_id, **values)
        if task is None:
            raise RuntimeError("task disappeared")
        return task

    async def _escalate(self, task: Task) -> None:
        if task.status in {
            TaskStatus.DRAFT,
            TaskStatus.L1_VALIDATED,
            TaskStatus.L2_VERIFIED,
        }:
            try:
                await self._state.update(
                    task.id,
                    status=TaskStatus.ESCALATE,
                    error_message="execution_failed",
                )
            except Exception:
                pass
        elif task.status == TaskStatus.PARSING:
            try:
                await self._state.update(
                    task.id,
                    status=TaskStatus.FAILED,
                    error_message="worker_failed",
                )
            except Exception:
                pass

    @staticmethod
    def _response(
        status: FakeVerticalStatus,
        message: str,
        *,
        task_id: UUID | None = None,
        result_digest: str | None = None,
    ) -> FakeVerticalResponse:
        return FakeVerticalResponse(
            status=status,
            task_id=task_id,
            result_digest=result_digest,
            message=message,
        )
