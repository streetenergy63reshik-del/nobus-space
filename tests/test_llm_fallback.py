"""Tests for the optional LLM fallback in the intent parser."""

from __future__ import annotations

import pytest

from src.models.task import UserRequest
from src.orchestrator.intent_parser import IntentParser


@pytest.mark.asyncio
async def test_llm_fallback_disabled_by_default() -> None:
    """When LLM fallback is disabled, unknown text stays unknown."""
    parser = IntentParser(llm_enabled=False)
    request = UserRequest(source="telegram", raw_text="something weird")

    parsed = await parser.parse(request)

    assert parsed.intent == "unknown"
    assert parsed.confidence == 0.0


@pytest.mark.asyncio
async def test_llm_fallback_recognizes_audit() -> None:
    """When LLM fallback is enabled, heuristic recognises audit intent."""
    parser = IntentParser(llm_enabled=True)
    request = UserRequest(source="telegram", raw_text="please audit my store")

    parsed = await parser.parse(request)

    assert parsed.intent == "audit"
    assert parsed.confidence > 0.0


@pytest.mark.asyncio
async def test_rules_take_precedence_over_llm() -> None:
    """Rule-based parsing should always win over LLM fallback."""
    parser = IntentParser(llm_enabled=True)
    request = UserRequest(source="telegram", raw_text="/audit ozon")

    parsed = await parser.parse(request)

    assert parsed.intent == "audit"
    assert parsed.confidence == 1.0
    assert parsed.payload["marketplace"] == "ozon"
