"""Tests for the LangGraph orchestration graph."""

from __future__ import annotations

import pytest

from src.agents.base import AgentResult, BaseAgent
from src.models.task import TaskSource, TaskStatus, UserRequest
from src.orchestrator.graph import OrchestratorGraph
from src.orchestrator.orchestrator import NobusOrchestrator


class FailingAgent(BaseAgent):
    """Worker used to prove exceptions are mapped to a public error code."""

    name = "audit"

    async def run(self, payload: dict[str, object]) -> AgentResult:
        raise RuntimeError("apiKeyData=secret-value; C:\\private\\artifact.wav")


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

    assert result.status == TaskStatus.DRAFT
    assert result.agent_id == "audit"
    assert result.verification_bundle is None
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

    assert result.status == TaskStatus.DRAFT
    assert result.agent_id == "core:rule-engine"
    assert result.result_digest is not None
    assert result.verification_bundle is None
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


@pytest.mark.asyncio
async def test_graph_redacts_worker_exception_details() -> None:
    orchestrator = NobusOrchestrator()
    orchestrator.registry.register(FailingAgent())
    task = await orchestrator.state_manager.create(
        source=TaskSource.API.value,
        external_chat_id=None,
        intent="audit",
        payload={},
    )

    result = await orchestrator.graph.run(task)

    assert result.status == TaskStatus.FAILED
    assert result.error_message == "agent_execution_failed"
    assert "secret-value" not in result.model_dump_json()
    assert "artifact.wav" not in result.model_dump_json()
