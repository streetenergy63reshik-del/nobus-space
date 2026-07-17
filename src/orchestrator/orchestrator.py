"""Main orchestrator agent for Space Nobus."""

from __future__ import annotations

from src.agents.audit_agent import AuditAgent
from src.agents.base import AgentRegistry
from src.memory.codebase_memory import CodebaseMemory
from src.models.task import Task, TaskSource, UserRequest
from src.orchestrator.intent_parser import IntentParser
from src.orchestrator.router import TaskRouter
from src.orchestrator.state_manager import StateManager


class NobusOrchestrator:
    """Central agent that accepts requests, routes them and tracks execution."""

    def __init__(
        self,
        state_manager: StateManager | None = None,
        intent_parser: IntentParser | None = None,
        router: TaskRouter | None = None,
        registry: AgentRegistry | None = None,
        codebase_memory: CodebaseMemory | None = None,
    ) -> None:
        self.state_manager = state_manager or StateManager()
        self.intent_parser = intent_parser or IntentParser()
        self.registry = registry or AgentRegistry()
        self.router = router or TaskRouter(self.registry)
        self.codebase_memory = codebase_memory or CodebaseMemory()

        # Lazy import avoids a circular dependency between graph.py and this file.
        from src.orchestrator.graph import OrchestratorGraph

        self.graph = OrchestratorGraph(self)

        self._register_default_agents()

    def _register_default_agents(self) -> None:
        """Register the built-in agents."""
        self.registry.register(AuditAgent())

    async def submit(self, request: UserRequest) -> Task:
        """Accept a user request, create a task and start execution."""
        parsed = await self.intent_parser.parse(request)

        task = await self.state_manager.create(
            source=request.source.value,
            external_chat_id=request.external_chat_id,
            intent=parsed.intent,
            payload=parsed.payload,
        )

        # For the sandbox we execute immediately; later this can be queued.
        return await self._execute(task)

    async def _execute(self, task: Task) -> Task:
        """Run the task through the LangGraph workflow."""
        return await self.graph.run(task)

    async def get_status(self, task_id: int) -> Task | None:
        """Return the current task state."""
        return await self.state_manager.get(task_id)

    async def list_agents(self) -> list[str]:
        """Return the names of registered agents."""
        return self.registry.list_agents()
