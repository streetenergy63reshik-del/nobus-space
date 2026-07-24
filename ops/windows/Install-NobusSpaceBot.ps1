[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$TaskName = 'NobusSpaceBot',
    [string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
$runner = Join-Path $root 'scripts\run_telegram_mvp1.py'
$health = Join-Path $root 'scripts\check_telegram_health.py'
$healthTaskName = "$TaskName-Health"
if (-not (Test-Path -LiteralPath $python -PathType Leaf) -or
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

$runtime = Join-Path $root '.runtime'
$logs = Join-Path $runtime 'logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$launcher = Join-Path $runtime 'start-nobus-space-bot.ps1'
$healthLauncher = Join-Path $runtime 'check-nobus-space-bot.ps1'
$launcherBody = @"
`$ErrorActionPreference = 'Stop'
`$log = '$($logs.Replace("'", "''"))\runner.log'
if (Test-Path -LiteralPath `$log -PathType Leaf) {
    `$item = Get-Item -LiteralPath `$log
    if (`$item.Length -gt 5MB) {
        Move-Item -LiteralPath `$log -Destination "`$log.previous" -Force
    }
}
& '$($python.Replace("'", "''"))' '$($runner.Replace("'", "''"))' --serve --timeout 30 --announce *>> `$log
exit `$LASTEXITCODE
"@
$healthBody = @"
`$ErrorActionPreference = 'Continue'
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
& '$($python.Replace("'", "''"))' '$($health.Replace("'", "''"))' *>> `$log
if (`$LASTEXITCODE -ne 0) {
    Add-Content -LiteralPath `$alert -Value (
        (Get-Date).ToString('o') + ' runtime health probe failed'
    )
    exit 1
}
exit 0
"@
Set-Content -LiteralPath $launcher -Value $launcherBody -Encoding UTF8
Set-Content -LiteralPath $healthLauncher -Value $healthBody -Encoding UTF8

$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument (
    "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$launcher`""
)
$healthAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument (
    "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$healthLauncher`""
)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$healthTrigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 10 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew
$healthSettings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
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
