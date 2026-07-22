"""Reproduce Windows Job stdio, inheritance, and tree termination locally."""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4


_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from src.contracts import TaskContract
from src.workers.asyncio_spawner import AsyncioProcessSpawner, AsyncioSpawnedProcess
from src.workers.codex_cli import (
    CodexCliAdapter,
    ProcessOutput,
    _READ_ARGV,
    _SAFE_ENV,
)
from src.workers.windows_job import WindowsJobLauncher


_COMPILERS = (
    Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
    Path(r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"),
)
_SOURCE = _ROOT / "tests" / "fixtures" / "windows_job_probe.cs"
_MARKER = "job-probe-child.pid"
_PROCESS_TERMINATE = 0x0001
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_SYNCHRONIZE = 0x00100000
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 0x00000102
_WAIT_FAILED = 0xFFFFFFFF
_ERROR_INVALID_PARAMETER = 87


def _compiler() -> Path:
    for candidate in _COMPILERS:
        if candidate.is_file():
            return candidate
    raise RuntimeError("built-in C# compiler is unavailable")


def _compile_probe(destination: Path) -> Path:
    executable = destination / "windows-job-probe.exe"
    result = subprocess.run(
        (
            str(_compiler()),
            "/nologo",
            "/target:exe",
            "/out:" + str(executable),
            str(_SOURCE),
        ),
        check=False,
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0 or not executable.is_file():
        raise RuntimeError("probe compilation failed")
    return executable


class _ObservedProcess:
    def __init__(self, kernel32: Any, handle: int, process_id: int) -> None:
        self._kernel32 = kernel32
        self._handle = handle
        self.process_id = process_id

    def is_alive(self) -> bool:
        result = self._kernel32.WaitForSingleObject(self._handle, 0)
        if result == _WAIT_TIMEOUT:
            return True
        if result == _WAIT_OBJECT_0:
            return False
        if result == _WAIT_FAILED:
            raise ctypes.WinError(ctypes.get_last_error())
        raise RuntimeError("unexpected process wait result")

    def terminate(self) -> None:
        if not self.is_alive():
            return
        if not self._kernel32.TerminateProcess(self._handle, 125):
            error = ctypes.get_last_error()
            result = self._kernel32.WaitForSingleObject(self._handle, 5000)
            if result == _WAIT_OBJECT_0:
                return
            if result == _WAIT_FAILED:
                raise ctypes.WinError(ctypes.get_last_error())
            raise ctypes.WinError(error)
        result = self._kernel32.WaitForSingleObject(self._handle, 5000)
        if result == _WAIT_OBJECT_0:
            return
        if result == _WAIT_FAILED:
            raise ctypes.WinError(ctypes.get_last_error())
        raise RuntimeError("probe cleanup timed out")

    def close(self) -> None:
        if not self._handle:
            return
        if not self._kernel32.CloseHandle(self._handle):
            raise ctypes.WinError(ctypes.get_last_error())
        self._handle = 0


class _ProcessApi:
    def __init__(self, expected_executable: Path) -> None:
        self._expected_executable = expected_executable.resolve(strict=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (
            ctypes.c_uint32,
            ctypes.c_int,
            ctypes.c_uint32,
        )
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.QueryFullProcessImageNameW.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_wchar_p,
            ctypes.POINTER(ctypes.c_uint32),
        )
        kernel32.QueryFullProcessImageNameW.restype = ctypes.c_int
        kernel32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        kernel32.WaitForSingleObject.restype = ctypes.c_uint32
        kernel32.TerminateProcess.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        kernel32.TerminateProcess.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        kernel32.CloseHandle.restype = ctypes.c_int
        self._kernel32 = kernel32

    def observe(self, process_id: int) -> _ObservedProcess | None:
        handle = self._kernel32.OpenProcess(
            _SYNCHRONIZE
            | _PROCESS_QUERY_LIMITED_INFORMATION
            | _PROCESS_TERMINATE,
            False,
            process_id,
        )
        if not handle:
            error = ctypes.get_last_error()
            if error == _ERROR_INVALID_PARAMETER:
                return None
            raise ctypes.WinError(error)
        observed = _ObservedProcess(self._kernel32, handle, process_id)
        try:
            self._verify_image(handle)
            alive = observed.is_alive()
        except BaseException:
            observed.close()
            raise
        if alive:
            return observed
        observed.close()
        return None

    def _verify_image(self, handle: int) -> None:
        buffer = ctypes.create_unicode_buffer(32768)
        size = ctypes.c_uint32(len(buffer))
        if not self._kernel32.QueryFullProcessImageNameW(
            handle, 0, buffer, ctypes.byref(size)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            actual = Path(buffer.value).resolve(strict=True)
        except (OSError, RuntimeError):
            raise RuntimeError("probe process identity is invalid") from None
        if os.path.normcase(str(actual)) != os.path.normcase(
            str(self._expected_executable)
        ):
            raise RuntimeError("probe process identity does not match marker")


async def _wait_for_child(marker: Path, api: _ProcessApi) -> _ObservedProcess:
    deadline = asyncio.get_running_loop().time() + 10
    while asyncio.get_running_loop().time() < deadline:
        try:
            process_id = int(marker.read_text(encoding="ascii"))
        except (FileNotFoundError, OSError, UnicodeError, ValueError):
            await asyncio.sleep(0.05)
            continue
        if process_id > 0:
            observed = api.observe(process_id)
            if observed is not None:
                return observed
        await asyncio.sleep(0.05)
    raise RuntimeError("probe descendant did not become observable")


async def _wait_until_dead(process: _ObservedProcess) -> None:
    deadline = asyncio.get_running_loop().time() + 10
    while asyncio.get_running_loop().time() < deadline:
        if not process.is_alive():
            return
        await asyncio.sleep(0.05)
    raise RuntimeError("probe descendant survived Job termination")


def _parse_output(output: ProcessOutput, mode: str, child_id: int) -> dict[str, Any]:
    if mode == "exit" and output.returncode != 0:
        raise RuntimeError("normal-exit probe failed")
    if mode == "wait" and output.returncode == 0:
        raise RuntimeError("forced-kill probe exited normally")
    if output.stderr:
        raise RuntimeError("probe emitted unexpected stderr")
    try:
        payload = json.loads(output.stdout.decode("utf-8").strip())
    except (json.JSONDecodeError, UnicodeError):
        raise RuntimeError("probe stdout is invalid") from None
    if (
        type(payload) is not dict
        or payload.get("mode") != mode
        or payload.get("child_pid") != child_id
        or type(payload.get("root_pid")) is not int
    ):
        raise RuntimeError("probe stdout does not match the process tree")
    return payload


async def _spawn(
    directory: Path, executable: Path
) -> tuple[AsyncioSpawnedProcess, WindowsJobLauncher]:
    launcher = WindowsJobLauncher(
        workspace_root=directory,
        target_executable=executable,
    )
    spawner = AsyncioProcessSpawner(
        workspace_root=directory,
        executable=executable,
        spawn=launcher,
        tree_killer=launcher.kill_tree,
    )
    process = await spawner(
        executable=str(executable),
        argv=_READ_ARGV,
        cwd=str(directory),
        env=dict(_SAFE_ENV),
    )
    return process, launcher


async def _scenario(
    directory: Path, executable: Path, mode: str, api: _ProcessApi
) -> dict[str, Any]:
    marker = directory / _MARKER
    marker.unlink(missing_ok=True)
    process, _launcher = await _spawn(directory, executable)
    communication = asyncio.create_task(
        process.communicate(
            stdin=(mode + "\n").encode("ascii"),
            stdout_limit=4096,
            stderr_limit=4096,
        )
    )
    child: _ObservedProcess | None = None
    try:
        child = await _wait_for_child(marker, api)
        if mode == "wait":
            process.kill()
        output = await asyncio.wait_for(communication, timeout=15)
        payload = _parse_output(output, mode, child.process_id)
        await _wait_until_dead(child)
        await process.wait()
        return {
            "mode": mode,
            "stdio": "PASS",
            "descendant_alive_before_boundary": True,
            "descendant_dead_after_boundary": True,
            "root_pid": payload["root_pid"],
            "child_pid": child.process_id,
            "returncode": output.returncode,
        }
    finally:
        if not communication.done():
            process.kill()
            try:
                await asyncio.wait_for(process.wait(), timeout=10)
            except (Exception, asyncio.CancelledError):
                pass
            communication.cancel()
            await asyncio.gather(communication, return_exceptions=True)
        if child is not None:
            try:
                if child.is_alive():
                    child.terminate()
            finally:
                child.close()


async def _cancellation_scenario(
    directory: Path, executable: Path, api: _ProcessApi
) -> dict[str, Any]:
    marker = directory / _MARKER
    marker.unlink(missing_ok=True)
    launcher = WindowsJobLauncher(
        workspace_root=directory,
        target_executable=executable,
    )
    spawner = AsyncioProcessSpawner(
        workspace_root=directory,
        executable=executable,
        spawn=launcher,
        tree_killer=launcher.kill_tree,
    )
    adapter = CodexCliAdapter(
        workspace_root=directory,
        executable=executable,
        spawner=spawner,
        max_timeout_seconds=30,
        cleanup_timeout=10,
    )
    contract = TaskContract(
        task_id=uuid4(),
        idempotency_key="local-job-probe",
        ingress_digest="sha256:" + "0" * 64,
        tenant_id="local-probe",
        source="local-probe",
        instruction="Run the local cancellation probe.",
        allowed_paths=(str(directory),),
        permissions=("repo.read", "process.run_allowlisted"),
        risk="low",
        acceptance_criteria=("The process tree is cancelled.",),
        timeout_seconds=30,
        quality_profile="local-probe@1",
    )
    execution = asyncio.create_task(adapter.execute(contract))
    child: _ObservedProcess | None = None
    try:
        child = await _wait_for_child(marker, api)
        execution.cancel()
        try:
            await asyncio.wait_for(execution, timeout=15)
        except asyncio.CancelledError:
            pass
        else:
            raise RuntimeError("adapter cancellation did not propagate")
        await _wait_until_dead(child)
        return {
            "mode": "cancel",
            "cancellation_propagated": True,
            "descendant_alive_before_boundary": True,
            "descendant_dead_after_boundary": True,
            "child_pid": child.process_id,
        }
    finally:
        if not execution.done():
            execution.cancel()
            await asyncio.gather(execution, return_exceptions=True)
        if child is not None:
            try:
                if child.is_alive():
                    child.terminate()
            finally:
                child.close()


async def _run(directory: Path, executable: Path) -> dict[str, Any]:
    api = _ProcessApi(executable)
    normal = await _scenario(directory, executable, "exit", api)
    forced = await _scenario(directory, executable, "wait", api)
    cancelled = await _cancellation_scenario(directory, executable, api)
    return {
        "probe": "windows-job-object",
        "status": "PASS",
        "normal_exit": normal,
        "forced_kill": forced,
        "cancellation": cancelled,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="emit JSON evidence")
    arguments = parser.parse_args()
    if os.name != "nt":
        raise RuntimeError("Windows Job probe requires Windows")
    temp_root = _ROOT / "tmp"
    temp_root.mkdir(exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(
            prefix="nobus-job-probe-", dir=temp_root
        ) as temp:
            directory = Path(temp).resolve(strict=True)
            executable = _compile_probe(directory)
            evidence = asyncio.run(_run(directory, executable))
    finally:
        try:
            temp_root.rmdir()
        except OSError:
            pass
    if arguments.json:
        print(json.dumps(evidence, sort_keys=True))
    else:
        print("Windows Job Object live probe: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
