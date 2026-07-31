from __future__ import annotations

import json
import pytest

from test_runtime_maintenance_profiles import run_powershell


def test_start_verified_requires_every_live_authority_digest_before_reads() -> None:
    completed = run_powershell(
        r"""
$digest = 'sha256:' + ('1' * 64)
$script:coreReads = 0
$script:liveReads = 0
$script:startCalls = 0
function Get-FrozenPreCaptureAuthority {
  param($CanonicalRepoRoot,$ExpectedInputTreeDigest,$ExpectedFrozenTreeDigest,$ExpectedGitStatusDigest)
  $script:coreReads++
  return [pscustomobject]@{
    InputTreeDigest=$digest
    FrozenTreeDigest=$digest
    GitStatusDigest=$digest
  }
}
$classification = New-MaintenanceClassification `
  -SchedulerState 'ready' -MutexState 'free' -Candidates @()
$definition = [pscustomobject]@{
  DefinitionDigest=$digest
  LauncherDigest=$digest
  RunnerDigest=$digest
  PythonDigest=$digest
  ActionExecutableDigest=$digest
  ActionIdContractExact=$true
}
function Get-LiveMaintenanceState {
  param($CanonicalRepoRoot)
  $script:liveReads++
  return [pscustomobject]@{
    Definition=$definition
    Candidates=@()
    Classification=$classification
  }
}
function Start-ScheduledTask {
  param($TaskName,$ErrorAction)
  $script:startCalls++
}
$names = @(
  'ExpectedDefinitionDigest',
  'ExpectedLauncherDigest',
  'ExpectedRunnerDigest',
  'ExpectedPythonDigest',
  'ExpectedActionExecutableDigest'
)
$results = @()
foreach ($name in $names) {
  foreach ($variant in @('omitted', 'malformed')) {
    $script:coreReads = 0
    $script:liveReads = 0
    $script:startCalls = 0
    $parameters = @{
      SelectedMode='start-verified'
      CanonicalRepoRoot='C:\canonical'
      ExpectedInputTreeDigest=$digest
      ExpectedFrozenTreeDigest=$digest
      ExpectedGitStatusDigest=$digest
      ExpectedDefinitionDigest=$digest
      ExpectedLauncherDigest=$digest
      ExpectedRunnerDigest=$digest
      ExpectedPythonDigest=$digest
      ExpectedActionExecutableDigest=$digest
    }
    if ($variant -eq 'omitted') {
      $parameters.Remove($name)
    }
    else {
      $parameters[$name] = 'sha256:not-valid'
    }
    $blocked = $false
    try {
      Invoke-RuntimeMaintenance @parameters
    }
    catch {
      $blocked = $true
    }
    $results += [ordered]@{
      name=$name
      variant=$variant
      blocked=$blocked
      core_reads=$script:coreReads
      live_reads=$script:liveReads
      start_calls=$script:startCalls
    }
  }
}
$results | ConvertTo-Json -Compress
"""
    )

    assert completed.returncode == 0, completed.stderr
    results = json.loads(completed.stdout)
    assert len(results) == 10
    assert all(item["blocked"] is True for item in results)
    assert all(item["core_reads"] == 0 for item in results)
    assert all(item["live_reads"] == 0 for item in results)
    assert all(item["start_calls"] == 0 for item in results)


def test_start_verified_reads_final_live_state_after_third_core() -> None:
    completed = run_powershell(
        r"""
$digest = 'sha256:' + ('1' * 64)
$other = 'sha256:' + ('2' * 64)
$script:coreReads = 0
$script:liveReads = 0
$script:startCalls = 0
$script:currentDefinitionDigest = $digest
function Get-FrozenPreCaptureAuthority {
  param($CanonicalRepoRoot,$ExpectedInputTreeDigest,$ExpectedFrozenTreeDigest,$ExpectedGitStatusDigest)
  $script:coreReads++
  if ($script:coreReads -eq 3) {
    $script:currentDefinitionDigest = $other
  }
  return [pscustomobject]@{
    InputTreeDigest=$digest
    FrozenTreeDigest=$digest
    GitStatusDigest=$digest
  }
}
$classification = New-MaintenanceClassification `
  -SchedulerState 'ready' -MutexState 'free' -Candidates @()
function Get-LiveMaintenanceState {
  param($CanonicalRepoRoot)
  $script:liveReads++
  return [pscustomobject]@{
    Definition=[pscustomobject]@{
      DefinitionDigest=$script:currentDefinitionDigest
      LauncherDigest=$digest
      RunnerDigest=$digest
      PythonDigest=$digest
      ActionExecutableDigest=$digest
      ActionIdContractExact=$true
    }
    Candidates=@()
    Classification=$classification
  }
}
function Start-ScheduledTask {
  param($TaskName,$ErrorAction)
  $script:startCalls++
}
$blocked = $false
try {
  Invoke-RuntimeMaintenance `
    -SelectedMode 'start-verified' `
    -CanonicalRepoRoot 'C:\canonical' `
    -ExpectedInputTreeDigest $digest `
    -ExpectedFrozenTreeDigest $digest `
    -ExpectedGitStatusDigest $digest `
    -ExpectedDefinitionDigest $digest `
    -ExpectedLauncherDigest $digest `
    -ExpectedRunnerDigest $digest `
    -ExpectedPythonDigest $digest `
    -ExpectedActionExecutableDigest $digest
}
catch {
  $blocked = $true
}
[ordered]@{
  blocked=$blocked
  core_reads=$script:coreReads
  live_reads=$script:liveReads
  start_calls=$script:startCalls
} | ConvertTo-Json -Compress
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "blocked": True,
        "core_reads": 3,
        "live_reads": 2,
        "start_calls": 0,
    }


@pytest.mark.parametrize(
    "drift_value",
    ["$false", "$null", "'true'"],
)
def test_start_verified_rejects_action_id_contract_drift(drift_value: str) -> None:
    completed = run_powershell(
        r"""
$digest = 'sha256:' + ('1' * 64)
$script:coreReads = 0
$script:liveReads = 0
$script:startCalls = 0
function Get-FrozenPreCaptureAuthority {
  param($CanonicalRepoRoot,$ExpectedInputTreeDigest,$ExpectedFrozenTreeDigest,$ExpectedGitStatusDigest)
  $script:coreReads++
  return [pscustomobject]@{
    InputTreeDigest=$digest
    FrozenTreeDigest=$digest
    GitStatusDigest=$digest
  }
}
$classification = New-MaintenanceClassification `
  -SchedulerState 'ready' -MutexState 'free' -Candidates @()
function Get-LiveMaintenanceState {
  param($CanonicalRepoRoot)
  $script:liveReads++
  return [pscustomobject]@{
    Definition=[pscustomobject]@{
      DefinitionDigest=$digest
      LauncherDigest=$digest
      RunnerDigest=$digest
      PythonDigest=$digest
      ActionExecutableDigest=$digest
      ActionIdContractExact=$(
        if ($script:liveReads -eq 1) { $true }
        else { __ACTION_ID_DRIFT__ }
      )
    }
    Candidates=@()
    Classification=$classification
  }
}
function Start-ScheduledTask {
  param($TaskName,$ErrorAction)
  $script:startCalls++
}
$blocked = $false
try {
  Invoke-RuntimeMaintenance `
    -SelectedMode 'start-verified' `
    -CanonicalRepoRoot 'C:\canonical' `
    -ExpectedInputTreeDigest $digest `
    -ExpectedFrozenTreeDigest $digest `
    -ExpectedGitStatusDigest $digest `
    -ExpectedDefinitionDigest $digest `
    -ExpectedLauncherDigest $digest `
    -ExpectedRunnerDigest $digest `
    -ExpectedPythonDigest $digest `
    -ExpectedActionExecutableDigest $digest
}
catch {
  $blocked = $true
}
[ordered]@{
  blocked=$blocked
  core_reads=$script:coreReads
  live_reads=$script:liveReads
  start_calls=$script:startCalls
} | ConvertTo-Json -Compress
"""
    .replace("__ACTION_ID_DRIFT__", drift_value))

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "blocked": True,
        "core_reads": 3,
        "live_reads": 2,
        "start_calls": 0,
    }
