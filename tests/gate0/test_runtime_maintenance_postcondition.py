from __future__ import annotations

import json
import pathlib
import subprocess


ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / "tests/gate0/manage_runtime_maintenance.ps1"


def test_postcondition_requires_ready_zero_and_free_together() -> None:
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
$ready = New-MaintenanceClassification `
  -SchedulerState ready -MutexState free -Candidates @()
$running = New-MaintenanceClassification `
  -SchedulerState running -MutexState free -Candidates @()
$occupied = New-MaintenanceClassification `
  -SchedulerState ready -MutexState occupied -Candidates @()
$candidate = New-MaintenanceClassification `
  -SchedulerState ready -MutexState free `
  -Candidates @([pscustomobject]@{{
    identity_digest='sha256:' + ('1' * 64); verified=$true
  }})
[ordered]@{{
  ready=(Test-MaintenancePostcondition -Classification $ready)
  running=(Test-MaintenancePostcondition -Classification $running)
  occupied=(Test-MaintenancePostcondition -Classification $occupied)
  candidate=(Test-MaintenancePostcondition -Classification $candidate)
}} | ConvertTo-Json -Compress
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
    assert json.loads(completed.stdout) == {
        "ready": True,
        "running": False,
        "occupied": False,
        "candidate": False,
    }
