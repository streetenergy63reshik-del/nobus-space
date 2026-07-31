from __future__ import annotations

import json
import pathlib
import subprocess


ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / "tests/gate0/manage_runtime_maintenance.ps1"


def test_registered_runtime_root_is_exact_canonical_repo() -> None:
    helper = str(HELPER).replace("'", "''")
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f"""
. '{helper}'
$canonical = $script:MaintenanceCanonicalRepoRoot
$codeRoot = [System.IO.Directory]::GetParent($canonical).FullName
$live = Join-Path $codeRoot 'worktrees\\telegram-live'
[ordered]@{{
  live=(Test-RegisteredRuntimeRoot `
    -CanonicalRepoRoot $canonical `
    -RunnerRoot $live)
  canonical=(Test-RegisteredRuntimeRoot `
    -CanonicalRepoRoot $canonical `
    -RunnerRoot $canonical)
  canonical_case=(Test-RegisteredRuntimeRoot `
    -CanonicalRepoRoot $canonical.ToUpperInvariant() `
    -RunnerRoot $canonical.ToUpperInvariant())
  canonical_normalized=(Test-RegisteredRuntimeRoot `
    -CanonicalRepoRoot (Join-Path $canonical '.') `
    -RunnerRoot (Join-Path $canonical '.'))
  spoof=(Test-RegisteredRuntimeRoot `
    -CanonicalRepoRoot $live `
    -RunnerRoot $live)
  other=(Test-RegisteredRuntimeRoot `
    -CanonicalRepoRoot $canonical `
    -RunnerRoot (Join-Path $codeRoot 'worktrees\\other'))
  prefix=(Test-RegisteredRuntimeRoot `
    -CanonicalRepoRoot $canonical `
    -RunnerRoot ($canonical + '-copy'))
}} | ConvertTo-Json -Compress
""",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "live": False,
        "canonical": True,
        "canonical_case": True,
        "canonical_normalized": True,
        "spoof": False,
        "other": False,
        "prefix": False,
    }
