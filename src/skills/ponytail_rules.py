"""Ponytail-inspired rule-set for token-efficient agent behaviour.

Ponytail promotes the "lazy senior dev" approach: prefer rules and existing
tools over generating new code or calling LLMs. This module implements the
core heuristics used by the orchestrator and agents to decide whether an LLM
is needed at all.
"""

from __future__ import annotations

import re
from typing import Any


class PonytailRules:
    """Rule-based decisions that save tokens and reduce hallucinations."""

    # Intents that have a deterministic tool/agent implementation.
    TOOL_BASED_INTENTS: set[str] = {
        "audit",
        "report",
        "status",
        "help",
    }

    # Intents that can be answered directly from rules without any agent.
    DIRECT_RESPONSE_INTENTS: set[str] = {
        "help",
        "status",
    }

    @staticmethod
    def should_use_llm(intent: str, payload: dict[str, Any]) -> bool:
        """Return False when the task can be handled by rules/tools.

        Args:
            intent: Recognised intent.
            payload: Parameters extracted from the user request.

        Returns:
            True only when the task genuinely needs an LLM.
        """
        if intent == "unknown":
            return True

        # If we have a tool/agent for this intent, do not call LLM by default.
        if intent in PonytailRules.TOOL_BASED_INTENTS:
            return False

        # If the payload asks for explanation/summary, LLM may be useful.
        if payload.get("requires_explanation"):
            return True

        return True

    @staticmethod
    def has_tool_for_task(intent: str) -> bool:
        """Check whether a dedicated tool/agent exists for the intent."""
        return intent in PonytailRules.TOOL_BASED_INTENTS

    @staticmethod
    def compact_prompt(prompt: str) -> str:
        """Remove redundant whitespace and duplicate sentences from a prompt.

        This is a lightweight, rule-based prompt compressor. Later it can be
        replaced with a learned compressor or an LLM-based summary.
        """
        # Normalize whitespace.
        compacted = re.sub(r"\s+", " ", prompt).strip()

        # Split into sentences and deduplicate while preserving order.
        seen: set[str] = set()
        unique_sentences: list[str] = []
        for sentence in re.split(r"[.!?]+", compacted):
            normalized = sentence.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique_sentences.append(sentence.strip())

        return ". ".join(unique_sentences)

    @staticmethod
    def get_rule_based_response(intent: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Return a deterministic response for simple intents.

        Returns None when the intent should be handled by an agent/tool.
        """
        if intent == "help":
            return {
                "message": (
                    "Доступные команды:\n"
                    "/audit ozon|wb — аудит магазина\n"
                    "/report — сформировать отчёт\n"
                    "/status — статус интеграций"
                ),
            }

        if intent == "status":
            return {
                "message": "Space Nobus работает. LLM: отключён (вариант C). Агенты: audit.",
            }

        return None
