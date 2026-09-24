[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Low')]
param(
    [Parameter(Mandatory = $true)][string]$SourceRoot
)

$ErrorActionPreference = 'Stop'
$source = (Resolve-Path -LiteralPath $SourceRoot).Path
$skill = Join-Path $env:USERPROFILE '.codex\skills\nobus-send-results'
$installed = Join-Path $skill 'scripts\send_result.py'
$guardDestination = Join-Path $skill 'scripts\nobus_send_results_guard.py'
$guardSource = Join-Path $source 'ops\windows\nobus_send_results_guard.py'
$patch = Join-Path $source 'docs\gates\mvp2\m2-desktop\send-results-bridge-owner.patch'
$oldHash = '595f4db569519d1bb545b16320dbf8aabee3277d46263fe3f0d3efa04476a4df'
$newHash = 'd38d9809dda89a088eb9e4415f4a834bb47d58cc804b14fa2fa9cc523c9d9f2e'
$guardHash = 'e20cd35d1d09fc5c90ee91fe37bf80b4057de86ab4bb9e117d2ae0f0e6e6fe20'
$patchHash = '0ad0f13203176261c298f8b1f83619349778f8a5e3f1d5f0a48928181bc614d7'

function ExactHash([string]$path) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required file missing: $path"
    }
    $stream = [IO.File]::OpenRead($path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '').ToLowerInvariant()
    } finally {
        $stream.Dispose()
        $sha.Dispose()
    }
}

if ((ExactHash $guardSource) -ne $guardHash -or (ExactHash $patch) -ne $patchHash) {
    throw 'Candidate guard or patch bytes changed'
}
if ((ExactHash $installed) -eq $newHash -and
    (Test-Path -LiteralPath $guardDestination -PathType Leaf) -and
    (ExactHash $guardDestination) -eq $guardHash) {
    Write-Output 'ALREADY_INSTALLED'
    return
}
if ((ExactHash $installed) -ne $oldHash -or (Test-Path -LiteralPath $guardDestination)) {
    throw 'Installed skill drift or prior partial attempt; inspect before retry'
}
if (-not $PSCmdlet.ShouldProcess($skill, 'Install exact M2 bridge owner guard')) {
    Write-Output 'PREFLIGHT_PASS_NO_INSTALL'
    return
}

$gitCommon = (& git -C $source rev-parse --path-format=absolute --git-common-dir).Trim()
if ($LASTEXITCODE -ne 0 -or -not $gitCommon.EndsWith('.git')) {
    throw 'Git common directory unavailable'
}
$canonicalRoot = Split-Path -Parent $gitCommon
$stageRoot = Join-Path $canonicalRoot '.runtime\m2-send-results-guard-install'
$stage = Join-Path $stageRoot ([guid]::NewGuid().ToString('N'))
[void](New-Item -ItemType Directory -Path (Join-Path $stage 'scripts') -Force)
$stagedSender = Join-Path $stage 'scripts\send_result.py'
$backup = Join-Path $stage 'send_result.before.py'
Copy-Item -LiteralPath $installed -Destination $stagedSender
Copy-Item -LiteralPath $installed -Destination $backup
if ((ExactHash $backup) -ne $oldHash) { throw 'Backup bytes changed before install' }
$utf8 = New-Object System.Text.UTF8Encoding($false)
$senderText = [IO.File]::ReadAllText($stagedSender, $utf8)
$importBefore = "import json`nimport re`n"
$importAfter = "import json`nimport os`nimport re`n"
$methodBefore = "async def deliver(args: argparse.Namespace) -> None:`n    content = stable_read("
$guardPrelude = @'
    if args.send:
        try:
            from nobus_send_results_guard import (
                DeliveryOwnerGuardError,
                assert_skill_delivery_allowed,
            )
            assert_skill_delivery_allowed(
                settings_path=Path.home() / ".codex" / "nobus-task-notifier.json",
                codex_thread_id=os.environ.get("CODEX_THREAD_ID"),
            )
        except ImportError:
            fail("bridge_owner_guard_unavailable")
        except DeliveryOwnerGuardError as error:
            fail(str(error))
'@
$guardPrelude = $guardPrelude.Replace("`r`n", "`n") + "`n"
if ($senderText.IndexOf($importBefore) -lt 0 -or
    $senderText.IndexOf($importBefore) -ne $senderText.LastIndexOf($importBefore) -or
    $senderText.IndexOf($methodBefore) -lt 0 -or
    $senderText.IndexOf($methodBefore) -ne $senderText.LastIndexOf($methodBefore)) {
    throw 'Approved sender patch anchors changed'
}
$senderText = $senderText.Replace($importBefore, $importAfter)
$senderText = $senderText.Replace($methodBefore, "async def deliver(args: argparse.Namespace) -> None:`n" + $guardPrelude + "    content = stable_read(")
$senderText = $senderText.Replace("`n", "`r`n")
[IO.File]::WriteAllText($stagedSender, $senderText, $utf8)
if ((ExactHash $stagedSender) -ne $newHash) {
    throw 'Staged sender does not match the approved release'
}
Copy-Item -LiteralPath $guardSource -Destination $guardDestination
if ((ExactHash $guardDestination) -ne $guardHash) {
    throw 'Guard copy did not match approved bytes; inspect partial install'
}
try {
    [IO.File]::Replace($stagedSender, $installed, (Join-Path $stage 'send_result.atomic-backup.py'))
} catch {
    throw 'Atomic sender replacement failed; inspect installed files and backup before retry'
}
if ((ExactHash $installed) -ne $newHash -or (ExactHash $guardDestination) -ne $guardHash) {
    throw 'Installed readback mismatched; inspect before any retry'
}
Write-Output "INSTALLED backup=$backup"
