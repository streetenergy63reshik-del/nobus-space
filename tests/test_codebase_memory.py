"""Tests for the in-memory codebase memory."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.memory.codebase_memory import CodebaseMemory


@pytest.fixture
def sample_codebase() -> str:
    """Create a temporary directory with sample Python files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "main.py").write_text(
            "from utils import helper\n\n"
            "def main():\n"
            "    return helper()\n",
            encoding="utf-8",
        )
        (root / "utils.py").write_text(
            "def helper():\n"
            "    return 42\n\n"
            "class HelperClass:\n"
            "    pass\n",
            encoding="utf-8",
        )
        (root / ".venv").mkdir(parents=True)
        (root / ".venv" / "ignored.py").write_text("# should be ignored")
        yield tmpdir


@pytest.mark.asyncio
async def test_index_counts_snippets(sample_codebase: str) -> None:
    """Indexing creates expected numbers of snippets."""
    memory = CodebaseMemory()
    memory.index(sample_codebase)

    stats = memory.stats()
    assert stats["modules"] == 2
    assert stats["functions"] >= 2
    assert stats["classes"] == 1


@pytest.mark.asyncio
async def test_query_finds_helper_function(sample_codebase: str) -> None:
    """Query retrieves the helper function by name."""
    memory = CodebaseMemory()
    memory.index(sample_codebase)

    results = memory.query("how does helper work")
    assert len(results) > 0
    assert any("helper" in snippet.name.lower() for snippet in results)


@pytest.mark.asyncio
async def test_query_finds_class(sample_codebase: str) -> None:
    """Query retrieves a class by name."""
    memory = CodebaseMemory()
    memory.index(sample_codebase)

    results = memory.query("HelperClass")
    assert len(results) > 0
    assert any(snippet.name == "HelperClass" for snippet in results)


@pytest.mark.asyncio
async def test_venv_files_are_ignored(sample_codebase: str) -> None:
    """Files inside .venv are not indexed."""
    memory = CodebaseMemory()
    memory.index(sample_codebase)

    results = memory.query("ignored")
    assert not any("ignored" in snippet.file_path for snippet in results)
