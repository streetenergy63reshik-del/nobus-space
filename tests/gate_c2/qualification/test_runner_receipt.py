"""Receipt access must survive a bounded Windows share race, never corrupt data."""
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import threading
from unittest.mock import Mock

import pytest

spec = importlib.util.spec_from_file_location("c2_receipt_runner", Path(__file__).with_name("runner.py"))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.mark.skipif(os.name != "nt", reason="Windows file-sharing semantics")
def test_real_temporary_windows_share_conflict(tmp_path):
    path = tmp_path / "receipt.json"
    path.write_text('{"complete": false}', encoding="utf-8")
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                               ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    api.CreateFileW.restype = ctypes.c_void_p
    api.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = api.CreateFileW(str(path), 0x80000000, 0, None, 3, 0, None)
    assert handle != ctypes.c_void_p(-1).value
    release = threading.Event()
    closed = threading.Event()

    def close():
        release.wait()
        api.CloseHandle(handle)
        closed.set()

    thread = threading.Thread(target=close)
    thread.start()
    try:
        with pytest.raises(PermissionError) as failure:
            path.read_text(encoding="utf-8-sig")
        assert failure.value.errno == 13
        timer = threading.Timer(.03, release.set)
        timer.start()
        assert runner.read_json(path) == {"complete": False}
        timer.join()
    finally:
        release.set()
        thread.join()
    assert closed.is_set()


def test_permanent_share_conflict_is_bounded(monkeypatch):
    error = PermissionError("synthetic share conflict")
    error.winerror = 32
    path = Mock()
    path.read_text.side_effect = error
    monkeypatch.setattr(runner.time, "sleep", lambda _: None)
    with pytest.raises(PermissionError):
        runner.read_json(path)
    assert path.read_text.call_count == 21


@pytest.mark.parametrize("error", [PermissionError("unrelated"), json.JSONDecodeError("invalid", "", 0)])
def test_unrelated_or_malformed_receipt_is_not_retried(error):
    path = Mock()
    path.read_text.side_effect = error
    with pytest.raises(type(error)):
        runner.read_json(path)
    assert path.read_text.call_count == 1
