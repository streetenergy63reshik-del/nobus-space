from __future__ import annotations

import json
import pathlib
import subprocess


ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / "tests/gate0/manage_runtime_maintenance.ps1"


def test_descendant_plan_rejects_stale_parent_and_creation_chronology() -> None:
    helper = str(HELPER).replace("'", "''")
    body = """
$valid=@(
  [pscustomobject]@{internal_pid=10;internal_parent_pid=1;internal_creation_filetime=100;internal_is_root=$true},
  [pscustomobject]@{internal_pid=11;internal_parent_pid=10;internal_creation_filetime=200;internal_is_root=$false}
)
$stale=@(
  [pscustomobject]@{internal_pid=10;internal_parent_pid=1;internal_creation_filetime=100;internal_is_root=$true},
  [pscustomobject]@{internal_pid=11;internal_parent_pid=10;internal_creation_filetime=50;internal_is_root=$false}
)
$missing=@(
  [pscustomobject]@{internal_pid=10;internal_parent_pid=1;internal_creation_filetime=100;internal_is_root=$true},
  [pscustomobject]@{internal_pid=11;internal_parent_pid=99;internal_creation_filetime=200;internal_is_root=$false}
)
$duplicate=@(
  [pscustomobject]@{internal_pid=10;internal_parent_pid=1;internal_creation_filetime=100;internal_is_root=$true},
  [pscustomobject]@{internal_pid=10;internal_parent_pid=10;internal_creation_filetime=200;internal_is_root=$false}
)
[ordered]@{
  valid=(Test-TerminationPlanChronology -TerminationPlan $valid)
  stale=(Test-TerminationPlanChronology -TerminationPlan $stale)
  missing=(Test-TerminationPlanChronology -TerminationPlan $missing)
  duplicate=(Test-TerminationPlanChronology -TerminationPlan $duplicate)
}|ConvertTo-Json -Compress
"""
    completed = subprocess.run(
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

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "valid": True,
        "stale": False,
        "missing": False,
        "duplicate": False,
    }


def test_all_handles_are_opened_before_first_termination() -> None:
    source = HELPER.read_text(encoding="utf-8")
    function = source.split("function Invoke-ExactHandleTermination", 1)[1]
    function = function.split("function Get-ProductionMutexState", 1)[0]
    assert function.index("Open-ValidatedTerminationHandles") < function.index(
        "TerminateProcess"
    )
    assert "finally" in function
    assert "CloseHandle" in function
