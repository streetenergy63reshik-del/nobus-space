"""Tests for strict read-only Codex patch drafts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.workers.codex_patch import (
    CodexAnswerDraft,
    CodexPatchError,
    parse_codex_draft,
    parse_codex_patch,
)


def _message(patch: str, paths: list[str] | None = None) -> str:
    return json.dumps(
        {
            "summary": "Added one safe file.",
            "patch": patch,
            "paths": paths or ["src/safe.py"],
        },
        separators=(",", ":"),
    )


def test_accepts_bounded_text_patch(tmp_path: Path) -> None:
    patch = (
        "diff --git a/src/safe.py b/src/safe.py\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/src/safe.py\n"
        "@@ -0,0 +1 @@\n"
        "+SAFE = True\n"
    )

    draft = parse_codex_patch(_message(patch), tmp_path)

    assert draft.paths == ("src/safe.py",)
    assert draft.patch == patch


@pytest.mark.parametrize(
    ("patch", "paths"),
    [
        (
            "diff --git a/../escape.py b/../escape.py\n--- /dev/null\n+++ b/../escape.py\n",
            ["../escape.py"],
        ),
        (
            "diff --git a/.env b/.env\n--- /dev/null\n+++ b/.env\n",
            [".env"],
        ),
        (
            "diff --git a/src/safe.py b/src/safe.py\nGIT binary patch\n",
            ["src/safe.py"],
        ),
        (
            "diff --git a/src/safe.py b/src/safe.py\nnew mode 120000\n",
            ["src/safe.py"],
        ),
        (
            "diff --git a/src/one.py b/src/two.py\n--- a/src/one.py\n+++ b/src/two.py\n",
            ["src/two.py"],
        ),
    ],
)
def test_rejects_unsafe_patch_paths_and_modes(
    tmp_path: Path, patch: str, paths: list[str]
) -> None:
    with pytest.raises(CodexPatchError):
        parse_codex_patch(_message(patch, paths), tmp_path)


def test_rejects_duplicate_json_keys_and_path_manifest_mismatch(
    tmp_path: Path,
) -> None:
    duplicate = '{"summary":"one","summary":"two","patch":"x","paths":["x"]}'
    with pytest.raises(CodexPatchError):
        parse_codex_patch(duplicate, tmp_path)

    patch = "diff --git a/src/safe.py b/src/safe.py\n--- a/src/safe.py\n+++ b/src/safe.py\n"
    with pytest.raises(CodexPatchError):
        parse_codex_patch(_message(patch, ["src/other.py"]), tmp_path)


def test_accepts_bounded_informational_answer(tmp_path: Path) -> None:
    draft = parse_codex_draft(
        json.dumps({"answer": "  Готовность подтверждена.  "}, ensure_ascii=False),
        tmp_path,
    )

    assert draft == CodexAnswerDraft(answer="Готовность подтверждена.")


def test_removes_internal_desktop_notification_marker_from_answer(
    tmp_path: Path,
) -> None:
    draft = parse_codex_draft(
        json.dumps(
            {
                "answer": (
                    "Добрый день!\n\nОтвет для владельца.\n\n"
                    "<!-- nobus-notify:complete|Техническое уведомление. -->"
                )
            },
            ensure_ascii=False,
        ),
        tmp_path,
    )

    assert draft == CodexAnswerDraft(
        answer="Добрый день!\n\nОтвет для владельца."
    )


def test_rejects_answer_containing_only_desktop_notification_marker(
    tmp_path: Path,
) -> None:
    message = json.dumps(
        {"answer": "<!-- nobus-notify:complete|Техническое уведомление. -->"},
        ensure_ascii=False,
    )

    with pytest.raises(CodexPatchError):
        parse_codex_draft(message, tmp_path)


@pytest.mark.parametrize(
    "message",
    [
        '{"answer":"ok","extra":true}',
        '{"answer":"one","answer":"two"}',
        '{"answer":"\u0000"}',
        '{"answer":"123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}',
        '{"answer":"sk-proj-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}',
        '{"answer":"AKIAIOSFODNN7EXAMPLE"}',
        '{"answer":"AIzaSyD-ExampleKey123456789012345678"}',
        '{"answer":"aB3dE5gH7jK9mN2pQ4sT6vW8xY"}',
        '{"answer":"/home/owner/.ssh/id_rsa"}',
        '{"answer":"C:\\private\\credentials.txt"}',
        '{"answer":"15cc20b9-b62e-4000-babe-8fe99e1fc8bb"}',
        '{"answer":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}',    ],
)
def test_rejects_ambiguous_or_unsafe_answer(tmp_path: Path, message: str) -> None:
    with pytest.raises(CodexPatchError):
        parse_codex_draft(message, tmp_path)


def test_accepts_lowercase_build_identifier_without_false_secret_match(
    tmp_path: Path,
) -> None:
    draft = parse_codex_draft(
        '{"answer":"Build abcdef1234567890abcdef123456 is healthy."}',
        tmp_path,
    )

    assert isinstance(draft, CodexAnswerDraft)

def test_patch_only_parser_rejects_informational_answer(tmp_path: Path) -> None:
    with pytest.raises(CodexPatchError):
        parse_codex_patch('{"answer":"safe"}', tmp_path)
