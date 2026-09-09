"""Git identity lookup must finish while the Core shutdown reader is waiting."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Windows stdin pipe integration")
def test_application_binding_with_active_shutdown_reader(tmp_path):
    root = Path(__file__).resolve().parents[1]
    marker = tmp_path / "binding.json"
    child_code = """
import json,sys,threading,time
from pathlib import Path
sys.path[:0] = json.loads(sys.argv[2])
from src.application.runtime_maintenance import application_binding
reader = threading.Thread(target=lambda: sys.stdin.buffer.readline(16))
reader.start()
time.sleep(.2)
try:
    result = application_binding()
    Path(sys.argv[1]).write_text(json.dumps(result), encoding='utf-8')
finally:
    reader.join()
"""
    process = subprocess.Popen(
        [sys._base_executable, "-c", child_code, str(marker),
         json.dumps([str(root), *sys.path])],
        cwd=root, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(.05)
        assert marker.exists(), "Git identity lookup blocked behind the shutdown stdin reader"
        binding = json.loads(marker.read_text(encoding="utf-8"))
        expected = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], stdin=subprocess.DEVNULL,
        ).decode().strip()
        assert binding["source_commit"] == expected
        assert binding["code_digest"].startswith("sha256:")
    finally:
        if process.poll() is None:
            try:
                process.communicate(b"stop\n", timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if process.stdin is not None:
            process.stdin.close()
    assert process.returncode == 0
