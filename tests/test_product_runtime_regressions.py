"""Regressions for production failures observed through the Telegram product."""

from __future__ import annotations

import json
from datetime import date

import pytest

from src.application.gate5a4 import _simple_google_task_list_action
from src.application.telegram_product import (
    _BUSINESS_NOTES_BIND_REQUESTS,
    _GOOGLE_TASKS_FOLLOWUP_RE,
    _is_google_tasks_followup,
)
from src.integrations import GoogleTaskActionKind
from src.workers.codex_cli import CodexCliError
from src.workers.codex_sdk import CodexSdkAdapter


def test_sdk_accepts_plain_read_only_final_response() -> None:
    result = CodexSdkAdapter._validated_result(
        "Полезный итог без внутренней оболочки.",
        allow_plain_answer=True,
    )

    assert json.loads(result.message) == {
        "answer": "Полезный итог без внутренней оболочки."
    }


def test_sdk_wraps_direct_planner_json_as_read_only_answer() -> None:
    action = (
        '{"kind":"list","title":null,"target":null,"list_name":null,'
        '"notes":null,"due":null,"due_from":"2026-07-25",'
        '"due_to":"2026-07-25"}'
    )

    result = CodexSdkAdapter._validated_result(
        action,
        allow_plain_answer=True,
    )

    assert json.loads(result.message) == {"answer": action}


def test_sdk_keeps_plain_fallback_disabled_for_write_capability() -> None:
    with pytest.raises(CodexCliError, match="invalid output"):
        CodexSdkAdapter._validated_result(
            "not a patch envelope",
            allow_plain_answer=False,
        )


def test_sdk_accepts_useful_answer_when_optional_fields_are_superfluous() -> None:
    result = CodexSdkAdapter._validated_result(
        json.dumps(
            {
                "kind": "answer",
                "answer": "Итог",
                "summary": "Повтор итога",
                "patch": None,
                "paths": None,
            }
        )
    )

    assert json.loads(result.message) == {"answer": "Итог"}


def test_sdk_accepts_minimal_answer_object_for_read_only_work() -> None:
    result = CodexSdkAdapter._validated_result(
        '{"answer":"Итог"}',
        allow_plain_answer=True,
    )

    assert json.loads(result.message) == {"answer": "Итог"}


@pytest.mark.parametrize("field", ("patch", "paths"))
def test_sdk_rejects_answer_envelope_with_write_material(field: str) -> None:
    payload = {
        "kind": "answer",
        "answer": "Итог",
        "summary": None,
        "patch": None,
        "paths": None,
    }
    payload[field] = "diff" if field == "patch" else ["file.txt"]

    with pytest.raises(CodexCliError, match="invalid output"):
        CodexSdkAdapter._validated_result(json.dumps(payload))


@pytest.mark.parametrize(
    ("instruction", "due_from", "due_to"),
    (
        (
            "Пришли сводку актуальных и невыполненных задач из Google Tasks "
            "на этой неделе в разбивке по спискам",
            date(2026, 7, 20),
            date(2026, 7, 26),
        ),
        (
            "Все не выполненные задачи со сроком сегодня",
            date(2026, 7, 25),
            date(2026, 7, 25),
        ),
    ),
)
def test_common_google_task_lists_do_not_depend_on_llm_planner(
    instruction: str, due_from: date, due_to: date
) -> None:
    action = _simple_google_task_list_action(
        instruction,
        date(2026, 7, 25),
    )

    assert action is not None
    assert action.kind is GoogleTaskActionKind.LIST
    assert action.list_name is None
    assert action.due_from == due_from
    assert action.due_to == due_to


def test_read_word_execute_does_not_turn_listing_into_mutation() -> None:
    action = _simple_google_task_list_action(
        "Какие задачи мне нужно выполнить на этой неделе?",
        date(2026, 7, 25),
    )

    assert action is not None
    assert action.kind is GoogleTaskActionKind.LIST


@pytest.mark.parametrize(
    "instruction",
    (
        "Все не выполненные задачи со сроком сегодня",
        "Какие задачи мне нужно выполнить на этой неделе?",
        "Покажи задачи на сегодня",
        "Покажи актуальные задачи",
        "А что на завтра?",
    ),
)
def test_google_task_followup_is_routed_without_repeating_google_name(
    instruction: str,
) -> None:
    assert _GOOGLE_TASKS_FOLLOWUP_RE.search(instruction)
    assert _is_google_tasks_followup(instruction)


def test_project_task_language_switches_away_from_google_context() -> None:
    assert not _is_google_tasks_followup(
        "Составь актуальные задачи проекта Nobus"
    )


def test_calendar_language_switches_away_from_google_context() -> None:
    assert not _is_google_tasks_followup(
        "Покажи задачи в календаре на сегодня"
    )


def test_private_business_notes_requests_are_explicitly_recognized() -> None:
    assert "#nobus-bind-notes" in _BUSINESS_NOTES_BIND_REQUESTS
    assert "подключи заметки бизнеса" in _BUSINESS_NOTES_BIND_REQUESTS
