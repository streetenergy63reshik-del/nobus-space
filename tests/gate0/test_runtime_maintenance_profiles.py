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


def test_runner_argument_profile_is_exact_and_secret_safe() -> None:
    completed = run_powershell(
        r"""
$definition = [pscustomobject]@{
  PythonPath='C:\runtime\python.exe'
  RunnerPath='C:\runtime\scripts\run_telegram_mvp1.py'
}
$exact = Test-ExactRunnerCommandLine `
  -CommandLine '"C:\runtime\python.exe" "C:\runtime\scripts\run_telegram_mvp1.py" --serve --timeout 30 --announce' `
  -Definition $definition
$extra = Test-ExactRunnerCommandLine `
  -CommandLine '"C:\runtime\python.exe" "C:\runtime\scripts\run_telegram_mvp1.py" --serve --timeout 30 --announce --other' `
  -Definition $definition
$secret = Test-ExactRunnerCommandLine `
  -CommandLine '"C:\runtime\python.exe" "C:\runtime\scripts\run_telegram_mvp1.py" --serve --timeout 30 --announce token=value' `
  -Definition $definition
[ordered]@{ exact=$exact; extra=$extra; secret=$secret } |
  ConvertTo-Json -Compress
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "exact": True,
        "extra": False,
        "secret": False,
    }


def test_duplicate_expected_identity_digest_blocks_termination() -> None:
    completed = run_powershell(
        """
$digest = 'sha256:' + ('1' * 64)
$classification = New-MaintenanceClassification `
  -SchedulerState 'ready' `
  -MutexState 'occupied' `
  -Candidates @([pscustomobject]@{ identity_digest=$digest; verified=$true })
$result = Test-TerminationPreconditions `
  -Classification $classification `
  -ExpectedIdentityDigests @($digest, $digest)
[ordered]@{ result=$result } | ConvertTo-Json -Compress
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"result": False}


def test_cli_surface_has_only_authorized_modes() -> None:
    source = HELPER.read_text(encoding="utf-8")
    assert (
        '[ValidateSet(\n'
        '            "inspect",\n'
        '            "repair-action-verified",\n'
        '            "stop-verified",\n'
        '            "start-verified"\n'
        '        )]'
    ) in source
    assert "Stop-ScheduledTask" not in source
    assert source.count('Start-ScheduledTask -TaskName "NobusSpaceBot"') == 1
    assert "Get-FrozenPreCaptureAuthority" in source
    assert "Test-ExactLauncherContract" in source
    assert "Test-ExactScheduledTaskContract" in source


def test_executable_resolution_and_task_contract_have_distinct_failure_stages() -> None:
    source = HELPER.read_text(encoding="utf-8")
    action_stage = source.index('Set-MaintenanceFailureStage -Stage "action_executable"')
    resolution = source.index("$actionExecutable = (Get-Command")
    task_stage = source.index('Set-MaintenanceFailureStage -Stage "task_contract"')
    contract = source.index("$expectedPrincipal =", task_stage)
    assert '"task_contract",' in source
    assert action_stage < resolution < task_stage < contract
    assert "Get-ExactScheduledTaskContractProfile" in source


def test_exact_whole_launcher_contract_rejects_prefix_suffix_and_other_path() -> None:
    completed = run_powershell(
        r"""
$root = 'C:\canonical'
$path = 'C:\canonical\.runtime\start-nobus-space-bot.ps1'
$exactText = Get-ExpectedLauncherText -CanonicalRoot $root
[ordered]@{
  exact = Test-ExactLauncherContract `
    -LauncherPath $path -LauncherText $exactText -CanonicalRoot $root
  prefix = Test-ExactLauncherContract `
    -LauncherPath $path -LauncherText ("Write-Output unsafe`n" + $exactText) `
    -CanonicalRoot $root
  suffix = Test-ExactLauncherContract `
    -LauncherPath $path -LauncherText ($exactText + "`nWrite-Output unsafe") `
    -CanonicalRoot $root
  other_path = Test-ExactLauncherContract `
    -LauncherPath 'C:\other\launcher.ps1' -LauncherText $exactText `
    -CanonicalRoot $root
} | ConvertTo-Json -Compress
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "exact": True,
        "prefix": False,
        "suffix": False,
        "other_path": False,
    }


def test_start_verified_calls_scheduler_once_after_two_stable_reads() -> None:
    completed = run_powershell(
        r"""
$digest = 'sha256:' + ('1' * 64)
$core = [pscustomobject]@{
  InputTreeDigest=$digest
  FrozenTreeDigest=$digest
  GitStatusDigest=$digest
}
$script:sequence = @()
function Get-FrozenPreCaptureAuthority {
  param($CanonicalRepoRoot,$ExpectedInputTreeDigest,$ExpectedFrozenTreeDigest,$ExpectedGitStatusDigest)
  $script:sequence += 'core'
  return $core
}
$definition = [pscustomobject]@{
  DefinitionDigest=$digest
  LauncherDigest=$digest
  RunnerDigest=$digest
  PythonDigest=$digest
  ActionExecutableDigest=$digest
  ActionIdContractExact=$true
}
$classification = New-MaintenanceClassification `
  -SchedulerState 'ready' -MutexState 'free' -Candidates @()
$live = [pscustomobject]@{
  Definition=$definition
  Candidates=@()
  Classification=$classification
}
$script:liveReads = 0
function Get-LiveMaintenanceState {
  param($CanonicalRepoRoot)
  $script:liveReads++
  $script:sequence += 'live'
  return $live
}
$script:startCalls = 0
function Start-ScheduledTask {
  param($TaskName,$ErrorAction)
  $script:startCalls++
  $script:sequence += 'start'
}
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
[ordered]@{
  live_reads=$script:liveReads
  start_calls=$script:startCalls
  sequence=@($script:sequence)
} | ConvertTo-Json -Compress
"""
    )

    assert completed.returncode == 0, completed.stderr
    lines = [json.loads(line) for line in completed.stdout.splitlines()]
    assert lines[0]["result"] == "scheduler_start_requested"
    assert lines[0]["precondition_reads"] == 2
    assert lines[0]["raw_values_persisted"] is False
    assert lines[1] == {
        "live_reads": 2,
        "start_calls": 1,
        "sequence": ["core", "live", "core", "core", "live", "start"],
    }


def test_start_verified_blocks_definition_drift_without_start() -> None:
    completed = run_powershell(
        r"""
$digest = 'sha256:' + ('1' * 64)
$other = 'sha256:' + ('2' * 64)
function Get-FrozenPreCaptureAuthority {
  param($CanonicalRepoRoot,$ExpectedInputTreeDigest,$ExpectedFrozenTreeDigest,$ExpectedGitStatusDigest)
  return [pscustomobject]@{
    InputTreeDigest=$digest
    FrozenTreeDigest=$digest
    GitStatusDigest=$digest
  }
}
$classification = New-MaintenanceClassification `
  -SchedulerState 'ready' -MutexState 'free' -Candidates @()
$script:liveReads = 0
function Get-LiveMaintenanceState {
  param($CanonicalRepoRoot)
  $script:liveReads++
  $definitionDigest = if ($script:liveReads -eq 1) { $digest } else { $other }
  return [pscustomobject]@{
    Definition=[pscustomobject]@{
      DefinitionDigest=$definitionDigest
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
$script:startCalls = 0
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
  live_reads=$script:liveReads
  start_calls=$script:startCalls
} | ConvertTo-Json -Compress
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "blocked": True,
        "live_reads": 2,
        "start_calls": 0,
    }


def test_start_verified_blocks_expected_authority_mismatch_without_start() -> None:
    completed = run_powershell(
        r"""
$digest = 'sha256:' + ('1' * 64)
$other = 'sha256:' + ('2' * 64)
$script:coreReads = 0
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
  return [pscustomobject]@{
    Definition=$definition
    Candidates=@()
    Classification=$classification
  }
}
$script:startCalls = 0
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
    -ExpectedDefinitionDigest $other `
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
  start_calls=$script:startCalls
} | ConvertTo-Json -Compress
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "blocked": True,
        "core_reads": 3,
        "start_calls": 0,
    }


def test_exact_task_contract_rejects_settings_drift() -> None:
    completed = run_powershell(
        r"""
$launcher = 'C:\canonical\.runtime\start-nobus-space-bot.ps1'
$principal = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$trigger = [pscustomobject]@{
  CimClass=[pscustomobject]@{CimClassName='MSFT_TaskLogonTrigger'}
  UserId=$env:USERNAME
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
$task = [pscustomobject]@{
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
}
$action = [pscustomobject]@{
  Arguments=('-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"' -f $launcher)
  WorkingDirectory=''
}
$executable = Join-Path $PSHOME 'powershell.exe'
$exact = Test-ExactScheduledTaskContract `
  -Task $task -Action $action -LauncherPath $launcher `
  -ActionExecutablePath $executable -ExpectedPrincipal $principal
$task.Principal.UserId = $env:USERNAME
$trigger.UserId = $principal
$action.Arguments = " -nologo   -noprofile -noninteractive -executionpolicy bypass -file '$launcher' "
$normalized = Test-ExactScheduledTaskContract `
  -Task $task -Action $action -LauncherPath $launcher `
  -ActionExecutablePath $executable -ExpectedPrincipal $principal
$settings.RestartCount = 9
$drift = Test-ExactScheduledTaskContract `
  -Task $task -Action $action -LauncherPath $launcher `
  -ActionExecutablePath $executable -ExpectedPrincipal $principal
[ordered]@{exact=$exact;normalized=$normalized;drift=$drift} | ConvertTo-Json -Compress
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "exact": True,
        "normalized": True,
        "drift": False,
    }


def test_exact_task_contract_rejects_every_field_mutation() -> None:
    completed = run_powershell(
        r"""
$launcher = 'C:\canonical\.runtime\start-nobus-space-bot.ps1'
$principal = [Security.Principal.WindowsIdentity]::GetCurrent().Name
function New-ExactFixture {
  $trigger = [pscustomobject]@{
    CimClass=[pscustomobject]@{CimClassName='MSFT_TaskLogonTrigger'}
    UserId=$env:USERNAME
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
  $task = [pscustomobject]@{
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
  }
  return [pscustomobject]@{
    Task=$task
    Action=[pscustomobject]@{
      Arguments=('-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"' -f $launcher)
      WorkingDirectory=''
    }
    Executable=(Join-Path $PSHOME 'powershell.exe')
  }
}
function Test-Fixture($fixture) {
  return Test-ExactScheduledTaskContract `
    -Task $fixture.Task -Action $fixture.Action -LauncherPath $launcher `
    -ActionExecutablePath $fixture.Executable -ExpectedPrincipal $principal
}
$mutations = [ordered]@{
  task_name={param($f) $f.Task.TaskName='Other'}
  task_path={param($f) $f.Task.TaskPath='\Other\'}
  description={param($f) $f.Task.Description='Other'}
  enabled={param($f) $f.Task.Settings.Enabled=$false}
  multiple_instances={param($f) $f.Task.Settings.MultipleInstances='Parallel'}
  start_when_available={param($f) $f.Task.Settings.StartWhenAvailable=$false}
  disallow_battery={param($f) $f.Task.Settings.DisallowStartIfOnBatteries=$true}
  stop_on_battery={param($f) $f.Task.Settings.StopIfGoingOnBatteries=$true}
  restart_count={param($f) $f.Task.Settings.RestartCount=9}
  restart_interval={param($f) $f.Task.Settings.RestartInterval='PT2M'}
  execution_limit={param($f) $f.Task.Settings.ExecutionTimeLimit='PT1H'}
  principal_user={param($f) $f.Task.Principal.UserId='DOMAIN\Other'}
  logon_type={param($f) $f.Task.Principal.LogonType='Password'}
  run_level={param($f) $f.Task.Principal.RunLevel='Highest'}
  trigger_count={param($f) $f.Task.Triggers=@($f.Task.Triggers[0],$f.Task.Triggers[0])}
  trigger_type={param($f) $f.Task.Triggers[0].CimClass.CimClassName='Other'}
  trigger_user={param($f) $f.Task.Triggers[0].UserId='Other'}
  action_arguments={param($f) $f.Action.Arguments='-NoProfile'}
  working_directory={param($f) $f.Action.WorkingDirectory='C:\other'}
  executable={param($f) $f.Executable='C:\other.exe'}
}
$results = [ordered]@{}
$exact = Test-Fixture (New-ExactFixture)
foreach ($entry in $mutations.GetEnumerator()) {
  $fixture = New-ExactFixture
  & $entry.Value $fixture
  $results[$entry.Key] = Test-Fixture $fixture
}
[ordered]@{exact=$exact;mutations=$results} | ConvertTo-Json -Compress -Depth 4
"""
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["exact"] is True
    assert set(result["mutations"]) == {
        "task_name", "task_path", "description", "enabled",
        "multiple_instances", "start_when_available", "disallow_battery",
        "stop_on_battery", "restart_count", "restart_interval",
        "execution_limit", "principal_user", "logon_type", "run_level",
        "trigger_count", "trigger_type", "trigger_user", "action_arguments",
        "working_directory", "executable",
    }
    assert not any(result["mutations"].values())


def test_scheduler_normalization_rejects_different_identity_and_extra_token() -> None:
    completed = run_powershell(
        r"""
$launcher = 'C:\canonical\.runtime\start-nobus-space-bot.ps1'
$principal = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$normalized = " -nologo   -noprofile -noninteractive -executionpolicy bypass -file '$launcher' "
[ordered]@{
  identity_normalized = Test-ExactIdentityContract `
    -ObservedIdentity $env:USERNAME `
    -ExpectedIdentity $principal
  identity_wrong = Test-ExactIdentityContract `
    -ObservedIdentity 'NT AUTHORITY\SYSTEM' `
    -ExpectedIdentity $principal
  identity_unresolved_same = Test-ExactIdentityContract `
    -ObservedIdentity 'NOBUS_GATE0_UNRESOLVED\__NO_SUCH_PRINCIPAL__' `
    -ExpectedIdentity 'NOBUS_GATE0_UNRESOLVED\__NO_SUCH_PRINCIPAL__'
  arguments_normalized = Test-ExactScheduledActionArgumentsContract `
    -Arguments $normalized `
    -LauncherPath $launcher
  arguments_extra = Test-ExactScheduledActionArgumentsContract `
    -Arguments ($normalized + ' -Extra') `
    -LauncherPath $launcher
  arguments_missing = Test-ExactScheduledActionArgumentsContract `
    -Arguments ($normalized -replace ' -noninteractive', '') `
    -LauncherPath $launcher
  arguments_changed = Test-ExactScheduledActionArgumentsContract `
    -Arguments ($normalized -replace 'bypass', 'RemoteSigned') `
    -LauncherPath $launcher
  arguments_triple_quote = Test-ExactScheduledActionArgumentsContract `
    -Arguments (
      " -nologo -noprofile -noninteractive -executionpolicy bypass -file '''$launcher''' "
    ) `
    -LauncherPath $launcher
  arguments_control_newline = Test-ExactScheduledActionArgumentsContract `
    -Arguments (
      $normalized -replace ' -file', "`n-file"
    ) `
    -LauncherPath $launcher
  arguments_semicolon = Test-ExactScheduledActionArgumentsContract `
    -Arguments ($normalized + ' ; Write-Output blocked') `
    -LauncherPath $launcher
  arguments_pipeline = Test-ExactScheduledActionArgumentsContract `
    -Arguments ($normalized + ' | Write-Output') `
    -LauncherPath $launcher
  arguments_redirection = Test-ExactScheduledActionArgumentsContract `
    -Arguments ($normalized + ' > blocked.txt') `
    -LauncherPath $launcher
} | ConvertTo-Json -Compress
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "identity_normalized": True,
        "identity_wrong": False,
        "identity_unresolved_same": False,
        "arguments_normalized": True,
        "arguments_extra": False,
        "arguments_missing": False,
        "arguments_changed": False,
        "arguments_triple_quote": False,
        "arguments_control_newline": False,
        "arguments_semicolon": False,
        "arguments_pipeline": False,
        "arguments_redirection": False,
    }


def test_action_contract_structural_profile_is_fixed_and_fail_closed() -> None:
    completed = run_powershell(
        r"""
$launcher = 'C:\canonical\.runtime\start-nobus-space-bot.ps1'
$exact = Get-ExactScheduledActionArgumentsContractProfile `
  -Arguments (
    " -nologo -noprofile -noninteractive -executionpolicy bypass -file '$launcher' "
  ) `
  -LauncherPath $launcher
$newline = Get-ExactScheduledActionArgumentsContractProfile `
  -Arguments (
    " -nologo -noprofile -noninteractive -executionpolicy bypass`n-file '$launcher' "
  ) `
  -LauncherPath $launcher
$secret = Get-ExactScheduledActionArgumentsContractProfile `
  -Arguments '-NoLogo token=must-not-escape' `
  -LauncherPath $launcher
[ordered]@{exact=$exact;newline=$newline;secret=$secret} |
  ConvertTo-Json -Compress -Depth 4
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert "token=must-not-escape" not in completed.stdout.lower()
    result = json.loads(completed.stdout)
    fields = {
        "nonempty", "secret_shape_absent", "control_chars_absent", "parse_ok",
        "statement_count_one", "statement_is_pipeline",
        "pipeline_element_count_one", "element_is_command",
        "redirection_count_zero", "command_element_count_eight",
        "token_count_eight", "shell_token", "nologo_token", "noprofile_token",
        "noninteractive_token", "execution_policy_token", "bypass_token",
        "file_token", "launcher_quote_shape", "launcher_path_exact",
    }
    assert set(result["exact"]) == fields
    assert all(result["exact"].values())
    assert result["newline"]["nonempty"] is True
    assert result["newline"]["secret_shape_absent"] is True
    assert result["newline"]["control_chars_absent"] is False
    assert not any(
        value
        for key, value in result["newline"].items()
        if key not in {"nonempty", "secret_shape_absent"}
    )
    assert result["secret"]["nonempty"] is True
    assert result["secret"]["secret_shape_absent"] is False
    assert not any(
        value for key, value in result["secret"].items() if key != "nonempty"
    )
