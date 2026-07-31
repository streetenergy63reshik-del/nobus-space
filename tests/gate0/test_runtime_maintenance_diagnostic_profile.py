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


def test_diagnostic_profile_separates_identity_predicates() -> None:
    completed = run_powershell(
        r"""
$definition = [pscustomobject]@{
  PythonPath='C:\registered\.venv\Scripts\python.exe'
  PythonDigest='sha256:' + ('a' * 64)
  RunnerPath='C:\registered\scripts\run_telegram_mvp1.py'
}
$exact = New-RunnerCandidateProfile `
  -CommandLine '"C:\registered\.venv\Scripts\python.exe" "C:\registered\scripts\run_telegram_mvp1.py" --serve --timeout 30 --announce' `
  -ExecutablePath 'C:\registered\.venv\Scripts\python.exe' `
  -ExecutableDigest ('sha256:' + ('a' * 64)) `
  -Definition $definition
$legacy = New-RunnerCandidateProfile `
  -CommandLine '"D:\legacy\.venv\Scripts\python.exe" "D:\legacy\scripts\run_telegram_mvp1.py" --serve --timeout 30 --announce' `
  -ExecutablePath 'D:\legacy\.venv\Scripts\python.exe' `
  -ExecutableDigest ('sha256:' + ('a' * 64)) `
  -Definition $definition
[ordered]@{ exact=$exact; legacy=$legacy } |
  ConvertTo-Json -Compress -Depth 4
"""
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["exact"] == {
        "scheduler_action_match": True,
        "executable_hash_match": True,
        "registered_live_root_match": True,
        "exact_runner_script_match": True,
        "argument_profile_match": True,
        "secret_shape_absent": True,
        "verified": True,
    }
    assert payload["legacy"] == {
        "scheduler_action_match": False,
        "executable_hash_match": True,
        "registered_live_root_match": False,
        "exact_runner_script_match": True,
        "argument_profile_match": True,
        "secret_shape_absent": True,
        "verified": False,
    }


def test_secret_shaped_candidate_is_never_verified() -> None:
    completed = run_powershell(
        r"""
$definition = [pscustomobject]@{
  PythonPath='C:\registered\.venv\Scripts\python.exe'
  PythonDigest='sha256:' + ('a' * 64)
  RunnerPath='C:\registered\scripts\run_telegram_mvp1.py'
}
New-RunnerCandidateProfile `
  -CommandLine '"C:\registered\.venv\Scripts\python.exe" "C:\registered\scripts\run_telegram_mvp1.py" --serve --timeout 30 --announce token=value' `
  -ExecutablePath 'C:\registered\.venv\Scripts\python.exe' `
  -ExecutableDigest ('sha256:' + ('a' * 64)) `
  -Definition $definition |
  ConvertTo-Json -Compress
"""
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["secret_shape_absent"] is False
    assert payload["argument_profile_match"] is False
    assert payload["verified"] is False
