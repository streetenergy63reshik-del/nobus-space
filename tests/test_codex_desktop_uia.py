"""Pure selector checks for the read-only Codex Desktop UIA assessment."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.integrations.codex_desktop_uia import (
    UiBootstrapStatus,
    UiElementSnapshot,
    assess_ui_automation,
)


INVOKE = "InvokePatternIdentifiers.Pattern"
EXPAND = "ExpandCollapsePatternIdentifiers.Pattern"


def element(
    name: str,
    *,
    patterns: frozenset[str],
    control_type: str = "ControlType.Button",
    enabled: bool = True,
    offscreen: bool = False,
    ancestor_control_types: tuple[str, ...] = (),
) -> UiElementSnapshot:
    return UiElementSnapshot(
        name=name,
        control_type=control_type,
        patterns=patterns,
        enabled=enabled,
        offscreen=offscreen,
        ancestor_control_types=ancestor_control_types,
    )


def test_exact_semantic_selectors_cover_project_create_and_open() -> None:
    assessment = assess_ui_automation(
        [
            element("nobus-orchestrator-dev", patterns=frozenset({EXPAND})),
            element(
                "Начать новый чат в папке nobus-orchestrator-dev",
                patterns=frozenset({INVOKE}),
                offscreen=True,
            ),
            element(
                "Реализовать Gate M2-DESKTOP",
                patterns=frozenset({INVOKE}),
                ancestor_control_types=("ControlType.ListItem",),
            ),
            # The open task also appears as a header button. It must not make
            # the sidebar selector ambiguous.
            element("Реализовать Gate M2-DESKTOP", patterns=frozenset({INVOKE})),
        ],
        project_name="nobus-orchestrator-dev",
        task_title="Реализовать Gate M2-DESKTOP",
    )

    assert assessment.project.status is UiBootstrapStatus.READY
    assert assessment.create_task.status is UiBootstrapStatus.READY
    assert assessment.open_task is not None
    assert assessment.open_task.status is UiBootstrapStatus.READY
    assert assessment.can_create_in_project
    assert assessment.can_open_task


def test_duplicate_task_title_is_ambiguous_and_never_selected_by_position() -> None:
    task = element(
        "Повторяющаяся задача",
        patterns=frozenset({INVOKE}),
        ancestor_control_types=("ControlType.ListItem",),
    )
    assessment = assess_ui_automation(
        [
            element("nobus-orchestrator-dev", patterns=frozenset({EXPAND})),
            element(
                "Начать новый чат в папке nobus-orchestrator-dev",
                patterns=frozenset({INVOKE}),
            ),
            task,
            task,
        ],
        project_name="nobus-orchestrator-dev",
        task_title="Повторяющаяся задача",
    )

    assert assessment.open_task is not None
    assert assessment.open_task.status is UiBootstrapStatus.AMBIGUOUS
    assert assessment.open_task.match_count == 2
    assert not assessment.can_open_task


def test_missing_invoke_pattern_blocks_ui_action() -> None:
    assessment = assess_ui_automation(
        [
            element("nobus-orchestrator-dev", patterns=frozenset({EXPAND})),
            element(
                "Начать новый чат в папке nobus-orchestrator-dev",
                patterns=frozenset(),
            ),
        ],
        project_name="nobus-orchestrator-dev",
    )

    assert assessment.create_task.status is UiBootstrapStatus.UNSUPPORTED_PATTERN
    assert not assessment.can_create_in_project


def test_unverified_version_or_locale_fails_closed() -> None:
    with pytest.raises(ValueError, match="version mismatch"):
        assess_ui_automation(
            [],
            project_name="nobus-orchestrator-dev",
            desktop_version="future-version",
        )
    with pytest.raises(ValueError, match="locale"):
        assess_ui_automation(
            [],
            project_name="nobus-orchestrator-dev",
            locale="en-US",
        )


def test_powershell_adapter_uses_semantic_uia_without_input_fallbacks() -> None:
    script = (
        Path(__file__).parents[1] / "scripts" / "codex_desktop_uia.ps1"
    ).read_text(encoding="utf-8")
    assert "AddStructureChangedEventHandler" in script
    assert "RemoveStructureChangedEventHandler" in script
    assert "InvokePattern" in script
    assert "ValuePattern" in script
    assert "ExpandCollapsePattern" in script
    for forbidden in ("SendKeys", "SetCursorPos", "mouse_event", "Clipboard"):
        assert forbidden not in script
