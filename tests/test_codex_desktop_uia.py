"""Pure selector checks for the read-only Codex Desktop UIA assessment."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from src.integrations.codex_desktop_uia import (
    CodexDesktopUiAutomation,
    DesktopUiAutomationError,
    TESTED_DESKTOP_VERSION,
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
    script_path = Path(__file__).parents[1] / "scripts" / "codex_desktop_uia.ps1"
    # Windows PowerShell 5.1 interprets BOM-less -File input as ANSI and
    # silently corrupts Russian accessibility labels used by exact selectors.
    assert script_path.read_bytes().startswith(b"\xef\xbb\xbf")
    script = script_path.read_text(encoding="utf-8")
    assert "AddStructureChangedEventHandler" in script
    assert "RemoveStructureChangedEventHandler" in script
    assert "if ($found.Count -ge 1)" in script
    assert "if ($appRoots.Count -eq 1)" in script
    assert "if ($appDocuments.Count -eq 1)" in script
    assert "InvokePattern" in script
    assert "ValuePattern" in script
    assert "ExpandCollapsePattern" in script
    assert "Create task is offscreen without ScrollItem" in script
    assert "scrolled-create-task" in script
    assert "Assert-ActiveTaskHeader $Root $ExpectedTaskTitle" in script
    assert "Submit-Prompt $document $prompt -ExpectedTaskTitle $TaskTitle" in script
    assert "Submit-Prompt $document $prompt -ExpectedProjectName $ProjectName" in script
    assert "$script:uiaStage = 'check-draft-empty'" in script
    assert '$placeholderValue = "`n" + $composer.Element.Current.Name' in script
    assert "$initialValue -cne $placeholderValue" in script
    assert script.count("ExpandCollapsePattern]::Pattern) -InListItem") >= 2
    assert script.count("Assert-NewTaskProjectContext $Root $ExpectedProjectName") == 4
    assert script.count("Assert-NewTaskProjectContext $document $ProjectName") == 3
    assert "$contextDeadline = [DateTime]::UtcNow.AddSeconds(5)" in script
    standard_submit = script.split("function Submit-Prompt", 1)[1].split("function Submit-ExactDraft", 1)[0]
    assert standard_submit.rfind("Assert-NewTaskProjectContext $Root $ExpectedProjectName") < standard_submit.index("$send.Pattern.Invoke()")
    assert "New task project context changed; prompt was not sent" in script
    assert "[DateTime]::UtcNow.AddSeconds(3)" in script
    exact_draft = script.split("function Submit-ExactDraft", 1)[1].split("$desktop = Get-CodexDocument", 1)[0]
    assert exact_draft.count("$composer.Pattern.Current.Value -cne $Prompt") == 2
    assert ".SetValue(" not in exact_draft
    assert "} elseif ($Action -in @('OpenAndSubmit', 'OpenExisting')) {\n            $script:uiaStage = 'find-task'" in script
    open_only = script.split("if ($Action -eq 'OpenExisting') {\n            $script:uiaStage = 'check-active-context'", 1)[1].split("} else {\n            $script:uiaStage = 'submit-prompt'", 1)[0]
    assert "Assert-ActiveTaskHeader $document $TaskTitle" in open_only
    assert "Submit-Prompt" not in open_only
    assert "if ($Action -eq 'SubmitExactDraft') {\n                Submit-ExactDraft $document $prompt -ExpectedProjectName $ProjectName" in script
    assert "$projectCount -ne 1 -or $newTaskCount -lt 1 -or $newTaskCount -gt 2" in script
    for forbidden in ("SendKeys", "SetCursorPos", "mouse_event", "Clipboard"):
        assert forbidden not in script


@pytest.mark.asyncio
async def test_snapshot_passes_a_normal_powershell_parameter_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "uia.ps1"
    shell = tmp_path / "powershell.exe"
    script.write_text("# fixture", encoding="utf-8")
    shell.write_bytes(b"fixture")
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["errors"] = kwargs.get("errors")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "action": "Snapshot",
                    "desktop_version": TESTED_DESKTOP_VERSION,
                    "process_id": 123,
                    "mutations": [],
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    automation = CodexDesktopUiAutomation(
        script_path=script,
        runtime_root=tmp_path / "runtime",
        powershell_path=shell,
    )

    receipt = await automation.snapshot()

    command = captured["command"]
    project_index = command.index("-ProjectName")
    assert command[project_index + 1] == "snapshot"
    assert command[command.index("-ExpectedDesktopVersion") + 1] == TESTED_DESKTOP_VERSION
    assert captured["errors"] == "replace"
    assert receipt.mutations == ()


@pytest.mark.asyncio
async def test_open_existing_never_creates_prompt_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "uia.ps1"
    shell = tmp_path / "powershell.exe"
    script.write_text("# fixture", encoding="utf-8")
    shell.write_bytes(b"fixture")
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps({
            "action": "OpenExisting", "desktop_version": TESTED_DESKTOP_VERSION,
            "process_id": 123, "mutations": ["invoked-open-task"],
        }), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    automation = CodexDesktopUiAutomation(
        script_path=script, runtime_root=tmp_path / "runtime", powershell_path=shell,
    )
    receipt = await automation.open_existing(
        project_name="nobus-orchestrator-dev", task_title="Точная задача",
    )
    command = captured["command"]
    assert command[command.index("-Action") + 1] == "OpenExisting"
    assert command[command.index("-TaskTitle") + 1] == "Точная задача"
    assert "-PromptFile" not in command
    assert not list((tmp_path / "runtime").glob("prompt-*"))
    assert receipt.mutations == ("invoked-open-task",)


@pytest.mark.asyncio
async def test_exact_draft_recovery_uses_only_bound_action_and_cleans_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "uia.ps1"
    shell = tmp_path / "powershell.exe"
    script.write_text("# fixture", encoding="utf-8")
    shell.write_bytes(b"fixture")
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        prompt_path = Path(command[command.index("-PromptFile") + 1])
        captured["prompt_path"] = prompt_path
        captured["prompt"] = prompt_path.read_text(encoding="utf-8")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({
                "action": "SubmitExactDraft",
                "desktop_version": TESTED_DESKTOP_VERSION,
                "process_id": 123,
                "mutations": ["submitted-prompt"],
            }),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    automation = CodexDesktopUiAutomation(
        script_path=script,
        runtime_root=tmp_path / "runtime",
        powershell_path=shell,
    )
    receipt = await automation.submit_exact_draft(
        project_name="nobus-orchestrator-dev",
        prompt="exact staged test",
    )

    command = captured["command"]
    assert command[command.index("-Action") + 1] == "SubmitExactDraft"
    assert command[command.index("-ProjectName") + 1] == "nobus-orchestrator-dev"
    assert "-TaskTitle" not in command
    assert captured["prompt"] == "exact staged test"
    assert not captured["prompt_path"].exists()
    assert receipt.mutations == ("submitted-prompt",)


@pytest.mark.asyncio
async def test_failed_action_reports_only_allowlisted_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "uia.ps1"
    shell = tmp_path / "powershell.exe"
    script.write_text("# fixture", encoding="utf-8")
    shell.write_bytes(b"fixture")

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            1,
            stdout=json.dumps(
                {"action": "Snapshot", "failure_stage": "find-create-control", "selector_match_count": 2}
            ),
            stderr="redacted error with possible task contents",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    automation = CodexDesktopUiAutomation(
        script_path=script,
        runtime_root=tmp_path / "runtime",
        powershell_path=shell,
    )
    with pytest.raises(DesktopUiAutomationError) as caught:
        await automation.snapshot()
    assert str(caught.value) == "desktop-uia-action-failed:find-create-control:matches=2"


@pytest.mark.asyncio
async def test_only_exact_whitelisted_draft_error_is_identified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "uia.ps1"
    shell = tmp_path / "powershell.exe"
    script.write_text("# fixture", encoding="utf-8")
    shell.write_bytes(b"fixture")

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command, 1,
            stdout=json.dumps({
                "action": "Snapshot",
                "failure_stage": "check-draft-empty",
                "failure_code": "existing-draft",
            }),
            stderr="untrusted detail must not leak",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    automation = CodexDesktopUiAutomation(
        script_path=script, runtime_root=tmp_path / "runtime", powershell_path=shell,
    )
    with pytest.raises(DesktopUiAutomationError) as caught:
        await automation.snapshot()
    assert str(caught.value) == "desktop-uia-existing-draft"
