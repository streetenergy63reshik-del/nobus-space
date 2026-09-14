param(
    [Parameter(Mandatory)][ValidateSet('Inspect','Disable','Enable','Start','Stop')][string]$Operation,
    [Parameter(Mandatory)][ValidatePattern('^NobusSpace[A-Za-z0-9-]{1,64}$')][string]$TaskName
)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$OutputEncoding=[Console]::OutputEncoding
try {
    $task=Get-ScheduledTask -TaskName $TaskName -TaskPath '\' -ErrorAction Stop
    switch($Operation) {
        'Disable' { $task | Disable-ScheduledTask | Out-Null }
        'Enable' { $task | Enable-ScheduledTask | Out-Null }
        'Start' { $task | Start-ScheduledTask }
        'Stop' { $task | Stop-ScheduledTask }
    }
    $task=Get-ScheduledTask -TaskName $TaskName -TaskPath '\'
    $info=$task | Get-ScheduledTaskInfo
    $principal=([System.Security.Principal.NTAccount]::new($task.Principal.UserId)).Translate([System.Security.Principal.SecurityIdentifier]).Value
    $currentPrincipal=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    [ordered]@{
        name=$task.TaskName; state=$task.State.ToString(); enabled=[bool]$task.Settings.Enabled
        last_result=[int64]$info.LastTaskResult
        current_principal=$currentPrincipal
        signature=[ordered]@{
            principal=$principal; logon_type=[int]$task.Principal.LogonType; run_level=[int]$task.Principal.RunLevel
            actions=@($task.Actions | ForEach-Object { [ordered]@{execute=$_.Execute; arguments=$_.Arguments; working_directory=$_.WorkingDirectory} })
            triggers=@($task.Triggers | ForEach-Object {
                $triggerUser=$_.UserId
                if(-not [string]::IsNullOrWhiteSpace([string]$triggerUser)) {
                    $triggerUser=([System.Security.Principal.NTAccount]::new(
                        [string]$triggerUser
                    )).Translate(
                        [System.Security.Principal.SecurityIdentifier]
                    ).Value
                }
                [ordered]@{
                    type=$_.CimClass.CimClassName; enabled=[bool]$_.Enabled
                    start=$_.StartBoundary; end=$_.EndBoundary; user=$triggerUser
                    days_interval=$_.DaysInterval; interval=$_.Repetition.Interval
                    duration=$_.Repetition.Duration; stop_at_end=$_.Repetition.StopAtDurationEnd
                    execution_limit=[string]$_.ExecutionTimeLimit; id=[string]$_.Id
                    delay=[string]$_.Delay; random_delay=[string]$_.RandomDelay
                }
            })
            start_when_available=[bool]$task.Settings.StartWhenAvailable
            disallow_battery=[bool]$task.Settings.DisallowStartIfOnBatteries
            stop_on_battery=[bool]$task.Settings.StopIfGoingOnBatteries
            wake_to_run=[bool]$task.Settings.WakeToRun
            restart_count=$task.Settings.RestartCount; restart_interval=$task.Settings.RestartInterval
            execution_limit=$task.Settings.ExecutionTimeLimit; multiple_instances=[int]$task.Settings.MultipleInstances
            compatibility=[int]$task.Settings.Compatibility
            allow_demand_start=[bool]$task.Settings.AllowDemandStart
            allow_hard_terminate=[bool]$task.Settings.AllowHardTerminate
            delete_expired_task_after=[string]$task.Settings.DeleteExpiredTaskAfter
            hidden=[bool]$task.Settings.Hidden; priority=[int]$task.Settings.Priority
            run_only_if_idle=[bool]$task.Settings.RunOnlyIfIdle
            idle_duration=[string]$task.Settings.IdleSettings.IdleDuration
            idle_wait_timeout=[string]$task.Settings.IdleSettings.WaitTimeout
            stop_on_idle_end=[bool]$task.Settings.IdleSettings.StopOnIdleEnd
            restart_on_idle=[bool]$task.Settings.IdleSettings.RestartOnIdle
            run_only_if_network=[bool]$task.Settings.RunOnlyIfNetworkAvailable
            network_id=[string]$task.Settings.NetworkSettings.Id
            network_name=[string]$task.Settings.NetworkSettings.Name
            disallow_remote_app_session=[bool]$task.Settings.DisallowStartOnRemoteAppSession
            unified_scheduling_engine=[bool]$task.Settings.UseUnifiedSchedulingEngine
            volatile=[bool]$task.Settings.volatile
            maintenance_settings_present=($null -ne $task.Settings.MaintenanceSettings)
        }
    } | ConvertTo-Json -Depth 6 -Compress
} catch {
    Write-Output '{"status":"FAIL","code":"scheduler_operation_unavailable"}'
    exit 1
}
