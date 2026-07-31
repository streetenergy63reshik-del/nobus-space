from __future__ import annotations

import json
import pathlib
import subprocess


ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / "tests/gate0/manage_runtime_maintenance.ps1"


def test_pyvenv_cfg_resolves_exact_base_executable(tmp_path: pathlib.Path) -> None:
    venv_root = tmp_path / ".venv"
    scripts = venv_root / "Scripts"
    scripts.mkdir(parents=True)
    venv_python = scripts / "python.exe"
    venv_python.write_bytes(b"redirector")
    base_python = tmp_path / "Python312" / "python.exe"
    base_python.parent.mkdir()
    base_python.write_bytes(b"")
    (venv_root / "pyvenv.cfg").write_text(
        f"home = {base_python.parent}\n"
        "include-system-site-packages = false\n"
        "version = 3.12.10\n"
        f"executable = {base_python}\n",
        encoding="utf-8",
    )
    helper = str(HELPER).replace("'", "''")
    python_path = str(venv_python).replace("'", "''")
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
                f"$result=Get-VenvBasePythonDefinition -VenvPythonPath '{python_path}'; "
                "[ordered]@{path=$result.Path;digest=$result.Digest}|"
                "ConvertTo-Json -Compress"
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
        "path": str(base_python),
        "digest": "sha256:e3b0c44298fc1c149afbf4c8996fb924"
        "27ae41e4649b934ca495991b7852b855",
    }
