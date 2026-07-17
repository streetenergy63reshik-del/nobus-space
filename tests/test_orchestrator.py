"""Unit tests for the Nobus Orchestrator."""

from __future__ import annotations

import pytest

from src.models.task import TaskSource, TaskStatus, UserRequest
from src.orchestrator.orchestrator import NobusOrchestrator


@pytest.fixture
def orchestrator() -> NobusOrchestrator:
    """Return a fresh orchestrator instance for each test."""
    return NobusOrchestrator()


@pytest.mark.asyncio
async def test_audit_ozon_task_lifecycle(orchestrator: NobusOrchestrator) -> None:
    """Full cycle: submit /audit ozon and get a completed result."""
    request = UserRequest(
        source=TaskSource.TELEGRAM,
        raw_text="/audit ozon",
        external_chat_id="12345",
    )

    task = await orchestrator.submit(request)

    assert task.status == TaskStatus.COMPLETED
    assert task.intent == "audit"
    assert task.agent_id == "audit"
    assert task.result is not None
    assert task.result["success"] is True
    assert task.result["data"]["marketplace"] == "ozon"


@pytest.mark.asyncio
async def test_unknown_intent_fails(orchestrator: NobusOrchestrator) -> None:
    """An unrecognized command should fail with unknown intent."""
    request = UserRequest(
        source=TaskSource.TELEGRAM,
        raw_text="hello world",
    )

    task = await orchestrator.submit(request)

    assert task.status == TaskStatus.FAILED
    assert task.intent == "unknown"
    assert task.error_message == "Could not recognize intent."


@pytest.mark.asyncio
async def test_unrouted_intent_fails(orchestrator: NobusOrchestrator) -> None:
    """A recognized intent without a registered agent or rule should fail."""
    request = UserRequest(
        source=TaskSource.TELEGRAM,
        raw_text="/report",
    )

    task = await orchestrator.submit(request)

    assert task.status == TaskStatus.FAILED
    assert task.intent == "report"
    assert "No agent available" in (task.error_message or "")


@pytest.mark.asyncio
async def test_help_rule_based_response(orchestrator: NobusOrchestrator) -> None:
    """Help intent should be answered by Ponytail rules without an agent."""
    request = UserRequest(
        source=TaskSource.TELEGRAM,
        raw_text="/help",
    )

    task = await orchestrator.submit(request)

    assert task.status == TaskStatus.COMPLETED
    assert task.intent == "help"
    assert task.agent_id is None
    assert task.result is not None
    assert "/audit" in task.result["data"]["message"]


@pytest.mark.asyncio
async def test_status_rule_based_response(orchestrator: NobusOrchestrator) -> None:
    """Status intent should be answered by Ponytail rules without an agent."""
    request = UserRequest(
        source=TaskSource.TELEGRAM,
        raw_text="/status",
    )

    task = await orchestrator.submit(request)

    assert task.status == TaskStatus.COMPLETED
    assert task.intent == "status"
    assert task.agent_id is None
    assert task.result is not None
    assert "Space Nobus" in task.result["data"]["message"]


@pytest.mark.asyncio
async def test_get_status_returns_task(orchestrator: NobusOrchestrator) -> None:
    """State manager should return the task after submission."""
    request = UserRequest(
        source=TaskSource.API,
        raw_text="/audit wb",
    )

    task = await orchestrator.submit(request)
    fetched = await orchestrator.get_status(task.id)

    assert fetched is not None
    assert fetched.id == task.id
    assert fetched.status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_list_agents(orchestrator: NobusOrchestrator) -> None:
    """Default agents should be registered."""
    agents = await orchestrator.list_agents()

    assert "audit" in agents
