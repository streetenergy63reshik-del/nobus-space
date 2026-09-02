"""Validated read-only Codex patch drafts for an isolated Git worktree."""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator


_DIFF_HEADER_RE = re.compile(
    r"^diff --git a/([A-Za-z0-9._/-]{1,512}) b/([A-Za-z0-9._/-]{1,512})$"
)
_FILE_HEADER_RE = re.compile(r"^(---|\+\+\+) (?:[ab]/([A-Za-z0-9._/-]{1,512})|/dev/null)$")
_SECRET_VALUE_RE = re.compile(
    r"(?:\b[1-9][0-9]{4,15}:[A-Za-z0-9_-]{20,128}\b|"
    r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b|"
    r"\b(?:AKIA|ASIA|AIDA|AROA|AIPA|ANPA|ANVA)[A-Z0-9]{16}\b|"
    r"\bAIza[A-Za-z0-9_-]{30,}\b|"
    r"\bgh[pousr]_[A-Za-z0-9]{20,}\b|"
    r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b|"
    r"\bsk_live_[A-Za-z0-9]{16,}\b|"
    r"\b(?:api[_-]?key|token|password|secret)\s*[:=]\s*\S+|"
    r"\b[A-Za-z0-9_-]{40,}\b)",
    re.IGNORECASE,
)
_MIXED_SECRET_RE = re.compile(
    r"\b(?=[A-Za-z0-9_-]{24,39}\b)(?=[A-Za-z0-9_-]*[a-z])"
    r"(?=[A-Za-z0-9_-]*[A-Z])(?=[A-Za-z0-9_-]*[0-9])[A-Za-z0-9_-]+\b"
)
_LOCAL_PATH_RE = re.compile(
    r"(?:\b[A-Za-z]:[\\/]|\\\\[^\\\s]+[\\/]|"
    r"(?:^|\s)/(?:home|users|root|etc|var|tmp|opt)/|/\.ssh/)",
    re.IGNORECASE,
)
_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_NOTIFICATION_GAP = r"[\s\u200b\u200c\u200d\u2060\ufeff]*"
_NOTIFICATION_DASH = r"[-\u2010\u2011\u2012\u2013\u2014\u2015]"
_DESKTOP_NOTIFICATION_MARKER_RE = re.compile(
    rf"(?:<!--{_NOTIFICATION_GAP})?"
    rf"nobus{_NOTIFICATION_GAP}{_NOTIFICATION_DASH}{_NOTIFICATION_GAP}"
    rf"notify{_NOTIFICATION_GAP}:{_NOTIFICATION_GAP}"
    rf"[a-z]{{1,32}}{_NOTIFICATION_GAP}\|.*?(?:-->|$)",
    re.IGNORECASE | re.DOTALL,
)
_DESKTOP_NOTIFICATION_TOKEN_RE = re.compile(
    rf"nobus{_NOTIFICATION_GAP}{_NOTIFICATION_DASH}{_NOTIFICATION_GAP}notify",
    re.IGNORECASE,
)
_FORBIDDEN_LINES = (
    "GIT binary patch",
    "Binary files ",
    "rename from ",
    "rename to ",
    "similarity index ",
    "old mode ",
    "new mode ",
    "new file mode ",
    "deleted file mode ",
)
_FORBIDDEN_NAMES = {
    ".env",
    ".git",
    ".codex",
    ".runtime",
    ".gitattributes",
    ".gitmodules",
    "conftest.py",
    "sitecustomize.py",
    "usercustomize.py",
    "pytest.ini",
    "tox.ini",
    "credentials",
    "secrets",
    "telegram-bindings.local.json",
}


class CodexPatchError(RuntimeError):
    """Stable validation failure with no raw model output."""


class CodexPatchDraft(BaseModel):
    """Bounded model-generated patch kept only in process memory."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    summary: str = Field(min_length=1, max_length=1_500)
    patch: str = Field(min_length=1, max_length=16 * 1024)
    paths: tuple[str, ...] = Field(min_length=1, max_length=20)

    @field_validator("summary")
    @classmethod
    def _safe_summary(cls, value: str) -> str:
        return _without_desktop_notification(value)

    @field_validator("paths", mode="before")
    @classmethod
    def _json_array_to_tuple(cls, value: object) -> object:
        if not isinstance(value, list):
            raise ValueError
        return tuple(value)


class CodexAnswerDraft(BaseModel):
    """Bounded informational answer from the read-only worker."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    answer: str = Field(min_length=1, max_length=3_400)

    @field_validator("answer")
    @classmethod
    def _safe_answer(cls, value: str) -> str:
        normalized = _without_desktop_notification(value)
        if (
            not normalized
            or "\x00" in normalized
            or _SECRET_VALUE_RE.search(normalized) is not None
            or _MIXED_SECRET_RE.search(normalized) is not None
            or _LOCAL_PATH_RE.search(normalized) is not None
            or _UUID_RE.search(normalized) is not None
        ):
            raise ValueError
        if any(
            ord(character) < 32 and character not in "\n\t"
            for character in normalized
        ):
            raise ValueError
        return normalized


def _without_desktop_notification(value: str) -> str:
    normalized = _DESKTOP_NOTIFICATION_MARKER_RE.sub("", value).strip()
    if (
        not normalized
        or _DESKTOP_NOTIFICATION_TOKEN_RE.search(normalized) is not None
    ):
        raise ValueError
    return normalized


CodexDraft: TypeAlias = CodexPatchDraft | CodexAnswerDraft


def parse_codex_draft(message: str, workspace_root: str | Path) -> CodexDraft:
    """Parse one exact answer or patch object from the read-only worker."""
    try:
        value = json.loads(message, object_pairs_hook=_unique_object)
        if not isinstance(value, dict):
            raise ValueError
        if set(value) == {"answer"}:
            return CodexAnswerDraft.model_validate(value)
        draft = CodexPatchDraft.model_validate(value)
        workspace = Path(workspace_root).resolve(strict=True)
        if not workspace.is_dir() or "\x00" in draft.summary:
            raise ValueError
        paths = _patch_paths(draft.patch, workspace)
        if paths != draft.paths:
            raise ValueError
        return draft
    except (OSError, RuntimeError, TypeError, ValueError):
        raise CodexPatchError("codex_patch_invalid") from None


def parse_codex_patch(message: str, workspace_root: str | Path) -> CodexPatchDraft:
    """Parse exact JSON and reject patches outside the selected worktree."""
    draft = parse_codex_draft(message, workspace_root)
    if not isinstance(draft, CodexPatchDraft):
        raise CodexPatchError("codex_patch_invalid") from None
    return draft


def _patch_paths(patch: str, workspace: Path) -> tuple[str, ...]:
    if not patch.endswith("\n") or "\x00" in patch or "\r" in patch:
        raise ValueError
    paths: list[str] = []
    file_headers: list[str] = []
    for line in patch.splitlines():
        if line.startswith(_FORBIDDEN_LINES):
            if not line.endswith(" 100644"):
                raise ValueError
        if line.startswith("index ") and line.rsplit(" ", 1)[-1].isdigit():
            if not line.endswith(" 100644"):
                raise ValueError
        match = _DIFF_HEADER_RE.fullmatch(line)
        if match is not None:
            left, right = match.groups()
            if left != right or left in paths:
                raise ValueError
            _validate_path(left, workspace)
            paths.append(left)
            if len(paths) > 20:
                raise ValueError
            continue
        header = _FILE_HEADER_RE.fullmatch(line)
        if header is not None and header.group(2) is not None:
            _validate_path(header.group(2), workspace)
            file_headers.append(header.group(2))
    if not paths:
        raise ValueError
    if any(path not in paths for path in file_headers):
        raise ValueError
    return tuple(paths)


def _validate_path(raw: str, workspace: Path) -> None:
    path = PurePosixPath(raw)
    parts = path.parts
    if (
        path.is_absolute()
        or str(path) != raw
        or not parts
        or any(part in {"", ".", ".."} for part in parts)
        or any(part.casefold() in _FORBIDDEN_NAMES for part in parts)
        or any(part.casefold().endswith((".env", ".sqlite3")) for part in parts)
    ):
        raise ValueError
    unresolved = workspace.joinpath(*parts)
    if unresolved.is_symlink():
        raise ValueError
    candidate = unresolved.resolve(strict=False)
    candidate.relative_to(workspace)


def validate_codex_patch_path(raw: str, workspace_root: str | Path) -> str:
    """Apply the production patch-path policy to persisted recovery metadata."""
    try:
        workspace = Path(workspace_root).resolve(strict=True)
        if not workspace.is_dir() or not isinstance(raw, str):
            raise ValueError
        _validate_path(raw, workspace)
    except (OSError, RuntimeError, TypeError, ValueError):
        raise CodexPatchError("codex_patch_invalid") from None
    return raw

def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError
        value[key] = item
    return value
