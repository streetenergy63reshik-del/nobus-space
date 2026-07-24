from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.application.gate5a4 import Gate5A4Runtime
from src.integrations import GoogleTaskActionKind
from src.workers.codex_cli import CodexCliResult
from tests.test_contracts import make_envelope


class _Worker:
    def __init__(self, message: str) -> None:
        self.message = message
        self.contract = None

    async def execute(self, contract: object) -> CodexCliResult:
        self.contract = contract
        return CodexCliResult(message=self.message)


@pytest.mark.asyncio
async def test_google_tasks_planner_uses_closed_read_only_contract(
    tmp_path,
) -> None:
    action = json.dumps(
        {
            "kind": "create",
            "title": "Подготовить отчёт",
            "target": None,
            "list_name": "Основные",
            "notes": None,
            "due": "2026-07-31",
        },
        ensure_ascii=False,
    )
    worker = _Worker(json.dumps({"answer": action}, ensure_ascii=False))
    runtime = object.__new__(Gate5A4Runtime)
    runtime._worker = worker
    runtime._allowed_path = str(tmp_path)
    runtime._pipeline = SimpleNamespace(root=tmp_path)

    result = await runtime.plan_google_task_action(
        "Добавь задачу в Google Tasks", make_envelope()
    )

    assert result.kind is GoogleTaskActionKind.CREATE
    assert result.title == "Подготовить отчёт"
    assert worker.contract is not None
    assert worker.contract.permissions == (
        "repo.read",
        "process.run_allowlisted",
    )
    assert worker.contract.risk.value == "low"
    assert worker.contract.timeout_seconds == 120
    assert "Do not use tools" in worker.contract.instruction
