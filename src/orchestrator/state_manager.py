"""In-memory state manager for the orchestrator sandbox."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.models.task import Task, TaskStatus


class StateManager:
    """Manages task state in memory.

    This implementation is intended for local development and tests.
    It will be replaced by PostgreSQL + Redis when moving to production.
    """

    def __init__(self) -> None:
        self._tasks: dict[int, Task] = {}
        self._counter = 0

    async def create(
        self,
        source: str,
        external_chat_id: str | None,
        intent: str,
        payload: dict[str, Any],
    ) -> Task:
        """Create a new task and return it."""
        self._counter += 1
        task = Task(
            id=self._counter,
            source=source,  # type: ignore[arg-type]
            external_chat_id=external_chat_id,
            intent=intent,
            payload=payload,
            status=TaskStatus.PENDING,
        )
        self._tasks[task.id] = task
        return task

    async def update(
        self,
        task_id: int,
        status: TaskStatus | None = None,
        agent_id: str | None = None,
        result: dict[str, Any] | None = None,
        error_message: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> Task | None:
        """Update task fields and refresh updated_at."""
        task = self._tasks.get(task_id)
        if not task:
            return None

        if status is not None:
            task.status = status
        if agent_id is not None:
            task.agent_id = agent_id
        if result is not None:
            task.result = result
        if error_message is not None:
            task.error_message = error_message
        if context is not None:
            task.context.update(context)

        task.updated_at = datetime.now(UTC)
        return task

    async def get(self, task_id: int) -> Task | None:
        """Retrieve a task by id."""
        return self._tasks.get(task_id)
