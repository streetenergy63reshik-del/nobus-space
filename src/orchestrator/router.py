"""Task router: maps intents to registered agents."""

from __future__ import annotations

from src.agents.base import AgentRegistry, BaseAgent


class TaskRouter:
    """Routes a parsed intent to the corresponding agent."""

    INTENT_TO_AGENT: dict[str, str] = {
        "audit": "audit",
        "report": "report",
        "status": "notification",
        "help": "notification",
    }

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    def resolve(self, intent: str) -> BaseAgent | None:
        """Return the agent responsible for the given intent."""
        agent_name = self.INTENT_TO_AGENT.get(intent)
        if not agent_name:
            return None
        return self.registry.get(agent_name)

    def has_route(self, intent: str) -> bool:
        """Check whether the intent can be routed to any agent."""
        return intent in self.INTENT_TO_AGENT
