param(
    [string] $Mode,
    [string] $RepoRoot,
    [string] $ExpectedInputTreeDigest,
    [string] $ExpectedFrozenTreeDigest,
    [string] $ExpectedGitStatusDigest,
    [string] $ExpectedDefinitionDigest,
    [string] $ExpectedLauncherDigest,
    [string] $ExpectedRunnerDigest,
    [string] $ExpectedPythonDigest,
    [string] $ExpectedActionExecutableDigest,
    [string[]] $ExpectedIdentityDigest = @(),
    [switch] $AllowLegacyExecutableRemediation
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$script:MaintenanceCanonicalRepoRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..\..")
).TrimEnd("\")

$script:MaintenanceSchema = "nobus.gate0.runtime_maintenance.v1"
$script:DigestPattern = "^sha256:[0-9a-f]{64}$"
$script:SecretPattern =
    "(?i)(token|password|passwd|secret|cookie|oauth|authorization|bearer|api[_-]?key)\s*[:=]"
$script:TaskContractProfileFields = @(
    "task_name",
    "task_path",
    "description",
    "enabled",
    "multiple_instances",
    "start_when_available",
    "disallow_battery",
    "stop_on_battery",
    "restart_count",
    "restart_interval",
    "execution_limit",
    "principal_user",
    "logon_type",
    "run_level",
    "trigger_count",
    "trigger_type",
    "trigger_user",
    "action_arguments",
    "working_directory",
    "executable"
)
$script:MaintenanceTaskContractProfile = $null
$script:ActionContractProfileFields = @(
    "nonempty",
    "secret_shape_absent",
    "control_chars_absent",
    "parse_ok",
    "statement_count_one",
    "statement_is_pipeline",
    "pipeline_element_count_one",
    "element_is_command",
    "redirection_count_zero",
    "command_element_count_eight",
    "token_count_eight",
    "shell_token",
    "nologo_token",
    "noprofile_token",
    "noninteractive_token",
    "execution_policy_token",
    "bypass_token",
    "file_token",
    "launcher_quote_shape",
    "launcher_path_exact"
)
$script:MaintenanceActionContractProfile = $null

$script:MaintenanceFailureStages = @(
    "entry",
    "canonical_repo_authority",
    "scheduler_task",
    "scheduler_action",
    "scheduler_arguments",
    "launcher",
    "runner_invocation",
    "runtime_files",
    "runner_root",
    "runner_root_other_worktree",
    "runner_root_other_code",
    "runner_root_unauthorized",
    "runner_script",
    "argument_profile",
    "action_executable",
    "task_contract",
    "registered_digests",
    "pyvenv_base",
    "pre_capture_readback",
    "start_preconditions",
    "scheduler_start",
    "runner_candidates",
    "production_mutex",
    "classification",
    "remediation_preconditions",
    "action_repair_preconditions",
    "action_repair_mutation",
    "action_repair_postcondition",
    "termination_plan",
    "termination_handles",
    "postcondition",
    "unknown"
)
$script:MaintenanceFailureStage = "entry"

function Set-MaintenanceFailureStage {
    param([Parameter(Mandatory = $true)][string] $Stage)

    if ($Stage -in $script:MaintenanceFailureStages) {
        $script:MaintenanceFailureStage = $Stage
    }
    else {
        $script:MaintenanceFailureStage = "unknown"
    }
}

function Write-SanitizedMaintenanceFailure {
    $stage = if (
        [string] $script:MaintenanceFailureStage -in
        $script:MaintenanceFailureStages
    ) {
        [string] $script:MaintenanceFailureStage
    }
    else {
        "unknown"
    }
    $output = [ordered]@{
        schema = $script:MaintenanceSchema
        result = "blocked"
        error_stage = $stage
    }
    if (
        $stage -ceq "task_contract" -and
        $null -ne $script:MaintenanceTaskContractProfile
    ) {
        $profile = [ordered]@{}
        foreach ($field in $script:TaskContractProfileFields) {
            if (-not $script:MaintenanceTaskContractProfile.Contains($field)) {
                $profile = $null
                break
            }
            $profile[$field] = [bool] $script:MaintenanceTaskContractProfile[$field]
        }
        if ($null -ne $profile) {
            $output.task_contract_profile = $profile
        }
    }
    if (
        $stage -ceq "task_contract" -and
        $null -ne $script:MaintenanceTaskContractProfile -and
        $script:MaintenanceTaskContractProfile.Contains("action_arguments") -and
        -not [bool] $script:MaintenanceTaskContractProfile["action_arguments"] -and
        $null -ne $script:MaintenanceActionContractProfile
    ) {
        $actionProfile = [ordered]@{}
        foreach ($field in $script:ActionContractProfileFields) {
            if (-not $script:MaintenanceActionContractProfile.Contains($field)) {
                $actionProfile = $null
                break
            }
            $actionProfile[$field] = [bool] (
                $script:MaintenanceActionContractProfile[$field]
            )
        }
        if ($null -ne $actionProfile) {
            $output.action_contract_profile = $actionProfile
        }
    }
    $output | ConvertTo-Json -Compress
}

function Get-MaintenanceDigest {
    param([Parameter(Mandatory = $true)][object] $Projection)

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

function Get-MaintenanceFileDigest {
    param([Parameter(Mandatory = $true)][string] $LiteralPath)

    $path = [System.IO.Path]::GetFullPath($LiteralPath)
    if (-not [System.IO.File]::Exists($path)) {
        throw "Maintenance digest input is unavailable."
    }
    $stream = [System.IO.File]::OpenRead($path)
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        return "sha256:" + [System.BitConverter]::ToString(
            $hasher.ComputeHash($stream)
        ).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $hasher.Dispose()
        $stream.Dispose()
    }
}

function Get-VenvBasePythonDefinition {
    param([Parameter(Mandatory = $true)][string] $VenvPythonPath)

    $venvPython = [System.IO.Path]::GetFullPath($VenvPythonPath)
    $scriptsDirectory = [System.IO.Directory]::GetParent($venvPython)
    if (
        -not [System.IO.File]::Exists($venvPython) -or
        $null -eq $scriptsDirectory -or
        [System.IO.Path]::GetFileName($venvPython) -ine "python.exe" -or
        $scriptsDirectory.Name -ine "Scripts"
    ) {
        throw "Registered venv Python layout is invalid."
    }
    $venvRoot = $scriptsDirectory.Parent
    if ($null -eq $venvRoot) {
        throw "Registered venv root is unresolved."
    }
    $configurationPath = Join-Path $venvRoot.FullName "pyvenv.cfg"
    if (-not [System.IO.File]::Exists($configurationPath)) {
        throw "Registered pyvenv configuration is unavailable."
    }
    $executableEntries = @(
        [System.IO.File]::ReadAllLines(
            $configurationPath,
            [System.Text.Encoding]::UTF8
        ) | ForEach-Object {
            $match = [regex]::Match(
                [string] $_,
                "^\s*executable\s*=\s*(?<path>.+?)\s*$",
                [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
            )
            if ($match.Success) {
                $match.Groups["path"].Value.Trim().Trim('"', "'")
            }
        }
    )
    if ($executableEntries.Count -ne 1) {
        throw "Registered pyvenv base executable is ambiguous."
    }
    $basePython = [System.IO.Path]::GetFullPath($executableEntries[0])
    if (
        -not [System.IO.File]::Exists($basePython) -or
        [System.IO.Path]::GetFileName($basePython) -ine "python.exe" -or
        $basePython.Equals(
            $venvPython,
            [System.StringComparison]::OrdinalIgnoreCase
        )
    ) {
        throw "Registered pyvenv base executable is invalid."
    }
    return [pscustomobject]@{
        Path = $basePython
        Digest = Get-MaintenanceFileDigest -LiteralPath $basePython
    }
}

function Test-MaintenanceCanonicalRepoAuthority {
    param(
        [Parameter(Mandatory = $true)][string] $CanonicalRepoRoot
    )

    try {
        $supplied = [System.IO.Path]::GetFullPath(
            $CanonicalRepoRoot
        ).TrimEnd("\")
        return (
            [System.IO.Directory]::Exists(
                $script:MaintenanceCanonicalRepoRoot
            ) -and
            $script:MaintenanceCanonicalRepoRoot.Equals(
                $supplied,
                [System.StringComparison]::OrdinalIgnoreCase
            )
        )
    }
    catch {
        return $false
    }
}

function Test-RegisteredRuntimeRoot {
    param(
        [Parameter(Mandatory = $true)][string] $CanonicalRepoRoot,
        [Parameter(Mandatory = $true)][string] $RunnerRoot
    )

    try {
        if (-not (
            Test-MaintenanceCanonicalRepoAuthority `
                -CanonicalRepoRoot $CanonicalRepoRoot
        )) {
            return $false
        }
        $observed = [System.IO.Path]::GetFullPath($RunnerRoot).TrimEnd("\")
        return $script:MaintenanceCanonicalRepoRoot.Equals(
            $observed,
            [System.StringComparison]::OrdinalIgnoreCase
        )
    }
    catch {
        return $false
    }
}

function Get-RegisteredRuntimeRootFailureStage {
    param(
        [Parameter(Mandatory = $true)][string] $CanonicalRepoRoot,
        [Parameter(Mandatory = $true)][string] $RunnerRoot
    )

    try {
        $canonical = [System.IO.Path]::GetFullPath(
            $CanonicalRepoRoot
        ).TrimEnd("\")
        $codeRoot = [System.IO.Directory]::GetParent($canonical)
        if ($null -eq $codeRoot) {
            return "runner_root_unauthorized"
        }
        $observed = [System.IO.Path]::GetFullPath($RunnerRoot).TrimEnd("\")
        $worktreesRoot = [System.IO.Path]::GetFullPath(
            (Join-Path $codeRoot.FullName "worktrees")
        ).TrimEnd("\")
        if ($observed.StartsWith(
            ($worktreesRoot + "\"),
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            return "runner_root_other_worktree"
        }
        $codeRootPath = [System.IO.Path]::GetFullPath(
            $codeRoot.FullName
        ).TrimEnd("\")
        if ($observed.StartsWith(
            ($codeRootPath + "\"),
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            return "runner_root_other_code"
        }
        return "runner_root_unauthorized"
    }
    catch {
        return "runner_root_unauthorized"
    }
}

function New-MaintenanceClassification {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("ready", "running", "disabled", "unknown")]
        [string] $SchedulerState,
        [Parameter(Mandatory = $true)]
        [ValidateSet("occupied", "free", "unknown")]
        [string] $MutexState,
        [object[]] $Candidates = @()
    )

    $candidateArray = @($Candidates)
    $digests = @()
    $verifiedCount = 0
    foreach ($candidate in $candidateArray) {
        $digest = [string] $candidate.identity_digest
        if ($digest -notmatch $script:DigestPattern) {
            throw "Candidate identity digest is invalid."
        }
        $digests += $digest
        if ([bool] $candidate.verified) {
            $verifiedCount++
        }
    }
    $digests = @($digests | Sort-Object)
    $unverifiedCount = $candidateArray.Count - $verifiedCount
    $verdict = "blocked"
    if (
        $SchedulerState -eq "ready" -and
        $candidateArray.Count -ge 1 -and
        $unverifiedCount -eq 0 -and
        $MutexState -eq "occupied"
    ) {
        $verdict = "verified_set_ready"
    }
    elseif (
        $SchedulerState -eq "ready" -and
        $candidateArray.Count -eq 0 -and
        $MutexState -eq "free"
    ) {
        $verdict = "no_candidates_mutex_free"
    }

    return [ordered]@{
        schema = $script:MaintenanceSchema
        scheduler_state = $SchedulerState
        candidate_count = $candidateArray.Count
        verified_count = $verifiedCount
        unverified_count = $unverifiedCount
        identity_digests = $digests
        mutex_state = $MutexState
        classification_verdict = $verdict
    }
}

function Test-MaintenancePostcondition {
    param([Parameter(Mandatory = $true)][object] $Classification)

    return (
        [string] $Classification.schema -eq $script:MaintenanceSchema -and
        [string] $Classification.scheduler_state -eq "ready" -and
        [int] $Classification.candidate_count -eq 0 -and
        [int] $Classification.verified_count -eq 0 -and
        [int] $Classification.unverified_count -eq 0 -and
        @($Classification.identity_digests).Count -eq 0 -and
        [string] $Classification.mutex_state -eq "free"
    )
}

function Test-TerminationPreconditions {
    param(
        [Parameter(Mandatory = $true)][object] $Classification,
        [string[]] $ExpectedIdentityDigests = @()
    )

    $expected = @($ExpectedIdentityDigests)
    $observed = @($Classification.identity_digests)
    if (
        [string] $Classification.schema -ne $script:MaintenanceSchema -or
        [string] $Classification.classification_verdict -ne "verified_set_ready" -or
        [int] $Classification.candidate_count -lt 1 -or
        [int] $Classification.unverified_count -ne 0 -or
        $expected.Count -ne $observed.Count -or
        @($expected | Select-Object -Unique).Count -ne $expected.Count
    ) {
        return $false
    }
    foreach ($digest in $expected) {
        if ([string] $digest -notmatch $script:DigestPattern) {
            return $false
        }
    }
    $expectedSorted = @($expected | Sort-Object)
    $observedSorted = @($observed | Sort-Object)
    for ($index = 0; $index -lt $expectedSorted.Count; $index++) {
        if (-not [string]::Equals(
            [string] $expectedSorted[$index],
            [string] $observedSorted[$index],
            [System.StringComparison]::Ordinal
        )) {
            return $false
        }
    }
    return $true
}

function ConvertTo-CanonicalLauncherText {
    param([Parameter(Mandatory = $true)][string] $Text)

    $normalized = $Text.Replace("`r`n", "`n").Replace("`r", "`n")
    return $normalized.TrimEnd([char] 10) + "`n"
}

function Get-ExpectedLauncherText {
    param([Parameter(Mandatory = $true)][string] $CanonicalRoot)

    $root = [System.IO.Path]::GetFullPath($CanonicalRoot).TrimEnd("\")
    $logs = Join-Path $root ".runtime\logs"
    $python = Join-Path $root ".venv\Scripts\python.exe"
    $runner = Join-Path $root "scripts\run_telegram_mvp1.py"
    $safeLogs = $logs.Replace("'", "''")
    $safePython = $python.Replace("'", "''")
    $safeRunner = $runner.Replace("'", "''")
    $expected = @"
`$ErrorActionPreference = 'Stop'
`$log = '$safeLogs\runner.log'
if (Test-Path -LiteralPath `$log -PathType Leaf) {
    `$item = Get-Item -LiteralPath `$log
    if (`$item.Length -gt 5MB) {
        Move-Item -LiteralPath `$log -Destination "`$log.previous" -Force
    }
}
& '$safePython' '$safeRunner' --serve --timeout 30 --announce *>> `$log
exit `$LASTEXITCODE
"@
    return ConvertTo-CanonicalLauncherText -Text $expected
}

function Test-ExactLauncherContract {
    param(
        [Parameter(Mandatory = $true)][string] $LauncherPath,
        [Parameter(Mandatory = $true)][string] $LauncherText,
        [Parameter(Mandatory = $true)][string] $CanonicalRoot
    )

    try {
        $root = [System.IO.Path]::GetFullPath($CanonicalRoot).TrimEnd("\")
        $actualPath = [System.IO.Path]::GetFullPath($LauncherPath)
        $expectedPath = [System.IO.Path]::GetFullPath(
            (Join-Path $root ".runtime\start-nobus-space-bot.ps1")
        )
        if (-not $actualPath.Equals(
            $expectedPath,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            return $false
        }
        $actual = ConvertTo-CanonicalLauncherText -Text $LauncherText
        $expected = Get-ExpectedLauncherText -CanonicalRoot $root
        return [string]::Equals(
            $actual,
            $expected,
            [System.StringComparison]::Ordinal
        )
    }
    catch {
        return $false
    }
}

function ConvertTo-IdentitySid {
    param([Parameter(Mandatory = $true)][string] $Identity)

    if ([string]::IsNullOrWhiteSpace($Identity)) {
        return $null
    }
    try {
        if ($Identity -match "^S-\d(?:-\d+)+$") {
            return (
                [Security.Principal.SecurityIdentifier]::new($Identity)
            ).Value
        }
        return (
            [Security.Principal.NTAccount]::new($Identity).Translate(
                [Security.Principal.SecurityIdentifier]
            )
        ).Value
    }
    catch {
        return $null
    }
}

function Test-ExactIdentityContract {
    param(
        [Parameter(Mandatory = $true)][string] $ObservedIdentity,
        [Parameter(Mandatory = $true)][string] $ExpectedIdentity
    )

    $observedSid = ConvertTo-IdentitySid -Identity $ObservedIdentity
    $expectedSid = ConvertTo-IdentitySid -Identity $ExpectedIdentity
    return (
        -not [string]::IsNullOrWhiteSpace([string] $observedSid) -and
        [string]::Equals(
            [string] $observedSid,
            [string] $expectedSid,
            [System.StringComparison]::Ordinal
        )
    )
}

function Get-ExactScheduledActionArgumentsContractProfile {
    param(
        [Parameter(Mandatory = $true)][string] $Arguments,
        [Parameter(Mandatory = $true)][string] $LauncherPath
    )

    $profile = [ordered]@{}
    foreach ($field in $script:ActionContractProfileFields) {
        $profile[$field] = $false
    }
    if ([string]::IsNullOrWhiteSpace($Arguments)) {
        return $profile
    }
    $profile.nonempty = $true
    if ([regex]::IsMatch($Arguments, $script:SecretPattern)) {
        return $profile
    }
    $profile.secret_shape_absent = $true
    $profile.control_chars_absent = $true
    foreach ($character in $Arguments.ToCharArray()) {
        if ([char]::IsControl($character)) {
            $profile.control_chars_absent = $false
            return $profile
        }
    }
    $tokens = $null
    $parseErrors = $null
    try {
        $ast = [System.Management.Automation.Language.Parser]::ParseInput(
            ("powershell.exe " + $Arguments),
            [ref] $tokens,
            [ref] $parseErrors
        )
    }
    catch {
        return $profile
    }
    $profile.parse_ok = @($parseErrors).Count -eq 0
    if (-not $profile.parse_ok) {
        return $profile
    }
    $statements = @($ast.EndBlock.Statements)
    $profile.statement_count_one = $statements.Count -eq 1
    if (-not $profile.statement_count_one) {
        return $profile
    }
    $profile.statement_is_pipeline = $statements[0] -is (
        [System.Management.Automation.Language.PipelineAst]
    )
    if (-not $profile.statement_is_pipeline) {
        return $profile
    }
    $pipelineElements = @($statements[0].PipelineElements)
    $profile.pipeline_element_count_one = $pipelineElements.Count -eq 1
    if (-not $profile.pipeline_element_count_one) {
        return $profile
    }
    $profile.element_is_command = $pipelineElements[0] -is (
        [System.Management.Automation.Language.CommandAst]
    )
    if (-not $profile.element_is_command) {
        return $profile
    }
    $profile.redirection_count_zero =
        @($pipelineElements[0].Redirections).Count -eq 0
    $profile.command_element_count_eight =
        @($pipelineElements[0].CommandElements).Count -eq 8
    $actual = @(
        $tokens | Where-Object {
            [string] $_.Kind -ne "EndOfInput"
        } | ForEach-Object {
            [string] $_.Text
        }
    )
    $profile.token_count_eight = $actual.Count -eq 8
    $expectedTokens = @(
        @("shell_token", "powershell.exe"),
        @("nologo_token", "-NoLogo"),
        @("noprofile_token", "-NoProfile"),
        @("noninteractive_token", "-NonInteractive"),
        @("execution_policy_token", "-ExecutionPolicy"),
        @("bypass_token", "Bypass"),
        @("file_token", "-File")
    )
    for ($index = 0; $index -lt $expectedTokens.Count; $index++) {
        $field = [string] $expectedTokens[$index][0]
        $expected = [string] $expectedTokens[$index][1]
        $profile[$field] = (
            $actual.Count -gt $index -and
            [string]::Equals(
            [string] $actual[$index],
            $expected,
            [System.StringComparison]::OrdinalIgnoreCase
            )
        )
    }
    $singleQuote = [char] 39
    $doubleQuote = [char] 34
    if ($actual.Count -gt 7) {
        $launcherToken = [string] $actual[7]
        $quoteShape = $false
        if (
            -not $launcherToken.Contains([string] $singleQuote) -and
            -not $launcherToken.Contains([string] $doubleQuote)
        ) {
            $quoteShape = $true
        }
        elseif (
            $launcherToken.Length -ge 2 -and (
                $launcherToken[0] -eq $singleQuote -or
                $launcherToken[0] -eq $doubleQuote
            ) -and
            $launcherToken[$launcherToken.Length - 1] -eq $launcherToken[0]
        ) {
            $innerToken = $launcherToken.Substring(
                1,
                $launcherToken.Length - 2
            )
            if (
                -not $innerToken.Contains([string] $singleQuote) -and
                -not $innerToken.Contains([string] $doubleQuote)
            ) {
                $launcherToken = $innerToken
                $quoteShape = $true
            }
        }
        $profile.launcher_quote_shape = $quoteShape
        $profile.launcher_path_exact = (
            $quoteShape -and
            [string]::Equals(
                $launcherToken,
                [System.IO.Path]::GetFullPath($LauncherPath),
                [System.StringComparison]::OrdinalIgnoreCase
            )
        )
    }
    return $profile
}

function Test-ExactScheduledActionArgumentsContract {
    param(
        [Parameter(Mandatory = $true)][string] $Arguments,
        [Parameter(Mandatory = $true)][string] $LauncherPath
    )

    $script:MaintenanceActionContractProfile =
        Get-ExactScheduledActionArgumentsContractProfile `
        -Arguments $Arguments `
        -LauncherPath $LauncherPath
    foreach ($field in $script:ActionContractProfileFields) {
        if (-not [bool] $script:MaintenanceActionContractProfile[$field]) {
            return $false
        }
    }
    return $true
}

function Get-ExactScheduledTaskContractProfile {
    param(
        [Parameter(Mandatory = $true)][object] $Task,
        [Parameter(Mandatory = $true)][object] $Action,
        [Parameter(Mandatory = $true)][string] $LauncherPath,
        [Parameter(Mandatory = $true)][string] $ActionExecutablePath,
        [Parameter(Mandatory = $true)][string] $ExpectedPrincipal
    )

    $expectedExecutable = [System.IO.Path]::GetFullPath(
        (Join-Path $PSHOME "powershell.exe")
    )
    $triggers = @($Task.Triggers)
    $triggerType = if ($triggers.Count -eq 1) {
        [string] $triggers[0].CimClass.CimClassName
    }
    else {
        ""
    }
    return [ordered]@{
        task_name = [string] $Task.TaskName -ceq "NobusSpaceBot"
        task_path = [string] $Task.TaskPath -ceq "\"
        description = [string] $Task.Description -ceq (
            "Nobus Space owner Telegram orchestrator"
        )
        enabled = [bool] $Task.Settings.Enabled
        multiple_instances =
            [string] $Task.Settings.MultipleInstances -ceq "IgnoreNew"
        start_when_available = [bool] $Task.Settings.StartWhenAvailable
        disallow_battery =
            -not [bool] $Task.Settings.DisallowStartIfOnBatteries
        stop_on_battery =
            -not [bool] $Task.Settings.StopIfGoingOnBatteries
        restart_count = [int] $Task.Settings.RestartCount -eq 10
        restart_interval =
            [string] $Task.Settings.RestartInterval -ceq "PT1M"
        execution_limit =
            [string] $Task.Settings.ExecutionTimeLimit -ceq "PT0S"
        principal_user = Test-ExactIdentityContract `
            -ObservedIdentity ([string] $Task.Principal.UserId) `
            -ExpectedIdentity $ExpectedPrincipal
        logon_type = [string] $Task.Principal.LogonType -ceq "Interactive"
        run_level = [string] $Task.Principal.RunLevel -ceq "Limited"
        trigger_count = $triggers.Count -eq 1
        trigger_type = $triggerType -ceq "MSFT_TaskLogonTrigger"
        trigger_user = Test-ExactIdentityContract `
            -ObservedIdentity ([string] $triggers[0].UserId) `
            -ExpectedIdentity $ExpectedPrincipal
        action_arguments = Test-ExactScheduledActionArgumentsContract `
            -Arguments ([string] $Action.Arguments) `
            -LauncherPath $LauncherPath
        working_directory =
            [string]::IsNullOrWhiteSpace([string] $Action.WorkingDirectory)
        executable = [System.IO.Path]::GetFullPath(
            $ActionExecutablePath
        ).Equals(
            $expectedExecutable,
            [System.StringComparison]::OrdinalIgnoreCase
        )
    }
}

function Test-ExactScheduledTaskContract {
    param(
        [Parameter(Mandatory = $true)][object] $Task,
        [Parameter(Mandatory = $true)][object] $Action,
        [Parameter(Mandatory = $true)][string] $LauncherPath,
        [Parameter(Mandatory = $true)][string] $ActionExecutablePath,
        [Parameter(Mandatory = $true)][string] $ExpectedPrincipal
    )

    try {
        $profile = Get-ExactScheduledTaskContractProfile @PSBoundParameters
        foreach ($field in $script:TaskContractProfileFields) {
            if (-not [bool] $profile[$field]) {
                return $false
            }
        }
        return $true
    }
    catch {
        return $false
    }
}

function Test-ExactRepairLauncherContract {
    param([Parameter(Mandatory = $true)][string] $CanonicalRepoRoot)

    if (-not (
        Test-MaintenanceCanonicalRepoAuthority `
            -CanonicalRepoRoot $CanonicalRepoRoot
    )) {
        return $false
    }
    $launcherPath = [System.IO.Path]::GetFullPath(
        (Join-Path $CanonicalRepoRoot ".runtime\start-nobus-space-bot.ps1")
    )
    if (-not [System.IO.File]::Exists($launcherPath)) {
        return $false
    }
    try {
        $launcherText = [System.IO.File]::ReadAllText(
            $launcherPath,
            [System.Text.Encoding]::UTF8
        )
        return (
            -not [regex]::IsMatch($launcherText, $script:SecretPattern) -and
            (Test-ExactLauncherContract `
                -LauncherPath $launcherPath `
                -LauncherText $launcherText `
                -CanonicalRoot $CanonicalRepoRoot)
        )
    }
    catch {
        return $false
    }
}

function Get-ScheduledTaskXmlRepairSnapshot {
    param([Parameter(Mandatory = $true)][string] $TaskXml)

    try {
        [xml] $document = $TaskXml
        $execNodes = @(
            $document.SelectNodes(
                "//*[local-name()='Actions']/*[local-name()='Exec']"
            )
        )
        if ($execNodes.Count -ne 1) {
            throw "Scheduler action XML is not exact."
        }
        $commandNodes = @(
            $execNodes[0].SelectNodes("./*[local-name()='Command']")
        )
        $argumentNodes = @(
            $execNodes[0].SelectNodes("./*[local-name()='Arguments']")
        )
        $workingNodes = @(
            $execNodes[0].SelectNodes("./*[local-name()='WorkingDirectory']")
        )
        if (
            $commandNodes.Count -ne 1 -or
            $argumentNodes.Count -ne 1 -or
            $workingNodes.Count -gt 1
        ) {
            throw "Scheduler action XML fields are not exact."
        }
        $arguments = [string] $argumentNodes[0].InnerText
        $command = [string] $commandNodes[0].InnerText
        $workingDirectory = if ($workingNodes.Count -eq 1) {
            [string] $workingNodes[0].InnerText
        }
        else {
            ""
        }
        $actionId = [string] $execNodes[0].GetAttribute("id")
        $dateNodes = @(
            $document.SelectNodes(
                "//*[local-name()='RegistrationInfo']/*[local-name()='Date']"
            )
        )
        foreach ($dateNode in $dateNodes) {
            $null = $dateNode.ParentNode.RemoveChild($dateNode)
        }
        $fullDigest = Get-MaintenanceDigest ([ordered]@{
            task_xml_without_registration_date = [string] $document.OuterXml
        })
        $argumentNodes[0].InnerText = "__NOBUS_ACTION_ARGUMENTS__"
        return [pscustomobject]@{
            FullDefinitionDigest = $fullDigest
            NonArgumentDigest = Get-MaintenanceDigest ([ordered]@{
                normalized_task_xml = [string] $document.OuterXml
            })
            ArgumentsDigest = Get-MaintenanceDigest ([ordered]@{
                action_arguments = $arguments
            })
            ActionExecute = $command
            ActionWorkingDirectory = $workingDirectory
            ActionId = $actionId
        }
    }
    catch {
        throw "Scheduler XML repair snapshot is unresolved."
    }
}

function Get-NonArgumentScheduledTaskDigest {
    param([Parameter(Mandatory = $true)][string] $TaskXml)

    return (
        Get-ScheduledTaskXmlRepairSnapshot -TaskXml $TaskXml
    ).NonArgumentDigest
}

function Get-ScheduledTaskObjectRepairDigest {
    param([Parameter(Mandatory = $true)][object] $Task)

    $actions = @($Task.Actions)
    $triggers = @($Task.Triggers)
    return Get-MaintenanceDigest ([ordered]@{
        task_name = [string] $Task.TaskName
        task_path = [string] $Task.TaskPath
        description = [string] $Task.Description
        settings = [ordered]@{
            enabled = [bool] $Task.Settings.Enabled
            multiple_instances = [string] $Task.Settings.MultipleInstances
            start_when_available = [bool] $Task.Settings.StartWhenAvailable
            disallow_battery =
                [bool] $Task.Settings.DisallowStartIfOnBatteries
            stop_on_battery = [bool] $Task.Settings.StopIfGoingOnBatteries
            restart_count = [int] $Task.Settings.RestartCount
            restart_interval = [string] $Task.Settings.RestartInterval
            execution_limit = [string] $Task.Settings.ExecutionTimeLimit
        }
        principal = [ordered]@{
            user = [string] $Task.Principal.UserId
            logon_type = [string] $Task.Principal.LogonType
            run_level = [string] $Task.Principal.RunLevel
        }
        triggers = @(
            $triggers | ForEach-Object {
                [ordered]@{
                    type = [string] $_.CimClass.CimClassName
                    user = [string] $_.UserId
                }
            }
        )
        actions = @(
            $actions | ForEach-Object {
                [ordered]@{
                    execute = [string] $_.Execute
                    arguments = [string] $_.Arguments
                    working_directory = [string] $_.WorkingDirectory
                    id = [string] $_.Id
                }
            }
        )
    })
}

function Test-ExactObservedRepairLauncherTarget {
    param(
        [Parameter(Mandatory = $true)][string] $Arguments,
        [Parameter(Mandatory = $true)][string] $LauncherPath
    )

    if (
        [string]::IsNullOrWhiteSpace($Arguments) -or
        [regex]::IsMatch($Arguments, $script:SecretPattern)
    ) {
        return $false
    }
    foreach ($character in $Arguments.ToCharArray()) {
        if ([char]::IsControl($character)) {
            return $false
        }
    }
    $tokens = $null
    $parseErrors = $null
    try {
        $null = [System.Management.Automation.Language.Parser]::ParseInput(
            ("powershell.exe " + $Arguments),
            [ref] $tokens,
            [ref] $parseErrors
        )
    }
    catch {
        return $false
    }
    if (@($parseErrors).Count -ne 0) {
        return $false
    }
    $fileIndexes = @(
        for ($index = 0; $index -lt $tokens.Count; $index++) {
            if ([string] $tokens[$index].Text -ieq "-File") {
                $index
            }
        }
    )
    if (
        $fileIndexes.Count -ne 1 -or
        $fileIndexes[0] + 1 -ge $tokens.Count
    ) {
        return $false
    }
    $launcherToken = [string] $tokens[$fileIndexes[0] + 1].Text
    $singleQuote = [char] 39
    $doubleQuote = [char] 34
    if ($launcherToken.Length -ge 1 -and (
        $launcherToken[0] -eq $singleQuote -or
        $launcherToken[0] -eq $doubleQuote
    )) {
        $quote = $launcherToken[0]
        if (
            $launcherToken.Length -lt 2 -or
            $launcherToken[$launcherToken.Length - 1] -ne $quote
        ) {
            return $false
        }
        $launcherToken = $launcherToken.Substring(
            1,
            $launcherToken.Length - 2
        )
    }
    return (
        -not $launcherToken.Contains([string] $singleQuote) -and
        -not $launcherToken.Contains([string] $doubleQuote) -and
        [string]::Equals(
            $launcherToken,
            [System.IO.Path]::GetFullPath($LauncherPath),
            [System.StringComparison]::OrdinalIgnoreCase
        )
    )
}

function Get-SchedulerActionRepairObservation {
    param([Parameter(Mandatory = $true)][string] $CanonicalRepoRoot)

    $task = Get-ScheduledTask -TaskName "NobusSpaceBot" -ErrorAction Stop
    $taskObjectDigest = Get-ScheduledTaskObjectRepairDigest -Task $task
    $actions = @($task.Actions)
    if ($actions.Count -ne 1) {
        throw "Scheduler action count is not exactly one."
    }
    $action = $actions[0]
    $arguments = [string] $action.Arguments
    if (
        [string]::IsNullOrWhiteSpace($arguments) -or
        [regex]::IsMatch($arguments, $script:SecretPattern)
    ) {
        throw "Scheduler action is not eligible for repair."
    }
    $actionExecutable = (
        Get-Command ([string] $action.Execute) -ErrorAction Stop
    ).Source
    $expectedExecutable = [System.IO.Path]::GetFullPath(
        (Join-Path $PSHOME "powershell.exe")
    )
    if (-not [System.IO.Path]::GetFullPath($actionExecutable).Equals(
        $expectedExecutable,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Scheduler action executable is not approved."
    }
    $taskXml = Export-ScheduledTask `
        -TaskName "NobusSpaceBot" `
        -TaskPath "\" `
        -ErrorAction Stop
    $xmlSnapshot = Get-ScheduledTaskXmlRepairSnapshot `
        -TaskXml ([string] $taskXml)
    $confirmTask = Get-ScheduledTask `
        -TaskName "NobusSpaceBot" `
        -ErrorAction Stop
    $confirmActions = @($confirmTask.Actions)
    if (
        $confirmActions.Count -ne 1 -or
        [string] $taskObjectDigest -cne
            [string] (Get-ScheduledTaskObjectRepairDigest -Task $confirmTask)
    ) {
        throw "Scheduler task object was not stable."
    }
    $confirmAction = $confirmActions[0]
    $argumentsDigest = Get-MaintenanceDigest ([ordered]@{
        action_arguments = [string] $confirmAction.Arguments
    })
    if (
        [string] $xmlSnapshot.ArgumentsDigest -cne
            [string] $argumentsDigest -or
        [string] $xmlSnapshot.ActionExecute -cne
            [string] $confirmAction.Execute -or
        [string] $xmlSnapshot.ActionWorkingDirectory -cne
            [string] $confirmAction.WorkingDirectory -or
        [string] $xmlSnapshot.ActionId -cne [string] $confirmAction.Id
    ) {
        throw "Scheduler task object and XML were not coherent."
    }
    $task = $confirmTask
    $action = $confirmAction
    $arguments = [string] $action.Arguments
    $launcherPath = [System.IO.Path]::GetFullPath(
        (Join-Path $CanonicalRepoRoot ".runtime\start-nobus-space-bot.ps1")
    )
    $expectedPrincipal = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $actionExecutable = (
        Get-Command ([string] $action.Execute) -ErrorAction Stop
    ).Source
    $taskProfile = Get-ExactScheduledTaskContractProfile `
        -Task $task `
        -Action $action `
        -LauncherPath $launcherPath `
        -ActionExecutablePath $actionExecutable `
        -ExpectedPrincipal $expectedPrincipal
    $observedLauncherTargetExact = Test-ExactObservedRepairLauncherTarget `
        -Arguments $arguments `
        -LauncherPath $launcherPath
    $actionProfile = [ordered]@{}
    foreach ($field in $script:ActionContractProfileFields) {
        if (-not $script:MaintenanceActionContractProfile.Contains($field)) {
            throw "Scheduler action profile is incomplete."
        }
        $actionProfile[$field] = [bool] (
            $script:MaintenanceActionContractProfile[$field]
        )
    }
    return [pscustomobject]@{
        TaskProfile = $taskProfile
        ActionProfile = $actionProfile
        FullDefinitionDigest = [string] $xmlSnapshot.FullDefinitionDigest
        NonArgumentDigest = [string] $xmlSnapshot.NonArgumentDigest
        ArgumentsDigest = [string] $argumentsDigest
        ActionExecute = [string] $action.Execute
        ActionWorkingDirectory = [string] $action.WorkingDirectory
        ActionId = [string] $action.Id
        ObservedLauncherTargetExact = $observedLauncherTargetExact
    }
}

function Test-ExpectedActionRepairDriftProfile {
    param([Parameter(Mandatory = $true)][object] $Profile)

    $falseFields = @(
        "command_element_count_eight",
        "token_count_eight",
        "nologo_token",
        "noprofile_token",
        "noninteractive_token",
        "execution_policy_token",
        "bypass_token",
        "file_token",
        "launcher_path_exact"
    )
    foreach ($field in $script:ActionContractProfileFields) {
        if (-not $Profile.Contains($field)) {
            return $false
        }
        $expected = $field -notin $falseFields
        if ([bool] $Profile[$field] -ne $expected) {
            return $false
        }
    }
    return $true
}

function Test-SchedulerActionRepairPrecondition {
    param([Parameter(Mandatory = $true)][object] $Observation)

    if (
        -not [bool] $Observation.ObservedLauncherTargetExact -or
        -not [string]::IsNullOrEmpty([string] $Observation.ActionId)
    ) {
        return $false
    }
    foreach ($field in $script:TaskContractProfileFields) {
        if (-not $Observation.TaskProfile.Contains($field)) {
            return $false
        }
        $expected = $field -cne "action_arguments"
        if ([bool] $Observation.TaskProfile[$field] -ne $expected) {
            return $false
        }
    }
    return Test-ExpectedActionRepairDriftProfile `
        -Profile $Observation.ActionProfile
}

function Test-SchedulerActionRepairPostcondition {
    param([Parameter(Mandatory = $true)][object] $Observation)

    foreach ($field in $script:TaskContractProfileFields) {
        if (
            -not $Observation.TaskProfile.Contains($field) -or
            -not [bool] $Observation.TaskProfile[$field]
        ) {
            return $false
        }
    }
    foreach ($field in $script:ActionContractProfileFields) {
        if (
            -not $Observation.ActionProfile.Contains($field) -or
            -not [bool] $Observation.ActionProfile[$field]
        ) {
            return $false
        }
    }
    return $true
}

function Test-SchedulerActionRepairObservationsEqual {
    param(
        [Parameter(Mandatory = $true)][object] $First,
        [Parameter(Mandatory = $true)][object] $Second
    )

    $fields = @(
        "FullDefinitionDigest",
        "NonArgumentDigest",
        "ArgumentsDigest",
        "ActionExecute",
        "ActionWorkingDirectory",
        "ActionId"
    )
    foreach ($field in $fields) {
        if ([string] $First.$field -cne [string] $Second.$field) {
            return $false
        }
    }
    return $true
}

function Invoke-ExactSchedulerActionRepair {
    param([Parameter(Mandatory = $true)][string] $CanonicalRepoRoot)

    $repairMutex = [System.Threading.Mutex]::new(
        $false,
        "Local\NobusSpaceBot.Gate0.ActionRepair.v1"
    )
    $lockTaken = $false
    try {
        try {
            $lockTaken = $repairMutex.WaitOne(0)
        }
        catch [System.Threading.AbandonedMutexException] {
            $lockTaken = $true
            throw "Scheduler action repair mutex was abandoned."
        }
        if (-not $lockTaken) {
            throw "Scheduler action repair mutex is occupied."
        }
        Invoke-ExactSchedulerActionRepairCore `
            -CanonicalRepoRoot $CanonicalRepoRoot
    }
    finally {
        if ($lockTaken) {
            $repairMutex.ReleaseMutex()
        }
        $repairMutex.Dispose()
    }
}

function Invoke-ExactSchedulerActionRepairCore {
    param([Parameter(Mandatory = $true)][string] $CanonicalRepoRoot)

    Set-MaintenanceFailureStage -Stage "action_repair_preconditions"
    if (-not (
        Test-MaintenanceCanonicalRepoAuthority `
            -CanonicalRepoRoot $CanonicalRepoRoot
    )) {
        throw "Canonical repository authority is invalid."
    }
    if (-not (
        Test-ExactRepairLauncherContract `
            -CanonicalRepoRoot $CanonicalRepoRoot
    )) {
        throw "Canonical repair launcher authority is invalid."
    }
    $first = Get-SchedulerActionRepairObservation `
        -CanonicalRepoRoot $CanonicalRepoRoot
    $second = Get-SchedulerActionRepairObservation `
        -CanonicalRepoRoot $CanonicalRepoRoot
    if (
        -not (Test-SchedulerActionRepairPrecondition -Observation $first) -or
        -not (Test-SchedulerActionRepairPrecondition -Observation $second) -or
        -not (Test-SchedulerActionRepairObservationsEqual `
            -First $first `
            -Second $second)
    ) {
        throw "Scheduler action repair preconditions were not stable."
    }
    $launcherPath = [System.IO.Path]::GetFullPath(
        (Join-Path $CanonicalRepoRoot ".runtime\start-nobus-space-bot.ps1")
    )
    $expectedArguments = (
        '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"'
    ) -f $launcherPath
    $newActionParameters = @{
        Execute = [string] $second.ActionExecute
        Argument = $expectedArguments
    }
    if (-not [string]::IsNullOrEmpty(
        [string] $second.ActionWorkingDirectory
    )) {
        $newActionParameters.WorkingDirectory = (
            [string] $second.ActionWorkingDirectory
        )
    }
    $newAction = New-ScheduledTaskAction @newActionParameters
    $final = Get-SchedulerActionRepairObservation `
        -CanonicalRepoRoot $CanonicalRepoRoot
    if (
        -not (Test-SchedulerActionRepairPrecondition -Observation $final) -or
        -not (Test-SchedulerActionRepairObservationsEqual `
            -First $second `
            -Second $final)
    ) {
        throw "Scheduler action repair final freshness check failed."
    }
    Set-MaintenanceFailureStage -Stage "action_repair_mutation"
    Set-ScheduledTask -TaskName "NobusSpaceBot" -TaskPath "\" -Action $newAction -ErrorAction Stop | Out-Null

    Set-MaintenanceFailureStage -Stage "action_repair_postcondition"
    $post = Get-SchedulerActionRepairObservation `
        -CanonicalRepoRoot $CanonicalRepoRoot
    $nonArgumentUnchanged = (
        [string] $post.NonArgumentDigest -ceq
        [string] $final.NonArgumentDigest
    )
    $taskContractExact = Test-SchedulerActionRepairPostcondition `
        -Observation $post
    if (
        -not $nonArgumentUnchanged -or
        -not $taskContractExact -or
        [string] $post.ActionExecute -cne [string] $final.ActionExecute -or
        [string] $post.ActionWorkingDirectory -cne
            [string] $final.ActionWorkingDirectory -or
        [string] $post.ActionId -cne [string] $final.ActionId
    ) {
        throw "Scheduler action repair postcondition failed."
    }
    [ordered]@{
        schema = $script:MaintenanceSchema
        result = "scheduler_action_repaired"
        mutation_count = 1
        non_argument_contract_unchanged = $nonArgumentUnchanged
        task_contract_exact = $taskContractExact
        raw_values_persisted = $false
    } | ConvertTo-Json -Compress
}

function Get-RegisteredRuntimeDefinition {
    param([Parameter(Mandatory = $true)][string] $CanonicalRepoRoot)

    Set-MaintenanceFailureStage -Stage "canonical_repo_authority"
    if (-not (
        Test-MaintenanceCanonicalRepoAuthority `
            -CanonicalRepoRoot $CanonicalRepoRoot
    )) {
        throw "Canonical repository authority is invalid."
    }

    Set-MaintenanceFailureStage -Stage "scheduler_task"
    $task = Get-ScheduledTask -TaskName "NobusSpaceBot" -ErrorAction Stop
    Set-MaintenanceFailureStage -Stage "scheduler_action"
    $actions = @($task.Actions)
    if ($actions.Count -ne 1) {
        throw "Scheduler action count is not exactly one."
    }
    $action = $actions[0]
    $actionIdContractExact = [string]::IsNullOrEmpty([string] $action.Id)
    if (-not $actionIdContractExact) {
        throw "Scheduler action Id is not installer-equivalent."
    }
    $schedulerArguments = [string] $action.Arguments
    if (
        [string]::IsNullOrWhiteSpace($schedulerArguments) -or
        [regex]::IsMatch($schedulerArguments, $script:SecretPattern)
    ) {
        throw "Scheduler arguments are not eligible."
    }

    Set-MaintenanceFailureStage -Stage "scheduler_arguments"
    $tokens = $null
    $parseErrors = $null
    $null = [System.Management.Automation.Language.Parser]::ParseInput(
        ("powershell.exe " + $schedulerArguments),
        [ref] $tokens,
        [ref] $parseErrors
    )
    if (@($parseErrors).Count -ne 0) {
        throw "Scheduler arguments cannot be parsed."
    }
    $fileTokenIndex = -1
    for ($index = 0; $index -lt $tokens.Count; $index++) {
        if ($tokens[$index].Text -ieq "-File") {
            $fileTokenIndex = $index
            break
        }
    }
    if ($fileTokenIndex -lt 0 -or $fileTokenIndex + 1 -ge $tokens.Count) {
        throw "Scheduler launcher is unresolved."
    }
    $launcherToken = ([string] $tokens[$fileTokenIndex + 1].Text).Trim('"', "'")
    Set-MaintenanceFailureStage -Stage "launcher"
    $launcherPath = [System.IO.Path]::GetFullPath($launcherToken)
    $expectedLauncherPath = [System.IO.Path]::GetFullPath(
        (Join-Path $script:MaintenanceCanonicalRepoRoot ".runtime\start-nobus-space-bot.ps1")
    )
    if (-not $launcherPath.Equals(
        $expectedLauncherPath,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Scheduler launcher path is not exact."
    }
    if (-not [System.IO.File]::Exists($launcherPath)) {
        throw "Scheduler launcher is unavailable."
    }
    $launcherText = [System.IO.File]::ReadAllText(
        $launcherPath,
        [System.Text.Encoding]::UTF8
    )
    if (-not (Test-ExactLauncherContract `
        -LauncherPath $launcherPath `
        -LauncherText $launcherText `
        -CanonicalRoot $script:MaintenanceCanonicalRepoRoot)) {
        throw "Scheduler launcher content is not exact."
    }
    if ([regex]::IsMatch($launcherText, $script:SecretPattern)) {
        throw "Scheduler launcher is not eligible."
    }
    Set-MaintenanceFailureStage -Stage "runner_invocation"
    $invoke = [regex]::Match(
        $launcherText,
        "(?m)^\s*&\s+'(?<python>[^']+)'\s+'(?<runner>[^']+)'(?<tail>[^\r\n]*)$"
    )
    if (-not $invoke.Success) {
        throw "Registered runner invocation is unresolved."
    }

    $pythonPath = [System.IO.Path]::GetFullPath($invoke.Groups["python"].Value)
    $runnerPath = [System.IO.Path]::GetFullPath($invoke.Groups["runner"].Value)
    Set-MaintenanceFailureStage -Stage "runtime_files"
    if (
        -not [System.IO.File]::Exists($pythonPath) -or
        -not [System.IO.File]::Exists($runnerPath)
    ) {
        throw "Registered runtime files are unavailable."
    }
    $runnerRoot = [System.IO.Directory]::GetParent(
        [System.IO.Directory]::GetParent($runnerPath).FullName
    ).FullName.TrimEnd("\")
    $canonicalRoot = $script:MaintenanceCanonicalRepoRoot
    $runnerFileName = [System.IO.Path]::GetFileName($runnerPath)
    Set-MaintenanceFailureStage -Stage "runner_root"
    $registeredRootAccepted = Test-RegisteredRuntimeRoot `
            -CanonicalRepoRoot $canonicalRoot `
            -RunnerRoot $runnerRoot
    if (-not $registeredRootAccepted) {
        Set-MaintenanceFailureStage -Stage (
            Get-RegisteredRuntimeRootFailureStage `
                -CanonicalRepoRoot $canonicalRoot `
                -RunnerRoot $runnerRoot
        )
        throw "Registered runner root is not authorized."
    }
    Set-MaintenanceFailureStage -Stage "runner_script"
    if (
        $runnerFileName -ne "run_telegram_mvp1.py" -or
        -not $runnerPath.Equals(
            (Join-Path $runnerRoot "scripts\run_telegram_mvp1.py"),
            [System.StringComparison]::OrdinalIgnoreCase
        )
    ) {
        throw "Registered runner script is not exact."
    }
    $tail = ([string] $invoke.Groups["tail"].Value).Trim()
    Set-MaintenanceFailureStage -Stage "argument_profile"
    $tailProfile = [ordered]@{
        serve = $tail -match "(?i)(?:^|\s)--serve(?:\s|$)"
        timeout_30 = $tail -match "(?i)(?:^|\s)--timeout\s+30(?:\s|$)"
        announce = $tail -match "(?i)(?:^|\s)--announce(?:\s|$)"
        redirects_log = $tail -match "\*>>"
    }
    if (
        -not $tailProfile.serve -or
        -not $tailProfile.timeout_30 -or
        -not $tailProfile.announce
    ) {
        throw "Registered argument profile is not eligible."
    }

    Set-MaintenanceFailureStage -Stage "action_executable"
    $actionExecutable = (Get-Command ([string] $action.Execute) -ErrorAction Stop).Source
    Set-MaintenanceFailureStage -Stage "task_contract"
    $expectedPrincipal = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $script:MaintenanceTaskContractProfile =
        Get-ExactScheduledTaskContractProfile `
        -Task $task `
        -Action $action `
        -LauncherPath $launcherPath `
        -ActionExecutablePath $actionExecutable `
        -ExpectedPrincipal $expectedPrincipal
    foreach ($field in $script:TaskContractProfileFields) {
        if (-not [bool] $script:MaintenanceTaskContractProfile[$field]) {
            $taskContractExact = $false
            break
        }
        $taskContractExact = $true
    }
    if (-not $taskContractExact) {
        throw "Scheduler definition is not exact."
    }
    $script:MaintenanceTaskContractProfile = $null
    $script:MaintenanceActionContractProfile = $null
    Set-MaintenanceFailureStage -Stage "registered_digests"
    $pythonDigest = Get-MaintenanceFileDigest -LiteralPath $pythonPath
    $runnerDigest = Get-MaintenanceFileDigest -LiteralPath $runnerPath
    $actionExecutableDigest = Get-MaintenanceFileDigest -LiteralPath $actionExecutable
    $launcherDigest = Get-MaintenanceFileDigest -LiteralPath $launcherPath
    Set-MaintenanceFailureStage -Stage "pyvenv_base"
    $basePython = Get-VenvBasePythonDefinition -VenvPythonPath $pythonPath
    Set-MaintenanceFailureStage -Stage "registered_digests"
    $definitionDigest = Get-MaintenanceDigest ([ordered]@{
        action_executable_digest = $actionExecutableDigest
        scheduler_arguments_digest = Get-MaintenanceDigest ([ordered]@{
            launcher_role = "telegram-runner"
            runner_role = "run-telegram-mvp1"
            profile = $tailProfile
        })
        launcher_digest = $launcherDigest
        base_executable_digest = [string] $basePython.Digest
        base_executable_ref_digest = Get-MaintenanceDigest (
            $basePython.Path.ToLowerInvariant()
        )
        enabled = [bool] $task.Settings.Enabled
        multiple_instances = [string] $task.Settings.MultipleInstances
        start_when_available = [bool] $task.Settings.StartWhenAvailable
        disallow_start_on_battery = [bool] $task.Settings.DisallowStartIfOnBatteries
        stop_on_battery = [bool] $task.Settings.StopIfGoingOnBatteries
        restart_count = [int] $task.Settings.RestartCount
        restart_interval = [string] $task.Settings.RestartInterval
        execution_time_limit = [string] $task.Settings.ExecutionTimeLimit
        principal_logon_type = [string] $task.Principal.LogonType
        principal_run_level = [string] $task.Principal.RunLevel
    })

    return [pscustomobject]@{
        SchedulerState = ([string] $task.State).ToLowerInvariant()
        PythonPath = $pythonPath
        PythonDigest = $pythonDigest
        BasePythonPath = [string] $basePython.Path
        BasePythonDigest = [string] $basePython.Digest
        RunnerPath = $runnerPath
        RunnerDigest = $runnerDigest
        RunnerRoot = $runnerRoot
        CanonicalRoot = $canonicalRoot
        DefinitionDigest = $definitionDigest
        LauncherDigest = $launcherDigest
        ActionExecutableDigest = $actionExecutableDigest
        ActionIdContractExact = $actionIdContractExact
        TaskContractProfile = "exact_installer_v1"
    }
}

function Test-IsRunnerCandidate {
    param(
        [Parameter(Mandatory = $true)][string] $CommandLine,
        [Parameter(Mandatory = $true)][string] $RunnerScriptName
    )

    if ([string]::IsNullOrWhiteSpace($RunnerScriptName)) {
        return $false
    }
    $pattern = '(?i)(?:^|[\\/\s"''])' +
        [regex]::Escape($RunnerScriptName) +
        '(?=$|[\s"''])'
    return [regex]::IsMatch($CommandLine, $pattern)
}
function Test-ExactRunnerCommandLine {
    param(
        [Parameter(Mandatory = $true)][string] $CommandLine,
        [Parameter(Mandatory = $true)][object] $Definition
    )

    if ([regex]::IsMatch($CommandLine, $script:SecretPattern)) {
        return $false
    }
    $escapedPython = [regex]::Escape([string] $Definition.PythonPath)
    $escapedRunner = [regex]::Escape([string] $Definition.RunnerPath)
    $pattern = (
        "^\s*`"?{0}`"?\s+(?:-B\s+)?`"?{1}`"?\s+" +
        "--serve\s+--timeout\s+30\s+--announce\s*$"
    ) -f $escapedPython, $escapedRunner
    return [regex]::IsMatch(
        $CommandLine,
        $pattern,
        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
}

function Test-ExactRunnerArgumentProfile {
    param(
        [Parameter(Mandatory = $true)][string] $CommandLine,
        [Parameter(Mandatory = $true)][string] $ExecutablePath,
        [Parameter(Mandatory = $true)][string] $RunnerScriptName
    )

    if (
        [regex]::IsMatch($CommandLine, $script:SecretPattern) -or
        [string]::IsNullOrWhiteSpace($ExecutablePath) -or
        [string]::IsNullOrWhiteSpace($RunnerScriptName)
    ) {
        return $false
    }
    $escapedExecutable = [regex]::Escape($ExecutablePath)
    $escapedRunnerName = [regex]::Escape($RunnerScriptName)
    $runnerToken = '(?:"[^"]*[\\/]' + $escapedRunnerName +
        '"|[^\s"]*[\\/]' + $escapedRunnerName + ')'
    $pattern = '^\s*"?' + $escapedExecutable +
        '"?\s+(?:-B\s+)?' + $runnerToken +
        '\s+--serve\s+--timeout\s+30\s+--announce\s*$'
    return [regex]::IsMatch(
        $CommandLine,
        $pattern,
        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
}
function New-RunnerCandidateProfile {
    param(
        [Parameter(Mandatory = $true)][string] $CommandLine,
        [Parameter(Mandatory = $true)][string] $ExecutablePath,
        [Parameter(Mandatory = $true)][string] $ExecutableDigest,
        [Parameter(Mandatory = $true)][object] $Definition
    )

    $secretShapeAbsent = -not [regex]::IsMatch(
        $CommandLine,
        $script:SecretPattern
    )
    $runnerScriptName = [System.IO.Path]::GetFileName(
        [string] $Definition.RunnerPath
    )
    $exactRunnerScriptMatch = Test-IsRunnerCandidate `
        -CommandLine $CommandLine `
        -RunnerScriptName $runnerScriptName
    $registeredRunnerPattern = '(?i)(?:^|[\s"''])' +
        [regex]::Escape([string] $Definition.RunnerPath) +
        '(?=$|[\s"''])'
    $registeredLiveRootMatch = [regex]::IsMatch(
        $CommandLine,
        $registeredRunnerPattern
    )
    $argumentProfileMatch = Test-ExactRunnerArgumentProfile `
        -CommandLine $CommandLine `
        -ExecutablePath $ExecutablePath `
        -RunnerScriptName $runnerScriptName
    $executableHashMatch = $ExecutableDigest -ceq [string] $Definition.PythonDigest
    $schedulerActionMatch = (
        $registeredLiveRootMatch -and
        $secretShapeAbsent -and
        (Test-ExactRunnerCommandLine `
            -CommandLine $CommandLine `
            -Definition $Definition)
    )
    $verified = (
        $schedulerActionMatch -and
        $executableHashMatch -and
        $registeredLiveRootMatch -and
        $exactRunnerScriptMatch -and
        $argumentProfileMatch -and
        $secretShapeAbsent
    )
    return [ordered]@{
        scheduler_action_match = $schedulerActionMatch
        executable_hash_match = $executableHashMatch
        registered_live_root_match = $registeredLiveRootMatch
        exact_runner_script_match = $exactRunnerScriptMatch
        argument_profile_match = $argumentProfileMatch
        secret_shape_absent = $secretShapeAbsent
        verified = $verified
    }
}
function Get-RunnerCandidates {
    param([Parameter(Mandatory = $true)][object] $Definition)

    $processes = @(
        Get-CimInstance -Query (
            "SELECT ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine,CreationDate " +
            "FROM Win32_Process WHERE Name='python.exe'"
        )
    )
    $candidates = @()
    foreach ($process in $processes) {
        $executablePath = if ($process.ExecutablePath) {
            [System.IO.Path]::GetFullPath([string] $process.ExecutablePath)
        }
        else {
            ""
        }
        $commandLine = [string] $process.CommandLine
        $runnerCandidate = Test-IsRunnerCandidate `
            -CommandLine $commandLine `
            -RunnerScriptName ([System.IO.Path]::GetFileName(
                [string] $Definition.RunnerPath
            ))
        if (-not $runnerCandidate) {
            continue
        }

        $executableDigest = if ($executablePath -and [System.IO.File]::Exists($executablePath)) {
            Get-MaintenanceFileDigest -LiteralPath $executablePath
        }
        else {
            ""
        }
        $profile = New-RunnerCandidateProfile `
            -CommandLine $commandLine `
            -ExecutablePath $executablePath `
            -ExecutableDigest $executableDigest `
            -Definition $Definition
        $verified = [bool] $profile.verified
        $identityDigest = Get-MaintenanceDigest ([ordered]@{
            process_id = [int] $process.ProcessId
            parent_process_id = [int] $process.ParentProcessId
            creation_identity = [string] $process.CreationDate
            executable_digest = $executableDigest
            runner_digest = [string] $Definition.RunnerDigest
            scheduler_definition_digest = [string] $Definition.DefinitionDigest
            identity_profile = $profile
        })
        $candidates += [pscustomobject]@{
            identity_digest = $identityDigest
            verified = $verified
            internal_profile = $profile
            internal_pid = [int] $process.ProcessId
            internal_parent_pid = [int] $process.ParentProcessId
            internal_creation_identity = [string] $process.CreationDate
            internal_creation_filetime = (
                [datetime] $process.CreationDate
            ).ToUniversalTime().ToFileTimeUtc()
            internal_executable_path = $executablePath
            internal_executable_digest = $executableDigest
        }
    }
    return @($candidates)
}

function Test-RunningLogicalRunnerGroup {
    param(
        [Parameter(Mandatory = $true)][object] $Classification,
        [object[]] $Candidates = @(),
        [string[]] $ExpectedIdentityDigests = @(),
        [Parameter(Mandatory = $true)][object] $Definition
    )

    $candidateArray = @($Candidates)
    $expected = @($ExpectedIdentityDigests)
    if (
        [string] $Classification.schema -ne $script:MaintenanceSchema -or
        [string] $Classification.scheduler_state -ne "running" -or
        [string] $Classification.mutex_state -ne "occupied" -or
        [int] $Classification.candidate_count -ne 2 -or
        [int] $Classification.verified_count -ne 1 -or
        [int] $Classification.unverified_count -ne 1 -or
        @($Classification.identity_digests).Count -ne 2 -or
        $candidateArray.Count -ne 2 -or
        $expected.Count -ne 2 -or
        @($expected | Select-Object -Unique).Count -ne 2 -or
        [string] $Definition.PythonDigest -notmatch $script:DigestPattern -or
        [string] $Definition.BasePythonDigest -notmatch $script:DigestPattern
    ) {
        return $false
    }
    foreach ($digest in $expected) {
        if ([string] $digest -notmatch $script:DigestPattern) {
            return $false
        }
    }
    $candidateDigests = @(
        $candidateArray | ForEach-Object { [string] $_.identity_digest } |
            Sort-Object
    )
    $classificationDigests = @(
        $Classification.identity_digests | ForEach-Object { [string] $_ } |
            Sort-Object
    )
    $expectedSorted = @($expected | Sort-Object)
    for ($index = 0; $index -lt 2; $index++) {
        if (
            -not [string]::Equals(
                [string] $candidateDigests[$index],
                [string] $expectedSorted[$index],
                [System.StringComparison]::Ordinal
            ) -or
            -not [string]::Equals(
                [string] $classificationDigests[$index],
                [string] $expectedSorted[$index],
                [System.StringComparison]::Ordinal
            )
        ) {
            return $false
        }
    }

    $exactCandidates = @(
        $candidateArray | Where-Object {
            [bool] $_.verified -and
            [bool] $_.internal_profile.verified -and
            [bool] $_.internal_profile.scheduler_action_match -and
            [bool] $_.internal_profile.executable_hash_match -and
            [bool] $_.internal_profile.registered_live_root_match -and
            [bool] $_.internal_profile.exact_runner_script_match -and
            [bool] $_.internal_profile.argument_profile_match -and
            [bool] $_.internal_profile.secret_shape_absent
        }
    )
    $baseCandidates = @(
        $candidateArray | Where-Object {
            -not [bool] $_.verified -and
            -not [bool] $_.internal_profile.verified -and
            -not [bool] $_.internal_profile.scheduler_action_match -and
            -not [bool] $_.internal_profile.executable_hash_match -and
            [bool] $_.internal_profile.registered_live_root_match -and
            [bool] $_.internal_profile.exact_runner_script_match -and
            [bool] $_.internal_profile.argument_profile_match -and
            [bool] $_.internal_profile.secret_shape_absent
        }
    )
    if ($exactCandidates.Count -ne 1 -or $baseCandidates.Count -ne 1) {
        return $false
    }
    $exact = $exactCandidates[0]
    $base = $baseCandidates[0]
    return (
        [int] $exact.internal_pid -gt 0 -and
        [int] $base.internal_pid -gt 0 -and
        [int] $exact.internal_pid -ne [int] $base.internal_pid -and
        [int] $base.internal_parent_pid -eq [int] $exact.internal_pid -and
        [long] $exact.internal_creation_filetime -gt 0 -and
        (
            [long] $base.internal_creation_filetime -ge
            [long] $exact.internal_creation_filetime
        ) -and
        [string]::Equals(
            [string] $exact.internal_executable_path,
            [string] $Definition.PythonPath,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -and
        [string]::Equals(
            [string] $exact.internal_executable_digest,
            [string] $Definition.PythonDigest,
            [System.StringComparison]::Ordinal
        ) -and
        [string]::Equals(
            [string] $base.internal_executable_path,
            [string] $Definition.BasePythonPath,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -and
        [string]::Equals(
            [string] $base.internal_executable_digest,
            [string] $Definition.BasePythonDigest,
            [System.StringComparison]::Ordinal
        )
    )
}

function Test-LegacyExecutableRemediationSet {
    param(
        [Parameter(Mandatory = $true)][object] $Classification,
        [object[]] $Candidates = @(),
        [string[]] $ExpectedIdentityDigests = @()
    )

    $candidateArray = @($Candidates)
    $expected = @($ExpectedIdentityDigests)
    if (
        [string] $Classification.schema -ne $script:MaintenanceSchema -or
        [string] $Classification.scheduler_state -ne "ready" -or
        [string] $Classification.mutex_state -ne "occupied" -or
        [int] $Classification.candidate_count -ne 2 -or
        [int] $Classification.verified_count -ne 1 -or
        [int] $Classification.unverified_count -ne 1 -or
        $candidateArray.Count -ne 2 -or
        $expected.Count -ne 2 -or
        @($expected | Select-Object -Unique).Count -ne 2
    ) {
        return $false
    }
    foreach ($digest in $expected) {
        if ([string] $digest -notmatch $script:DigestPattern) {
            return $false
        }
    }
    $observed = @($candidateArray | ForEach-Object { [string] $_.identity_digest })
    $expectedSorted = @($expected | Sort-Object)
    $observedSorted = @($observed | Sort-Object)
    for ($index = 0; $index -lt 2; $index++) {
        if (-not [string]::Equals(
            [string] $expectedSorted[$index],
            [string] $observedSorted[$index],
            [System.StringComparison]::Ordinal
        )) {
            return $false
        }
    }

    $exactCount = 0
    $legacyCount = 0
    foreach ($candidate in $candidateArray) {
        $profile = $candidate.internal_profile
        $common = (
            [bool] $profile.registered_live_root_match -and
            [bool] $profile.exact_runner_script_match -and
            [bool] $profile.argument_profile_match -and
            [bool] $profile.secret_shape_absent
        )
        $isExact = (
            $common -and
            [bool] $profile.scheduler_action_match -and
            [bool] $profile.executable_hash_match -and
            [bool] $profile.verified -and
            [bool] $candidate.verified
        )
        $isLegacy = (
            $common -and
            -not [bool] $profile.scheduler_action_match -and
            -not [bool] $profile.executable_hash_match -and
            -not [bool] $profile.verified -and
            -not [bool] $candidate.verified
        )
        if ($isExact) {
            $exactCount++
        }
        elseif ($isLegacy) {
            $legacyCount++
        }
        else {
            return $false
        }
    }
    return $exactCount -eq 1 -and $legacyCount -eq 1
}
function Test-CreationIdentityMatches {
    param(
        [Parameter(Mandatory = $true)][long] $ExpectedFileTime,
        [Parameter(Mandatory = $true)][long] $ObservedFileTime
    )

    return (
        $ExpectedFileTime -gt 0 -and
        $ObservedFileTime -gt 0 -and
        $ExpectedFileTime -eq $ObservedFileTime
    )
}

function Get-ProvenTerminationPlan {
    param([object[]] $RootCandidates = @())

    $roots = @($RootCandidates)
    if ($roots.Count -lt 1) {
        throw "Termination roots are empty."
    }
    $allProcesses = @(
        Get-CimInstance -Query (
            "SELECT ProcessId,ParentProcessId,CreationDate FROM Win32_Process"
        )
    )
    $plan = @(
        $roots | ForEach-Object {
            [pscustomobject]@{
                internal_pid = [int] $_.internal_pid
                internal_parent_pid = [int] $_.internal_parent_pid
                internal_creation_filetime = [long] $_.internal_creation_filetime
                internal_is_root = $true
            }
        }
    )
    $plannedIds = @($plan | ForEach-Object { [int] $_.internal_pid })
    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($process in $allProcesses) {
            $processId = [int] $process.ProcessId
            $parentId = [int] $process.ParentProcessId
            if ($parentId -in $plannedIds -and $processId -notin $plannedIds) {
                $plan += [pscustomobject]@{
                    internal_pid = $processId
                    internal_parent_pid = $parentId
                    internal_creation_filetime = (
                        [datetime] $process.CreationDate
                    ).ToUniversalTime().ToFileTimeUtc()
                    internal_is_root = $false
                }
                $plannedIds += $processId
                $changed = $true
            }
        }
    }
    return @($plan)
}

function Test-TerminationPlanChronology {
    param([object[]] $TerminationPlan = @())

    $plan = @($TerminationPlan)
    if ($plan.Count -lt 1) {
        return $false
    }
    $ids = @($plan | ForEach-Object { [int] $_.internal_pid })
    if (
        @($ids | Select-Object -Unique).Count -ne $ids.Count -or
        @($plan | Where-Object { [bool] $_.internal_is_root }).Count -lt 1
    ) {
        return $false
    }
    foreach ($entry in $plan) {
        $processId = [int] $entry.internal_pid
        $creation = [long] $entry.internal_creation_filetime
        if ($processId -le 0 -or $creation -le 0) {
            return $false
        }
        if ([bool] $entry.internal_is_root) {
            continue
        }
        $parentId = [int] $entry.internal_parent_pid
        $parents = @(
            $plan | Where-Object { [int] $_.internal_pid -eq $parentId }
        )
        if (
            $parentId -eq $processId -or
            $parents.Count -ne 1 -or
            [long] $parents[0].internal_creation_filetime -gt $creation
        ) {
            return $false
        }
    }
    return $true
}
function Initialize-NativeProcessApi {
    if ($null -ne ("NobusGate0.NativeProcess" -as [type])) {
        return
    }
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
namespace NobusGate0 {
    public static class NativeProcess {
        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern IntPtr OpenProcess(
            UInt32 desiredAccess,
            bool inheritHandle,
            Int32 processId
        );
        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool GetProcessTimes(
            IntPtr processHandle,
            out long creationTime,
            out long exitTime,
            out long kernelTime,
            out long userTime
        );
        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool TerminateProcess(
            IntPtr processHandle,
            UInt32 exitCode
        );
        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool CloseHandle(IntPtr handle);
    }
}
"@
}

function Open-ValidatedTerminationHandles {
    param([object[]] $TerminationPlan = @())

    if (-not (Test-TerminationPlanChronology -TerminationPlan $TerminationPlan)) {
        throw "Termination plan chronology is invalid."
    }
    Initialize-NativeProcessApi
    $handles = @()
    try {
        foreach ($entry in @($TerminationPlan)) {
            $handle = [NobusGate0.NativeProcess]::OpenProcess(
                [uint32] 0x00101001,
                $false,
                [int] $entry.internal_pid
            )
            if ($handle -eq [IntPtr]::Zero) {
                throw "Exact process handle could not be opened."
            }
            $creation = [long] 0
            $exit = [long] 0
            $kernel = [long] 0
            $user = [long] 0
            $timesRead = [NobusGate0.NativeProcess]::GetProcessTimes(
                $handle,
                [ref] $creation,
                [ref] $exit,
                [ref] $kernel,
                [ref] $user
            )
            if (
                -not $timesRead -or
                -not (Test-CreationIdentityMatches `
                    -ExpectedFileTime ([long] $entry.internal_creation_filetime) `
                    -ObservedFileTime $creation)
            ) {
                $null = [NobusGate0.NativeProcess]::CloseHandle($handle)
                throw "Process creation identity changed before termination."
            }
            $handles += [pscustomobject]@{
                internal_handle = $handle
                internal_pid = [int] $entry.internal_pid
            }
        }
        return @($handles)
    }
    catch {
        foreach ($opened in $handles) {
            $null = [NobusGate0.NativeProcess]::CloseHandle(
                $opened.internal_handle
            )
        }
        throw
    }
}

function Invoke-ExactHandleTermination {
    param([object[]] $TerminationPlan = @())

    $handles = @(Open-ValidatedTerminationHandles -TerminationPlan $TerminationPlan)
    try {
        foreach ($opened in $handles) {
            if (-not [NobusGate0.NativeProcess]::TerminateProcess(
                $opened.internal_handle,
                [uint32] 0
            )) {
                throw "Exact process handle termination failed."
            }
        }
    }
    finally {
        foreach ($opened in $handles) {
            $null = [NobusGate0.NativeProcess]::CloseHandle(
                $opened.internal_handle
            )
        }
    }
}
function Get-ProductionMutexState {
    param([Parameter(Mandatory = $true)][object] $Definition)

    $probe = @"
import sys
sys.path.insert(0, sys.argv[1])
from src.application.windows_singleton import RunnerAlreadyActive, WindowsNamedMutex
try:
    with WindowsNamedMutex():
        raise SystemExit(0)
except RunnerAlreadyActive:
    raise SystemExit(11)
"@
    $null = & $Definition.PythonPath -B -c $probe $Definition.RunnerRoot 2>$null
    if ($LASTEXITCODE -eq 0) {
        return "free"
    }
    if ($LASTEXITCODE -eq 11) {
        return "occupied"
    }
    return "unknown"
}

function Get-LiveMaintenanceState {
    param([Parameter(Mandatory = $true)][string] $CanonicalRepoRoot)

    $definition = Get-RegisteredRuntimeDefinition -CanonicalRepoRoot $CanonicalRepoRoot
    Set-MaintenanceFailureStage -Stage "runner_candidates"
    $candidates = @(Get-RunnerCandidates -Definition $definition)
    Set-MaintenanceFailureStage -Stage "production_mutex"
    $mutexState = Get-ProductionMutexState -Definition $definition
    Set-MaintenanceFailureStage -Stage "classification"
    $classification = New-MaintenanceClassification `
        -SchedulerState ([string] $definition.SchedulerState) `
        -MutexState $mutexState `
        -Candidates $candidates
    return [pscustomobject]@{
        Definition = $definition
        Candidates = $candidates
        Classification = $classification
    }
}

function Get-FrozenPreCaptureAuthority {
    param(
        [Parameter(Mandatory = $true)][string] $CanonicalRepoRoot,
        [Parameter(Mandatory = $true)][string] $ExpectedInputTreeDigest,
        [Parameter(Mandatory = $true)][string] $ExpectedFrozenTreeDigest,
        [Parameter(Mandatory = $true)][string] $ExpectedGitStatusDigest
    )

    Set-MaintenanceFailureStage -Stage "pre_capture_readback"
    foreach ($digest in @(
        $ExpectedInputTreeDigest,
        $ExpectedFrozenTreeDigest,
        $ExpectedGitStatusDigest
    )) {
        if ([string] $digest -notmatch $script:DigestPattern) {
            throw "Expected pre-capture digest is invalid."
        }
    }
    if (-not (
        Test-MaintenanceCanonicalRepoAuthority `
            -CanonicalRepoRoot $CanonicalRepoRoot
    )) {
        throw "Pre-capture repository authority is invalid."
    }

    $python = Join-Path $script:MaintenanceCanonicalRepoRoot ".venv\Scripts\python.exe"
    $readbackScript = Join-Path (
        $script:MaintenanceCanonicalRepoRoot
    ) "tests\gate0\gate0_precapture.py"
    if (
        -not [System.IO.File]::Exists($python) -or
        -not [System.IO.File]::Exists($readbackScript)
    ) {
        throw "Pre-capture readback runtime is unavailable."
    }
    $raw = @(
        & $python -B $readbackScript readback `
            --root $script:MaintenanceCanonicalRepoRoot 2>$null
    )
    if ($LASTEXITCODE -ne 0 -or $raw.Count -ne 1) {
        throw "Pre-capture readback failed."
    }
    try {
        $core = [string] $raw[0] | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        throw "Pre-capture readback shape is invalid."
    }
    if (
        [string] $core.schema -cne "nobus.gate0.pre_capture_core.v1" -or
        [string] $core.status -cne "pre_capture_ready" -or
        [string] $core.input_tree_digest -cne $ExpectedInputTreeDigest -or
        [string] $core.frozen_tree_digest -cne $ExpectedFrozenTreeDigest -or
        [string] $core.git_status_digest -cne $ExpectedGitStatusDigest -or
        [string] $core.repository_head -notmatch "^[0-9a-f]{40}$"
    ) {
        throw "Pre-capture readback does not match expected authority."
    }
    return [pscustomobject]@{
        InputTreeDigest = [string] $core.input_tree_digest
        FrozenTreeDigest = [string] $core.frozen_tree_digest
        GitStatusDigest = [string] $core.git_status_digest
        RepositoryHead = [string] $core.repository_head
    }
}

function Test-StartReadyState {
    param([Parameter(Mandatory = $true)][object] $Classification)

    return (
        [string] $Classification.schema -ceq $script:MaintenanceSchema -and
        [string] $Classification.scheduler_state -ceq "ready" -and
        [int] $Classification.candidate_count -eq 0 -and
        [int] $Classification.verified_count -eq 0 -and
        [int] $Classification.unverified_count -eq 0 -and
        @($Classification.identity_digests).Count -eq 0 -and
        [string] $Classification.mutex_state -ceq "free" -and
        [string] $Classification.classification_verdict -ceq
            "no_candidates_mutex_free"
    )
}

function Test-StableStartAuthority {
    param(
        [Parameter(Mandatory = $true)][object] $FirstCore,
        [Parameter(Mandatory = $true)][object] $SecondCore,
        [Parameter(Mandatory = $true)][object] $ThirdCore,
        [Parameter(Mandatory = $true)][object] $FirstLive,
        [Parameter(Mandatory = $true)][object] $SecondLive,
        [string] $ExpectedDefinitionDigest,
        [string] $ExpectedLauncherDigest,
        [string] $ExpectedRunnerDigest,
        [string] $ExpectedPythonDigest,
        [string] $ExpectedActionExecutableDigest
    )

    foreach ($field in @(
        "InputTreeDigest",
        "FrozenTreeDigest",
        "GitStatusDigest"
    )) {
        if (
            [string] $FirstCore.$field -cne [string] $SecondCore.$field -or
            [string] $FirstCore.$field -cne [string] $ThirdCore.$field
        ) {
            return $false
        }
    }
    $definitionFields = @(
        "DefinitionDigest",
        "LauncherDigest",
        "RunnerDigest",
        "PythonDigest",
        "ActionExecutableDigest"
    )
    $expected = @(
        $ExpectedDefinitionDigest,
        $ExpectedLauncherDigest,
        $ExpectedRunnerDigest,
        $ExpectedPythonDigest,
        $ExpectedActionExecutableDigest
    )
    foreach ($live in @($FirstLive, $SecondLive)) {
        $actionIdContractExact = $live.Definition.ActionIdContractExact
        if (
            $null -eq $actionIdContractExact -or
            $actionIdContractExact -isnot [bool] -or
            -not $actionIdContractExact
        ) {
            return $false
        }
    }
    for ($index = 0; $index -lt $definitionFields.Count; $index++) {
        $field = $definitionFields[$index]
        $first = [string] $FirstLive.Definition.$field
        $second = [string] $SecondLive.Definition.$field
        if (
            $first -notmatch $script:DigestPattern -or
            $second -cne $first -or
            [string] $expected[$index] -cne $first
        ) {
            return $false
        }
    }
    return (
        (Test-StartReadyState -Classification $FirstLive.Classification) -and
        (Test-StartReadyState -Classification $SecondLive.Classification)
    )
}

function Write-SanitizedClassification {
    param([Parameter(Mandatory = $true)][object] $Classification)

    $Classification | ConvertTo-Json -Compress -Depth 4
}

function Write-SanitizedDiagnostic {
    param(
        [Parameter(Mandatory = $true)][object] $Classification,
        [object[]] $Candidates = @(),
        [object] $Definition
    )

    $profiles = @(
        $Candidates | Sort-Object identity_digest | ForEach-Object {
            [ordered]@{
                identity_digest = [string] $_.identity_digest
                scheduler_action_match = [bool] $_.internal_profile.scheduler_action_match
                executable_hash_match = [bool] $_.internal_profile.executable_hash_match
                registered_live_root_match = [bool] $_.internal_profile.registered_live_root_match
                exact_runner_script_match = [bool] $_.internal_profile.exact_runner_script_match
                argument_profile_match = [bool] $_.internal_profile.argument_profile_match
                secret_shape_absent = [bool] $_.internal_profile.secret_shape_absent
            }
        }
    )
    [ordered]@{
        schema = [string] $Classification.schema
        scheduler_state = [string] $Classification.scheduler_state
        candidate_count = [int] $Classification.candidate_count
        verified_count = [int] $Classification.verified_count
        unverified_count = [int] $Classification.unverified_count
        identity_digests = @($Classification.identity_digests)
        mutex_state = [string] $Classification.mutex_state
        classification_verdict = [string] $Classification.classification_verdict
        runtime_authority = [ordered]@{
            definition_digest = [string] $Definition.DefinitionDigest
            launcher_digest = [string] $Definition.LauncherDigest
            runner_digest = [string] $Definition.RunnerDigest
            python_digest = [string] $Definition.PythonDigest
            action_executable_digest = [string] $Definition.ActionExecutableDigest
            task_contract_profile = [string] $Definition.TaskContractProfile
            raw_values_persisted = $false
        }
        candidate_profiles = $profiles
    } | ConvertTo-Json -Compress -Depth 5
}
function Invoke-RuntimeMaintenance {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet(
            "inspect",
            "repair-action-verified",
            "stop-verified",
            "start-verified"
        )]
        [string] $SelectedMode,
        [Parameter(Mandatory = $true)][string] $CanonicalRepoRoot,
        [string] $ExpectedInputTreeDigest,
        [string] $ExpectedFrozenTreeDigest,
        [string] $ExpectedGitStatusDigest,
        [string] $ExpectedDefinitionDigest,
        [string] $ExpectedLauncherDigest,
        [string] $ExpectedRunnerDigest,
        [string] $ExpectedPythonDigest,
        [string] $ExpectedActionExecutableDigest,
        [string[]] $ExpectedDigests = @(),
        [switch] $AllowLegacyRemediation
    )

    if ($SelectedMode -eq "repair-action-verified") {
        Invoke-ExactSchedulerActionRepair -CanonicalRepoRoot $CanonicalRepoRoot
        return
    }
    if ($SelectedMode -eq "start-verified") {
        Set-MaintenanceFailureStage -Stage "start_preconditions"
        foreach ($digest in @(
            $ExpectedInputTreeDigest,
            $ExpectedFrozenTreeDigest,
            $ExpectedGitStatusDigest,
            $ExpectedDefinitionDigest,
            $ExpectedLauncherDigest,
            $ExpectedRunnerDigest,
            $ExpectedPythonDigest,
            $ExpectedActionExecutableDigest
        )) {
            if ([string] $digest -notmatch $script:DigestPattern) {
                throw "Start authority digest is invalid."
            }
        }
        $firstCore = Get-FrozenPreCaptureAuthority `
            -CanonicalRepoRoot $CanonicalRepoRoot `
            -ExpectedInputTreeDigest $ExpectedInputTreeDigest `
            -ExpectedFrozenTreeDigest $ExpectedFrozenTreeDigest `
            -ExpectedGitStatusDigest $ExpectedGitStatusDigest
        $firstLive = Get-LiveMaintenanceState `
            -CanonicalRepoRoot $CanonicalRepoRoot
        $secondCore = Get-FrozenPreCaptureAuthority `
            -CanonicalRepoRoot $CanonicalRepoRoot `
            -ExpectedInputTreeDigest $ExpectedInputTreeDigest `
            -ExpectedFrozenTreeDigest $ExpectedFrozenTreeDigest `
            -ExpectedGitStatusDigest $ExpectedGitStatusDigest
        $thirdCore = Get-FrozenPreCaptureAuthority `
            -CanonicalRepoRoot $CanonicalRepoRoot `
            -ExpectedInputTreeDigest $ExpectedInputTreeDigest `
            -ExpectedFrozenTreeDigest $ExpectedFrozenTreeDigest `
            -ExpectedGitStatusDigest $ExpectedGitStatusDigest
        $secondLive = Get-LiveMaintenanceState `
            -CanonicalRepoRoot $CanonicalRepoRoot
        Set-MaintenanceFailureStage -Stage "start_preconditions"
        if (-not (Test-StableStartAuthority `
            -FirstCore $firstCore `
            -SecondCore $secondCore `
            -ThirdCore $thirdCore `
            -FirstLive $firstLive `
            -SecondLive $secondLive `
            -ExpectedDefinitionDigest $ExpectedDefinitionDigest `
            -ExpectedLauncherDigest $ExpectedLauncherDigest `
            -ExpectedRunnerDigest $ExpectedRunnerDigest `
            -ExpectedPythonDigest $ExpectedPythonDigest `
            -ExpectedActionExecutableDigest $ExpectedActionExecutableDigest)) {
            throw "Verified start preconditions were not met."
        }
        Set-MaintenanceFailureStage -Stage "scheduler_start"
        Start-ScheduledTask -TaskName "NobusSpaceBot" -ErrorAction Stop
        [ordered]@{
            schema = $script:MaintenanceSchema
            result = "scheduler_start_requested"
            input_tree_digest = [string] $thirdCore.InputTreeDigest
            frozen_tree_digest = [string] $thirdCore.FrozenTreeDigest
            git_status_digest = [string] $thirdCore.GitStatusDigest
            definition_digest = [string] $secondLive.Definition.DefinitionDigest
            launcher_digest = [string] $secondLive.Definition.LauncherDigest
            runner_digest = [string] $secondLive.Definition.RunnerDigest
            python_digest = [string] $secondLive.Definition.PythonDigest
            action_executable_digest =
                [string] $secondLive.Definition.ActionExecutableDigest
            precondition_reads = 2
            frozen_readbacks = 3
            raw_values_persisted = $false
        } | ConvertTo-Json -Compress
        return
    }

    $live = Get-LiveMaintenanceState -CanonicalRepoRoot $CanonicalRepoRoot
    if ($SelectedMode -eq "inspect") {
        Write-SanitizedDiagnostic `
            -Classification $live.Classification `
            -Candidates $live.Candidates `
            -Definition $live.Definition
        return
    }
    if ($AllowLegacyRemediation) {
        Write-SanitizedDiagnostic `
            -Classification $live.Classification `
            -Candidates $live.Candidates `
            -Definition $live.Definition
        $secondRead = Get-LiveMaintenanceState `
            -CanonicalRepoRoot $CanonicalRepoRoot
        Write-SanitizedDiagnostic `
            -Classification $secondRead.Classification `
            -Candidates $secondRead.Candidates `
            -Definition $secondRead.Definition
        $remediationDigests = @($ExpectedDigests)
        if (
            [string] $live.Classification.scheduler_state -eq "running" -and
            $remediationDigests.Count -eq 0
        ) {
            $remediationDigests = @($live.Classification.identity_digests)
        }
        if ([string] $live.Classification.scheduler_state -eq "running") {
            $firstAllowed = Test-RunningLogicalRunnerGroup `
                -Classification $live.Classification `
                -Candidates $live.Candidates `
                -ExpectedIdentityDigests $remediationDigests `
                -Definition $live.Definition
            $secondAllowed = Test-RunningLogicalRunnerGroup `
                -Classification $secondRead.Classification `
                -Candidates $secondRead.Candidates `
                -ExpectedIdentityDigests $remediationDigests `
                -Definition $secondRead.Definition
        }
        else {
            $firstAllowed = Test-LegacyExecutableRemediationSet `
                -Classification $live.Classification `
                -Candidates $live.Candidates `
                -ExpectedIdentityDigests $ExpectedDigests
            $secondAllowed = Test-LegacyExecutableRemediationSet `
                -Classification $secondRead.Classification `
                -Candidates $secondRead.Candidates `
                -ExpectedIdentityDigests $ExpectedDigests
        }
        Set-MaintenanceFailureStage -Stage "remediation_preconditions"
        if (-not $firstAllowed -or -not $secondAllowed) {
            throw "Legacy executable remediation preconditions were not met."
        }
        $live = $secondRead
    }
    elseif (
        -not (Test-TerminationPreconditions `
            -Classification $live.Classification `
            -ExpectedIdentityDigests $ExpectedDigests)
    ) {
        Write-SanitizedClassification -Classification $live.Classification
        throw "Verified termination preconditions were not met."
    }

    Set-MaintenanceFailureStage -Stage "termination_plan"
    $terminationPlan = @(Get-ProvenTerminationPlan `
        -RootCandidates $live.Candidates)
    Set-MaintenanceFailureStage -Stage "termination_handles"
    Invoke-ExactHandleTermination -TerminationPlan $terminationPlan

    $deadline = (Get-Date).AddSeconds(15)
    do {
        Start-Sleep -Milliseconds 250
        $post = Get-LiveMaintenanceState -CanonicalRepoRoot $CanonicalRepoRoot
        if (Test-MaintenancePostcondition -Classification $post.Classification) {
            Write-SanitizedClassification -Classification $post.Classification
            return
        }
        Set-MaintenanceFailureStage -Stage "postcondition"
    } while ((Get-Date) -lt $deadline)
    Write-SanitizedClassification -Classification $post.Classification
    throw "Runtime maintenance postcondition failed."
}

if ($MyInvocation.InvocationName -ne ".") {
    try {
        Set-MaintenanceFailureStage -Stage "entry"
        if (
            [string]::IsNullOrWhiteSpace($Mode) -or
            $Mode -notin @(
                "inspect",
                "repair-action-verified",
                "stop-verified",
                "start-verified"
            ) -or
            [string]::IsNullOrWhiteSpace($RepoRoot)
        ) {
            throw "Mode and RepoRoot are required."
        }
        $startDigests = @(
            $ExpectedInputTreeDigest,
            $ExpectedFrozenTreeDigest,
            $ExpectedGitStatusDigest,
            $ExpectedDefinitionDigest,
            $ExpectedLauncherDigest,
            $ExpectedRunnerDigest,
            $ExpectedPythonDigest,
            $ExpectedActionExecutableDigest
        )
        if ($Mode -eq "start-verified") {
            if (
                @($ExpectedIdentityDigest).Count -ne 0 -or
                $AllowLegacyExecutableRemediation
            ) {
                throw "Start mode arguments are not exact."
            }
            foreach ($digest in $startDigests) {
                if ([string] $digest -notmatch $script:DigestPattern) {
                    throw "Start authority digest is invalid."
                }
            }
        }
        elseif ($Mode -eq "repair-action-verified") {
            if (
                @($ExpectedIdentityDigest).Count -ne 0 -or
                $AllowLegacyExecutableRemediation
            ) {
                throw "Action repair mode arguments are not exact."
            }
        }
        elseif (
            @(
                $startDigests | Where-Object {
                    -not [string]::IsNullOrWhiteSpace([string] $_)
                }
            ).Count -ne 0
        ) {
            throw "Start authority arguments require start-verified mode."
        }
        Invoke-RuntimeMaintenance `
            -SelectedMode $Mode `
            -CanonicalRepoRoot $RepoRoot `
            -ExpectedInputTreeDigest $ExpectedInputTreeDigest `
            -ExpectedFrozenTreeDigest $ExpectedFrozenTreeDigest `
            -ExpectedGitStatusDigest $ExpectedGitStatusDigest `
            -ExpectedDefinitionDigest $ExpectedDefinitionDigest `
            -ExpectedLauncherDigest $ExpectedLauncherDigest `
            -ExpectedRunnerDigest $ExpectedRunnerDigest `
            -ExpectedPythonDigest $ExpectedPythonDigest `
            -ExpectedActionExecutableDigest $ExpectedActionExecutableDigest `
            -ExpectedDigests $ExpectedIdentityDigest `
            -AllowLegacyRemediation:$AllowLegacyExecutableRemediation
    }
    catch {
        Write-SanitizedMaintenanceFailure
        exit 1
    }
}
