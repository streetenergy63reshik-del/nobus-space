from __future__ import annotations

import json
import pathlib
import subprocess

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / "tests/gate0/manage_runtime_maintenance.ps1"


def run_case(case: str) -> subprocess.CompletedProcess[str]:
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
            f"""
. '{helper}'
$case = '{case}'
$exactDigest = 'sha256:' + ('1' * 64)
$baseDigest = 'sha256:' + ('2' * 64)
$definition = [pscustomobject]@{{
  PythonPath='C:\\runtime\\.venv\\Scripts\\python.exe'
  PythonDigest='sha256:' + ('a' * 64)
  BasePythonPath='C:\\Python312\\python.exe'
  BasePythonDigest='sha256:' + ('b' * 64)
}}
$exactProfile = [ordered]@{{
  scheduler_action_match=$true
  executable_hash_match=$true
  registered_live_root_match=$true
  exact_runner_script_match=$true
  argument_profile_match=$true
  secret_shape_absent=$true
  verified=$true
}}
$baseProfile = [ordered]@{{
  scheduler_action_match=$false
  executable_hash_match=$false
  registered_live_root_match=$true
  exact_runner_script_match=$true
  argument_profile_match=$true
  secret_shape_absent=$true
  verified=$false
}}
$exact = [pscustomobject]@{{
  identity_digest=$exactDigest
  verified=$true
  internal_profile=$exactProfile
  internal_pid=100
  internal_parent_pid=1
  internal_creation_filetime=1000
  internal_executable_path=$definition.PythonPath
  internal_executable_digest=$definition.PythonDigest
}}
$base = [pscustomobject]@{{
  identity_digest=$baseDigest
  verified=$false
  internal_profile=$baseProfile
  internal_pid=101
  internal_parent_pid=100
  internal_creation_filetime=2000
  internal_executable_path=$definition.BasePythonPath
  internal_executable_digest=$definition.BasePythonDigest
}}
$candidates = @($exact, $base)
$expected = @(($exactDigest), ($baseDigest))
switch ($case) {{
  'extra_candidate' {{
    $extra = [pscustomobject]@{{
      identity_digest='sha256:' + ('3' * 64)
      verified=$false
      internal_profile=$baseProfile
      internal_pid=102
      internal_parent_pid=100
      internal_creation_filetime=3000
      internal_executable_path=$definition.BasePythonPath
      internal_executable_digest=$definition.BasePythonDigest
    }}
    $candidates = @($exact, $base, $extra)
    $expected = @(($exactDigest), ($baseDigest), ($extra.identity_digest))
  }}
  'wrong_parent' {{ $base.internal_parent_pid = 999 }}
  'base_mismatch' {{
    $base.internal_executable_path = 'C:\\Other\\python.exe'
  }}
  'chronology_mismatch' {{ $base.internal_creation_filetime = 500 }}
  'digest_drift' {{
    $expected = @(($exactDigest), ('sha256:' + ('4' * 64)))
  }}
}}
$classification = New-MaintenanceClassification `
  -SchedulerState running `
  -MutexState occupied `
  -Candidates $candidates
$allowed = Test-RunningLogicalRunnerGroup `
  -Classification $classification `
  -Candidates $candidates `
  -ExpectedIdentityDigests $expected `
  -Definition $definition
[ordered]@{{ allowed=$allowed }} | ConvertTo-Json -Compress
""",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        pytest.param("valid", True, id="direct-pyvenv-child"),
        pytest.param("extra_candidate", False, id="ambiguous-extra-candidate"),
        pytest.param("wrong_parent", False, id="not-direct-child"),
        pytest.param("base_mismatch", False, id="pyvenv-base-mismatch"),
        pytest.param("chronology_mismatch", False, id="creation-chronology"),
        pytest.param("digest_drift", False, id="unstable-opaque-digest-set"),
    ],
)
def test_running_logical_group_contract(case: str, expected: bool) -> None:
    completed = run_case(case)

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"allowed": expected}
