from __future__ import annotations

import json
import pathlib
import subprocess


ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / "tests/gate0/manage_runtime_maintenance.ps1"


def test_native_handle_api_compiles_without_touching_runtime() -> None:
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
            (
                f". '{helper}'; "
                "Initialize-NativeProcessApi; "
                "$methods=[NobusGate0.NativeProcess].GetMethods().Name; "
                "[ordered]@{"
                "open=('OpenProcess' -in $methods);"
                "times=('GetProcessTimes' -in $methods);"
                "terminate=('TerminateProcess' -in $methods);"
                "close=('CloseHandle' -in $methods)"
                "}|ConvertTo-Json -Compress"
            ),
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
        "open": True,
        "times": True,
        "terminate": True,
        "close": True,
    }
