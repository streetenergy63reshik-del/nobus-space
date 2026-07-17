"""Tests for Ponytail token-efficiency rules."""

from __future__ import annotations

import pytest

from src.skills.ponytail_rules import PonytailRules


@pytest.mark.asyncio
async def test_should_not_use_llm_for_known_intents() -> None:
    """Known intents with tools should be handled without LLM."""
    assert PonytailRules.should_use_llm("audit", {"marketplace": "ozon"}) is False
    assert PonytailRules.should_use_llm("report", {}) is False
    assert PonytailRules.should_use_llm("status", {}) is False


@pytest.mark.asyncio
async def test_should_use_llm_for_unknown_intent() -> None:
    """Unknown intents need LLM fallback."""
    assert PonytailRules.should_use_llm("unknown", {"raw_text": "hello"}) is True


@pytest.mark.asyncio
async def test_has_tool_for_task() -> None:
    """Tool-based intents are recognised."""
    assert PonytailRules.has_tool_for_task("audit") is True
    assert PonytailRules.has_tool_for_task("report") is True
    assert PonytailRules.has_tool_for_task("unknown") is False


@pytest.mark.asyncio
async def test_compact_prompt_removes_duplicates() -> None:
    """ compact_prompt removes redundant whitespace and duplicate sentences."""
    prompt = "Hello world. Hello world.   This is a test.  This is a test."
    compacted = PonytailRules.compact_prompt(prompt)
    assert "Hello world" in compacted
    assert "This is a test" in compacted
    assert compacted.count("Hello world") == 1
    assert compacted.count("This is a test") == 1


@pytest.mark.asyncio
async def test_rule_based_help_response() -> None:
    """Help intent returns a deterministic response."""
    response = PonytailRules.get_rule_based_response("help", {})
    assert response is not None
    assert "/audit" in response["message"]


@pytest.mark.asyncio
async def test_rule_based_status_response() -> None:
    """Status intent returns a deterministic response."""
    response = PonytailRules.get_rule_based_response("status", {})
    assert response is not None
    assert "Space Nobus" in response["message"]


@pytest.mark.asyncio
async def test_no_rule_response_for_agent_intents() -> None:
    """Audit/report should be handled by agents, not direct rules."""
    assert PonytailRules.get_rule_based_response("audit", {}) is None
    assert PonytailRules.get_rule_based_response("report", {}) is None
