from __future__ import annotations

import json
import pathlib
import subprocess


ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / "tests/gate0/manage_runtime_maintenance.ps1"


def test_argument_profile_matrix_is_closed() -> None:
    helper = str(HELPER).replace("'", "''")
    body = r"""
$exe='C:\runtime\python.exe'
$runner='run_telegram_mvp1.py'
$cases=[ordered]@{
  exact='"C:\runtime\python.exe" "C:\runtime\run_telegram_mvp1.py" --serve --timeout 30 --announce'
  exact_b='"C:\runtime\python.exe" -B "C:\runtime\run_telegram_mvp1.py" --serve --timeout 30 --announce'
  code='"C:\runtime\python.exe" -c pass "C:\runtime\run_telegram_mvp1.py" --serve --timeout 30 --announce'
  module='"C:\runtime\python.exe" -m module "C:\runtime\run_telegram_mvp1.py" --serve --timeout 30 --announce'
  reordered='"C:\runtime\python.exe" "C:\runtime\run_telegram_mvp1.py" --timeout 30 --serve --announce'
  missing='"C:\runtime\python.exe" "C:\runtime\run_telegram_mvp1.py" --serve --announce'
  leading_flag='"C:\runtime\python.exe" "C:\runtime\run_telegram_mvp1.py" --other --serve --timeout 30 --announce'
  trailing_flag='"C:\runtime\python.exe" "C:\runtime\run_telegram_mvp1.py" --serve --timeout 30 --announce --other'
}
$result=[ordered]@{}
foreach($entry in $cases.GetEnumerator()){
  $result[$entry.Key]=Test-ExactRunnerArgumentProfile `
    -CommandLine $entry.Value `
    -ExecutablePath $exe `
    -RunnerScriptName $runner
}
$result|ConvertTo-Json -Compress
"""
    completed = subprocess.run(
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

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "exact": True,
        "exact_b": True,
        "code": False,
        "module": False,
        "reordered": False,
        "missing": False,
        "leading_flag": False,
        "trailing_flag": False,
    }
