from __future__ import annotations

import json
import pathlib
import subprocess


ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / "tests/gate0/manage_runtime_maintenance.ps1"


def test_stop_uses_first_running_read_as_stability_baseline() -> None:
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
$exactDigest = 'sha256:' + ('1' * 64)
$baseDigest = 'sha256:' + ('2' * 64)
$definition = [pscustomobject]@{{
  PythonPath='C:\\runtime\\.venv\\Scripts\\python.exe'
  PythonDigest='sha256:' + ('a' * 64)
  BasePythonPath='C:\\Python312\\python.exe'
  BasePythonDigest='sha256:' + ('b' * 64)
}}
$exactProfile = [ordered]@{{
  scheduler_action_match=$true; executable_hash_match=$true
  registered_live_root_match=$true; exact_runner_script_match=$true
  argument_profile_match=$true; secret_shape_absent=$true; verified=$true
}}
$baseProfile = [ordered]@{{
  scheduler_action_match=$false; executable_hash_match=$false
  registered_live_root_match=$true; exact_runner_script_match=$true
  argument_profile_match=$true; secret_shape_absent=$true; verified=$false
}}
$candidates = @(
  [pscustomobject]@{{
    identity_digest=$exactDigest; verified=$true; internal_profile=$exactProfile
    internal_pid=100; internal_parent_pid=1; internal_creation_filetime=1000
    internal_executable_path=$definition.PythonPath
    internal_executable_digest=$definition.PythonDigest
  }},
  [pscustomobject]@{{
    identity_digest=$baseDigest; verified=$false; internal_profile=$baseProfile
    internal_pid=101; internal_parent_pid=100; internal_creation_filetime=2000
    internal_executable_path=$definition.BasePythonPath
    internal_executable_digest=$definition.BasePythonDigest
  }}
)
$running = New-MaintenanceClassification `
  -SchedulerState running -MutexState occupied -Candidates $candidates
$stopped = New-MaintenanceClassification `
  -SchedulerState ready -MutexState free -Candidates @()
$script:readCount = 0
$script:terminationCalls = 0
function Get-LiveMaintenanceState {{
  $script:readCount++
  if ($script:readCount -le 2) {{
    return [pscustomobject]@{{
      Definition=$definition; Candidates=$candidates; Classification=$running
    }}
  }}
  return [pscustomobject]@{{
    Definition=$definition; Candidates=@(); Classification=$stopped
  }}
}}
function Get-ProvenTerminationPlan {{
  return @([pscustomobject]@{{
    internal_pid=100; internal_parent_pid=1
    internal_creation_filetime=1000; internal_is_root=$true
  }})
}}
function Invoke-ExactHandleTermination {{ $script:terminationCalls++ }}
Invoke-RuntimeMaintenance `
  -SelectedMode stop-verified `
  -CanonicalRepoRoot 'C:\\repo' `
  -ExpectedDigests @() `
  -AllowLegacyRemediation
[ordered]@{{
  reads=$script:readCount
  termination_calls=$script:terminationCalls
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
    assert json.loads(completed.stdout.splitlines()[-1]) == {
        "reads": 3,
        "termination_calls": 1,
    }
