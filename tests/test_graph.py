"""Tests for the LangGraph orchestration graph."""

from __future__ import annotations

import pytest

from src.models.task import TaskSource, TaskStatus, UserRequest
from src.orchestrator.graph import OrchestratorGraph
from src.orchestrator.orchestrator import NobusOrchestrator


@pytest.fixture
def graph() -> OrchestratorGraph:
    """Return a fresh compiled graph for each test."""
    return OrchestratorGraph(NobusOrchestrator())


@pytest.mark.asyncio
async def test_graph_executes_audit_task(graph: OrchestratorGraph) -> None:
    """The graph should run AuditAgent for an audit intent."""
    request = UserRequest(
        source=TaskSource.API,
        raw_text="/audit ozon",
    )
    task = await graph.orchestrator.state_manager.create(
        source=request.source.value,
        external_chat_id=request.external_chat_id,
        intent="audit",
        payload={"marketplace": "ozon"},
    )

    result = await graph.run(task)

    assert result.status == TaskStatus.COMPLETED
    assert result.agent_id == "audit"
    assert result.result is not None
    assert result.result["data"]["marketplace"] == "ozon"


@pytest.mark.asyncio
async def test_graph_rule_based_help(graph: OrchestratorGraph) -> None:
    """Help intent should be resolved by Ponytail rules inside the graph."""
    request = UserRequest(
        source=TaskSource.TELEGRAM,
        raw_text="/help",
    )
    task = await graph.orchestrator.state_manager.create(
        source=request.source.value,
        external_chat_id=request.external_chat_id,
        intent="help",
        payload={},
    )

    result = await graph.run(task)

    assert result.status == TaskStatus.COMPLETED
    assert result.agent_id is None
    assert "/audit" in result.result["data"]["message"]


@pytest.mark.asyncio
async def test_graph_unknown_intent_fails(graph: OrchestratorGraph) -> None:
    """Unknown intent should fail at the parse node."""
    task = await graph.orchestrator.state_manager.create(
        source=TaskSource.API.value,
        external_chat_id=None,
        intent="unknown",
        payload={"raw_text": "hello"},
    )

    result = await graph.run(task)

    assert result.status == TaskStatus.FAILED
    assert "Could not recognize intent" in (result.error_message or "")


@pytest.mark.asyncio
async def test_graph_missing_agent_fails(graph: OrchestratorGraph) -> None:
    """Recognised intent without a registered agent should fail at routing."""
    task = await graph.orchestrator.state_manager.create(
        source=TaskSource.API.value,
        external_chat_id=None,
        intent="report",
        payload={},
    )

    result = await graph.run(task)

    assert result.status == TaskStatus.FAILED
    assert "No agent available" in (result.error_message or "")
