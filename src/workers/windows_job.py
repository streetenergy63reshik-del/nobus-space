"""Windows Job Object launcher with a gated, non-racy child start."""

from __future__ import annotations

import asyncio
import ctypes
import os
import subprocess
import sys
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from src.workers.codex_cli import (
    _INTENT_ARGV,
    _RATE_LIMIT_ARGV,
    _READ_ARGV,
    _SAFE_ENV,
    _WEB_ARGV,
    _WRITE_ARGV,
    _validated_worker_env,
)


_ARGV_PROFILES = frozenset(
    {_READ_ARGV, _WEB_ARGV, _WRITE_ARGV, _RATE_LIMIT_ARGV, _INTENT_ARGV}
)
_CREATE_FLAGS = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_EXTENDED_LIMIT_INFORMATION = 9
_PROCESS_ACCESS = 0x0001 | 0x0100 | 0x1000


class WindowsJobApi(Protocol):
    def create_job(self) -> int: ...

    def create_gate(self) -> tuple[int, str]: ...

    def assign(self, job: int, process_id: int) -> None: ...

    def signal(self, gate: int) -> None: ...

    def terminate(self, job: int) -> None: ...

    def close(self, handle: int) -> None: ...


class WindowsJobLauncher:
    """Spawn a waiting helper, bind it to a Job, then release the child start."""

    def __init__(
        self,
        *,
        workspace_root: str | Path,
        target_executable: str | Path,
        python_executable: str | Path = sys.executable,
        helper_script: str | Path | None = None,
        spawn: Callable[..., Awaitable[asyncio.subprocess.Process]] | None = None,
        api: WindowsJobApi | None = None,
        worker_env: Mapping[str, str] = _SAFE_ENV,
    ) -> None:
        helper = Path(helper_script or Path(__file__).with_name("windows_job_helper.py"))
        try:
            workspace = Path(workspace_root).resolve(strict=True)
            target = Path(target_executable).resolve(strict=True)
            python = Path(python_executable).resolve(strict=True)
            helper = helper.resolve(strict=True)
            valid = (
                workspace.is_dir()
                and target.is_file()
                and python.is_file()
                and helper.is_file()
                and (spawn is None or callable(spawn))
            )
            normalized_env = _validated_worker_env(worker_env)
        except (OSError, RuntimeError, TypeError):
            valid = False
        if not valid or (api is None and os.name != "nt"):
            raise ValueError("Windows Job launcher configuration is invalid")
        self._workspace = workspace
        self._target = target
        self._python = python
        self._helper = helper
        self._spawn = spawn or asyncio.create_subprocess_exec
        self._api = api or _Kernel32JobApi()
        self._worker_env = normalized_env
        self._jobs: dict[asyncio.subprocess.Process, tuple[int, int]] = {}
        self._reapers: set[asyncio.Task[None]] = set()

    async def __call__(self, executable: str, *argv: str, **options: Any) -> asyncio.subprocess.Process:
        cwd = self._validate_call(executable, tuple(argv), options)
        job: int | None = None
        gate: int | None = None
        process: asyncio.subprocess.Process | None = None
        failed = False
        try:
            job = self._api.create_job()
            gate, gate_name = self._api.create_gate()
            process = await self._spawn(
                str(self._python),
                "-I",
                str(self._helper),
                gate_name,
                "--",
                str(self._target),
                *argv,
                cwd=str(cwd),
                env=dict(self._worker_env),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=_CREATE_FLAGS,
            )
            if type(process.pid) is not int or process.pid <= 0:
                raise RuntimeError("created process is invalid")
            self._api.assign(job, process.pid)
            self._api.signal(gate)
            self._jobs[process] = (job, gate)
            reaper = asyncio.create_task(self._reap(process))
            self._reapers.add(reaper)
            reaper.add_done_callback(
                lambda task: self._reaper_finished(process, job, gate, task)
            )
            return process
        except asyncio.CancelledError:
            await self._cleanup_failed(process, job, gate)
            raise
        except BaseException:
            failed = True
        if failed:
            await self._cleanup_failed(process, job, gate)
            raise RuntimeError("Windows Job Object launch failed")
        raise AssertionError("unreachable")

    async def kill_tree(self, process: asyncio.subprocess.Process) -> None:
        ownership = self._jobs.pop(process, None)
        if ownership is None:
            return
        job, gate = ownership
        failed = False
        try:
            self._api.terminate(job)
        except BaseException:
            failed = True
            try:
                process.kill()
            except BaseException:
                pass
        try:
            self._api.close(job)
        except BaseException:
            failed = True
        try:
            self._api.close(gate)
        except BaseException:
            failed = True
        try:
            await process.wait()
        except BaseException:
            failed = True
        if failed:
            raise RuntimeError("Windows Job Object termination failed")

    def _validate_call(
        self, executable: str, argv: tuple[str, ...], options: Mapping[str, Any]
    ) -> Path:
        try:
            target = Path(executable).resolve(strict=True)
            cwd = Path(options["cwd"]).resolve(strict=True)
            cwd.relative_to(self._workspace)
            valid = (
                target == self._target
                and cwd.is_dir()
                and argv in _ARGV_PROFILES
                and options.get("env") == dict(self._worker_env)
                and options.get("stdin") == asyncio.subprocess.PIPE
                and options.get("stdout") == asyncio.subprocess.PIPE
                and options.get("stderr") == asyncio.subprocess.PIPE
                and options.get("creationflags") == _CREATE_FLAGS
                and set(options) == {
                    "cwd", "env", "stdin", "stdout", "stderr", "creationflags"
                }
            )
        except (KeyError, OSError, RuntimeError, TypeError, ValueError):
            valid = False
        if not valid:
            raise RuntimeError("Windows Job process request is not allowlisted")
        return cwd

    async def _cleanup_failed(
        self,
        process: asyncio.subprocess.Process | None,
        job: int | None,
        gate: int | None,
    ) -> None:
        if gate is not None:
            self._quiet(self._api.close, gate)
        if job is not None:
            self._quiet(self._api.terminate, job)
        if process is not None:
            try:
                process.kill()
                await process.wait()
            except BaseException:
                pass
        if job is not None:
            self._quiet(self._api.close, job)

    @staticmethod
    async def _reap(process: asyncio.subprocess.Process) -> None:
        try:
            while process.returncode is None:
                await asyncio.sleep(0.01)
        except BaseException:
            pass

    def _reaper_finished(
        self,
        process: asyncio.subprocess.Process,
        job: int,
        gate: int,
        task: asyncio.Task[None],
    ) -> None:
        self._reapers.discard(task)
        try:
            task.result()
        except BaseException:
            pass
        if self._jobs.get(process) == (job, gate):
            self._jobs.pop(process, None)
            self._quiet(self._api.close, job)
            self._quiet(self._api.close, gate)

    @staticmethod
    def _quiet(operation: Callable[[int], None], handle: int) -> None:
        try:
            operation(handle)
        except BaseException:
            pass


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
    )]


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _Kernel32JobApi:
    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError("Windows Job Objects are unavailable")
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = ctypes.c_void_p
        boolean = ctypes.c_int
        self._kernel32.CreateJobObjectW.argtypes = (handle, ctypes.c_wchar_p)
        self._kernel32.CreateJobObjectW.restype = handle
        self._kernel32.SetInformationJobObject.argtypes = (
            handle, ctypes.c_int, handle, ctypes.c_uint32
        )
        self._kernel32.SetInformationJobObject.restype = boolean
        self._kernel32.CreateEventW.argtypes = (
            handle, boolean, boolean, ctypes.c_wchar_p
        )
        self._kernel32.CreateEventW.restype = handle
        self._kernel32.OpenProcess.argtypes = (
            ctypes.c_uint32, boolean, ctypes.c_uint32
        )
        self._kernel32.OpenProcess.restype = handle
        self._kernel32.AssignProcessToJobObject.argtypes = (handle, handle)
        self._kernel32.AssignProcessToJobObject.restype = boolean
        self._kernel32.SetEvent.argtypes = (handle,)
        self._kernel32.SetEvent.restype = boolean
        self._kernel32.TerminateJobObject.argtypes = (handle, ctypes.c_uint32)
        self._kernel32.TerminateJobObject.restype = boolean
        self._kernel32.CloseHandle.argtypes = (handle,)
        self._kernel32.CloseHandle.restype = boolean

    def create_job(self) -> int:
        handle = self._kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise OSError("Job Object creation failed")
        info = _ExtendedLimitInformation()
        info.BasicLimitInformation.LimitFlags = _KILL_ON_JOB_CLOSE
        if not self._kernel32.SetInformationJobObject(
            handle,
            _JOB_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            self.close(handle)
            raise OSError("Job Object configuration failed")
        return int(handle)

    def create_gate(self) -> tuple[int, str]:
        name = f"Local\\NobusOrchestrator-{uuid4().hex}"
        handle = self._kernel32.CreateEventW(None, True, False, name)
        if not handle:
            raise OSError("startup gate creation failed")
        return int(handle), name

    def assign(self, job: int, process_id: int) -> None:
        process = self._kernel32.OpenProcess(_PROCESS_ACCESS, False, process_id)
        if not process:
            raise OSError("process handle is unavailable")
        try:
            if not self._kernel32.AssignProcessToJobObject(job, process):
                raise OSError("Job Object assignment failed")
        finally:
            self.close(process)

    def signal(self, gate: int) -> None:
        if not self._kernel32.SetEvent(gate):
            raise OSError("startup gate signal failed")

    def terminate(self, job: int) -> None:
        if not self._kernel32.TerminateJobObject(job, 125):
            raise OSError("Job Object termination failed")

    def close(self, handle: int) -> None:
        if handle and not self._kernel32.CloseHandle(handle):
            raise OSError("Windows handle close failed")
