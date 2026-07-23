"""Reviewer regressions for unsafe Codex patch shapes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.workers.codex_patch import CodexPatchError, parse_codex_patch


def _message(path: str, body: str) -> str:
    return json.dumps(
        {"summary": "bounded", "patch": body, "paths": [path]},
        separators=(",", ":"),
    )


@pytest.mark.parametrize(
    ("path", "mode"),
    [
        ("link", "new file mode 120000"),
        ("run.py", "new file mode 100755"),
        ("module", "new file mode 160000"),
    ],
)
def test_rejects_symlink_executable_and_submodule_modes(
    tmp_path: Path, path: str, mode: str
) -> None:
    patch = (
        f"diff --git a/{path} b/{path}\n"
        f"{mode}\n"
        "--- /dev/null\n"
        f"+++ b/{path}\n"
        "@@ -0,0 +1 @@\n"
        "+payload\n"
    )
    with pytest.raises(CodexPatchError):
        parse_codex_patch(_message(path, patch), tmp_path)


@pytest.mark.parametrize(
    "path",
    [
        ".git/config",
        ".gitattributes",
        ".gitmodules",
        "conftest.py",
        "tests/conftest.py",
        "sitecustomize.py",
        "usercustomize.py",
        "pytest.ini",
        "tox.ini",
    ],
)
def test_rejects_repository_and_python_execution_hooks(
    tmp_path: Path, path: str
) -> None:
    patch = (
        f"diff --git a/{path} b/{path}\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        f"+++ b/{path}\n"
        "@@ -0,0 +1 @@\n"
        "+payload\n"
    )
    with pytest.raises(CodexPatchError):
        parse_codex_patch(_message(path, patch), tmp_path)


def test_rejects_existing_symlink_even_when_target_stays_inside_workspace(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target.py"
    target.write_text("safe\n", encoding="utf-8")
    link = tmp_path / "link.py"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    patch = (
        "diff --git a/link.py b/link.py\n"
        "--- a/link.py\n"
        "+++ b/link.py\n"
        "@@ -1 +1 @@\n"
        "-safe\n"
        "+changed\n"
    )
    with pytest.raises(CodexPatchError):
        parse_codex_patch(_message("link.py", patch), tmp_path)


def test_rejects_patch_too_large_for_full_telegram_preview(tmp_path: Path) -> None:
    patch = (
        "diff --git a/safe.txt b/safe.txt\n"
        "--- a/safe.txt\n"
        "+++ b/safe.txt\n"
        "@@ -1 +1 @@\n"
        "-old\n+"
        + "x" * (16 * 1024)
        + "\n"
    )
    with pytest.raises(CodexPatchError):
        parse_codex_patch(_message("safe.txt", patch), tmp_path)
