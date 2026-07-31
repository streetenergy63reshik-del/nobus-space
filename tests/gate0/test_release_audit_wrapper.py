from __future__ import annotations

import json
import pathlib
import subprocess

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "tests/gate0/invoke_release_audit.ps1"


def run_wrapper(report: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(WRAPPER),
            "-GitleaksReportPath",
            str(report),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def write_report(tmp_path: pathlib.Path, text: str) -> pathlib.Path:
    report = tmp_path / "gitleaks.json"
    report.write_text(text, encoding="utf-8")
    return report


def test_legacy_ps51_wrapper_miscounts_empty_array(tmp_path: pathlib.Path) -> None:
    report = write_report(tmp_path, "[]")
    escaped_report = str(report).replace("'", "''")
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            (
                f"$items=@(Get-Content -Raw -LiteralPath '{escaped_report}' | "
                "ConvertFrom-Json); [Console]::Write($items.Count)"
            ),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stdout == "1"


def test_empty_gitleaks_array_is_zero_findings(tmp_path: pathlib.Path) -> None:
    completed = run_wrapper(write_report(tmp_path, "[]"))

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "schema": "nobus.gate0.gitleaks_report_verdict.v1",
        "status": "passed",
        "finding_count": 0,
        "raw_values_emitted": False,
    }


@pytest.mark.parametrize(
    "payload",
    [
        '[{"RuleID":"synthetic-one","File":"fixture","StartLine":1}]',
        (
            '[{"RuleID":"synthetic-one","File":"fixture","StartLine":1},'
            '{"RuleID":"synthetic-two","File":"fixture","StartLine":2}]'
        ),
    ],
)
def test_any_gitleaks_finding_fails_closed(
    tmp_path: pathlib.Path,
    payload: str,
) -> None:
    completed = run_wrapper(write_report(tmp_path, payload))

    assert completed.returncode != 0
    assert completed.stdout == ""


@pytest.mark.parametrize("payload", ["[", "", "{}", "null"])
def test_invalid_or_non_array_gitleaks_report_fails_closed(
    tmp_path: pathlib.Path,
    payload: str,
) -> None:
    completed = run_wrapper(write_report(tmp_path, payload))

    assert completed.returncode != 0
    assert completed.stdout == ""


def test_missing_gitleaks_report_fails_closed(tmp_path: pathlib.Path) -> None:
    completed = run_wrapper(tmp_path / "missing.json")

    assert completed.returncode != 0
    assert completed.stdout == ""
