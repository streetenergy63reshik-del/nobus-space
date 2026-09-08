param(
    [Parameter(Mandatory)][ValidateSet('Inspect','Disable','Enable','Start')][string]$Operation,
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
    }
    $task=Get-ScheduledTask -TaskName $TaskName -TaskPath '\'
    $info=$task | Get-ScheduledTaskInfo
    $principal=([System.Security.Principal.NTAccount]::new($task.Principal.UserId)).Translate([System.Security.Principal.SecurityIdentifier]).Value
    [ordered]@{
        name=$task.TaskName; state=$task.State.ToString(); enabled=[bool]$task.Settings.Enabled
        last_result=[int64]$info.LastTaskResult
        signature=[ordered]@{
            principal=$principal; logon_type=[int]$task.Principal.LogonType; run_level=[int]$task.Principal.RunLevel
            actions=@($task.Actions | ForEach-Object { [ordered]@{execute=$_.Execute; arguments=$_.Arguments; working_directory=$_.WorkingDirectory} })
            triggers=@($task.Triggers | ForEach-Object { [ordered]@{
                type=$_.CimClass.CimClassName; enabled=[bool]$_.Enabled; start=$_.StartBoundary; end=$_.EndBoundary
                user=$_.UserId; days_interval=$_.DaysInterval; interval=$_.Repetition.Interval
                duration=$_.Repetition.Duration; stop_at_end=$_.Repetition.StopAtDurationEnd
            } })
            start_when_available=[bool]$task.Settings.StartWhenAvailable
            disallow_battery=[bool]$task.Settings.DisallowStartIfOnBatteries
            stop_on_battery=[bool]$task.Settings.StopIfGoingOnBatteries
            wake_to_run=[bool]$task.Settings.WakeToRun
            restart_count=$task.Settings.RestartCount; restart_interval=$task.Settings.RestartInterval
            execution_limit=$task.Settings.ExecutionTimeLimit; multiple_instances=[int]$task.Settings.MultipleInstances
        }
    } | ConvertTo-Json -Depth 6 -Compress
} catch {
    Write-Output '{"status":"FAIL","code":"scheduler_operation_unavailable"}'
    exit 1
}
