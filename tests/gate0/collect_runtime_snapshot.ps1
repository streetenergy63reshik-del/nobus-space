param(
    [Parameter(Mandatory = $true)]
    [string] $RepoRoot,
    [Parameter(Mandatory = $true)]
    [string] $LiveRoot,
    [Parameter(Mandatory = $true)]
    [int] $CollectorPid
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$scriptRepoRootFull = [System.IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\..")
).TrimEnd("\")
$scriptCodeRoot = [System.IO.Directory]::GetParent($scriptRepoRootFull)
$expectedLiveRootFull = [System.IO.Path]::GetFullPath(
    (Join-Path $scriptCodeRoot.FullName "worktrees\telegram-live")
).TrimEnd("\")

try {
    $repoRootFull = [System.IO.Path]::GetFullPath($RepoRoot).TrimEnd("\")
    $liveRootFull = [System.IO.Path]::GetFullPath($LiveRoot).TrimEnd("\")
}
catch {
    [Console]::Error.WriteLine(
        '{"schema":"nobus.gate0.runtime_inventory.v1","result":"blocked","error_stage":"canonical_repo_authority"}'
    )
    exit 1
}

if (
    -not $repoRootFull.Equals(
        $scriptRepoRootFull,
        [System.StringComparison]::OrdinalIgnoreCase
    ) -or
    -not $expectedLiveRootFull.Equals(
        $liveRootFull,
        [System.StringComparison]::OrdinalIgnoreCase
    )
) {
    [Console]::Error.WriteLine(
        '{"schema":"nobus.gate0.runtime_inventory.v1","result":"blocked","error_stage":"canonical_repo_authority"}'
    )
    exit 1
}

$repoRootFull = $scriptRepoRootFull
$liveRootFull = $expectedLiveRootFull
$maintenanceHelper = Join-Path (
    $repoRootFull
) "tests\gate0\manage_runtime_maintenance.ps1"
. $maintenanceHelper
$firstRuntimeAuthority = Get-RegisteredRuntimeDefinition -CanonicalRepoRoot $repoRootFull
$captureStartedAt = (Get-Date).ToUniversalTime()

function Get-SafeDigest([object] $Projection) {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes(
        ($Projection | ConvertTo-Json -Compress -Depth 10)
    )
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        return "sha256:" + [System.BitConverter]::ToString(
            $hasher.ComputeHash($bytes)
        ).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $hasher.Dispose()
    }
}

function Get-RootProfile([string] $Path) {
    $full = [System.IO.Path]::GetFullPath($Path).TrimEnd("\")
    if ($full.Equals($repoRootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        return "canonical-repo"
    }
    if ($full.Equals($liveRootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        return "telegram-live-worktree"
    }
    return "unapproved-root"
}

$task = Get-ScheduledTask -TaskName "NobusSpaceBot" -ErrorAction Stop
$taskInfo = Get-ScheduledTaskInfo -TaskName "NobusSpaceBot" -ErrorAction Stop
$action = @($task.Actions)[0]
$rawSchedulerArguments = [string] $action.Arguments
$secretPattern = "(?i)(token|password|passwd|secret|cookie|oauth|authorization|bearer|api[_-]?key)\s*[:=]"
$schedulerSecretShaped = [regex]::IsMatch($rawSchedulerArguments, $secretPattern)
$tokens = $null
$parseErrors = $null
$null = [System.Management.Automation.Language.Parser]::ParseInput(
    ("powershell.exe " + $rawSchedulerArguments),
    [ref] $tokens,
    [ref] $parseErrors
)
$fileTokenIndex = -1
for ($index = 0; $index -lt $tokens.Count; $index++) {
    if ($tokens[$index].Text -ieq "-File") {
        $fileTokenIndex = $index
        break
    }
}
$launcherPath = $null
if ($fileTokenIndex -ge 0 -and $fileTokenIndex + 1 -lt $tokens.Count) {
    $launcherToken = ([string] $tokens[$fileTokenIndex + 1].Text).Trim('"', "'")
    $launcherPath = [System.IO.Path]::GetFullPath($launcherToken)
}
$launcherExists = $launcherPath -and [System.IO.File]::Exists($launcherPath)
$launcherText = if ($launcherExists) {
    [System.IO.File]::ReadAllText($launcherPath, [System.Text.Encoding]::UTF8)
}
else {
    ""
}
$launcherSecretShaped = [regex]::IsMatch($launcherText, $secretPattern)
$invoke = [regex]::Match(
    $launcherText,
    "(?m)^\s*&\s+'(?<python>[^']+)'\s+'(?<runner>[^']+)'(?<tail>[^\r\n]*)$"
)
$pythonPath = if ($invoke.Success) {
    [System.IO.Path]::GetFullPath($invoke.Groups["python"].Value)
}
else {
    $null
}
$runnerPath = if ($invoke.Success) {
    [System.IO.Path]::GetFullPath($invoke.Groups["runner"].Value)
}
else {
    $null
}
$runnerRoot = if ($runnerPath) {
    [System.IO.Directory]::GetParent(
        [System.IO.Directory]::GetParent($runnerPath).FullName
    ).FullName
}
else {
    $null
}
$rootProfile = if ($runnerRoot) { Get-RootProfile $runnerRoot } else { "unresolved" }
$tail = if ($invoke.Success) { $invoke.Groups["tail"].Value } else { "" }
$argumentProjection = [ordered]@{
    shell_flags = @("NoLogo", "NoProfile", "NonInteractive", "ExecutionPolicyBypass", "File")
    launcher_ref = "runtime-launcher:telegram-runner"
    launcher_root_profile = if ($launcherPath) {
        Get-RootProfile ([System.IO.Directory]::GetParent(
            [System.IO.Directory]::GetParent($launcherPath).FullName
        ).FullName)
    }
    else {
        "unresolved"
    }
    runner_ref = "script:run-telegram-mvp1"
    runner_root_profile = $rootProfile
    serve = $tail -match "(?i)(?:^|\s)--serve(?:\s|$)"
    timeout_30 = $tail -match "(?i)(?:^|\s)--timeout\s+30(?:\s|$)"
    announce = $tail -match "(?i)(?:^|\s)--announce(?:\s|$)"
    redirects_log = $tail -match "\*>>"
}
$actionValid = @($parseErrors).Count -eq 0 -and $launcherExists -and
    $invoke.Success -and $rootProfile -eq "canonical-repo" -and
    $argumentProjection.serve -and $argumentProjection.timeout_30 -and
    $argumentProjection.announce -and -not $schedulerSecretShaped -and
    -not $launcherSecretShaped -and
    [string] $firstRuntimeAuthority.TaskContractProfile -ceq
        "exact_installer_v1"
$scheduledCommit = if ($runnerRoot -and $rootProfile -ne "unapproved-root") {
    (& git -C $runnerRoot rev-parse HEAD).Trim()
}
else {
    $null
}
$runnerCodeDigest = if ($runnerPath -and [System.IO.File]::Exists($runnerPath)) {
    "sha256:" + (Get-FileHash -Algorithm SHA256 -LiteralPath $runnerPath).Hash.ToLowerInvariant()
}
else {
    $null
}
$pythonDigest = if ($pythonPath -and [System.IO.File]::Exists($pythonPath)) {
    "sha256:" + (Get-FileHash -Algorithm SHA256 -LiteralPath $pythonPath).Hash.ToLowerInvariant()
}
else {
    Get-SafeDigest ([ordered]@{ executable = "unresolved" })
}
$actionExecutable = (Get-Command ([string] $action.Execute) -ErrorAction Stop).Source
$actionExecutableDigest = "sha256:" + (
    Get-FileHash -Algorithm SHA256 -LiteralPath $actionExecutable
).Hash.ToLowerInvariant()
$launcherDigest = "sha256:" + (
    Get-FileHash -Algorithm SHA256 -LiteralPath $launcherPath
).Hash.ToLowerInvariant()
if (
    [string] $firstRuntimeAuthority.LauncherDigest -cne $launcherDigest -or
    [string] $firstRuntimeAuthority.RunnerDigest -cne $runnerCodeDigest -or
    [string] $firstRuntimeAuthority.PythonDigest -cne $pythonDigest -or
    [string] $firstRuntimeAuthority.ActionExecutableDigest -cne
        $actionExecutableDigest
) {
    throw "Runtime authority does not match collector artifacts."
}
$actionArgumentsDigest = Get-SafeDigest $argumentProjection

function Get-PrefilteredCandidates {
    if (-not $pythonPath) {
        return @()
    }
    return @(
        Get-CimInstance -Query (
            "SELECT ProcessId,ParentProcessId,Name,ExecutablePath,CreationDate FROM Win32_Process " +
            "WHERE Name='python.exe'"
        ) | Where-Object {
            $_.ProcessId -ne $CollectorPid -and $_.ExecutablePath -and
            [System.IO.Path]::GetFullPath([string] $_.ExecutablePath).Equals(
                $pythonPath,
                [System.StringComparison]::OrdinalIgnoreCase
            )
        }
    )
}

$safeCandidates = @()
$candidateWaitStartedAt = Get-Date
do {
    $safeCandidates = @(Get-PrefilteredCandidates)
    if (
        $safeCandidates.Count -gt 0 -or
        ((Get-Date) - $candidateWaitStartedAt).TotalSeconds -ge 45
    ) {
        break
    }
    Start-Sleep -Milliseconds 500
} while ($true)
$candidateWaitMilliseconds = [int] (
    (Get-Date) - $candidateWaitStartedAt
).TotalMilliseconds
$instances = @()
foreach ($candidate in $safeCandidates) {
    $withCommand = Get-CimInstance -Query (
        "SELECT ProcessId,ParentProcessId,CommandLine,CreationDate FROM Win32_Process WHERE ProcessId=" +
        [int] $candidate.ProcessId
    )
    if (
        -not $withCommand -or
        [int] $withCommand.ProcessId -ne [int] $candidate.ProcessId -or
        [datetime] $withCommand.CreationDate -ne [datetime] $candidate.CreationDate
    ) {
        throw "Runner candidate identity changed during sanitized capture."
    }
    $rawCommandLine = [string] $withCommand.CommandLine
    $profile = New-RunnerCandidateProfile `
        -CommandLine $rawCommandLine `
        -ExecutablePath $pythonPath `
        -ExecutableDigest $pythonDigest `
        -Definition $firstRuntimeAuthority
    if (
        -not [bool] $profile.secret_shape_absent -and
        [bool] $profile.exact_runner_script_match
    ) {
        throw "Secret-shaped runner candidate is not eligible for capture."
    }
    if ([bool] $profile.verified) {
        $instances += [ordered]@{
            pid = [int] $withCommand.ProcessId
            parent_pid = [int] $withCommand.ParentProcessId
            started_at = ([datetime] $withCommand.CreationDate).ToUniversalTime().ToString("o")
            executable_digest = $pythonDigest
            argv_profile = "scheduler_bound_runner"
            argv_digest = Get-SafeDigest ([ordered]@{
                runner_ref = "script:run-telegram-mvp1"
                argument_profile = $argumentProjection
            })
            loaded_commit = $scheduledCommit
            loaded_code_digest = $runnerCodeDigest
            secret_shaped_fragment_detected = $false
        }
    }
}
$runnerCount = $instances.Count
$runnerStatus = if ($runnerCount -eq 1) {
    "verified"
}
elseif ($runnerCount -eq 0) {
    "not_observed"
}
else {
    "contradictory"
}
$runtimeStatus = if ($runnerCount -eq 1) { "verified" } else { "offline" }

$bindingEligible = $actionValid -and $runnerRoot -and $rootProfile -eq "canonical-repo"
if (-not $bindingEligible) {
    throw "Sanitized Scheduler-to-runtime binding is unverifiable."
}
$collectorPython = Join-Path $repoRootFull ".venv\Scripts\python.exe"
$databaseHelper = Join-Path $repoRootFull "tests\gate0\collect_gate0_snapshot.py"
if (
    -not [System.IO.File]::Exists($collectorPython) -or
    -not [System.IO.File]::Exists($databaseHelper)
) {
    throw "Approved database collector is unavailable."
}
$databaseJson = & $collectorPython -B $databaseHelper databases `
    --runtime-root (Join-Path $runnerRoot ".runtime") 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Read-only database collector failed."
}
$databaseSnapshot = ConvertFrom-Json -InputObject (
    $databaseJson -join [System.Environment]::NewLine
)
$databaseRoles = @(
    $databaseSnapshot.databases | ForEach-Object { [string] $_.database_role }
)
if (
    $databaseRoles.Count -ne 4 -or
    (@($databaseRoles | Sort-Object) -join ",") -ne
        "business_notes,checkpoint,core,telegram_state"
) {
    throw "Authoritative database inventory is incomplete or ambiguous."
}
foreach ($database in @($databaseSnapshot.databases)) {
    $database.runtime_binding_status = "verified"
    $database.source_profile = "scheduler_bound_registered_runtime_directory"
    $database.runtime_binding_reason =
        "SCHEDULER_RUNNER_ROOT_BOUND_IN_SINGLE_CAPTURE"
}
$captureObservedAt = (Get-Date).ToUniversalTime()
$captureFreshUntil = $captureObservedAt.AddMinutes(5)

$lastRunAt = if ($taskInfo.LastRunTime.Year -gt 2000) {
    $taskInfo.LastRunTime.ToUniversalTime().ToString("o")
}
else {
    $null
}
$nextRunAt = if ($taskInfo.NextRunTime.Year -gt 2000) {
    $taskInfo.NextRunTime.ToUniversalTime().ToString("o")
}
else {
    $null
}
$clockService = Get-Service -Name "W32Time" -ErrorAction SilentlyContinue
$clockTrusted = $null -ne $clockService -and $clockService.Status -eq "Running"
$secondRuntimeAuthority = Get-RegisteredRuntimeDefinition -CanonicalRepoRoot $repoRootFull
if (
    [string] $firstRuntimeAuthority.DefinitionDigest -cne
        [string] $secondRuntimeAuthority.DefinitionDigest -or
    [string] $firstRuntimeAuthority.LauncherDigest -cne
        [string] $secondRuntimeAuthority.LauncherDigest -or
    [string] $firstRuntimeAuthority.RunnerDigest -cne
        [string] $secondRuntimeAuthority.RunnerDigest -or
    [string] $firstRuntimeAuthority.PythonDigest -cne
        [string] $secondRuntimeAuthority.PythonDigest -or
    [string] $firstRuntimeAuthority.ActionExecutableDigest -cne
        [string] $secondRuntimeAuthority.ActionExecutableDigest -or
    [string] $firstRuntimeAuthority.TaskContractProfile -cne
        "exact_installer_v1" -or
    [string] $secondRuntimeAuthority.TaskContractProfile -cne
        "exact_installer_v1"
) {
    throw "Runtime authority drifted during capture."
}
$definitionDigest = [string] $secondRuntimeAuthority.DefinitionDigest

$result = [ordered]@{
    schema = "nobus.gate0.runtime_inventory.v1"
    capture_started_at = $captureStartedAt.ToString("o")
    observed_at = $captureObservedAt.ToString("o")
    fresh_until = $captureFreshUntil.ToString("o")
    host_ref = "windows-owner-pc"
    clock = [ordered]@{
        trusted = $clockTrusted
        source = "windows_system_clock"
        w32time_status = if ($null -eq $clockService) {
            "not_observed"
        }
        else {
            ([string] $clockService.Status).ToLowerInvariant()
        }
    }
    collector_constraints = [ordered]@{
        authority_ref = "owner-authority:gate0-evidence-closure-2026-07-29"
        access_profile = "one_time_transient_prefiltered"
        raw_command_lines_read = $safeCandidates.Count -gt 0
        process_command_lines_read_for_prefiltered_candidates = $safeCandidates.Count -gt 0
        candidate_wait_milliseconds = $candidateWaitMilliseconds
        scheduler_arguments_read = $true
        environment_values_read = $false
        secret_values_detected = $schedulerSecretShaped -or $launcherSecretShaped -or
            @($instances | Where-Object { $_.secret_shaped_fragment_detected }).Count -gt 0
        raw_values_persisted = $false
        process_match_basis = "scheduler_python_plus_exact_runner_path"
        scheduler_arguments_persisted = $false
        scheduler_definition_projection = "authorized_sanitized_arguments_projection"
    }
    processes = @(
        [ordered]@{
            process_role = "telegram_runner"
            status = $runnerStatus
            observed_count = $runnerCount
            instances = $instances
            loaded_commit = if ($runnerCount -eq 1) { $instances[0].loaded_commit } else { $null }
            scheduled_commit = $scheduledCommit
            root_profile = $rootProfile
            reason_code = if ($runnerCount -eq 1) {
                "EXACT_SCHEDULER_BOUND_RUNNER_OBSERVED"
            }
            elseif ($runnerCount -eq 0) {
                "EXPECTED_SCHEDULER_BOUND_RUNNER_NOT_OBSERVED"
            }
            else {
                "MULTIPLE_SCHEDULER_BOUND_RUNNERS_OBSERVED"
            }
        },
        [ordered]@{
            process_role = "codex_app_server"
            status = "not_configured"
            observed_count = 0
            loaded_commit = $null
            reason_code = "OWNER_VERIFIED_SERVER_NOT_DEPLOYED"
        },
        [ordered]@{
            process_role = "bridge"
            status = "not_configured"
            observed_count = 0
            loaded_commit = $null
            reason_code = "GATE5_TARGET_NOT_IMPLEMENTED"
        }
    )
    scheduler = [ordered]@{
        task_ref = "scheduler-task:nobus-space-bot"
        enabled = [bool] $task.Settings.Enabled
        state = [string] $secondRuntimeAuthority.SchedulerState
        last_run_at = $lastRunAt
        last_result_code = [long] $taskInfo.LastTaskResult
        next_run_at = $nextRunAt
        action_executable_profile = [System.IO.Path]::GetFileName([string] $action.Execute)
        action_executable_digest = $actionExecutableDigest
        action_arguments_digest = $actionArgumentsDigest
        action_arguments_status = if ($actionValid) { "verified_sanitized" } else { "unverifiable" }
        definition_digest = $definitionDigest
        arguments_present = -not [string]::IsNullOrWhiteSpace($rawSchedulerArguments)
        arguments_persisted = $false
        working_directory_present = -not [string]::IsNullOrWhiteSpace([string] $action.WorkingDirectory)
        logon_type = [string] $task.Principal.LogonType
        run_level = [string] $task.Principal.RunLevel
        trigger_count = @($task.Triggers).Count
        root_profile = $rootProfile
        scheduled_commit = $scheduledCommit
        status = if ($actionValid) { "verified" } else { "unverifiable" }
    }
    database_binding = [ordered]@{
        status = if ($bindingEligible) { "verified" } else { "unverifiable" }
        source_contract = "scheduler-runner-root/.runtime/four-pinned-sqlite-files"
        root_profile = $rootProfile
        scheduled_commit = $scheduledCommit
    }
    database_snapshot = $databaseSnapshot
    server = [ordered]@{
        status = "not_applicable_verified"
        authority_ref = "owner-decision:gate0-l4-server-not-deployed"
    }
    runtime_claim = [ordered]@{
        status = $runtimeStatus
        reason_code = if ($runnerCount -eq 1) {
            "SCHEDULER_BOUND_RUNNER_OBSERVED"
        }
        else {
            "EXPECTED_SCHEDULER_BOUND_RUNNER_NOT_OBSERVED"
        }
        process_loaded_commit = if ($runnerCount -eq 1) { $instances[0].loaded_commit } else { $null }
        scheduled_commit = $scheduledCommit
    }
}

$result | ConvertTo-Json -Depth 12 -Compress