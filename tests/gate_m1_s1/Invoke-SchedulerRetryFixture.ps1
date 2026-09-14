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
$exhaustedTask = "NobusSpace-M1S1-Fixture-Budget-$($RunId.Substring(0, 8))"
$permanentTask = "NobusSpace-M1S1-Fixture-Permanent-$($RunId.Substring(0, 8))"
$taskNames = @($transientTask, $exhaustedTask, $permanentTask)
$transientReceipt = Join-Path $evidenceRoot 'transient.jsonl'
$exhaustedReceipt = Join-Path $evidenceRoot 'exhausted.jsonl'
$permanentReceipt = Join-Path $evidenceRoot 'permanent.jsonl'
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
$exhaustedRows = @()
$permanentRows = @()
$transientController = $null
$exhaustedController = $null
$permanentController = $null
$triggerAt = $null
$cleanupTaskStates = [ordered]@{}
$cleanupProcessCount = $null
$cleanupMutexesAbsent = $false
$cleanupEventsAbsent = $false
$cleanupDefinitionsAbsent = $false
$cleanupDeadlineSeconds = 30
$evidenceRootCreated = $false

function Get-Sha256Text([string] $Value) {
    $hash = [System.Security.Cryptography.SHA256]::HashData(
        [System.Text.Encoding]::UTF8.GetBytes($Value)
    )
    return 'sha256:' + [Convert]::ToHexString($hash).ToLowerInvariant()
}

function Get-FixtureObjectSuffix([string] $ReceiptPath) {
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::ASCII.GetBytes(
            $RunId + [IO.Path]::GetFileName($ReceiptPath)
        )
        $digest = $hasher.ComputeHash($bytes)
        $hex = -join @($digest | ForEach-Object { $_.ToString('x2') })
        return $hex.Substring(0, 32)
    }
    finally {
        $hasher.Dispose()
    }
}

function Test-MutexAbsent([string] $Name) {
    $handle = $null
    try {
        $handle = [Threading.Mutex]::OpenExisting($Name)
        return $false
    }
    catch [Threading.WaitHandleCannotBeOpenedException] {
        return $true
    }
    finally {
        if ($null -ne $handle) { $handle.Dispose() }
    }
}

function Test-EventAbsent([string] $Name) {
    $handle = $null
    try {
        $handle = [Threading.EventWaitHandle]::OpenExisting($Name)
        return $false
    }
    catch [Threading.WaitHandleCannotBeOpenedException] {
        return $true
    }
    finally {
        if ($null -ne $handle) { $handle.Dispose() }
    }
}

function Get-FixtureProcessCount(
    [string] $ExpectedRunId,
    [string] $ExpectedProbe
) {
    $count = 0
    foreach ($process in @(Get-CimInstance Win32_Process -ErrorAction Stop)) {
        if (
            [string] $process.Name -in @('python.exe','pythonw.exe') -and
            -not [string]::IsNullOrEmpty([string] $process.CommandLine) -and
            ([string] $process.CommandLine).Contains($ExpectedRunId) -and
            ([string] $process.CommandLine).Contains($ExpectedProbe)
        ) {
            $count += 1
        }
    }
    return $count
}

$fixtureObjectSuffixes = @(
    Get-FixtureObjectSuffix $transientReceipt
    Get-FixtureObjectSuffix $exhaustedReceipt
    Get-FixtureObjectSuffix $permanentReceipt
)
$fixtureMutexNames = @($fixtureObjectSuffixes | ForEach-Object {
    'Global\NobusSpaceM1S1Fixture-' + $_
})
$fixtureEventNames = @($fixtureObjectSuffixes | ForEach-Object {
    'Local\NobusSpaceM1S1Stop-' + $_
})

function Read-SafeRows(
    [string] $Path,
    [string] $ExpectedRunId,
    [string] $ExpectedControllerSha256,
    [ValidateSet('transient','permanent')]
    [string] $ExpectedFailureMode
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
        $expectedKeys = @('at','attempt','controller_sha256','exit_code','failure_mode','outcome','restart_budget','run_id','schema')
        if (
            (Compare-Object $keys $expectedKeys) -or
            $row.schema -cne 'nobus-m1-scheduler-fixture-2' -or
            $row.run_id -cne $ExpectedRunId -or
            $row.controller_sha256 -cne $ExpectedControllerSha256 -or
            $row.failure_mode -cne $ExpectedFailureMode -or
            [int] $row.attempt -ne ($rows.Count + 1) -or
            [int] $row.restart_budget -ne 2 -or
            [string] $row.outcome -notin @('retryable_failure','recovered','budget_exhausted','permanent_failure') -or
            [int] $row.exit_code -notin @(0,23,29) -or
            ($ExpectedFailureMode -ceq 'permanent' -and (
                [int] $row.attempt -ne 1 -or
                [string] $row.outcome -cne 'permanent_failure' -or
                [int] $row.exit_code -ne 29
            )) -or
            ($ExpectedFailureMode -ceq 'transient' -and [string] $row.outcome -ceq 'permanent_failure')
        ) {
            throw 'Fixture receipt schema is invalid.'
        }
        $rows += [ordered]@{
            at = [string] $row.at
            attempt = [int] $row.attempt
            outcome = [string] $row.outcome
            exit_code = [int] $row.exit_code
            failure_mode = [string] $row.failure_mode
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
    $evidenceRootCreated = $true
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
            failure_mode = 'transient'
        },
        @{
            name = $exhaustedTask
            receipt = $exhaustedReceipt
            succeed_on = 0
            failure_mode = 'transient'
        },
        @{
            name = $permanentTask
            receipt = $permanentReceipt
            succeed_on = 0
            failure_mode = 'permanent'
        }
    )
    foreach ($definition in $definitions) {
        $arguments = @(
            ('"' + $probe + '"'),
            '--receipt', ('"' + $definition.receipt + '"'),
            '--run-id', $RunId,
            '--restart-budget', [string] $restartBudget,
            '--succeed-on', [string] $definition.succeed_on,
            '--failure-mode', [string] $definition.failure_mode,
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
        $transientRows = @(Read-SafeRows $transientReceipt $RunId $controllerSha256 'transient')
        $exhaustedRows = @(Read-SafeRows $exhaustedReceipt $RunId $controllerSha256 'transient')
        $permanentRows = @(Read-SafeRows $permanentReceipt $RunId $controllerSha256 'permanent')
        $transientSnapshot = Get-TaskSnapshot $transientTask
        $exhaustedSnapshot = Get-TaskSnapshot $exhaustedTask
        $permanentSnapshot = Get-TaskSnapshot $permanentTask
        $observed = (
            $transientRows.Count -eq 2 -and
            $exhaustedRows.Count -eq $expectedAttempts -and
            $permanentRows.Count -eq 1 -and
            $transientSnapshot.state -cne 'Running' -and
            $exhaustedSnapshot.state -cne 'Running' -and
            $permanentSnapshot.state -cne 'Running' -and
            $transientSnapshot.last_result -eq 0 -and
            $exhaustedSnapshot.last_result -eq 23 -and
            $permanentSnapshot.last_result -eq 29 -and
            $transientSnapshot.restart_count -eq 0 -and
            $exhaustedSnapshot.restart_count -eq 0 -and
            $permanentSnapshot.restart_count -eq 0 -and
            [string]::IsNullOrEmpty($transientSnapshot.restart_interval) -and
            [string]::IsNullOrEmpty($exhaustedSnapshot.restart_interval) -and
            [string]::IsNullOrEmpty($permanentSnapshot.restart_interval) -and
            $transientSnapshot.multiple_instances -ceq 'IgnoreNew' -and
            $exhaustedSnapshot.multiple_instances -ceq 'IgnoreNew' -and
            $permanentSnapshot.multiple_instances -ceq 'IgnoreNew'
        )
    } while (-not $observed -and (Get-Date) -lt $deadline)

    if ($observed) {
        $stage = 'confirm_budget_stop'
        $confirmationDeadline = (Get-Date).AddSeconds(75)
        do {
            Start-Sleep -Seconds 2
            $confirmedTransient = @(Read-SafeRows $transientReceipt $RunId $controllerSha256 'transient')
            $confirmedExhausted = @(Read-SafeRows $exhaustedReceipt $RunId $controllerSha256 'transient')
            $confirmedPermanent = @(Read-SafeRows $permanentReceipt $RunId $controllerSha256 'permanent')
        } while (
            $confirmedTransient.Count -eq 2 -and
            $confirmedExhausted.Count -eq $expectedAttempts -and
            $confirmedPermanent.Count -eq 1 -and
            (Get-Date) -lt $confirmationDeadline
        )
        $stable = (
            $confirmedTransient.Count -eq 2 -and
            $confirmedExhausted.Count -eq $expectedAttempts -and
            $confirmedPermanent.Count -eq 1
        )
    }
    $snapshots = [ordered]@{
        transient = Get-TaskSnapshot $transientTask
        exhausted = Get-TaskSnapshot $exhaustedTask
        permanent = Get-TaskSnapshot $permanentTask
    }
    $transientRows = @(Read-SafeRows $transientReceipt $RunId $controllerSha256 'transient')
    $exhaustedRows = @(Read-SafeRows $exhaustedReceipt $RunId $controllerSha256 'transient')
    $permanentRows = @(Read-SafeRows $permanentReceipt $RunId $controllerSha256 'permanent')
    $transientController = Get-ControllerHistorySummary `
        $transientReceipt 'stop_planned' 2 0 'new'
    $exhaustedController = Get-ControllerHistorySummary `
        $exhaustedReceipt 'stop_budget_exhausted' 3 1 'blocked'
    $permanentController = Get-ControllerHistorySummary `
        $permanentReceipt 'stop_non_retryable' 1 1 'blocked'
    $stable = (
        $stable -and
        $snapshots.transient.state -cne 'Running' -and
        $snapshots.exhausted.state -cne 'Running' -and
        $snapshots.permanent.state -cne 'Running' -and
        $snapshots.transient.last_result -eq 0 -and
        $snapshots.exhausted.last_result -eq 23 -and
        $snapshots.permanent.last_result -eq 29 -and
        $snapshots.transient.restart_count -eq 0 -and
        $snapshots.exhausted.restart_count -eq 0 -and
        $snapshots.permanent.restart_count -eq 0 -and
        [string]::IsNullOrEmpty($snapshots.transient.restart_interval) -and
        [string]::IsNullOrEmpty($snapshots.exhausted.restart_interval) -and
        [string]::IsNullOrEmpty($snapshots.permanent.restart_interval) -and
        $snapshots.transient.multiple_instances -ceq 'IgnoreNew' -and
        $snapshots.exhausted.multiple_instances -ceq 'IgnoreNew' -and
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
    $cleanupOutcome = 'not_proven'
    try {
        foreach ($name in @($registered)) {
            $task = Get-ScheduledTask -TaskName $name -TaskPath '\' -ErrorAction SilentlyContinue
            if ($null -ne $task -and [string] $task.State -in @('Running','Queued')) {
                try {
                    Stop-ScheduledTask -TaskName $name -TaskPath '\' -ErrorAction Stop
                }
                catch {
                    $task = Get-ScheduledTask -TaskName $name -TaskPath '\' -ErrorAction SilentlyContinue
                    if ($null -ne $task -and [string] $task.State -in @('Running','Queued')) {
                        throw
                    }
                }
            }
        }

        $cleanupDeadline = (Get-Date).AddSeconds($cleanupDeadlineSeconds)
        do {
            $cleanupTaskStates = [ordered]@{}
            $tasksInactive = $true
            foreach ($name in @($registered)) {
                $task = Get-ScheduledTask -TaskName $name -TaskPath '\' -ErrorAction SilentlyContinue
                $state = if ($null -eq $task) { 'Absent' } else { [string] $task.State }
                $cleanupTaskStates[$name] = $state
                if ($state -in @('Running','Queued')) { $tasksInactive = $false }
            }
            $cleanupProcessCount = Get-FixtureProcessCount $RunId $probe
            $cleanupMutexesAbsent = @(
                $fixtureMutexNames | Where-Object { Test-MutexAbsent $_ }
            ).Count -eq $fixtureMutexNames.Count
            $cleanupEventsAbsent = @(
                $fixtureEventNames | Where-Object { Test-EventAbsent $_ }
            ).Count -eq $fixtureEventNames.Count
            $cleanupSettled = (
                $tasksInactive -and
                $cleanupProcessCount -eq 0 -and
                $cleanupMutexesAbsent -and
                $cleanupEventsAbsent
            )
            if (-not $cleanupSettled) { Start-Sleep -Milliseconds 250 }
        } while (-not $cleanupSettled -and (Get-Date) -lt $cleanupDeadline)

        if (-not $cleanupSettled) {
            throw 'Fixture cleanup could not be proven before its deadline.'
        }

        foreach ($name in @($registered)) {
            if (Get-ScheduledTask -TaskName $name -TaskPath '\' -ErrorAction SilentlyContinue) {
                Unregister-ScheduledTask -TaskName $name -TaskPath '\' -Confirm:$false -ErrorAction Stop
            }
        }
        $cleanupDefinitionsAbsent = $true
        foreach ($name in @($registered)) {
            if (Get-ScheduledTask -TaskName $name -TaskPath '\' -ErrorAction SilentlyContinue) {
                $cleanupDefinitionsAbsent = $false
            }
        }
        if (-not $cleanupDefinitionsAbsent) {
            throw 'Fixture task definitions remain after cleanup.'
        }
        $cleanupOutcome = 'proven'
    }
    catch {
        $cleanupOutcome = 'failed'
        if ($null -eq $cleanupProcessCount) {
            try { $cleanupProcessCount = Get-FixtureProcessCount $RunId $probe }
            catch { $cleanupProcessCount = $null }
        }
        if ($cleanupTaskStates.Count -eq 0) {
            foreach ($name in @($registered)) {
                try {
                    $task = Get-ScheduledTask -TaskName $name -TaskPath '\' -ErrorAction SilentlyContinue
                    $cleanupTaskStates[$name] = if ($null -eq $task) {
                        'Absent'
                    } else { [string] $task.State }
                }
                catch {
                    $cleanupTaskStates[$name] = 'UNKNOWN'
                }
            }
        }
    }
    if ($cleanupOutcome -eq 'failed' -and $null -eq $errorClass) {
        $errorClass = 'fixture_cleanup_failed'
    }
    if ($evidenceRootCreated -and (Test-Path -LiteralPath $evidenceRoot -PathType Container)) {
        $result = [ordered]@{
            schema = 'nobus-m1-scheduler-fixture-result-3'
            run_id = $RunId
            status = if ($null -eq $errorClass -and $cleanupOutcome -eq 'proven') { 'PASS' } else { 'FAIL' }
            error_class = $errorClass
            mechanism = 'Windows Task Scheduler action -> product mutex/recovery/history/attempt/Job/gated-helper/cleanup chain'
            action = [ordered]@{
                executable = [IO.Path]::GetFileName($pythonw)
                executable_bytes = [long](Get-Item -LiteralPath $pythonw).Length
                executable_sha256 = (Get-FileHash -LiteralPath $pythonw -Algorithm SHA256).Hash.ToLowerInvariant()
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
                trigger_at_utc = if ($null -ne $triggerAt) {
                    $triggerAt.ToUniversalTime().ToString('o')
                } else { $null }
                multiple_instances = 'IgnoreNew'
                principal = 'Interactive/Limited'
            }
            transient = [ordered]@{
                rows = @($transientRows)
                task = $snapshots.transient
                controller = $transientController
            }
            exhausted = [ordered]@{
                rows = @($exhaustedRows)
                task = $snapshots.exhausted
                controller = $exhaustedController
            }
            permanent = [ordered]@{
                rows = @($permanentRows)
                task = $snapshots.permanent
                controller = $permanentController
            }
            stop_confirmation_seconds = 75
            cleanup_outcome = $cleanupOutcome
            cleanup = [ordered]@{
                outcome = $cleanupOutcome
                deadline_seconds = $cleanupDeadlineSeconds
                task_states = $cleanupTaskStates
                process_count = $cleanupProcessCount
                mutexes_absent = $cleanupMutexesAbsent
                stop_events_absent = $cleanupEventsAbsent
                definitions_absent = $cleanupDefinitionsAbsent
            }
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
