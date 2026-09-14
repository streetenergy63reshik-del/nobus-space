[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9a-f]{32}$')]
    [string] $RunId,
    [string] $RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
    [Parameter(Mandatory)]
    [string] $Pythonw
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$pythonw = (Resolve-Path -LiteralPath $Pythonw).Path
$probe = Join-Path $root 'tests\fixtures\m1_scheduler_exit_probe.py'
$evidenceRoot = Join-Path $root ".runtime\m1-s1\scheduler-fixture\$RunId"
$transientTask = "NobusSpace-M1S1-Fixture-Transient-$($RunId.Substring(0, 8))"
$permanentTask = "NobusSpace-M1S1-Fixture-Permanent-$($RunId.Substring(0, 8))"
$taskNames = @($transientTask, $permanentTask)
$restartBudget = 2
$expectedAttempts = $restartBudget + 1
$registered = [System.Collections.Generic.List[string]]::new()
$stage = 'preflight'
$errorClass = $null
$cleanupOutcome = 'not_started'
$observed = $false
$stable = $false
$snapshots = @{}
$transientRows = @()
$permanentRows = @()

function Get-Sha256Text([string] $Value) {
    $hash = [System.Security.Cryptography.SHA256]::HashData(
        [System.Text.Encoding]::UTF8.GetBytes($Value)
    )
    return 'sha256:' + [Convert]::ToHexString($hash).ToLowerInvariant()
}

function Read-SafeRows([string] $Path, [string] $ExpectedRunId) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return @() }
    $item = Get-Item -LiteralPath $Path
    if ($item.Length -gt 8192 -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Fixture receipt is invalid.'
    }
    $rows = @()
    foreach ($line in @(Get-Content -LiteralPath $Path -Encoding Ascii)) {
        $row = $line | ConvertFrom-Json -AsHashtable
        $keys = @($row.Keys | Sort-Object)
        $expectedKeys = @('at','attempt','exit_code','outcome','restart_budget','run_id','schema')
        if (
            (Compare-Object $keys $expectedKeys) -or
            $row.schema -cne 'nobus-m1-scheduler-fixture-1' -or
            $row.run_id -cne $ExpectedRunId -or
            [int] $row.attempt -ne ($rows.Count + 1) -or
            [int] $row.restart_budget -ne 2 -or
            [string] $row.outcome -notin @('retryable_failure','recovered','budget_exhausted') -or
            [int] $row.exit_code -notin @(0,23)
        ) {
            throw 'Fixture receipt schema is invalid.'
        }
        $rows += [ordered]@{
            at = [string] $row.at
            attempt = [int] $row.attempt
            outcome = [string] $row.outcome
            exit_code = [int] $row.exit_code
        }
    }
    return @($rows)
}

function Get-TaskSnapshot([string] $Name) {
    $task = Get-ScheduledTask -TaskName $Name -TaskPath '\' -ErrorAction Stop
    $info = Get-ScheduledTaskInfo -TaskName $Name -TaskPath '\' -ErrorAction Stop
    $xml = Export-ScheduledTask -TaskName $Name -TaskPath '\' -ErrorAction Stop
    return [ordered]@{
        state = [string] $task.State
        last_result = [long] $info.LastTaskResult
        last_run_time = $info.LastRunTime.ToUniversalTime().ToString('o')
        definition_digest = Get-Sha256Text $xml
        restart_count = [int] $task.Settings.RestartCount
        restart_interval = [string] $task.Settings.RestartInterval
        multiple_instances = [string] $task.Settings.MultipleInstances
    }
}

try {
    foreach ($required in @($pythonw, $probe)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            throw 'Fixture input is unavailable.'
        }
    }
    foreach ($name in $taskNames) {
        if (Get-ScheduledTask -TaskName $name -TaskPath '\' -ErrorAction SilentlyContinue) {
            throw 'Fixture task name is already occupied.'
        }
    }
    if (Test-Path -LiteralPath $evidenceRoot) {
        throw 'Fixture evidence directory already exists.'
    }
    if (-not $PSCmdlet.ShouldProcess(($taskNames -join ', '), 'Register and run isolated retry fixtures')) {
        return
    }

    $stage = 'register'
    New-Item -ItemType Directory -Path $evidenceRoot | Out-Null
    $transientReceipt = Join-Path $evidenceRoot 'transient.jsonl'
    $permanentReceipt = Join-Path $evidenceRoot 'permanent.jsonl'
    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
        -MultipleInstances IgnoreNew
    $principal = New-ScheduledTaskPrincipal `
        -UserId "$env:USERDOMAIN\$env:USERNAME" `
        -LogonType Interactive `
        -RunLevel Limited
    $triggerAt = (Get-Date).AddSeconds(20)
    $trigger = New-ScheduledTaskTrigger -Once -At $triggerAt
    $definitions = @(
        @{
            name = $transientTask
            receipt = $transientReceipt
            succeed_on = 2
        },
        @{
            name = $permanentTask
            receipt = $permanentReceipt
            succeed_on = 0
        }
    )
    foreach ($definition in $definitions) {
        $arguments = @(
            ('"' + $probe + '"'),
            '--receipt', ('"' + $definition.receipt + '"'),
            '--run-id', $RunId,
            '--restart-budget', [string] $restartBudget,
            '--succeed-on', [string] $definition.succeed_on,
            '--controller',
            '--retry-interval-seconds', '60'
        ) -join ' '
        $action = New-ScheduledTaskAction -Execute $pythonw -Argument $arguments -WorkingDirectory $root
        $task = New-ScheduledTask `
            -Action $action `
            -Trigger $trigger `
            -Settings $settings `
            -Principal $principal `
            -Description 'Nobus Space M1-S1 isolated scheduler-hosted recovery fixture; no production input'
        Register-ScheduledTask -TaskName $definition.name -TaskPath '\' -InputObject $task | Out-Null
        $registered.Add($definition.name)
    }

    $stage = 'observe'
    $deadline = (Get-Date).AddMinutes(4)
    do {
        Start-Sleep -Seconds 2
        $transientRows = @(Read-SafeRows $transientReceipt $RunId)
        $permanentRows = @(Read-SafeRows $permanentReceipt $RunId)
        $transientSnapshot = Get-TaskSnapshot $transientTask
        $permanentSnapshot = Get-TaskSnapshot $permanentTask
        $observed = (
            $transientRows.Count -eq 2 -and
            $permanentRows.Count -eq $expectedAttempts -and
            $transientSnapshot.state -cne 'Running' -and
            $permanentSnapshot.state -cne 'Running' -and
            $transientSnapshot.last_result -eq 0 -and
            $permanentSnapshot.last_result -eq 23 -and
            $transientSnapshot.restart_count -eq 0 -and
            $permanentSnapshot.restart_count -eq 0 -and
            [string]::IsNullOrEmpty($transientSnapshot.restart_interval) -and
            [string]::IsNullOrEmpty($permanentSnapshot.restart_interval) -and
            $transientSnapshot.multiple_instances -ceq 'IgnoreNew' -and
            $permanentSnapshot.multiple_instances -ceq 'IgnoreNew'
        )
    } while (-not $observed -and (Get-Date) -lt $deadline)

    if ($observed) {
        $stage = 'confirm_budget_stop'
        $confirmationDeadline = (Get-Date).AddSeconds(75)
        do {
            Start-Sleep -Seconds 2
            $confirmedTransient = @(Read-SafeRows $transientReceipt $RunId)
            $confirmedPermanent = @(Read-SafeRows $permanentReceipt $RunId)
        } while (
            $confirmedTransient.Count -eq 2 -and
            $confirmedPermanent.Count -eq $expectedAttempts -and
            (Get-Date) -lt $confirmationDeadline
        )
        $stable = (
            $confirmedTransient.Count -eq 2 -and
            $confirmedPermanent.Count -eq $expectedAttempts
        )
    }
    $snapshots = [ordered]@{
        transient = Get-TaskSnapshot $transientTask
        permanent = Get-TaskSnapshot $permanentTask
    }
    $transientRows = @(Read-SafeRows $transientReceipt $RunId)
    $permanentRows = @(Read-SafeRows $permanentReceipt $RunId)
    $stable = (
        $stable -and
        $snapshots.transient.state -cne 'Running' -and
        $snapshots.permanent.state -cne 'Running' -and
        $snapshots.transient.last_result -eq 0 -and
        $snapshots.permanent.last_result -eq 23 -and
        $snapshots.transient.restart_count -eq 0 -and
        $snapshots.permanent.restart_count -eq 0 -and
        [string]::IsNullOrEmpty($snapshots.transient.restart_interval) -and
        [string]::IsNullOrEmpty($snapshots.permanent.restart_interval) -and
        $snapshots.transient.multiple_instances -ceq 'IgnoreNew' -and
        $snapshots.permanent.multiple_instances -ceq 'IgnoreNew'
    )
    if (-not ($observed -and $stable)) {
        $errorClass = 'scheduler_hosted_recovery_contract_not_observed'
    }
}
catch {
    $errorClass = switch ($stage) {
        'preflight' { 'fixture_preflight_failed' }
        'register' { 'fixture_registration_failed' }
        'observe' { 'fixture_observation_failed' }
        'confirm_budget_stop' { 'fixture_confirmation_failed' }
        default { 'fixture_failed' }
    }
}
finally {
    $stage = 'cleanup'
    $cleanupOutcome = 'proven'
    foreach ($name in @($registered)) {
        try {
            Unregister-ScheduledTask -TaskName $name -TaskPath '\' -Confirm:$false -ErrorAction Stop
        }
        catch {
            $cleanupOutcome = 'failed'
        }
    }
    foreach ($name in $taskNames) {
        if (Get-ScheduledTask -TaskName $name -TaskPath '\' -ErrorAction SilentlyContinue) {
            $cleanupOutcome = 'failed'
        }
    }
    if ($cleanupOutcome -eq 'failed' -and $null -eq $errorClass) {
        $errorClass = 'fixture_cleanup_failed'
    }
    if (Test-Path -LiteralPath $evidenceRoot -PathType Container) {
        $result = [ordered]@{
            schema = 'nobus-m1-scheduler-fixture-result-1'
            run_id = $RunId
            status = if ($null -eq $errorClass -and $cleanupOutcome -eq 'proven') { 'PASS' } else { 'FAIL' }
            error_class = $errorClass
            mechanism = 'Windows Task Scheduler action -> candidate bounded recovery controller'
            action = [ordered]@{
                executable = 'pythonw.exe'
                probe_sha256 = (Get-FileHash -LiteralPath $probe -Algorithm SHA256).Hash.ToLowerInvariant()
            }
            config = [ordered]@{
                scheduler_restart_count = 0
                scheduler_restart_interval = $null
                controller_retry_budget = $restartBudget
                controller_retry_interval_seconds = 60
                total_attempts = $expectedAttempts
                trigger = 'one_time'
                multiple_instances = 'IgnoreNew'
                principal = 'Interactive/Limited'
            }
            transient = [ordered]@{
                rows = @($transientRows)
                task = $snapshots.transient
            }
            permanent = [ordered]@{
                rows = @($permanentRows)
                task = $snapshots.permanent
            }
            stop_confirmation_seconds = 75
            cleanup_outcome = $cleanupOutcome
        }
        $resultPath = Join-Path $evidenceRoot 'result.json'
        [IO.File]::WriteAllText(
            $resultPath,
            ($result | ConvertTo-Json -Depth 8 -Compress),
            [Text.UTF8Encoding]::new($false)
        )
        Write-Output ($result | ConvertTo-Json -Depth 8 -Compress)
    }
}

if ($null -ne $errorClass -or $cleanupOutcome -ne 'proven') { exit 1 }
exit 0
