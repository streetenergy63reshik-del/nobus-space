"""Semantic UI Automation selectors and executor for Desktop bootstrap only.

The module plans exact accessible-name operations.  It intentionally contains
no coordinate fallback, no implicit focus change and no generic SendKeys path.
An executing Windows backend remains behind the separately authorized live
probe; ordinary local tests operate on read-only snapshots.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable
from uuid import uuid4


TESTED_DESKTOP_VERSION = "26.917.9434.0"
TESTED_UI_LOCALE = "ru-RU"
DEFAULT_UIA_TIMEOUT_SECONDS = 45
_SAFE_FAILURE_STAGES = frozenset(
    {
        "prepare-action",
        "acquire-bootstrap-lock",
        "read-prompt",
        "find-project",
        "find-create-control",
        "invoke-create-control",
        "find-task",
        "invoke-open-control",
        "submit-prompt",
        "check-active-context",
        "find-composer",
        "check-draft-empty",
        "check-exact-draft",
        "set-composer",
        "find-send-control",
        "recheck-active-context",
        "invoke-send-control",
    }
)


class DesktopUiAutomationError(RuntimeError):
    """Fail-closed UI Automation boundary without raw Desktop contents."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class DesktopUiActionReceipt:
    action: str
    desktop_version: str
    project_name: str
    task_title: str | None
    process_id: int
    mutations: tuple[str, ...]


class UiBootstrapStatus(str, Enum):
    READY = "ready"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED_PATTERN = "unsupported_pattern"


@dataclass(frozen=True, slots=True)
class UiElementSnapshot:
    name: str
    control_type: str
    patterns: frozenset[str]
    enabled: bool
    offscreen: bool
    automation_id: str = ""
    ancestor_control_types: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UiSelector:
    purpose: str
    name: str
    control_type: str
    required_pattern: str
    required_ancestor_control_type: str | None = None


@dataclass(frozen=True, slots=True)
class UiSelectorResult:
    selector: UiSelector
    status: UiBootstrapStatus
    match_count: int


@dataclass(frozen=True, slots=True)
class UiBootstrapAssessment:
    desktop_version: str
    locale: str
    project: UiSelectorResult
    create_task: UiSelectorResult
    open_task: UiSelectorResult | None

    @property
    def can_create_in_project(self) -> bool:
        return (
            self.project.status is UiBootstrapStatus.READY
            and self.create_task.status is UiBootstrapStatus.READY
        )

    @property
    def can_open_task(self) -> bool:
        return (
            self.open_task is not None
            and self.open_task.status is UiBootstrapStatus.READY
        )


def selectors_for_project(
    project_name: str,
    *,
    task_title: str | None = None,
    locale: str = TESTED_UI_LOCALE,
) -> tuple[UiSelector, UiSelector, UiSelector | None]:
    """Build exact version/locale-bound selectors without fuzzy matching."""
    project_name = _selector_text(project_name, "project")
    if locale != TESTED_UI_LOCALE:
        raise ValueError("Codex Desktop UI locale is not supported by this profile")
    project = UiSelector(
        purpose="select-project",
        name=project_name,
        control_type="ControlType.Button",
        required_pattern="ExpandCollapsePatternIdentifiers.Pattern",
    )
    create_task = UiSelector(
        purpose="create-task",
        name=f"Начать новый чат в папке {project_name}",
        control_type="ControlType.Button",
        required_pattern="InvokePatternIdentifiers.Pattern",
    )
    open_task = None
    if task_title is not None:
        open_task = UiSelector(
            purpose="open-task",
            name=_selector_text(task_title, "task title"),
            control_type="ControlType.Button",
            required_pattern="InvokePatternIdentifiers.Pattern",
            required_ancestor_control_type="ControlType.ListItem",
        )
    return project, create_task, open_task


def assess_ui_automation(
    elements: Iterable[UiElementSnapshot],
    *,
    project_name: str,
    task_title: str | None = None,
    desktop_version: str = TESTED_DESKTOP_VERSION,
    locale: str = TESTED_UI_LOCALE,
) -> UiBootstrapAssessment:
    """Assess exact selectors from a read-only UIA snapshot."""
    if desktop_version != TESTED_DESKTOP_VERSION:
        raise ValueError("Codex Desktop UI profile version mismatch")
    project, create_task, open_task = selectors_for_project(
        project_name, task_title=task_title, locale=locale
    )
    snapshot = tuple(elements)
    return UiBootstrapAssessment(
        desktop_version=desktop_version,
        locale=locale,
        project=_assess_selector(snapshot, project),
        create_task=_assess_selector(snapshot, create_task),
        open_task=(
            None if open_task is None else _assess_selector(snapshot, open_task)
        ),
    )


class CodexDesktopUiAutomation:
    """Run the version/locale-bound semantic PowerShell UIA adapter.

    Prompt material is placed in a private runtime directory and removed after
    the bounded subprocess finishes.  The PowerShell side accepts only files
    below that exact directory and has no coordinate, clipboard or SendKeys
    fallback.
    """

    def __init__(
        self,
        *,
        script_path: Path,
        runtime_root: Path,
        powershell_path: Path | None = None,
        timeout_seconds: int = DEFAULT_UIA_TIMEOUT_SECONDS,
    ) -> None:
        script = Path(script_path).resolve()
        root = Path(runtime_root).resolve()
        shell = Path(powershell_path or _default_powershell()).resolve()
        if (
            not script.is_file()
            or not shell.is_file()
            or type(timeout_seconds) is not int
            or not 5 <= timeout_seconds <= 120
        ):
            raise ValueError("Codex Desktop UI Automation configuration is invalid")
        root.mkdir(parents=True, exist_ok=True)
        self._script = script
        self._runtime_root = root
        self._powershell = shell
        self._timeout_seconds = timeout_seconds

    async def snapshot(self) -> DesktopUiActionReceipt:
        # A bare "-" is parsed as a switch boundary by Windows PowerShell
        # when passed as the value of -ProjectName and exits before the script
        # runs.  Snapshot does not use this selector, but it still needs a
        # normal argument so the read-only health probe exercises the real
        # wrapper successfully.
        return await self._run("Snapshot", project_name="snapshot")

    async def create_and_submit(
        self, *, project_name: str, prompt: str
    ) -> DesktopUiActionReceipt:
        return await self._run(
            "CreateAndSubmit",
            project_name=_selector_text(project_name, "project"),
            prompt=_prompt_text(prompt),
        )

    async def open_and_submit(
        self, *, project_name: str, task_title: str, prompt: str
    ) -> DesktopUiActionReceipt:
        return await self._run(
            "OpenAndSubmit",
            project_name=_selector_text(project_name, "project"),
            task_title=_selector_text(task_title, "task title"),
            prompt=_prompt_text(prompt),
        )

    async def submit_exact_draft(
        self, *, project_name: str, prompt: str
    ) -> DesktopUiActionReceipt:
        """Send only a pre-existing exact draft in the verified new project view."""
        return await self._run(
            "SubmitExactDraft",
            project_name=_selector_text(project_name, "project"),
            prompt=_prompt_text(prompt),
        )

    async def _run(
        self,
        action: str,
        *,
        project_name: str,
        task_title: str | None = None,
        prompt: str | None = None,
    ) -> DesktopUiActionReceipt:
        prompt_path: Path | None = None
        cleanup_failed = False
        command = [
            str(self._powershell),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self._script),
            "-Action",
            action,
            "-ProjectName",
            project_name,
            "-ExpectedDesktopVersion",
            TESTED_DESKTOP_VERSION,
            "-AllowedPromptRoot",
            str(self._runtime_root),
        ]
        if task_title is not None:
            command.extend(("-TaskTitle", task_title))
        try:
            if prompt is not None:
                prompt_path = self._runtime_root / f"prompt-{uuid4().hex}.txt"
                descriptor = os.open(
                    prompt_path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                    0o600,
                )
                try:
                    os.write(descriptor, prompt.encode("utf-8"))
                finally:
                    os.close(descriptor)
                command.extend(("-PromptFile", str(prompt_path)))
            completed = await asyncio.to_thread(
                subprocess.run,
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                # Windows PowerShell 5.1 can emit localized errors to stderr
                # in a legacy code page. A decoder failure must not obscure
                # the subprocess exit status or interrupt lost-ACK recovery.
                errors="replace",
                timeout=self._timeout_seconds,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise DesktopUiAutomationError("desktop-uia-unavailable") from exc
        finally:
            if prompt_path is not None:
                try:
                    prompt_path.unlink(missing_ok=True)
                except OSError:
                    cleanup_failed = True
        if cleanup_failed:
            raise DesktopUiAutomationError("desktop-uia-prompt-cleanup-failed")
        if completed.returncode != 0:
            stage: str | None = None
            selector_count: int | None = None
            existing_draft = False
            try:
                diagnostic = json.loads(completed.stdout.splitlines()[-1])
                if isinstance(diagnostic, dict) and diagnostic.get("action") == action:
                    candidate = diagnostic.get("failure_stage")
                    if candidate in _SAFE_FAILURE_STAGES:
                        stage = candidate
                        existing_draft = (
                            stage == "check-draft-empty"
                            and diagnostic.get("failure_code") == "existing-draft"
                        )
                        count = diagnostic.get("selector_match_count")
                        if type(count) is int and 0 <= count <= 1000:
                            selector_count = count
            except (IndexError, TypeError, ValueError, json.JSONDecodeError):
                pass
            reason = "desktop-uia-existing-draft" if existing_draft else "desktop-uia-action-failed"
            if stage is not None and not existing_draft:
                reason += f":{stage}"
                if selector_count is not None:
                    reason += f":matches={selector_count}"
            raise DesktopUiAutomationError(reason)
        try:
            result = json.loads(completed.stdout)
            process_id = result["process_id"]
            mutations = result["mutations"]
            if (
                not isinstance(result, dict)
                or result.get("action") != action
                or result.get("desktop_version") != TESTED_DESKTOP_VERSION
                or type(process_id) is not int
                or process_id <= 0
                or not isinstance(mutations, list)
                or not all(isinstance(value, str) for value in mutations)
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DesktopUiAutomationError("desktop-uia-invalid-response") from exc
        return DesktopUiActionReceipt(
            action=action,
            desktop_version=TESTED_DESKTOP_VERSION,
            project_name=project_name,
            task_title=task_title,
            process_id=process_id,
            mutations=tuple(mutations),
        )
def _assess_selector(
    elements: tuple[UiElementSnapshot, ...], selector: UiSelector
) -> UiSelectorResult:
    matches = tuple(
        element
        for element in elements
        if element.name == selector.name
        and element.control_type == selector.control_type
        and element.enabled
        and (
            selector.required_ancestor_control_type is None
            or selector.required_ancestor_control_type
            in element.ancestor_control_types
        )
    )
    if not matches:
        status = UiBootstrapStatus.MISSING
    elif len(matches) != 1:
        status = UiBootstrapStatus.AMBIGUOUS
    elif selector.required_pattern not in matches[0].patterns:
        status = UiBootstrapStatus.UNSUPPORTED_PATTERN
    else:
        status = UiBootstrapStatus.READY
    return UiSelectorResult(
        selector=selector,
        status=status,
        match_count=len(matches),
    )


def _selector_text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Codex Desktop {label} selector is invalid")
    normalized = value.strip()
    if not normalized or len(normalized) > 256 or any(
        character in normalized for character in "\r\n\x00"
    ):
        raise ValueError(f"Codex Desktop {label} selector is invalid")
    return normalized


def _prompt_text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Codex Desktop prompt is invalid")
    normalized = value.strip()
    if not normalized or len(normalized) > 12_000 or "\x00" in normalized:
        raise ValueError("Codex Desktop prompt is invalid")
    return normalized


def _default_powershell() -> Path:
    system_root = Path(os.environ.get("SYSTEMROOT", r"C:\Windows"))
    return system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
