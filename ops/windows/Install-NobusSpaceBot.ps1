[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$TaskName = 'NobusSpaceBot',
    [string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [string]$RuntimeRoot = ''
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$runtimeOwner = if ([string]::IsNullOrWhiteSpace($RuntimeRoot)) {
    $root
}
else {
    (Resolve-Path -LiteralPath $RuntimeRoot).Path
}
$python = Join-Path $runtimeOwner '.venv\Scripts\python.exe'
$pythonw = Join-Path $runtimeOwner '.venv\Scripts\pythonw.exe'
$runner = Join-Path $root 'scripts\run_nobus_space_live.py'
$health = Join-Path $root 'scripts\check_telegram_health.py'
$healthTaskName = "$TaskName-Health"
if (-not (Test-Path -LiteralPath $python -PathType Leaf) -or
    -not (Test-Path -LiteralPath $pythonw -PathType Leaf) -or
    -not (Test-Path -LiteralPath $runner -PathType Leaf) -or
    -not (Test-Path -LiteralPath $health -PathType Leaf)) {
    throw 'Canonical runner, health probe or virtual environment is unavailable.'
}

if (-not $PSCmdlet.ShouldProcess(
    "$TaskName and $healthTaskName",
    'Install launchers and scheduled tasks'
)) {
    return
}

$runtime = Join-Path $runtimeOwner '.runtime'
$logs = Join-Path $runtime 'logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$healthLauncher = Join-Path $runtime 'check-nobus-space-bot.ps1'
$healthBody = @"
`$ErrorActionPreference = 'Continue'
`$taskName = '$($TaskName.Replace("'", "''"))'
`$log = '$($logs.Replace("'", "''"))\health.log'
`$alert = '$($logs.Replace("'", "''"))\health-alerts.log'
foreach (`$path in @(`$log, `$alert)) {
    if (Test-Path -LiteralPath `$path -PathType Leaf) {
        `$item = Get-Item -LiteralPath `$path
        if (`$item.Length -gt 2MB) {
            Move-Item -LiteralPath `$path -Destination "`$path.previous" -Force
        }
    }
}
`$healthy = `$true
& '$($python.Replace("'", "''"))' '$($health.Replace("'", "''"))' *>> `$log
if (`$LASTEXITCODE -ne 0) {
    `$healthy = `$false
}
try {
    `$local = Invoke-WebRequest -UseBasicParsing -Headers @{ Host = 'app.nobusspace.com' } -Uri 'http://127.0.0.1:8765/readyz' -TimeoutSec 5
    if (`$local.StatusCode -ne 200) {
        `$healthy = `$false
    }
}
catch {
    `$healthy = `$false
}
try {
    `$public = Invoke-WebRequest -UseBasicParsing -Uri 'https://app.nobusspace.com/readyz' -TimeoutSec 10
    if (`$public.StatusCode -ne 200) {
        `$healthy = `$false
    }
}
catch {
    `$healthy = `$false
}
if (-not `$healthy) {
    Add-Content -LiteralPath `$alert -Value (
        (Get-Date).ToUniversalTime().ToString('o') + ' product health probe failed'
    )
    try {
        `$task = Get-ScheduledTask -TaskName `$taskName -ErrorAction Stop
        if (`$task.State -eq 'Ready') {
            Start-ScheduledTask -TaskName `$taskName
            Add-Content -LiteralPath `$alert -Value (
                (Get-Date).ToUniversalTime().ToString('o') + ' recovery start requested'
            )
        }
    }
    catch {
        Add-Content -LiteralPath `$alert -Value (
            (Get-Date).ToUniversalTime().ToString('o') + ' recovery check failed'
        )
    }
    exit 1
}
exit 0
"@
$utf8Bom = [System.Text.UTF8Encoding]::new($true)
[System.IO.File]::WriteAllText($healthLauncher, $healthBody, $utf8Bom)
$tokens = $null
$parseErrors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
    $healthLauncher,
    [ref]$tokens,
    [ref]$parseErrors
) | Out-Null
if ($parseErrors.Count -ne 0) {
    throw 'Generated health launcher is invalid.'
}

$action = New-ScheduledTaskAction `
    -Execute $pythonw `
    -Argument "`"$runner`"" `
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
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 10 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew
$healthSettings = New-ScheduledTaskSettingsSet `
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

Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
Register-ScheduledTask `
    -TaskName $healthTaskName `
    -InputObject $healthTask `
    -Force | Out-Null
