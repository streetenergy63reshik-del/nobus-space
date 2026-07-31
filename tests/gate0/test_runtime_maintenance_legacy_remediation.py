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


def test_legacy_remediation_requires_one_exact_and_one_legacy_only() -> None:
    completed = run_powershell(
        """
$exactDigest = 'sha256:' + ('1' * 64)
$legacyDigest = 'sha256:' + ('2' * 64)
$exactProfile = [ordered]@{
  scheduler_action_match=$true
  executable_hash_match=$true
  registered_live_root_match=$true
  exact_runner_script_match=$true
  argument_profile_match=$true
  secret_shape_absent=$true
  verified=$true
}
$legacyProfile = [ordered]@{
  scheduler_action_match=$false
  executable_hash_match=$false
  registered_live_root_match=$true
  exact_runner_script_match=$true
  argument_profile_match=$true
  secret_shape_absent=$true
  verified=$false
}
$exactCandidate = [pscustomobject]@{
  identity_digest=$exactDigest
  verified=$true
  internal_profile=$exactProfile
}
$legacyCandidate = [pscustomobject]@{
  identity_digest=$legacyDigest
  verified=$false
  internal_profile=$legacyProfile
}
$classification = New-MaintenanceClassification `
  -SchedulerState ready `
  -MutexState occupied `
  -Candidates @($exactCandidate, $legacyCandidate)
$allowed = Test-LegacyExecutableRemediationSet `
  -Classification $classification `
  -Candidates @($legacyCandidate, $exactCandidate) `
  -ExpectedIdentityDigests @(($legacyDigest), ($exactDigest))
$wrongProfile = [ordered]@{
  scheduler_action_match=$false
  executable_hash_match=$false
  registered_live_root_match=$true
  exact_runner_script_match=$true
  argument_profile_match=$false
  secret_shape_absent=$true
  verified=$false
}
$wrongCandidate = [pscustomobject]@{
  identity_digest=$legacyDigest
  verified=$false
  internal_profile=$wrongProfile
}
$blocked = Test-LegacyExecutableRemediationSet `
  -Classification $classification `
  -Candidates @($exactCandidate, $wrongCandidate) `
  -ExpectedIdentityDigests @(($exactDigest), ($legacyDigest))
[ordered]@{ allowed=$allowed; blocked=$blocked } |
  ConvertTo-Json -Compress
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"allowed": True, "blocked": False}


def test_legacy_remediation_rejects_extra_candidate() -> None:
    completed = run_powershell(
        """
$digest1 = 'sha256:' + ('1' * 64)
$digest2 = 'sha256:' + ('2' * 64)
$digest3 = 'sha256:' + ('3' * 64)
$exactProfile = [ordered]@{
  scheduler_action_match=$true; executable_hash_match=$true
  registered_live_root_match=$true; exact_runner_script_match=$true
  argument_profile_match=$true; secret_shape_absent=$true; verified=$true
}
$legacyProfile = [ordered]@{
  scheduler_action_match=$false; executable_hash_match=$false
  registered_live_root_match=$true; exact_runner_script_match=$true
  argument_profile_match=$true; secret_shape_absent=$true; verified=$false
}
$candidates = @(
  [pscustomobject]@{identity_digest=$digest1;verified=$true;internal_profile=$exactProfile},
  [pscustomobject]@{identity_digest=$digest2;verified=$false;internal_profile=$legacyProfile},
  [pscustomobject]@{identity_digest=$digest3;verified=$false;internal_profile=$legacyProfile}
)
$classification = New-MaintenanceClassification `
  -SchedulerState ready -MutexState occupied -Candidates $candidates
$result = Test-LegacyExecutableRemediationSet `
  -Classification $classification `
  -Candidates $candidates `
  -ExpectedIdentityDigests @(($digest1), ($digest2), ($digest3))
[ordered]@{ result=$result } | ConvertTo-Json -Compress
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"result": False}
