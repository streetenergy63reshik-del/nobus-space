"""Task and request models for the Nobus Orchestrator."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from src.contracts import HumanApprovalRecord, RiskLevel, VerificationBundle


class TaskStatus(str, Enum):
    """Finite set of task statuses managed by the orchestrator."""

    PENDING = "pending"
    PARSING = "parsing"
    ROUTING = "routing"
    IN_PROGRESS = "in_progress"
    WAITING_INPUT = "waiting_input"
    DRAFT = "draft"
    L1_VALIDATED = "l1_validated"
    L2_VERIFIED = "l2_verified"
    L3_APPROVED = "l3_approved"
    WAITING_HUMAN = "waiting_human"
    HUMAN_APPROVED = "human_approved"
    EXECUTING = "executing"
    REJECTED = "rejected"
    REWORK = "rework"
    DEFERRED = "deferred"
    ESCALATE = "escalate"
    COMPLETED = "completed"
    ANSWERED = "answered"
    FAILED = "failed"


class TaskSource(str, Enum):
    """Possible sources of incoming tasks."""

    TELEGRAM = "telegram"
    API = "api"
    SCHEDULER = "scheduler"


class UserRequest(BaseModel):
    """Incoming user request before it becomes a Task."""

    source: TaskSource
    raw_text: str
    external_chat_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Task(BaseModel):
    """Unit of work handled by the orchestrator."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    tenant_id: str
    contract_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source: TaskSource
    external_chat_id: str | None = None
    intent: str
    payload: dict[str, Any] = Field(default_factory=dict)
    risk: RiskLevel = RiskLevel.LOW
    status: TaskStatus = TaskStatus.PENDING
    agent_id: str | None = None
    result: dict[str, Any] | None = None
    result_revision: StrictInt = Field(default=0, ge=0)
    result_digest: str | None = None
    verification_bundle: VerificationBundle | None = None
    verification_history: tuple[VerificationBundle, ...] = ()
    human_approval: HumanApprovalRecord | None = None
    approval_history: tuple[HumanApprovalRecord, ...] = ()
    error_message: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("agent_id", mode="before")
    @classmethod
    def normalize_agent_id(cls, value: object) -> str | None:
        """Normalize an assigned executor and reject invalid identities."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("agent_id must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError("agent_id must not be empty")
        return normalized

    @field_validator("tenant_id", "contract_digest")
    @classmethod
    def normalize_required_core_text(cls, value: str, info: Any) -> str:
        """Normalize immutable Core bindings."""
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must not be empty")
        return normalized
