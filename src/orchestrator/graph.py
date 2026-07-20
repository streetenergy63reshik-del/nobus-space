"""LangGraph-based orchestration graph for Space Nobus.

The graph mirrors the existing state machine:

    parse -> route -> execute -> respond
      |        |
      v        v
   respond  respond

Conditional edges decide whether to exit early (unknown intent,
rule-based response, missing agent) or continue execution.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from src.models.task import Task, TaskStatus
from src.orchestrator.orchestrator import NobusOrchestrator
from src.skills.ponytail_rules import PonytailRules


class OrchestratorState(TypedDict):
    """LangGraph state shared across nodes."""

    task: Task
    orchestrator: NobusOrchestrator


class OrchestratorGraph:
    """Compiled LangGraph workflow for the Nobus Orchestrator."""

    def __init__(self, orchestrator: NobusOrchestrator) -> None:
        self.orchestrator = orchestrator
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        """Build and compile the state graph."""
        workflow = StateGraph(OrchestratorState)

        workflow.add_node("parse", self._parse_node)
        workflow.add_node("route", self._route_node)
        workflow.add_node("execute", self._execute_node)
        workflow.add_node("human_input", self._human_input_node)
        workflow.add_node("respond", self._respond_node)

        workflow.set_entry_point("parse")
        workflow.add_conditional_edges("parse", self._after_parse)
        workflow.add_conditional_edges("route", self._after_route)
        workflow.add_conditional_edges("execute", self._after_execute)
        workflow.add_edge("human_input", "respond")
        workflow.add_edge("respond", END)

        return workflow.compile()

    async def run(self, task: Task) -> Task:
        """Run the graph for a given task and return the updated task."""
        final_state = await self.graph.ainvoke(
            {"task": task, "orchestrator": self.orchestrator}
        )
        return final_state["task"]

    async def _parse_node(self, state: OrchestratorState) -> dict[str, Any]:
        """Parse intent and apply Ponytail early-exit rules."""
        task = state["task"]
        orchestrator = state["orchestrator"]
        state_manager = orchestrator.state_manager

        await state_manager.update(task.id, status=TaskStatus.PARSING)

        if task.intent == "unknown":
            await state_manager.update(
                task.id,
                status=TaskStatus.FAILED,
                error_message="Could not recognize intent.",
            )
            return {"task": await state_manager.get(task.id)}  # type: ignore[return-value]

        rule_response = PonytailRules.get_rule_based_response(task.intent, task.payload)
        if rule_response is not None:
            await state_manager.update(
                task.id,
                status=TaskStatus.DRAFT,
                agent_id="core:rule-engine",
                result={
                    "success": True,
                    "data": rule_response,
                    "message": rule_response.get("message", ""),
                },
            )
            return {"task": await state_manager.get(task.id)}  # type: ignore[return-value]

        return {"task": await state_manager.get(task.id)}  # type: ignore[return-value]

    async def _route_node(self, state: OrchestratorState) -> dict[str, Any]:
        """Route the task to the appropriate agent."""
        task = state["task"]
        orchestrator = state["orchestrator"]
        state_manager = orchestrator.state_manager

        await state_manager.update(task.id, status=TaskStatus.ROUTING)

        agent = orchestrator.router.resolve(task.intent)
        if agent is None:
            await state_manager.update(
                task.id,
                status=TaskStatus.FAILED,
                error_message=f"No agent available for intent '{task.intent}'.",
            )
        else:
            await state_manager.update(task.id, agent_id=agent.name)

        return {"task": await state_manager.get(task.id)}  # type: ignore[return-value]

    async def _execute_node(self, state: OrchestratorState) -> dict[str, Any]:
        """Run the selected agent."""
        task = state["task"]
        orchestrator = state["orchestrator"]
        state_manager = orchestrator.state_manager

        agent = orchestrator.router.resolve(task.intent)
        if agent is None:
            # Should not happen because routing guards it, but stay safe.
            await state_manager.update(
                task.id,
                status=TaskStatus.FAILED,
                error_message=f"No agent available for intent '{task.intent}'.",
            )
            return {"task": await state_manager.get(task.id)}  # type: ignore[return-value]

        await state_manager.update(task.id, status=TaskStatus.IN_PROGRESS)

        try:
            result = await agent.run(task.payload)
            if result.requires_input:
                await state_manager.update(
                    task.id,
                    status=TaskStatus.WAITING_INPUT,
                    result=result.model_dump(),
                    context={"pending_question": result.question},
                )
            elif result.success:
                await state_manager.update(
                    task.id,
                    status=TaskStatus.DRAFT,
                    result=result.model_dump(),
                )
            else:
                await state_manager.update(
                    task.id,
                    status=TaskStatus.FAILED,
                    result=result.model_dump(),
                    error_message=result.message or "Agent execution failed.",
                )
        except Exception:  # noqa: BLE001
            await state_manager.update(
                task.id,
                status=TaskStatus.FAILED,
                error_message="agent_execution_failed",
            )

        return {"task": await state_manager.get(task.id)}  # type: ignore[return-value]

    async def _human_input_node(self, state: OrchestratorState) -> dict[str, Any]:
        """Pause and surface the question to the user.

        The actual answer is supplied externally via resume().
        """
        task = state["task"]
        orchestrator = state["orchestrator"]
        updated = await orchestrator.state_manager.get(task.id)
        return {"task": updated or task}

    async def _respond_node(self, state: OrchestratorState) -> dict[str, Any]:
        """Final node: ensure the latest task state is returned."""
        task = state["task"]
        orchestrator = state["orchestrator"]
        updated = await orchestrator.state_manager.get(task.id)
        return {"task": updated or task}

    @staticmethod
    def _after_parse(state: OrchestratorState) -> str:
        """Decide the next step after parsing."""
        status = state["task"].status
        if status in {TaskStatus.FAILED, TaskStatus.DRAFT}:
            return "respond"
        return "route"

    @staticmethod
    def _after_route(state: OrchestratorState) -> str:
        """Decide the next step after routing."""
        status = state["task"].status
        if status == TaskStatus.FAILED:
            return "respond"
        return "execute"

    @staticmethod
    def _after_execute(state: OrchestratorState) -> str:
        """Decide the next step after execution."""
        status = state["task"].status
        if status == TaskStatus.WAITING_INPUT:
            return "human_input"
        return "respond"
