param(
    [ValidateSet('Snapshot', 'CreateAndSubmit', 'OpenAndSubmit', 'OpenExisting', 'SubmitExactDraft')]
    [string]$Action = 'Snapshot',
    [Parameter(Mandatory = $true)][string]$ProjectName,
    [string]$TaskTitle = '',
    [string]$PromptFile = '',
    [Parameter(Mandatory = $true)][string]$AllowedPromptRoot,
    [Parameter(Mandatory = $true)][string]$ExpectedDesktopVersion,
    [switch]$InspectProjectContext
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class NobusDesktopWindows {
    public delegate bool EnumWindowsProc(IntPtr handle, IntPtr state);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc callback, IntPtr state);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr handle);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr handle, StringBuilder name, int capacity);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr handle, out uint processId);
}
'@

function Get-CodexDocument {
    $documents = [System.Collections.Generic.List[object]]::new()
    $script:discoveryFrames = 0
    $script:discoveryCodex = 0
    $script:discoveryVersion = 0
    $script:discoveryRoots = 0
    $script:discoveryErrors = 0
    $script:discoveryDescendants = 0
    $script:discoveryRootMatches = 0
    $script:discoveryRootSummary = ''
    $script:discoveryWebIds = [System.Collections.Generic.HashSet[string]]::new()
    [NobusDesktopWindows]::EnumWindows({
        param($handle, $state)
        if (-not [NobusDesktopWindows]::IsWindowVisible($handle)) { return $true }
        $className = [Text.StringBuilder]::new(256)
        [void][NobusDesktopWindows]::GetClassName($handle, $className, 256)
        if ($className.ToString() -ne 'Chrome_WidgetWin_1') { return $true }
        $script:discoveryFrames++
        $processId = 0
        [void][NobusDesktopWindows]::GetWindowThreadProcessId($handle, [ref]$processId)
        try {
            $process = Get-Process -Id $processId -ErrorAction Stop
            $processName = $process.ProcessName
            $executablePath = $process.Path
        } catch { return $true }
        if ($processName -ne 'ChatGPT') { return $true }
        $script:discoveryCodex++
        $versionMatch = [regex]::Match($executablePath, 'OpenAI\.Codex_(\d+\.\d+\.\d+\.\d+)_', [Text.RegularExpressions.RegexOptions]::IgnoreCase)
        if (-not $versionMatch.Success -or $versionMatch.Groups[1].Value -ne $ExpectedDesktopVersion) { return $true }
        $script:discoveryVersion++
        $listener = [System.Windows.Automation.StructureChangedEventHandler]{
            param($sender, $eventArgs)
        }
        $listenerRegistered = $false
        $listenerTransferred = $false
        try {
            $window = [System.Windows.Automation.AutomationElement]::FromHandle($handle)
            # Chromium exposes only its native frame until a UIA client is
            # listening.  Keep a standard structure listener for the lifetime
            # of this action so the semantic web tree remains available.
            [System.Windows.Automation.Automation]::AddStructureChangedEventHandler(
                $window,
                [System.Windows.Automation.TreeScope]::Subtree,
                $listener
            )
            $listenerRegistered = $true
            $deadline = [DateTime]::UtcNow.AddSeconds(5)
            do {
                $all = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
                $script:discoveryDescendants = $all.Count
                $found = @()
                for ($index = 0; $index -lt $all.Count; $index++) {
                    $automationId = $all.Item($index).Current.AutomationId
                    if ($automationId -eq 'RootWebArea') { $found += $all.Item($index) }
                    if ($automationId -match '(?i)web|root|document') {
                        [void]$script:discoveryWebIds.Add($automationId)
                    }
                }
                $script:discoveryRootMatches = $found.Count
                if ($found.Count -ge 1) {
                    $appDocuments = @()
                    $appRootCondition = [System.Windows.Automation.PropertyCondition]::new(
                        [System.Windows.Automation.AutomationElement]::AutomationIdProperty,
                        'root'
                    )
                    foreach ($candidate in $found) {
                        $appRoots = $candidate.FindAll(
                            [System.Windows.Automation.TreeScope]::Descendants,
                            $appRootCondition
                        )
                        if ($appRoots.Count -eq 1) { $appDocuments += $candidate }
                    }
                    if ($appDocuments.Count -eq 1) { $found = @($appDocuments[0]) }
                }
                if ($found.Count -eq 1) { break }
                Start-Sleep -Milliseconds 100
            } while ([DateTime]::UtcNow -lt $deadline)
            if ($found.Count -gt 1) {
                $summaries = [System.Collections.Generic.List[string]]::new()
                for ($rootIndex = 0; $rootIndex -lt $found.Count; $rootIndex++) {
                    $children = $found[$rootIndex].FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
                    $projectMatches = 0
                    $createMatches = 0
                    $appRootMatches = 0
                    for ($childIndex = 0; $childIndex -lt $children.Count; $childIndex++) {
                        $child = $children.Item($childIndex)
                        if ($child.Current.AutomationId -eq 'root') { $appRootMatches++ }
                        if ($child.Current.Name -eq $ProjectName -and $child.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button) { $projectMatches++ }
                        if ($child.Current.Name -eq "Начать новый чат в папке $ProjectName" -and $child.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button) { $createMatches++ }
                    }
                    $summaries.Add("$rootIndex/$($children.Count)/$appRootMatches/$projectMatches/$createMatches")
                }
                $script:discoveryRootSummary = ($summaries -join ',')
            }
            if ($found.Count -eq 1) {
                $script:discoveryRoots++
                $listenerTransferred = $true
                $documents.Add([pscustomobject]@{
                    Element = $found[0]
                    Window = $window
                    Listener = $listener
                    ProcessId = [int]$processId
                    DesktopVersion = $versionMatch.Groups[1].Value
                })
            }
        } catch { $script:discoveryErrors++ } finally {
            if ($listenerRegistered -and -not $listenerTransferred) {
                [System.Windows.Automation.Automation]::RemoveStructureChangedEventHandler(
                    $window,
                    $listener
                )
            }
        }
        return $true
    }, [IntPtr]::Zero) | Out-Null
    if ($documents.Count -ne 1) {
        foreach ($candidate in $documents) {
            [System.Windows.Automation.Automation]::RemoveStructureChangedEventHandler(
                $candidate.Window,
                $candidate.Listener
            )
        }
        $webIds = ($script:discoveryWebIds | Sort-Object) -join ','
        throw "Expected one Codex document, found $($documents.Count); visible_frames=$script:discoveryFrames codex_frames=$script:discoveryCodex version_frames=$script:discoveryVersion roots=$script:discoveryRoots root_matches=$script:discoveryRootMatches root_summary=index/children/app_root/project/create:$script:discoveryRootSummary descendants=$script:discoveryDescendants web_ids=$webIds uia_errors=$script:discoveryErrors"
    }
    return $documents[0]
}

function Get-Pattern {
    param($Element, $Pattern)
    $value = $null
    if (-not $Element.TryGetCurrentPattern($Pattern, [ref]$value)) { return $null }
    return $value
}

function Test-ListItemAncestor {
    param($Element)
    $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
    $parent = $walker.GetParent($Element)
    for ($depth = 0; $depth -lt 8 -and $null -ne $parent; $depth++) {
        if ($parent.Current.ControlType -eq [System.Windows.Automation.ControlType]::ListItem) { return $true }
        $parent = $walker.GetParent($parent)
    }
    return $false
}

function Find-Exact {
    param($Root, [string]$Name, $ControlType, $Pattern, [switch]$InListItem)
    $all = $Root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    $matches = [System.Collections.Generic.List[object]]::new()
    for ($index = 0; $index -lt $all.Count; $index++) {
        $element = $all.Item($index)
        try {
            if ($element.Current.Name -ne $Name -or $element.Current.ControlType -ne $ControlType -or -not $element.Current.IsEnabled) { continue }
            if ($InListItem -and -not (Test-ListItemAncestor $element)) { continue }
            $patternValue = Get-Pattern $element $Pattern
            if ($null -ne $patternValue) { $matches.Add([pscustomobject]@{ Element = $element; Pattern = $patternValue }) }
        } catch { }
    }
    if ($matches.Count -ne 1) { throw "Selector expected one match, found $($matches.Count)" }
    return $matches[0]
}

function Wait-Exact {
    param($Root, [string]$Name, $ControlType, $Pattern, [switch]$InListItem, [int]$TimeoutMs = 10000)
    $deadline = [DateTime]::UtcNow.AddMilliseconds($TimeoutMs)
    $lastError = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        try { return Find-Exact $Root $Name $ControlType $Pattern -InListItem:$InListItem } catch { $lastError = $_ }
        Start-Sleep -Milliseconds 200
    }
    throw $lastError
}

function Read-Prompt {
    if ([string]::IsNullOrWhiteSpace($PromptFile)) { throw 'PromptFile is required' }
    $root = [IO.Path]::GetFullPath($AllowedPromptRoot).TrimEnd([IO.Path]::DirectorySeparatorChar)
    $resolved = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $PromptFile).Path)
    $prefix = $root + [IO.Path]::DirectorySeparatorChar
    if (-not $resolved.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'PromptFile is outside allowed directory' }
    $text = [IO.File]::ReadAllText($resolved, [Text.Encoding]::UTF8)
    if ([string]::IsNullOrWhiteSpace($text) -or $text.Length -gt 12000 -or $text.Contains([char]0)) { throw 'Prompt is invalid' }
    return $text
}

function Assert-ActiveTaskHeader {
    param($Root, [string]$Title)
    $all = $Root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    $count = 0
    for ($index = 0; $index -lt $all.Count; $index++) {
        $element = $all.Item($index)
        try {
            if ($element.Current.Name -eq $Title -and
                $element.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button -and
                -not (Test-ListItemAncestor $element) -and
                -not $element.Current.IsOffscreen) { $count++ }
        } catch { }
    }
    if ($count -ne 1) { throw 'Active task header changed; prompt was not sent' }
}

function Assert-NewTaskProjectContext {
    param($Root, [string]$Project)
    $all = $Root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    $projectCount = 0
    $newTaskCount = 0
    for ($index = 0; $index -lt $all.Count; $index++) {
        $element = $all.Item($index)
        try {
            if ($element.Current.IsOffscreen -or
                $element.Current.ControlType -ne [System.Windows.Automation.ControlType]::Button -or
                (Test-ListItemAncestor $element)) { continue }
            if ($element.Current.Name -ceq $Project) { $projectCount++ }
            if ($element.Current.Name -cmatch '^\u041d\u043e\u0432\u044b\u0439 \u0447\u0430\u0442$') { $newTaskCount++ }
        } catch { }
    }
    # The main view can coexist with one global New Chat control in this
    # Desktop version. The unique active project button is the binding guard.
    if ($projectCount -ne 1 -or $newTaskCount -lt 1 -or $newTaskCount -gt 2) {
        throw 'New task project context changed; prompt was not sent'
    }
}

function Submit-Prompt {
    param($Root, [string]$Prompt, [string]$ExpectedTaskTitle = '', [string]$ExpectedProjectName = '')
    $script:uiaStage = 'check-active-context'
    if (-not [string]::IsNullOrWhiteSpace($ExpectedTaskTitle)) {
        Assert-ActiveTaskHeader $Root $ExpectedTaskTitle
    }
    if (-not [string]::IsNullOrWhiteSpace($ExpectedProjectName)) {
        Assert-NewTaskProjectContext $Root $ExpectedProjectName
    }
    $script:uiaStage = 'find-composer'
    $composer = Wait-Exact $Root 'Поручите что угодно' ([System.Windows.Automation.ControlType]::Edit) ([System.Windows.Automation.ValuePattern]::Pattern) -TimeoutMs 15000
    if ($composer.Element.Current.IsOffscreen) {
        $scroll = Get-Pattern $composer.Element ([System.Windows.Automation.ScrollItemPattern]::Pattern)
        if ($null -eq $scroll) { throw 'Composer is offscreen without ScrollItem' }
        $scroll.ScrollIntoView()
    }
    $script:uiaStage = 'check-draft-empty'
    # Chromium UIA exposes the visually empty contenteditable as LF followed
    # by its accessible placeholder. Do not trim arbitrary user text.
    $placeholderValue = "`n" + $composer.Element.Current.Name
    $initialValue = $composer.Pattern.Current.Value
    if (-not [string]::IsNullOrEmpty($initialValue) -and
        $initialValue -cne $placeholderValue) {
        throw 'Composer has an existing draft; no input was changed'
    }
    $script:uiaStage = 'set-composer'
    $composer.Pattern.SetValue($Prompt)
    $valueDeadline = [DateTime]::UtcNow.AddSeconds(3)
    while ($composer.Pattern.Current.Value -cne $Prompt -and
        [DateTime]::UtcNow -lt $valueDeadline) {
        Start-Sleep -Milliseconds 100
    }
    if ($composer.Pattern.Current.Value -cne $Prompt) {
        throw 'Composer did not retain the exact prompt; send was stopped'
    }
    $script:uiaStage = 'find-send-control'
    $send = Wait-Exact $Root 'Отправить' ([System.Windows.Automation.ControlType]::Button) ([System.Windows.Automation.InvokePattern]::Pattern) -TimeoutMs 10000
    if ($composer.Pattern.Current.Value -cne $Prompt) {
        throw 'Composer changed before send; prompt was not sent'
    }
    $script:uiaStage = 'recheck-active-context'
    if (-not [string]::IsNullOrWhiteSpace($ExpectedTaskTitle)) {
        Assert-ActiveTaskHeader $Root $ExpectedTaskTitle
    }
    if (-not [string]::IsNullOrWhiteSpace($ExpectedProjectName)) {
        Assert-NewTaskProjectContext $Root $ExpectedProjectName
    }
    $script:uiaStage = 'invoke-send-control'
    $send.Pattern.Invoke()
}

function Submit-ExactDraft {
    param($Root, [string]$Prompt, [string]$ExpectedProjectName)
    $script:uiaStage = 'check-exact-draft'
    Assert-NewTaskProjectContext $Root $ExpectedProjectName
    $composer = Wait-Exact $Root 'Поручите что угодно' ([System.Windows.Automation.ControlType]::Edit) ([System.Windows.Automation.ValuePattern]::Pattern) -TimeoutMs 10000
    if ($composer.Pattern.Current.Value -cne $Prompt) {
        throw 'Existing Desktop draft is not the exact expected prompt; send was stopped'
    }
    $script:uiaStage = 'find-send-control'
    $send = Wait-Exact $Root 'Отправить' ([System.Windows.Automation.ControlType]::Button) ([System.Windows.Automation.InvokePattern]::Pattern) -TimeoutMs 10000
    $script:uiaStage = 'recheck-active-context'
    Assert-NewTaskProjectContext $Root $ExpectedProjectName
    if ($composer.Pattern.Current.Value -cne $Prompt) {
        throw 'Existing Desktop draft changed before send; send was stopped'
    }
    $script:uiaStage = 'invoke-send-control'
    $send.Pattern.Invoke()
}

$desktop = Get-CodexDocument
$bootstrapMutex = $null
$bootstrapLockHeld = $false
$script:uiaStage = 'prepare-action'
try {
    $document = $desktop.Element
    $result = [ordered]@{ action = $Action; desktop_version = $desktop.DesktopVersion; process_id = $desktop.ProcessId; mutations = @() }
    if ($Action -eq 'Snapshot') {
        if ($ProjectName -ne 'snapshot') {
            $project = Find-Exact $document $ProjectName ([System.Windows.Automation.ControlType]::Button) ([System.Windows.Automation.ExpandCollapsePattern]::Pattern) -InListItem
            $result.project_found = $true
            $result.project_expanded = ($project.Pattern.Current.ExpandCollapseState -eq [System.Windows.Automation.ExpandCollapseState]::Expanded)
        }
        if ($InspectProjectContext) {
            $candidates = [System.Collections.Generic.List[object]]::new()
            $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
            $all = $document.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
            for ($index = 0; $index -lt $all.Count; $index++) {
                $element = $all.Item($index)
                try {
                    if ($element.Current.Name -ne $ProjectName -or $element.Current.IsOffscreen) { continue }
                    $trail = [System.Collections.Generic.List[string]]::new()
                    $ancestor = $element
                    for ($depth = 0; $depth -lt 6 -and $null -ne $ancestor; $depth++) {
                        $trail.Add($ancestor.Current.ControlType.ProgrammaticName + '/' + $ancestor.Current.AutomationId)
                        $ancestor = $walker.GetParent($ancestor)
                    }
                    $candidates.Add([pscustomobject]@{
                        control_type = $element.Current.ControlType.ProgrammaticName
                        automation_id = $element.Current.AutomationId
                        ancestor_types_and_ids = @($trail.ToArray())
                    })
                } catch { }
            }
            $result.project_context_candidates = @($candidates.ToArray())
            $activeProjectButtons = 0
            $visibleNewChatButtons = 0
            $newChatStructures = [System.Collections.Generic.List[object]]::new()
            for ($index = 0; $index -lt $all.Count; $index++) {
                $element = $all.Item($index)
                try {
                    if ($element.Current.IsOffscreen -or
                        $element.Current.ControlType -ne [System.Windows.Automation.ControlType]::Button -or
                        (Test-ListItemAncestor $element)) { continue }
                    if ($element.Current.Name -ceq $ProjectName) { $activeProjectButtons++ }
                    if ($element.Current.Name -cmatch '^\u041d\u043e\u0432\u044b\u0439 \u0447\u0430\u0442$') {
                        $visibleNewChatButtons++
                        $trail = [System.Collections.Generic.List[string]]::new()
                        $ancestor = $element
                        for ($depth = 0; $depth -lt 7 -and $null -ne $ancestor; $depth++) {
                            $trail.Add($ancestor.Current.ControlType.ProgrammaticName + '/' + $ancestor.Current.AutomationId)
                            $ancestor = $walker.GetParent($ancestor)
                        }
                        $newChatStructures.Add([pscustomobject]@{
                            automation_id = $element.Current.AutomationId
                            ancestor_types_and_ids = @($trail.ToArray())
                        })
                    }
                } catch { }
            }
            $result.active_project_button_count = $activeProjectButtons
            $result.visible_new_chat_button_count = $visibleNewChatButtons
            $result.new_chat_structures = @($newChatStructures.ToArray())
            try {
                Assert-NewTaskProjectContext $document $ProjectName
                $result.new_task_project_context_verified = $true
            } catch {
                $result.new_task_project_context_verified = $false
            }
        }
        if (-not [string]::IsNullOrWhiteSpace($TaskTitle)) {
            $headerCount = 0
            $sidebarCount = 0
            $sidebarSelected = 0
            $all = $document.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
            for ($index = 0; $index -lt $all.Count; $index++) {
                $element = $all.Item($index)
                try {
                    if ($element.Current.Name -ne $TaskTitle -or $element.Current.ControlType -ne [System.Windows.Automation.ControlType]::Button) { continue }
                    if (Test-ListItemAncestor $element) {
                        $sidebarCount++
                        $selection = Get-Pattern $element ([System.Windows.Automation.SelectionItemPattern]::Pattern)
                        if ($null -ne $selection -and $selection.Current.IsSelected) { $sidebarSelected++ }
                    } else {
                        $headerCount++
                    }
                } catch { }
            }
            $result.task_header_count = $headerCount
            $result.task_sidebar_count = $sidebarCount
            $result.task_sidebar_selected_count = $sidebarSelected
        }
    }
    if ($Action -ne 'Snapshot') {
        $script:uiaStage = 'acquire-bootstrap-lock'
        $bootstrapMutex = [System.Threading.Mutex]::new($false, 'Local\NobusCodexDesktopBootstrap')
        try {
            $bootstrapLockHeld = $bootstrapMutex.WaitOne(30000)
        } catch [System.Threading.AbandonedMutexException] {
            throw 'Prior Desktop bootstrap ended without a confirmed outcome; inspect Desktop before retry'
        }
        if (-not $bootstrapLockHeld) { throw 'Another Desktop bootstrap is active' }
        if ($Action -ne 'OpenExisting') {
            $script:uiaStage = 'read-prompt'
            $prompt = Read-Prompt
        }
        if ($Action -eq 'CreateAndSubmit') {
            $script:uiaStage = 'find-project'
            $project = Find-Exact $document $ProjectName ([System.Windows.Automation.ControlType]::Button) ([System.Windows.Automation.ExpandCollapsePattern]::Pattern) -InListItem
            if ($project.Pattern.Current.ExpandCollapseState -eq [System.Windows.Automation.ExpandCollapseState]::Collapsed) {
                $project.Pattern.Expand(); $result.mutations += 'expanded-project'; Start-Sleep -Milliseconds 300
            }
            $script:uiaStage = 'find-create-control'
            $create = Wait-Exact $document "Начать новый чат в папке $ProjectName" ([System.Windows.Automation.ControlType]::Button) ([System.Windows.Automation.InvokePattern]::Pattern) -TimeoutMs 5000
            if ($create.Element.Current.IsOffscreen) {
                $scroll = Get-Pattern $create.Element ([System.Windows.Automation.ScrollItemPattern]::Pattern)
                if ($null -eq $scroll) { throw 'Create task is offscreen without ScrollItem' }
                $scroll.ScrollIntoView(); $result.mutations += 'scrolled-create-task'; Start-Sleep -Milliseconds 300
            }
            $script:uiaStage = 'invoke-create-control'
            $create.Pattern.Invoke(); $result.mutations += 'invoked-create-task'; Start-Sleep -Milliseconds 500
        } elseif ($Action -in @('OpenAndSubmit', 'OpenExisting')) {
            $script:uiaStage = 'find-task'
            if ([string]::IsNullOrWhiteSpace($TaskTitle)) { throw 'TaskTitle is required' }
            $task = Find-Exact $document $TaskTitle ([System.Windows.Automation.ControlType]::Button) ([System.Windows.Automation.InvokePattern]::Pattern) -InListItem
            if ($task.Element.Current.IsOffscreen) {
                $scroll = Get-Pattern $task.Element ([System.Windows.Automation.ScrollItemPattern]::Pattern)
                if ($null -eq $scroll) { throw 'Task is offscreen without ScrollItem' }
                $scroll.ScrollIntoView()
            }
            $script:uiaStage = 'invoke-open-control'
            $task.Pattern.Invoke(); $result.mutations += 'invoked-open-task'; Start-Sleep -Milliseconds 500
        }
        if ($Action -eq 'OpenExisting') {
            $script:uiaStage = 'check-active-context'
            $deadline = [DateTime]::UtcNow.AddSeconds(5)
            do {
                try { Assert-ActiveTaskHeader $document $TaskTitle; break } catch { Start-Sleep -Milliseconds 200 }
            } while ([DateTime]::UtcNow -lt $deadline)
            Assert-ActiveTaskHeader $document $TaskTitle
        } else {
            $script:uiaStage = 'submit-prompt'
            if ($Action -eq 'SubmitExactDraft') {
                Submit-ExactDraft $document $prompt -ExpectedProjectName $ProjectName
            } elseif ($Action -eq 'OpenAndSubmit') {
                Submit-Prompt $document $prompt -ExpectedTaskTitle $TaskTitle
            } else {
                Submit-Prompt $document $prompt -ExpectedProjectName $ProjectName
            }
            $result.mutations += 'submitted-prompt'
        }
    }
    $result | ConvertTo-Json -Depth 4 -Compress
} catch {
    # Only stable stage names and mutation labels cross the process boundary;
    # PowerShell exception text can include a local path or task contents.
    $selectorCount = $null
    if ($_.Exception.Message -match '^Selector expected one match, found ([0-9]+)$') {
        $selectorCount = [int]$Matches[1]
    }
    $failureCode = $null
    if ($script:uiaStage -eq 'check-draft-empty' -and
        $_.Exception.Message -ceq 'Composer has an existing draft; no input was changed') {
        $failureCode = 'existing-draft'
    }
    [pscustomobject]@{
        action = $Action
        failure_stage = $script:uiaStage
        failure_code = $failureCode
        mutations = @($result.mutations)
        selector_match_count = $selectorCount
    } | ConvertTo-Json -Depth 3 -Compress
    throw
} finally {
    if ($bootstrapLockHeld) { $bootstrapMutex.ReleaseMutex() }
    if ($null -ne $bootstrapMutex) { $bootstrapMutex.Dispose() }
    [System.Windows.Automation.Automation]::RemoveStructureChangedEventHandler(
        $desktop.Window,
        $desktop.Listener
    )
}
