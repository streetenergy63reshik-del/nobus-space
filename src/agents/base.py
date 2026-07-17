"""Base agent interface and registry for the Nobus Orchestrator."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from src.skills.ponytail_rules import PonytailRules


class PonytailMixin:
    """Mixin that gives an agent token-efficient decision helpers."""

    def should_use_llm(self, intent: str, payload: dict[str, Any]) -> bool:
        """Return True only when the task cannot be solved by rules/tools."""
        return PonytailRules.should_use_llm(intent, payload)

    def has_tool_for_task(self, intent: str) -> bool:
        """Check whether a dedicated tool/agent exists for the intent."""
        return PonytailRules.has_tool_for_task(intent)

    def compact_prompt(self, prompt: str) -> str:
        """Compact a prompt before sending it to an LLM."""
        return PonytailRules.compact_prompt(prompt)


class AgentResult(BaseModel):
    """Standard result object returned by any agent."""

    success: bool
    data: dict[str, Any] = {}
    message: str = ""
    requires_input: bool = False
    question: str = ""


class BaseAgent(ABC, PonytailMixin):
    """Abstract base class for all subordinate agents."""

    name: str
    version: str = "0.1.0"

    @abstractmethod
    async def run(self, payload: dict[str, Any]) -> AgentResult:
        """Execute the agent's logic for the given payload."""
        ...

    async def health_check(self) -> dict[str, Any]:
        """Optional health check used by the orchestrator before routing."""
        return {"agent": self.name, "status": "ok"}


class AgentRegistry:
    """Keeps track of available agents and routes intents to them."""

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        """Register an agent instance by its class name attribute."""
        self._agents[agent.name] = agent

    def get(self, name: str) -> BaseAgent | None:
        """Retrieve an agent by name."""
        return self._agents.get(name)

    def list_agents(self) -> list[str]:
        """Return a list of registered agent names."""
        return list(self._agents.keys())
