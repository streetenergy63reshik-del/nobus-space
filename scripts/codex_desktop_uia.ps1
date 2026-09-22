param(
    [ValidateSet('Snapshot', 'CreateAndSubmit', 'OpenAndSubmit')]
    [string]$Action = 'Snapshot',
    [Parameter(Mandatory = $true)][string]$ProjectName,
    [string]$TaskTitle = '',
    [string]$PromptFile = '',
    [Parameter(Mandatory = $true)][string]$AllowedPromptRoot,
    [Parameter(Mandatory = $true)][string]$ExpectedDesktopVersion
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
    [NobusDesktopWindows]::EnumWindows({
        param($handle, $state)
        if (-not [NobusDesktopWindows]::IsWindowVisible($handle)) { return $true }
        $className = [Text.StringBuilder]::new(256)
        [void][NobusDesktopWindows]::GetClassName($handle, $className, 256)
        if ($className.ToString() -ne 'Chrome_WidgetWin_1') { return $true }
        $processId = 0
        [void][NobusDesktopWindows]::GetWindowThreadProcessId($handle, [ref]$processId)
        try {
            $process = Get-Process -Id $processId -ErrorAction Stop
            $processName = $process.ProcessName
            $executablePath = $process.Path
        } catch { return $true }
        if ($processName -ne 'ChatGPT') { return $true }
        $versionMatch = [regex]::Match($executablePath, 'OpenAI\.Codex_(\d+\.\d+\.\d+\.\d+)_', [Text.RegularExpressions.RegexOptions]::IgnoreCase)
        if (-not $versionMatch.Success -or $versionMatch.Groups[1].Value -ne $ExpectedDesktopVersion) { return $true }
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
                $found = @()
                for ($index = 0; $index -lt $all.Count; $index++) {
                    if ($all.Item($index).Current.AutomationId -eq 'RootWebArea') { $found += $all.Item($index) }
                }
                if ($found.Count -eq 1) { break }
                Start-Sleep -Milliseconds 100
            } while ([DateTime]::UtcNow -lt $deadline)
            if ($found.Count -eq 1) {
                $listenerTransferred = $true
                $documents.Add([pscustomobject]@{
                    Element = $found[0]
                    Window = $window
                    Listener = $listener
                    ProcessId = [int]$processId
                    DesktopVersion = $versionMatch.Groups[1].Value
                })
            }
        } catch { } finally {
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
        throw "Expected one Codex document, found $($documents.Count)"
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

function Submit-Prompt {
    param($Root, [string]$Prompt)
    $composer = Wait-Exact $Root 'Поручите что угодно' ([System.Windows.Automation.ControlType]::Edit) ([System.Windows.Automation.ValuePattern]::Pattern) -TimeoutMs 15000
    if ($composer.Element.Current.IsOffscreen) {
        $scroll = Get-Pattern $composer.Element ([System.Windows.Automation.ScrollItemPattern]::Pattern)
        if ($null -eq $scroll) { throw 'Composer is offscreen without ScrollItem' }
        $scroll.ScrollIntoView()
    }
    $composer.Pattern.SetValue($Prompt)
    $send = Wait-Exact $Root 'Отправить' ([System.Windows.Automation.ControlType]::Button) ([System.Windows.Automation.InvokePattern]::Pattern) -TimeoutMs 10000
    $send.Pattern.Invoke()
}

$desktop = Get-CodexDocument
try {
    $document = $desktop.Element
    $result = [ordered]@{ action = $Action; desktop_version = $desktop.DesktopVersion; process_id = $desktop.ProcessId; mutations = @() }
    if ($Action -ne 'Snapshot') {
        $prompt = Read-Prompt
        if ($Action -eq 'CreateAndSubmit') {
            $project = Find-Exact $document $ProjectName ([System.Windows.Automation.ControlType]::Button) ([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
            if ($project.Pattern.Current.ExpandCollapseState -eq [System.Windows.Automation.ExpandCollapseState]::Collapsed) {
                $project.Pattern.Expand(); $result.mutations += 'expanded-project'; Start-Sleep -Milliseconds 300
            }
            $create = Wait-Exact $document "Начать новый чат в папке $ProjectName" ([System.Windows.Automation.ControlType]::Button) ([System.Windows.Automation.InvokePattern]::Pattern) -TimeoutMs 5000
            $create.Pattern.Invoke(); $result.mutations += 'invoked-create-task'; Start-Sleep -Milliseconds 500
        } else {
            if ([string]::IsNullOrWhiteSpace($TaskTitle)) { throw 'TaskTitle is required' }
            $task = Find-Exact $document $TaskTitle ([System.Windows.Automation.ControlType]::Button) ([System.Windows.Automation.InvokePattern]::Pattern) -InListItem
            if ($task.Element.Current.IsOffscreen) {
                $scroll = Get-Pattern $task.Element ([System.Windows.Automation.ScrollItemPattern]::Pattern)
                if ($null -eq $scroll) { throw 'Task is offscreen without ScrollItem' }
                $scroll.ScrollIntoView()
            }
            $task.Pattern.Invoke(); $result.mutations += 'invoked-open-task'; Start-Sleep -Milliseconds 500
        }
        Submit-Prompt $document $prompt
        $result.mutations += 'submitted-prompt'
    }
    $result | ConvertTo-Json -Depth 4 -Compress
} finally {
    [System.Windows.Automation.Automation]::RemoveStructureChangedEventHandler(
        $desktop.Window,
        $desktop.Listener
    )
}
