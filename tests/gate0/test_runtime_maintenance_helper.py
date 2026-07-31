from __future__ import annotations

import json
import pathlib
import subprocess


ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / "tests/gate0/manage_runtime_maintenance.ps1"


def run_powershell(body: str) -> subprocess.CompletedProcess[str]:
    helper = str(HELPER).replace("'", "''")
    return subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f". '{helper}'; {body}",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_verified_set_classification_is_sanitized() -> None:
    completed = run_powershell(
        """
$candidates = @(
  [pscustomobject]@{ identity_digest='sha256:' + ('1' * 64); verified=$true },
  [pscustomobject]@{ identity_digest='sha256:' + ('2' * 64); verified=$true }
)
$result = New-MaintenanceClassification `
  -SchedulerState 'ready' `
  -MutexState 'occupied' `
  -Candidates $candidates
$result | ConvertTo-Json -Compress -Depth 4
"""
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload == {
        "schema": "nobus.gate0.runtime_maintenance.v1",
        "scheduler_state": "ready",
        "candidate_count": 2,
        "verified_count": 2,
        "unverified_count": 0,
        "identity_digests": ["sha256:" + "1" * 64, "sha256:" + "2" * 64],
        "mutex_state": "occupied",
        "classification_verdict": "verified_set_ready",
    }
    serialized = json.dumps(payload).casefold()
    assert "pid" not in serialized
    assert "argv" not in serialized
    assert "commandline" not in serialized
    assert "path" not in serialized


def test_unverified_candidate_blocks_classification() -> None:
    completed = run_powershell(
        """
$candidates = @(
  [pscustomobject]@{ identity_digest='sha256:' + ('1' * 64); verified=$true },
  [pscustomobject]@{ identity_digest='sha256:' + ('2' * 64); verified=$false }
)
New-MaintenanceClassification `
  -SchedulerState 'ready' `
  -MutexState 'occupied' `
  -Candidates $candidates |
  ConvertTo-Json -Compress -Depth 4
"""
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["candidate_count"] == 2
    assert payload["verified_count"] == 1
    assert payload["unverified_count"] == 1
    assert payload["classification_verdict"] == "blocked"


def test_zero_candidates_and_free_mutex_is_explicit() -> None:
    completed = run_powershell(
        """
New-MaintenanceClassification `
  -SchedulerState 'ready' `
  -MutexState 'free' `
  -Candidates @() |
  ConvertTo-Json -Compress -Depth 4
"""
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["candidate_count"] == 0
    assert payload["verified_count"] == 0
    assert payload["unverified_count"] == 0
    assert payload["identity_digests"] == []
    assert payload["classification_verdict"] == "no_candidates_mutex_free"


def test_stop_precondition_requires_exact_verified_digest_set() -> None:
    completed = run_powershell(
        """
$candidates = @(
  [pscustomobject]@{ identity_digest='sha256:' + ('1' * 64); verified=$true },
  [pscustomobject]@{ identity_digest='sha256:' + ('2' * 64); verified=$true }
)
$classification = New-MaintenanceClassification `
  -SchedulerState 'ready' `
  -MutexState 'occupied' `
  -Candidates $candidates
$exact = Test-TerminationPreconditions `
  -Classification $classification `
  -ExpectedIdentityDigests @(
    ('sha256:' + ('2' * 64)),
    ('sha256:' + ('1' * 64))
  )
$missing = Test-TerminationPreconditions `
  -Classification $classification `
  -ExpectedIdentityDigests @('sha256:' + ('1' * 64))
[ordered]@{ exact=$exact; missing=$missing } |
  ConvertTo-Json -Compress
"""
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"exact": True, "missing": False}
