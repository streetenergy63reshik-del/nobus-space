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
$controller = Join-Path $root 'scripts\run_nobus_space_live.py'
$controllerSha256 = $null
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
$transientController = $null
$permanentController = $null

function Get-Sha256Text([string] $Value) {
    $hash = [System.Security.Cryptography.SHA256]::HashData(
        [System.Text.Encoding]::UTF8.GetBytes($Value)
    )
    return 'sha256:' + [Convert]::ToHexString($hash).ToLowerInvariant()
}

function Read-SafeRows(
    [string] $Path,
    [string] $ExpectedRunId,
    [string] $ExpectedControllerSha256
) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return @() }
    $item = Get-Item -LiteralPath $Path
    if ($item.Length -gt 8192 -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Fixture receipt is invalid.'
    }
    $rows = @()
    foreach ($line in @(Get-Content -LiteralPath $Path -Encoding Ascii)) {
        $row = $line | ConvertFrom-Json -AsHashtable
        $keys = @($row.Keys | Sort-Object)
        $expectedKeys = @('at','attempt','controller_sha256','exit_code','outcome','restart_budget','run_id','schema')
        if (
            (Compare-Object $keys $expectedKeys) -or
            $row.schema -cne 'nobus-m1-scheduler-fixture-2' -or
            $row.run_id -cne $ExpectedRunId -or
            $row.controller_sha256 -cne $ExpectedControllerSha256 -or
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
            controller_sha256 = [string] $row.controller_sha256
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

function Get-ControllerHistorySummary(
    [string] $ReceiptPath,
    [string] $ExpectedDisposition,
    [int] $ExpectedAttempt,
    [int] $ExpectedExit,
    [string] $ExpectedState
) {
    $directory = Join-Path (
        Split-Path -Parent $ReceiptPath
    ) ('controller-' + [IO.Path]::GetFileNameWithoutExtension($ReceiptPath))
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
        throw 'Controller history directory is unavailable.'
    }
    $directoryItem = Get-Item -LiteralPath $directory
    if ($directoryItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'Controller history directory is invalid.'
    }
    $allowed = @(
        'runner-supervisor-v3.jsonl',
        'runner-supervisor-v3.jsonl.previous',
        'runner-supervisor.log',
        'runner-supervisor.log.previous'
    )
    $files = @(Get-ChildItem -LiteralPath $directory -Force)
    if (
        $files.Count -eq 0 -or
        @($files | Where-Object {
            -not $_.PSIsContainer -and
            $_.Name -in $allowed -and
            -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint)
        }).Count -ne $files.Count
    ) {
        throw 'Controller history inventory is invalid.'
    }
    $historyFiles = @(
        'runner-supervisor-v3.jsonl.previous',
        'runner-supervisor-v3.jsonl'
    ) | ForEach-Object {
        $candidate = Join-Path $directory $_
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            Get-Item -LiteralPath $candidate
        }
    }
    if ($historyFiles.Count -eq 0) {
        throw 'Controller structured history is unavailable.'
    }
    $rows = @()
    $lastDigest = $null
    foreach ($file in $historyFiles) {
        if (
            $file.Length -le 0 -or $file.Length -gt 1MB -or
            ($file.Attributes -band [IO.FileAttributes]::ReparsePoint)
        ) {
            throw 'Controller structured history is invalid.'
        }
        foreach ($line in @(Get-Content -LiteralPath $file.FullName -Encoding Ascii)) {
            if ($line.Length -gt 2048) {
                throw 'Controller structured history row is invalid.'
            }
            $rows += $line | ConvertFrom-Json -AsHashtable
            $lastDigest = Get-Sha256Text ($line + "`n")
        }
    }
    $last = $rows[-1]
    if (
        $last.schema -cne 'nobus-runtime-event-3' -or
        $last.event -cne 'control_closed' -or
        $last.recovery_disposition -cne $ExpectedDisposition -or
        [int] $last.attempt -ne $ExpectedAttempt -or
        [int] $last.retry_budget -ne 2 -or
        [int] $last.supervisor_exit_code -ne $ExpectedExit -or
        $last.cleanup_outcome -cne 'proven' -or
        [string] $last.activation_binding -notmatch '^sha256:[0-9a-f]{64}$' -or
        [string] $last.previous_event_digest -notmatch '^sha256:[0-9a-f]{64}$'
    ) {
        throw 'Controller final history state is invalid.'
    }
    return [ordered]@{
        files = @($files | Sort-Object Name | ForEach-Object {
            [ordered]@{
                name = $_.Name
                bytes = [long] $_.Length
                sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            }
        })
        structured_rows = $rows.Count
        readback_state = $ExpectedState
        final = [ordered]@{
            event = [string] $last.event
            attempt = [int] $last.attempt
            retry_budget = [int] $last.retry_budget
            recovery_disposition = [string] $last.recovery_disposition
            supervisor_exit_code = [int] $last.supervisor_exit_code
            cleanup_outcome = [string] $last.cleanup_outcome
            activation_binding = [string] $last.activation_binding
            event_digest = $lastDigest
        }
    }
}

try {
    foreach ($required in @($pythonw, $probe, $controller)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            throw 'Fixture input is unavailable.'
        }
    }
    $controllerSha256 = (Get-FileHash -LiteralPath $controller -Algorithm SHA256).Hash.ToLowerInvariant()
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
            '--controller-sha256', $controllerSha256,
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
        $transientRows = @(Read-SafeRows $transientReceipt $RunId $controllerSha256)
        $permanentRows = @(Read-SafeRows $permanentReceipt $RunId $controllerSha256)
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
            $confirmedTransient = @(Read-SafeRows $transientReceipt $RunId $controllerSha256)
            $confirmedPermanent = @(Read-SafeRows $permanentReceipt $RunId $controllerSha256)
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
    $transientRows = @(Read-SafeRows $transientReceipt $RunId $controllerSha256)
    $permanentRows = @(Read-SafeRows $permanentReceipt $RunId $controllerSha256)
    $transientController = Get-ControllerHistorySummary `
        $transientReceipt 'stop_planned' 2 0 'new'
    $permanentController = Get-ControllerHistorySummary `
        $permanentReceipt 'stop_budget_exhausted' 3 1 'blocked'
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
            schema = 'nobus-m1-scheduler-fixture-result-2'
            run_id = $RunId
            status = if ($null -eq $errorClass -and $cleanupOutcome -eq 'proven') { 'PASS' } else { 'FAIL' }
            error_class = $errorClass
            mechanism = 'Windows Task Scheduler action -> product mutex/recovery/history/attempt/Job/gated-helper/cleanup chain'
            action = [ordered]@{
                executable = 'pythonw.exe'
                probe_sha256 = (Get-FileHash -LiteralPath $probe -Algorithm SHA256).Hash.ToLowerInvariant()
                controller_sha256 = $controllerSha256
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
                controller = $transientController
            }
            permanent = [ordered]@{
                rows = @($permanentRows)
                task = $snapshots.permanent
                controller = $permanentController
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
