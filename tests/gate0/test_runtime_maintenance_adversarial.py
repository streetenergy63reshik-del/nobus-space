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


def test_argument_profile_rejects_prefix_tokens_and_code_execution() -> None:
    completed = run_powershell(
        r"""
$definition = [pscustomobject]@{
  PythonPath='C:\registered\.venv\Scripts\python.exe'
  PythonDigest='sha256:' + ('a' * 64)
  RunnerPath='C:\registered\scripts\run_telegram_mvp1.py'
}
$extraPrefix = New-RunnerCandidateProfile `
  -CommandLine '"C:\registered\.venv\Scripts\python.exe" -c pass "C:\registered\scripts\run_telegram_mvp1.py" --serve --timeout 30 --announce' `
  -ExecutablePath 'C:\registered\.venv\Scripts\python.exe' `
  -ExecutableDigest ('sha256:' + ('a' * 64)) `
  -Definition $definition
$extraFlag = New-RunnerCandidateProfile `
  -CommandLine '"C:\registered\.venv\Scripts\python.exe" "C:\registered\scripts\run_telegram_mvp1.py" --other --serve --timeout 30 --announce' `
  -ExecutablePath 'C:\registered\.venv\Scripts\python.exe' `
  -ExecutableDigest ('sha256:' + ('a' * 64)) `
  -Definition $definition
[ordered]@{ prefix=$extraPrefix; flag=$extraFlag } |
  ConvertTo-Json -Compress -Depth 4
"""
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    for profile in payload.values():
        assert profile["argument_profile_match"] is False
        assert profile["scheduler_action_match"] is False
        assert profile["verified"] is False


def test_creation_identity_comparison_is_exact() -> None:
    completed = run_powershell(
        """
[ordered]@{
  exact=(Test-CreationIdentityMatches -ExpectedFileTime 123456789 -ObservedFileTime 123456789)
  reused=(Test-CreationIdentityMatches -ExpectedFileTime 123456789 -ObservedFileTime 123456790)
  missing=(Test-CreationIdentityMatches -ExpectedFileTime 123456789 -ObservedFileTime 0)
} | ConvertTo-Json -Compress
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "exact": True,
        "reused": False,
        "missing": False,
    }


def test_termination_uses_creation_bound_windows_handles() -> None:
    source = HELPER.read_text(encoding="utf-8")
    assert "OpenProcess" in source
    assert "GetProcessTimes" in source
    assert "TerminateProcess" in source
    assert "internal_creation_filetime" in source
    assert "Stop-Process" not in source
