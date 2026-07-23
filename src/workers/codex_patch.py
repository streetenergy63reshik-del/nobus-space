"""Validated read-only Codex patch drafts for an isolated Git worktree."""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


_DIFF_HEADER_RE = re.compile(
    r"^diff --git a/([A-Za-z0-9._/-]{1,512}) b/([A-Za-z0-9._/-]{1,512})$"
)
_FILE_HEADER_RE = re.compile(r"^(---|\+\+\+) (?:[ab]/([A-Za-z0-9._/-]{1,512})|/dev/null)$")
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

    @field_validator("paths", mode="before")
    @classmethod
    def _json_array_to_tuple(cls, value: object) -> object:
        if not isinstance(value, list):
            raise ValueError
        return tuple(value)


def parse_codex_patch(message: str, workspace_root: str | Path) -> CodexPatchDraft:
    """Parse exact JSON and reject patches outside the selected worktree."""
    try:
        value = json.loads(message, object_pairs_hook=_unique_object)
        draft = CodexPatchDraft.model_validate(value)
        workspace = Path(workspace_root).resolve(strict=True)
        if not workspace.is_dir() or "\x00" in draft.summary:
            raise ValueError
        paths = _patch_paths(draft.patch, workspace)
        if paths != draft.paths:
            raise ValueError
    except (OSError, RuntimeError, TypeError, ValueError):
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
