"""Task and request models for the Nobus Orchestrator."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Finite set of task statuses managed by the orchestrator."""

    PENDING = "pending"
    PARSING = "parsing"
    ROUTING = "routing"
    IN_PROGRESS = "in_progress"
    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
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

    id: int
    source: TaskSource
    external_chat_id: str | None = None
    intent: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    agent_id: str | None = None
    result: dict[str, Any] | None = None
    error_message: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def model_post_init(self, __context: Any) -> None:
        """Ensure updated_at is set when the model is created."""
        if self.updated_at is None:
            self.updated_at = self.created_at
