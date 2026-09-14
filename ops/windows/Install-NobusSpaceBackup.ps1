[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$TaskName='NobusSpaceBot-Backup',
    [Parameter(Mandatory)][string]$RepositoryRoot,
    [Parameter(Mandatory)][string]$Python,
    [Parameter(Mandatory)][string]$Config,
    [Parameter(Mandatory)][ValidatePattern('^sha256:[0-9a-f]{64}$')][string]$ConfigDigest,
    [ValidatePattern('^[0-2][0-9]:[0-5][0-9]$')][string]$LocalTime='03:30',
    [switch]$ReplaceExisting
)
$ErrorActionPreference='Stop'
if($TaskName -notmatch '^NobusSpace[A-Za-z0-9-]{1,64}$'){throw 'Invalid backup task name'}
foreach($path in @($RepositoryRoot,$Python,$Config)) {
    if($path -notmatch '^[A-Za-z]:[\\/]'){throw 'Absolute local paths required'}
    $item=Get-Item -LiteralPath $path -ErrorAction Stop
    while($null -ne $item) {
        if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint)-ne 0){throw 'Linked backup path'}
        $item=if($item.PSIsContainer){$item.Parent}else{$item.Directory}
    }
}
$script=Join-Path $RepositoryRoot 'scripts\run_telegram_backup_cycle.py'
if(-not(Test-Path -LiteralPath $script -PathType Leaf)){throw 'Backup coordinator unavailable'}
$existing=Get-ScheduledTask -TaskName $TaskName -TaskPath '\' -ErrorAction SilentlyContinue
if($null -ne $existing) {
    if(-not $ReplaceExisting){throw 'Backup task already exists; exact update required'}
    if([bool]$existing.Settings.Enabled -or [string]$existing.State -in @('Running','Queued')) {
        throw 'Exact backup task replacement requires a stopped disabled task'
    }
} elseif($ReplaceExisting) {
    throw 'Exact backup task replacement requires the existing task'
}
$at=[datetime]::Today.Add([TimeSpan]::ParseExact($LocalTime,'hh\:mm',[Globalization.CultureInfo]::InvariantCulture))
$action=New-ScheduledTaskAction -Execute $Python -Argument ('"{0}" --config "{1}" --config-digest {2}' -f $script,$Config,$ConfigDigest) -WorkingDirectory $RepositoryRoot
$trigger=New-ScheduledTaskTrigger -Daily -At $at
$settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -MultipleInstances IgnoreNew
$principal=New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$task=New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Nobus Space verified quiescent daily backup; 7 daily and 4 weekly, recoverable quarantine'
if($PSCmdlet.ShouldProcess(
    $TaskName,
    $(if($ReplaceExisting){'Replace stopped disabled exact daily backup task'}else{'Register exact daily backup task'})
)){
    if($ReplaceExisting) {
        Register-ScheduledTask -TaskName $TaskName -TaskPath '\' -InputObject $task -Force | Out-Null
    } else {
        Register-ScheduledTask -TaskName $TaskName -TaskPath '\' -InputObject $task | Out-Null
    }
}
