"""Deterministic checks for the canonical Nobus Space documentation."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote


REPO_ROOT = Path(__file__).parents[1]
DOCS_ROOT = REPO_ROOT / "docs"
CANONICAL_DOCS = {
    "README.md",
    "01-Единый-документ-проекта.md",
    "02-Глоссарий.md",
    "03-Архитектурный-обзор.md",
    "04-Журнал-ADR.md",
    "05-Спецификации-контрактов.md",
    "06-Регламент-качества-L1-L4.md",
    "07-Правила-внешней-записи.md",
    "08-Runbook-эксплуатации.md",
    "09-Стандарты-отчётов.md",
    "10-Политика-памяти.md",
}
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
INTERVIEW_REFERENCE = re.compile(r"[（(]В\d+[）)]")


def _markdown_files() -> list[Path]:
    return sorted(DOCS_ROOT.rglob("*.md"))


def test_canonical_document_set_exists() -> None:
    actual = {path.name for path in DOCS_ROOT.iterdir() if path.is_file()}
    assert CANONICAL_DOCS <= actual


def test_relative_markdown_links_resolve() -> None:
    broken: list[str] = []
    for document in _markdown_files() + [REPO_ROOT / "README.md", REPO_ROOT / "AGENTS.md"]:
        text = document.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(text):
            target = raw_target.strip().strip("<>").split("#", 1)[0]
            if not target or "://" in target or target.startswith(("mailto:", "#")):
                continue
            resolved = (document.parent / unquote(target)).resolve()
            if not resolved.exists():
                broken.append(f"{document.relative_to(REPO_ROOT)} -> {raw_target}")
    assert not broken, "Broken documentation links:\n" + "\n".join(broken)


def test_normative_docs_do_not_depend_on_unverifiable_interview_markers() -> None:
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _markdown_files()
        if INTERVIEW_REFERENCE.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, "Unverifiable В1…В29 references remain in: " + ", ".join(offenders)


def test_normative_docs_do_not_point_to_retired_copies() -> None:
    retired_markers = (
        "Code копия",
        "Nobus Space — Единый документ проекта.md",
        "01-Единый-документ-проекта-v2.md",
    )
    offenders: list[str] = []
    for path in _markdown_files():
        text = path.read_text(encoding="utf-8")
        if any(marker in text for marker in retired_markers):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, "Retired documentation references remain in: " + ", ".join(offenders)
