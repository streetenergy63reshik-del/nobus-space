"""Channel-neutral product projection of internal task states."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

from src.models.task import TaskStatus


class ProductTaskStatus(str, Enum):
    QUEUED = "queued"
    WORKING = "working"
    WAITING = "waiting"
    READY = "ready"
    ATTENTION = "attention"
    FAILED = "failed"


class ProductTaskState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ProductTaskStatus
    label: str
    terminal: bool


_STATE = {
    ProductTaskStatus.QUEUED: ProductTaskState(
        status=ProductTaskStatus.QUEUED,
        label="В очереди",
        terminal=False,
    ),
    ProductTaskStatus.WORKING: ProductTaskState(
        status=ProductTaskStatus.WORKING,
        label="В работе",
        terminal=False,
    ),
    ProductTaskStatus.WAITING: ProductTaskState(
        status=ProductTaskStatus.WAITING,
        label="Ожидает действия",
        terminal=False,
    ),
    ProductTaskStatus.READY: ProductTaskState(
        status=ProductTaskStatus.READY,
        label="Готово",
        terminal=True,
    ),
    ProductTaskStatus.ATTENTION: ProductTaskState(
        status=ProductTaskStatus.ATTENTION,
        label="Требует внимания",
        terminal=True,
    ),
    ProductTaskStatus.FAILED: ProductTaskState(
        status=ProductTaskStatus.FAILED,
        label="Не выполнено",
        terminal=True,
    ),
}

_TASK_STATUS = {
    TaskStatus.PENDING: ProductTaskStatus.QUEUED,
    TaskStatus.PARSING: ProductTaskStatus.QUEUED,
    TaskStatus.ROUTING: ProductTaskStatus.QUEUED,
    TaskStatus.IN_PROGRESS: ProductTaskStatus.WORKING,
    TaskStatus.DRAFT: ProductTaskStatus.WORKING,
    TaskStatus.L1_VALIDATED: ProductTaskStatus.WORKING,
    TaskStatus.L2_VERIFIED: ProductTaskStatus.WORKING,
    TaskStatus.L3_APPROVED: ProductTaskStatus.WORKING,
    TaskStatus.HUMAN_APPROVED: ProductTaskStatus.WORKING,
    TaskStatus.EXECUTING: ProductTaskStatus.WORKING,
    TaskStatus.REWORK: ProductTaskStatus.WORKING,
    TaskStatus.WAITING_INPUT: ProductTaskStatus.WAITING,
    TaskStatus.WAITING_HUMAN: ProductTaskStatus.WAITING,
    TaskStatus.DEFERRED: ProductTaskStatus.WAITING,
    TaskStatus.COMPLETED: ProductTaskStatus.READY,
    TaskStatus.ANSWERED: ProductTaskStatus.READY,
    TaskStatus.ESCALATE: ProductTaskStatus.ATTENTION,
    TaskStatus.REJECTED: ProductTaskStatus.FAILED,
    TaskStatus.FAILED: ProductTaskStatus.FAILED,
}

if set(_TASK_STATUS) != set(TaskStatus):  # pragma: no cover - import-time guard
    raise RuntimeError("product task status mapping is incomplete")


def product_task_state(status: TaskStatus) -> ProductTaskState:
    """Return one safe product state for an exact internal enum value."""
    if not isinstance(status, TaskStatus):
        raise ValueError("product task status is invalid")
    return _STATE[_TASK_STATUS[status]]
