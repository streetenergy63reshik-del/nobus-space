from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.application.gate5a4 import Gate5A4Runtime
from src.application.telegram_product import _message_chunks
from src.integrations.google_tasks import (
    GoogleTaskAction,
    GoogleTaskActionKind,
    GoogleTasksClient,
)
from src.workers.codex_cli import CodexCliResult
from tests.test_contracts import make_envelope
from tests.test_telegram_product import _product, text_update


class _Request:
    def __init__(self, value: object) -> None:
        self._value = value

    def execute(self) -> object:
        return deepcopy(self._value)


class _TaskLists:
    def list(self, *, pageToken: str | None = None, **_: object) -> _Request:
        if pageToken is None:
            return _Request(
                {
                    "items": [{"id": "personal", "title": "Личные"}],
                    "nextPageToken": "lists-2",
                }
            )
        return _Request(
            {"items": [{"id": "space", "title": "PROстранство"}]}
        )


class _Tasks:
    def list(
        self,
        *,
        tasklist: str,
        pageToken: str | None = None,
        **_: object,
    ) -> _Request:
        if tasklist == "personal":
            if pageToken is None:
                return _Request(
                    {
                        "items": [
                            {
                                "id": "p1",
                                "title": "Получить справку",
                                "status": "needsAction",
                                "due": "2026-07-24T00:00:00.000Z",
                            },
                            {
                                "id": "old",
                                "title": "Старая задача",
                                "status": "needsAction",
                                "due": "2026-07-19T00:00:00.000Z",
                            },
                        ],
                        "nextPageToken": "personal-2",
                    }
                )
            return _Request(
                {
                    "items": [
                        {
                            "id": "done",
                            "title": "Уже выполнена",
                            "status": "completed",
                            "due": "2026-07-25T00:00:00.000Z",
                        }
                    ]
                }
            )
        return _Request(
            {
                "items": [
                    {
                        "id": "s1",
                        "title": "Вопросы по Uzum",
                        "status": "needsAction",
                        "due": "2026-07-26T00:00:00.000Z",
                    },
                    {
                        "id": "undated",
                        "title": "Без даты",
                        "status": "needsAction",
                    },
                ]
            }
        )


class _Service:
    def tasklists(self) -> _TaskLists:
        return _TaskLists()

    def tasks(self) -> _Tasks:
        return _Tasks()


class _Worker:
    def __init__(self, answer: dict[str, object]) -> None:
        self._message = json.dumps(
            {"answer": json.dumps(answer, ensure_ascii=False)},
            ensure_ascii=False,
        )
        self.contract = None

    async def execute(self, contract: object) -> CodexCliResult:
        self.contract = contract
        return CodexCliResult(message=self._message)


@pytest.mark.asyncio
async def test_list_all_tasklists_is_paged_grouped_and_period_filtered() -> None:
    client = GoogleTasksClient(
        Path("C:/unused/google-token.json"),
        service_factory=_Service,
    )
    result = await client.execute(
        GoogleTaskAction(
            kind=GoogleTaskActionKind.LIST,
            due_from=date(2026, 7, 20),
            due_to=date(2026, 7, 26),
        ),
        idempotency_key="sha256:" + "a" * 64,
    )

    assert "Личные\n• Получить справку — до 24.07.2026" in result.message
    assert "PROстранство\n• Вопросы по Uzum — до 26.07.2026" in result.message
    assert all(
        value not in result.message
        for value in ("Старая задача", "Уже выполнена", "Без даты")
    )


@pytest.mark.asyncio
async def test_google_tasks_planner_contract_supports_week_across_all_lists(
    tmp_path: Path,
) -> None:
    worker = _Worker(
        {
            "kind": "list",
            "title": None,
            "target": None,
            "list_name": None,
            "notes": None,
            "due": None,
            "due_from": None,
            "due_to": None,
        }
    )
    runtime = object.__new__(Gate5A4Runtime)
    runtime._worker = worker
    runtime._allowed_path = str(tmp_path)
    runtime._pipeline = SimpleNamespace(root=tmp_path)
    runtime._clock = lambda: datetime(
        2026, 7, 25, 12, 0, tzinfo=UTC
    )

    action = await runtime.plan_google_task_action(
        "Покажи все незавершённые задачи Google Tasks за текущую неделю "
        "по всем спискам",
        make_envelope(),
    )

    assert action.due_from == date(2026, 7, 20)
    assert action.due_to == date(2026, 7, 26)
    assert action.list_name is None
    assert worker.contract is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "instruction",
    [
        "Проведи углублённое исследование последних изменений правил Ozon "
        "и Wildberries со ссылками на источники.",
        "Проведи исследование по официальным источникам, новостным порталам "
        "и СМИ бизнес-сообщества РФ.",
    ],
)
async def test_owner_research_phrases_use_web_profile(
    tmp_path: Path, instruction: str
) -> None:
    harness = _product(tmp_path)
    await harness.control.handle(text_update(instruction, 1))
    assert harness.runtime.drafted[0].contract.instruction.startswith(
        "[profile:research.web]\n"
    )


def test_long_effect_result_is_split_within_telegram_limit() -> None:
    value = "Задачи\n" + "\n".join(
        f"• Задача {index}: " + "x" * 90 for index in range(100)
    )
    chunks = _message_chunks(value)
    assert len(chunks) > 1
    assert all(0 < len(chunk) <= 3_400 for chunk in chunks)
    assert chunks[0].startswith("Задачи")
