from __future__ import annotations

import json
import pathlib
import subprocess


ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / "tests/gate0/manage_runtime_maintenance.ps1"


def run_powershell(body: str) -> subprocess.CompletedProcess[str]:
    helper = str(HELPER).replace("'", "''")
    return subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f". '{helper}'; {body}",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_candidate_scope_requires_exact_runner_script_name() -> None:
    completed = run_powershell(
        r"""
$unrelated = Test-IsRunnerCandidate `
  -CommandLine '"C:\runtime\python.exe" -m pytest' `
  -RunnerScriptName 'run_telegram_mvp1.py'
$registered = Test-IsRunnerCandidate `
  -CommandLine '"C:\runtime\python.exe" "C:\runtime\scripts\run_telegram_mvp1.py" --serve --timeout 30 --announce' `
  -RunnerScriptName 'run_telegram_mvp1.py'
$otherRoot = Test-IsRunnerCandidate `
  -CommandLine '"D:\other\python.exe" "D:\other\run_telegram_mvp1.py" --serve' `
  -RunnerScriptName 'run_telegram_mvp1.py'
$lookalike = Test-IsRunnerCandidate `
  -CommandLine '"D:\other\python.exe" "D:\other\run_telegram_mvp1.py.bak" --serve' `
  -RunnerScriptName 'run_telegram_mvp1.py'
[ordered]@{
  unrelated=$unrelated
  registered=$registered
  other_root=$otherRoot
  lookalike=$lookalike
} | ConvertTo-Json -Compress
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "unrelated": False,
        "registered": True,
        "other_root": True,
        "lookalike": False,
    }
