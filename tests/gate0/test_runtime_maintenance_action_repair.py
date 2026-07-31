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


SYNTHETIC_REPAIR_FIXTURE = r"""
$root = $script:MaintenanceCanonicalRepoRoot
$launcher = Join-Path $root '.runtime\start-nobus-space-bot.ps1'
$principal = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$driftArguments = (
  '-WindowStyle Hidden -NoLogo -NoProfile -NonInteractive ' +
  '-ExecutionPolicy Bypass -File "{0}"'
) -f $launcher
$exactArguments = (
  '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"'
) -f $launcher
$script:repaired = $false
$script:mutationCount = 0
$script:syntheticActionId = ''

function New-SyntheticTask {
  $arguments = if ($script:repaired) {$exactArguments} else {$driftArguments}
  $trigger = [pscustomobject]@{
    CimClass=[pscustomobject]@{CimClassName='MSFT_TaskLogonTrigger'}
    UserId=$principal
  }
  $settings = [pscustomobject]@{
    Enabled=$true
    MultipleInstances='IgnoreNew'
    StartWhenAvailable=$true
    DisallowStartIfOnBatteries=$false
    StopIfGoingOnBatteries=$false
    RestartCount=10
    RestartInterval='PT1M'
    ExecutionTimeLimit='PT0S'
  }
  return [pscustomobject]@{
    TaskName='NobusSpaceBot'
    TaskPath='\'
    Description='Nobus Space owner Telegram orchestrator'
    Settings=$settings
    Principal=[pscustomobject]@{
      UserId=$principal
      LogonType='Interactive'
      RunLevel='Limited'
    }
    Triggers=@($trigger)
    Actions=@([pscustomobject]@{
      Execute='powershell.exe'
      Arguments=$arguments
      WorkingDirectory=''
      Id=$script:syntheticActionId
    })
  }
}

function Get-ScheduledTask {
  param($TaskName, $ErrorAction)
  return New-SyntheticTask
}

function Export-ScheduledTask {
  param($TaskName, $TaskPath, $ErrorAction)
  $task = New-SyntheticTask
  $escaped = [Security.SecurityElement]::Escape(
    [string] $task.Actions[0].Arguments
  )
  return (
    '<Task><RegistrationInfo><Date>2026-01-01</Date></RegistrationInfo>' +
    '<Actions><Exec><Command>powershell.exe</Command><Arguments>' +
    $escaped +
    '</Arguments></Exec></Actions></Task>'
  )
}

function Get-Command {
  param($Name, $ErrorAction)
  return [pscustomobject]@{Source=(Join-Path $PSHOME 'powershell.exe')}
}

function Test-ExactRepairLauncherContract {
  param($CanonicalRepoRoot)
  return $true
}

function New-ScheduledTaskAction {
  param($Execute, $Argument, $WorkingDirectory)
  return [pscustomobject]@{
    Execute=$Execute
    Arguments=$Argument
    WorkingDirectory=[string] $WorkingDirectory
  }
}

function Set-ScheduledTask {
  param($TaskName, $TaskPath, $Action, $ErrorAction)
  $script:mutationCount += 1
  if (
    [string] $Action.Execute -cne 'powershell.exe' -or
    [string] $Action.Arguments -cne $exactArguments
  ) {
    throw 'Synthetic action was not exact.'
  }
  $script:repaired = $true
  return New-SyntheticTask
}
"""


def test_action_repair_has_one_literal_mutation_and_no_stop_or_start() -> None:
    source = HELPER.read_text(encoding="utf-8")

    assert source.count('Set-ScheduledTask -TaskName "NobusSpaceBot"') == 1
    assert "repair-action-verified" in source
    assert "Stop-ScheduledTask" not in source
    repair_branch = source.index('$SelectedMode -eq "repair-action-verified"')
    live_read = source.index(
        "$live = Get-LiveMaintenanceState -CanonicalRepoRoot"
    )
    assert repair_branch < live_read


def test_action_repair_mutates_once_and_preserves_non_argument_contract() -> None:
    completed = run_powershell(
        SYNTHETIC_REPAIR_FIXTURE
        + r"""
Invoke-ExactSchedulerActionRepair -CanonicalRepoRoot $root
"""
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["schema"] == "nobus.gate0.runtime_maintenance.v1"
    assert result["result"] == "scheduler_action_repaired"
    assert result["mutation_count"] == 1
    assert result["non_argument_contract_unchanged"] is True
    assert result["task_contract_exact"] is True
    assert result["raw_values_persisted"] is False
    assert set(result) == {
        "schema", "result", "mutation_count",
        "non_argument_contract_unchanged", "task_contract_exact",
        "raw_values_persisted",
    }


def test_action_repair_unapproved_executable_blocks_before_mutation() -> None:
    completed = run_powershell(
        SYNTHETIC_REPAIR_FIXTURE
        + r"""
function Get-Command {
  param($Name, $ErrorAction)
  return [pscustomobject]@{Source='C:\unapproved\powershell.exe'}
}
try {
  Invoke-ExactSchedulerActionRepair -CanonicalRepoRoot $root
  $blocked = $false
}
catch {
  $blocked = $true
}
[ordered]@{
  blocked=$blocked
  mutation_count=$script:mutationCount
} | ConvertTo-Json -Compress
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert "unapproved" not in completed.stdout.lower()
    assert json.loads(completed.stdout) == {
        "blocked": True,
        "mutation_count": 0,
    }


def test_action_repair_exact_precondition_blocks_without_mutation() -> None:
    completed = run_powershell(
        SYNTHETIC_REPAIR_FIXTURE
        + r"""
$script:repaired = $true
try {
  Invoke-ExactSchedulerActionRepair -CanonicalRepoRoot $root
  $blocked = $false
}
catch {
  $blocked = $true
}
[ordered]@{
  blocked=$blocked
  mutation_count=$script:mutationCount
} | ConvertTo-Json -Compress
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "blocked": True,
        "mutation_count": 0,
    }


def test_action_repair_failed_postcondition_does_not_retry_mutation() -> None:
    completed = run_powershell(
        SYNTHETIC_REPAIR_FIXTURE
        + r"""
function Set-ScheduledTask {
  param($TaskName, $TaskPath, $Action, $ErrorAction)
  $script:mutationCount += 1
  return New-SyntheticTask
}
try {
  Invoke-ExactSchedulerActionRepair -CanonicalRepoRoot $root
  $blocked = $false
}
catch {
  $blocked = $true
}
[ordered]@{
  blocked=$blocked
  mutation_count=$script:mutationCount
} | ConvertTo-Json -Compress
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "blocked": True,
        "mutation_count": 1,
    }


def test_action_repair_noncanonical_file_target_blocks_without_mutation() -> None:
    completed = run_powershell(
        SYNTHETIC_REPAIR_FIXTURE
        + r"""
$driftArguments = $driftArguments.Replace(
  $launcher,
  'C:\different\not-canonical.ps1'
)
try {
  Invoke-ExactSchedulerActionRepair -CanonicalRepoRoot $root
  $blocked = $false
}
catch {
  $blocked = $true
}
[ordered]@{
  blocked=$blocked
  mutation_count=$script:mutationCount
} | ConvertTo-Json -Compress
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert "different" not in completed.stdout.lower()
    assert json.loads(completed.stdout) == {
        "blocked": True,
        "mutation_count": 0,
    }


def test_action_repair_nonempty_action_id_blocks_without_mutation() -> None:
    completed = run_powershell(
        SYNTHETIC_REPAIR_FIXTURE
        + r"""
$script:syntheticActionId = 'non-installer-action-id'
try {
  Invoke-ExactSchedulerActionRepair -CanonicalRepoRoot $root
  $blocked = $false
}
catch {
  $blocked = $true
}
[ordered]@{
  blocked=$blocked
  mutation_count=$script:mutationCount
} | ConvertTo-Json -Compress
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert "non-installer-action-id" not in completed.stdout.lower()
    assert json.loads(completed.stdout) == {
        "blocked": True,
        "mutation_count": 0,
    }


def test_action_repair_incoherent_task_and_xml_blocks_without_mutation() -> None:
    completed = run_powershell(
        SYNTHETIC_REPAIR_FIXTURE
        + r"""
function Export-ScheduledTask {
  param($TaskName, $TaskPath, $ErrorAction)
  $escaped = [Security.SecurityElement]::Escape($exactArguments)
  return (
    '<Task><RegistrationInfo><Date>2026-01-01</Date></RegistrationInfo>' +
    '<Actions><Exec><Command>powershell.exe</Command><Arguments>' +
    $escaped +
    '</Arguments></Exec></Actions></Task>'
  )
}
try {
  Invoke-ExactSchedulerActionRepair -CanonicalRepoRoot $root
  $blocked = $false
}
catch {
  $blocked = $true
}
[ordered]@{
  blocked=$blocked
  mutation_count=$script:mutationCount
} | ConvertTo-Json -Compress
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "blocked": True,
        "mutation_count": 0,
    }


def test_action_repair_final_freshness_drift_blocks_without_mutation() -> None:
    completed = run_powershell(
        SYNTHETIC_REPAIR_FIXTURE
        + r"""
function New-ScheduledTaskAction {
  param($Execute, $Argument, $WorkingDirectory)
  $script:syntheticActionId = 'raced-after-second-read'
  return [pscustomobject]@{
    Execute=$Execute
    Arguments=$Argument
    WorkingDirectory=[string] $WorkingDirectory
  }
}
try {
  Invoke-ExactSchedulerActionRepair -CanonicalRepoRoot $root
  $blocked = $false
}
catch {
  $blocked = $true
}
[ordered]@{
  blocked=$blocked
  mutation_count=$script:mutationCount
} | ConvertTo-Json -Compress
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert "raced-after-second-read" not in completed.stdout.lower()
    assert json.loads(completed.stdout) == {
        "blocked": True,
        "mutation_count": 0,
    }
