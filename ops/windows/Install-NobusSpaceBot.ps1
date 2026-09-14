[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$TaskName = 'NobusSpaceBot',
    [string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [string]$RuntimeRoot = '',
    [string]$HealthLauncherRoot = '',
    [switch]$SemanticAdmission,
    [string]$StateRoot = '',
    [string]$VoiceModelDirectory = '',
    [string]$BackupRoot = '',
    [string]$BackupOwnership = '',
    [switch]$ReplaceExisting,
    [switch]$StageDisabled,
    [string]$ExpectedMainDefinitionDigest = '',
    [string]$ExpectedHealthDefinitionDigest = '',
    [string]$ExpectedHealthLauncherDigest = '',
    [string]$RollbackRoot = ''
)

$ErrorActionPreference = 'Stop'

function Resolve-CompositionDirectory([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return $null }
    if ($Path -notmatch '^[A-Za-z]:[\\/]') {
        throw 'Composition directory must be an absolute local path.'
    }
    $directory = Get-Item -LiteralPath $Path -ErrorAction Stop
    if (-not $directory.PSIsContainer -or $directory.FullName.StartsWith('\\')) {
        throw 'Composition directory must be a local directory.'
    }
    $ancestor = $directory
    while ($null -ne $ancestor) {
        if (($ancestor.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'Composition directory cannot use a reparse point.'
        }
        $ancestor = $ancestor.Parent
    }
    return $directory.FullName
}

function Test-Sha256Digest([string]$Value) {
    return $Value -cmatch '^sha256:[0-9a-f]{64}$'
}

function Get-Sha256Text([string]$Value) {
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
        $hash = $algorithm.ComputeHash($bytes)
        return 'sha256:' + ([System.BitConverter]::ToString($hash).Replace('-', '').ToLowerInvariant())
    }
    finally {
        $algorithm.Dispose()
    }
}

function Get-Sha256File([string]$Path) {
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    $stream = [System.IO.File]::Open(
        $Path,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::Read
    )
    try {
        $hash = $algorithm.ComputeHash($stream)
        return 'sha256:' + ([System.BitConverter]::ToString($hash).Replace('-', '').ToLowerInvariant())
    }
    finally {
        $stream.Dispose()
        $algorithm.Dispose()
    }
}

function Write-NewUtf8Text([string]$Path, [string]$Value) {
    $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($Value)
    $stream = [System.IO.File]::Open(
        $Path,
        [System.IO.FileMode]::CreateNew,
        [System.IO.FileAccess]::Write,
        [System.IO.FileShare]::None
    )
    try {
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
    }
    finally {
        $stream.Dispose()
    }
}

if ($TaskName -notmatch '^NobusSpace[A-Za-z0-9-]{1,64}$') {
    throw 'Invalid runtime task name.'
}

$stateDirectory = Resolve-CompositionDirectory $StateRoot
$modelDirectory = Resolve-CompositionDirectory $VoiceModelDirectory
$backupDirectory = Resolve-CompositionDirectory $BackupRoot
if ([bool]$backupDirectory -ne [bool]$BackupOwnership -or ($BackupOwnership -and $BackupOwnership -notmatch "^sha256:[0-9a-f]{64}$")) { throw "Backup root and ownership must be supplied together." }
$root = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$runtimeOwner = if ([string]::IsNullOrWhiteSpace($RuntimeRoot)) {
    $root
}
else {
    (Resolve-Path -LiteralPath $RuntimeRoot).Path
}
$healthLauncherOwner = if ([string]::IsNullOrWhiteSpace($HealthLauncherRoot)) {
    $runtimeOwner
}
else {
    Resolve-CompositionDirectory $HealthLauncherRoot
}
$python = Join-Path $runtimeOwner '.venv\Scripts\python.exe'
$pythonw = Join-Path $runtimeOwner '.venv\Scripts\pythonw.exe'
$runner = Join-Path $root 'scripts\run_nobus_space_live.py'
$health = Join-Path $root 'scripts\check_telegram_health.py'
$healthTaskName = "$TaskName-Health"
$runtime = Join-Path $healthLauncherOwner '.runtime'
$logs = Join-Path $runtime 'logs'
$healthLauncher = Join-Path $runtime 'check-nobus-space-bot.ps1'
if (-not (Test-Path -LiteralPath $python -PathType Leaf) -or
    -not (Test-Path -LiteralPath $pythonw -PathType Leaf) -or
    -not (Test-Path -LiteralPath $runner -PathType Leaf) -or
    -not (Test-Path -LiteralPath $health -PathType Leaf)) {
    throw 'Canonical runner, health probe or virtual environment is unavailable.'
}

$existingMain = Get-ScheduledTask `
    -TaskName $TaskName `
    -TaskPath '\' `
    -ErrorAction SilentlyContinue
$existingHealth = Get-ScheduledTask `
    -TaskName $healthTaskName `
    -TaskPath '\' `
    -ErrorAction SilentlyContinue
$hasMain = $null -ne $existingMain
$hasHealth = $null -ne $existingHealth
if ($hasMain -ne $hasHealth) {
    throw 'Exact runtime task pair is incomplete.'
}

$mainDefinition = $null
$healthDefinition = $null
$rollbackDirectory = $null
if ($hasMain) {
    if (-not $ReplaceExisting.IsPresent -or -not $StageDisabled.IsPresent) {
        throw 'Existing runtime replacement requires exact disabled staging.'
    }
    foreach ($existing in @($existingMain, $existingHealth)) {
        if ([bool]$existing.Settings.Enabled -or [string]$existing.State -in @('Running', 'Queued')) {
            throw 'Exact runtime task replacement requires stopped disabled tasks.'
        }
    }
    foreach ($digest in @(
        $ExpectedMainDefinitionDigest,
        $ExpectedHealthDefinitionDigest,
        $ExpectedHealthLauncherDigest
    )) {
        if (-not (Test-Sha256Digest $digest)) {
            throw 'Exact runtime replacement digest is invalid.'
        }
    }
    $mainDefinition = [string](Export-ScheduledTask `
        -TaskName $TaskName `
        -TaskPath '\' `
        -ErrorAction Stop)
    $healthDefinition = [string](Export-ScheduledTask `
        -TaskName $healthTaskName `
        -TaskPath '\' `
        -ErrorAction Stop)
    if ((Get-Sha256Text $mainDefinition) -cne $ExpectedMainDefinitionDigest -or
        (Get-Sha256Text $healthDefinition) -cne $ExpectedHealthDefinitionDigest) {
        throw 'Exact runtime task definition changed before staging.'
    }
    if (-not (Test-Path -LiteralPath $healthLauncher -PathType Leaf)) {
        throw 'Exact health launcher is unavailable.'
    }
    if (((Get-Item -LiteralPath $healthLauncher).Attributes -band
            [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'Exact health launcher cannot use a reparse point.'
    }
    $launcherDigest = Get-Sha256File $healthLauncher
    if ($launcherDigest -cne $ExpectedHealthLauncherDigest) {
        throw 'Exact health launcher changed before staging.'
    }
    $rollbackDirectory = Resolve-CompositionDirectory $RollbackRoot
    if ($null -eq $rollbackDirectory) {
        throw 'Exact runtime replacement requires a rollback directory.'
    }
}
elseif ($ReplaceExisting.IsPresent) {
    throw 'Exact runtime replacement requires the existing task pair.'
}
elseif (
    $ExpectedMainDefinitionDigest -or
    $ExpectedHealthDefinitionDigest -or
    $ExpectedHealthLauncherDigest -or
    $RollbackRoot
) {
    throw 'Initial runtime installation cannot accept replacement evidence.'
}

$healthStateDirectory = if ($null -ne $stateDirectory) { $stateDirectory } else { Join-Path $root '.runtime' }
$runnerArguments = @('"' + $runner + '"')
if ($SemanticAdmission.IsPresent) {
    $runnerArguments += '--semantic-admission'
}
if ($null -ne $stateDirectory) {
    $runnerArguments += @('--runtime-root', ('"' + $stateDirectory + '"'))
}
if ($null -ne $modelDirectory) {
    $runnerArguments += @('--voice-model-directory', ('"' + $modelDirectory + '"'))
}

if ($null -ne $backupDirectory) {
    $runnerArguments += @('--backup-root', ('"' + $backupDirectory + '"'), '--backup-ownership', $BackupOwnership)
}
$runnerArguments += @(
    '--health-launcher', ('"' + $healthLauncher + '"'),
    '--scheduler-task-name', $TaskName
)

if (-not $PSCmdlet.ShouldProcess(
    "$TaskName and $healthTaskName",
    'Install launchers and scheduled tasks'
)) {
    return
}

$healthBody = @"
`$ErrorActionPreference = 'Continue'
`$taskName = '$($TaskName.Replace("'", "''"))'
`$alert = '$($logs.Replace("'", "''"))\health-alerts.log'
if (Test-Path -LiteralPath `$alert -PathType Leaf) {
    `$item = Get-Item -LiteralPath `$alert
    if (`$item.Length -gt 2MB) {
        Move-Item -LiteralPath `$alert -Destination "`$alert.previous" -Force
    }
}
`$healthy = `$true
& '$($python.Replace("'", "''"))' '$($health.Replace("'", "''"))' --runtime '$($healthStateDirectory.Replace("'", "''"))' 1>`$null 2>`$null
if (`$LASTEXITCODE -ne 0) {
    `$healthy = `$false
}
# The shared read-only CLI enforces exact body, no redirects and total2s/5s deadlines.
& '$($python.Replace("'", "''"))' '$($runner.Replace("'", "''"))' --check-ready 1>`$null 2>`$null
if (`$LASTEXITCODE -ne 0) {
    `$healthy = `$false
}
if (-not `$healthy) {
    Add-Content -LiteralPath `$alert -Value (
        (Get-Date).ToUniversalTime().ToString('o') + ' product health probe failed'
    )
    # Health is observation-only; the main action owns bounded, evidence-gated recovery.
    exit 1
}
exit 0
"@
$candidateLauncher = $null
$candidateLauncherCreated = $false
$stagingStage = 'prepare_candidate_launcher'
$utf8Bom = [System.Text.UTF8Encoding]::new($true)
try {
    New-Item -ItemType Directory -Force -Path $logs | Out-Null
    $candidateLauncher = Join-Path $runtime (
        '.check-nobus-space-bot.' + [guid]::NewGuid().ToString('N') + '.candidate'
    )
    [System.IO.File]::WriteAllText($candidateLauncher, $healthBody, $utf8Bom)
    $candidateLauncherCreated = $true
    $stagingStage = 'parse_candidate_launcher'
    $tokens = $null
    $parseErrors = $null
    [System.Management.Automation.Language.Parser]::ParseFile(
        $candidateLauncher,
        [ref]$tokens,
        [ref]$parseErrors
    ) | Out-Null
    if ($parseErrors.Count -ne 0) {
        throw 'Generated health launcher is invalid.'
    }

    $stagingStage = 'build_candidate_tasks'
    $action = New-ScheduledTaskAction `
        -Execute $pythonw `
        -Argument ($runnerArguments -join ' ') `
        -WorkingDirectory $root
    $healthAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument (
        "-WindowStyle Hidden -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$healthLauncher`""
    )
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $healthTrigger = New-ScheduledTaskTrigger `
        -Once `
        -At (Get-Date).AddMinutes(1) `
        -RepetitionInterval (New-TimeSpan -Minutes 1) `
        -RepetitionDuration (New-TimeSpan -Days 3650)
    $settings = New-ScheduledTaskSettingsSet `
        -Disable:$StageDisabled.IsPresent `
        -StartWhenAvailable `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -MultipleInstances IgnoreNew
    $healthSettings = New-ScheduledTaskSettingsSet `
        -Disable:$StageDisabled.IsPresent `
        -StartWhenAvailable `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 2) `
        -MultipleInstances IgnoreNew
    $principal = New-ScheduledTaskPrincipal `
        -UserId "$env:USERDOMAIN\$env:USERNAME" `
        -LogonType Interactive `
        -RunLevel Limited
    $task = New-ScheduledTask `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description 'Nobus Space owner Telegram orchestrator'
    $healthTask = New-ScheduledTask `
        -Action $healthAction `
        -Trigger $healthTrigger `
        -Settings $healthSettings `
        -Principal $principal `
        -Description 'Nobus Space Telegram runtime health monitor'

    if ($ReplaceExisting.IsPresent) {
        $stagingStage = 'capture_rollback_definitions'
        $mainRollback = Join-Path $rollbackDirectory ($TaskName + '.xml')
        $healthRollback = Join-Path $rollbackDirectory ($healthTaskName + '.xml')
        $healthLauncherRollback = Join-Path $rollbackDirectory 'check-nobus-space-bot.ps1'
        foreach ($path in @($mainRollback, $healthRollback, $healthLauncherRollback)) {
            if (Test-Path -LiteralPath $path) {
                throw 'Exact runtime rollback destination already exists.'
            }
        }
        Write-NewUtf8Text $mainRollback $mainDefinition
        Write-NewUtf8Text $healthRollback $healthDefinition
        $stagingStage = 'register_main_disabled'
        Register-ScheduledTask `
            -TaskName $TaskName `
            -TaskPath '\' `
            -InputObject $task `
            -Force | Out-Null
        $stagingStage = 'register_health_disabled'
        Register-ScheduledTask `
            -TaskName $healthTaskName `
            -TaskPath '\' `
            -InputObject $healthTask `
            -Force | Out-Null
    }
    else {
        $stagingStage = 'register_main'
        Register-ScheduledTask `
            -TaskName $TaskName `
            -TaskPath '\' `
            -InputObject $task | Out-Null
        $stagingStage = 'register_health'
        Register-ScheduledTask `
            -TaskName $healthTaskName `
            -TaskPath '\' `
            -InputObject $healthTask | Out-Null
    }

    if ($StageDisabled.IsPresent) {
        $stagingStage = 'verify_disabled_readback'
        $stagedMain = Get-ScheduledTask -TaskName $TaskName -TaskPath '\' -ErrorAction Stop
        $stagedHealth = Get-ScheduledTask -TaskName $healthTaskName -TaskPath '\' -ErrorAction Stop
        if ([bool]$stagedMain.Settings.Enabled -or
            [bool]$stagedHealth.Settings.Enabled -or
            [string]$stagedMain.State -in @('Running', 'Queued') -or
            [string]$stagedHealth.State -in @('Running', 'Queued')) {
            throw 'Candidate task pair did not remain disabled.'
        }
    }

    if ($ReplaceExisting.IsPresent) {
        $stagingStage = 'replace_health_launcher'
        [System.IO.File]::Replace(
            $candidateLauncher,
            $healthLauncher,
            $healthLauncherRollback
        )
    }
    else {
        $stagingStage = 'install_health_launcher'
        [System.IO.File]::Move($candidateLauncher, $healthLauncher)
    }
    $candidateLauncherCreated = $false
}
catch {
    Disable-ScheduledTask `
        -TaskName $TaskName `
        -TaskPath '\' `
        -ErrorAction SilentlyContinue | Out-Null
    Disable-ScheduledTask `
        -TaskName $healthTaskName `
        -TaskPath '\' `
        -ErrorAction SilentlyContinue | Out-Null
    throw ('candidate staging failed closed: ' + $stagingStage)
}
finally {
    if ($candidateLauncherCreated -and
        $null -ne $candidateLauncher -and
        (Test-Path -LiteralPath $candidateLauncher -PathType Leaf)) {
        Remove-Item -LiteralPath $candidateLauncher -Force -ErrorAction SilentlyContinue
    }
}
