from __future__ import annotations

import json
import pathlib
import subprocess


ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / "tests/gate0/manage_runtime_maintenance.ps1"


def test_runner_root_mismatch_is_classified_without_exposing_path() -> None:
    helper = str(HELPER).replace("'", "''")
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f"""
. '{helper}'
$canonical = 'C:\\Code\\nobus-orchestrator-dev'
$cases = [ordered]@{{
  telegram_live = Get-RegisteredRuntimeRootFailureStage `
    -CanonicalRepoRoot $canonical `
    -RunnerRoot 'C:\\Code\\worktrees\\telegram-live'
  other_worktree = Get-RegisteredRuntimeRootFailureStage `
    -CanonicalRepoRoot $canonical `
    -RunnerRoot 'C:\\Code\\worktrees\\other'
  other_code = Get-RegisteredRuntimeRootFailureStage `
    -CanonicalRepoRoot $canonical `
    -RunnerRoot 'C:\\Code\\other'
  unauthorized = Get-RegisteredRuntimeRootFailureStage `
    -CanonicalRepoRoot $canonical `
    -RunnerRoot 'D:\\outside'
}}
$cases | ConvertTo-Json -Compress
""",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload == {
        "telegram_live": "runner_root_other_worktree",
        "other_worktree": "runner_root_other_worktree",
        "other_code": "runner_root_other_code",
        "unauthorized": "runner_root_unauthorized",
    }
    serialized = json.dumps(payload).casefold()
    assert "c:\\" not in serialized
    assert "d:\\" not in serialized
