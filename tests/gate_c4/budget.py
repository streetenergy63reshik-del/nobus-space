"""C4 has its own aggregate ledger; C3 accounting/cleanup rules are unchanged."""

from pathlib import Path
import subprocess

from tests.gate_c3.budget import Budget, LIMITS, TurnBudget


ROOT = Path(__file__).resolve().parents[2]


def ledger_path() -> Path:
    # git-common-dir identifies the canonical repository from review worktrees too.
    common = Path(subprocess.check_output(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=ROOT, text=True, encoding="utf-8",
    ).strip())
    return common.parent / ".runtime/worktrees/mvp1-closure-c4-frontend-journey/.runtime/c4/execution-budget.sqlite3"


__all__ = ["Budget", "LIMITS", "TurnBudget", "ledger_path"]
