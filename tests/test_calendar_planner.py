from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.application.gate5a4 import Gate5A4Runtime
from src.integrations import CalendarActionKind
from src.workers.codex_cli import CodexCliResult
from src.workers import CodexCliError
from tests.test_contracts import make_envelope


class _Worker:
    def __init__(self, message: str) -> None:
        self.message = message
        self.contract = None

    async def execute(self, contract: object) -> CodexCliResult:
        self.contract = contract
        return CodexCliResult(message=self.message)


@pytest.mark.asyncio
async def test_calendar_planner_uses_closed_read_only_contract(tmp_path) -> None:
    action = json.dumps(
        {
            "kind": "create",
            "title": "Планёрка",
            "target": None,
            "start": "2026-07-27T10:00:00+03:00",
            "end": "2026-07-27T11:00:00+03:00",
            "description": None,
        },
        ensure_ascii=False,
    )
    worker = _Worker(json.dumps({"answer": action}, ensure_ascii=False))
    runtime = object.__new__(Gate5A4Runtime)
    runtime._worker = worker
    runtime._allowed_path = str(tmp_path)
    runtime._pipeline = SimpleNamespace(root=tmp_path)

    result = await runtime.plan_calendar_action(
        "Запиши планёрку в календарь", make_envelope()
    )

    assert result.kind is CalendarActionKind.CREATE
    assert result.title == "Планёрка"
    assert worker.contract is not None
    assert worker.contract.permissions == (
        "repo.read",
        "process.run_allowlisted",
    )
    assert worker.contract.risk.value == "low"
    assert worker.contract.timeout_seconds == 120
    assert "Do not use tools" in worker.contract.instruction


@pytest.mark.asyncio
async def test_calendar_planner_rejects_non_protocol_result(tmp_path) -> None:
    runtime = object.__new__(Gate5A4Runtime)
    runtime._worker = _Worker('{"answer":"not-json"}')
    runtime._allowed_path = str(tmp_path)
    runtime._pipeline = SimpleNamespace(root=tmp_path)

    with pytest.raises(CodexCliError) as caught:
        await runtime.plan_calendar_action(
            "Календарь на сегодня", make_envelope()
        )

    assert caught.value.code == "worker_protocol_error"
