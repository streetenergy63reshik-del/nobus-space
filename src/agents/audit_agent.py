"""Rule-based audit agent for marketplace data collection."""

from __future__ import annotations

from typing import Any

from src.agents.base import AgentResult, BaseAgent


class AuditAgent(BaseAgent):
    """Variant C: rule-based audit agent without LLM calls.

    The agent accepts a payload describing the audit target and returns
    a structured result. Real marketplace API calls will be added in the
    next iteration.
    """

    name = "audit"
    version = "0.1.0"

    async def run(self, payload: dict[str, Any]) -> AgentResult:
        marketplace = payload.get("marketplace", "unknown")

        # Human-in-the-loop: ask for marketplace if missing.
        if marketplace in {"unknown", "", None}:
            return AgentResult(
                success=False,
                data={},
                message="Need clarification.",
                requires_input=True,
                question="Какой маркетплейс аудировать? Ответь: ozon или wb.",
            )

        # Placeholder logic: simulate an audit result.
        # In the next iteration this will call OzonClient / WBClient.
        return AgentResult(
            success=True,
            data={
                "marketplace": marketplace,
                "checked_items": 0,
                "issues_found": 0,
                "sample_metric": 0.0,
            },
            message=f"Audit placeholder completed for {marketplace}.",
        )
