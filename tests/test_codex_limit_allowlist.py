"""Exact allowlist parity for the non-generative Codex limit query."""

from __future__ import annotations

from pathlib import Path

from src.workers.codex_cli import _RATE_LIMIT_ARGV as ADAPTER_ARGV
from src.workers.windows_job_helper import (
    _RATE_LIMIT_ARGV as HELPER_ARGV,
    _validated,
)


def test_rate_limit_profile_matches_helper_and_validates(tmp_path: Path) -> None:
    executable = tmp_path / "codex.exe"
    executable.touch()
    gate = "Local\\NobusOrchestrator-" + "a" * 32

    assert ADAPTER_ARGV == HELPER_ARGV
    assert _validated([gate, "--", str(executable.resolve()), *ADAPTER_ARGV]) == (
        gate,
        (str(executable.resolve()), *ADAPTER_ARGV),
    )
