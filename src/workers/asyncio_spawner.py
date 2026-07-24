"""Fail-closed asyncio implementation of the existing process boundary."""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any

from src.workers.codex_cli import (
    ProcessOutput,
    _INTENT_ARGV,
    _RATE_LIMIT_ARGV,
    _READ_ARGV,
    _SAFE_ENV,
    _WEB_ARGV,
    _WRITE_ARGV,
    _validated_worker_env,
)


_ARGV_PROFILES = frozenset(
    {_READ_ARGV, _WRITE_ARGV, _WEB_ARGV, _RATE_LIMIT_ARGV, _INTENT_ARGV}
)
_READ_CHUNK = 64 * 1024
TreeKiller = Callable[[asyncio.subprocess.Process], Awaitable[None]]


class AsyncioSpawnedProcess:
    """Bind one asyncio child to the small ``SpawnedProcess`` protocol."""

    def __init__(
        self,
        process: asyncio.subprocess.Process,
        *,
        tree_killer: TreeKiller | None = None,
    ) -> None:
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise RuntimeError("worker pipes are unavailable")
        self._process = process
        if os.name == "nt" and tree_killer is None:
            raise ValueError(
                "Windows requires an independently verified Job Object tree guard"
            )
        self._tree_killer = tree_killer or _kill_posix_process_group
        self._kill_task: asyncio.Task[None] | None = None

    async def communicate(
        self, *, stdin: bytes, stdout_limit: int, stderr_limit: int
    ) -> ProcessOutput:
        if type(stdin) is not bytes or not _positive_int(stdout_limit) or not _positive_int(
            stderr_limit
        ):
            raise TypeError("worker communication arguments are invalid")
        assert self._process.stdout is not None
        assert self._process.stderr is not None
        async with asyncio.TaskGroup() as group:
            group.create_task(self._feed(stdin))
            stdout_task = group.create_task(
                _read_limited(self._process.stdout, stdout_limit)
            )
            stderr_task = group.create_task(
                _read_limited(self._process.stderr, stderr_limit)
            )
            wait_task = group.create_task(self._process.wait())
        return ProcessOutput(
            stdout=stdout_task.result(),
            stderr=stderr_task.result(),
            returncode=wait_task.result(),
        )

    def kill(self) -> None:
        if self._kill_task is None:
            self._kill_task = asyncio.create_task(self._tree_killer(self._process))

    async def wait(self) -> int:
        if self._kill_task is not None:
            await asyncio.shield(self._kill_task)
        return await self._process.wait()

    async def _feed(self, data: bytes) -> None:
        writer = self._process.stdin
        assert writer is not None
        try:
            writer.write(data)
            await writer.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (BrokenPipeError, ConnectionResetError):
                pass


class AsyncioProcessSpawner:
    """Create only the executable/workspace/profile approved at construction."""

    def __init__(
        self,
        *,
        workspace_root: str | Path,
        executable: str | Path,
        spawn: Callable[..., Awaitable[asyncio.subprocess.Process]] | None = None,
        tree_killer: TreeKiller | None = None,
        worker_env: Mapping[str, str] = _SAFE_ENV,
    ) -> None:
        try:
            configured_executable = Path(executable)
            workspace = Path(workspace_root).resolve(strict=True)
            resolved_executable = configured_executable.resolve(strict=True)
            valid = (
                configured_executable.is_absolute()
                and workspace.is_dir()
                and resolved_executable.is_absolute()
                and resolved_executable.is_file()
                and (tree_killer is None or callable(tree_killer))
            )
            normalized_env = _validated_worker_env(worker_env)
        except (OSError, RuntimeError, TypeError):
            valid = False
        if not valid or (
            os.name == "nt" and (spawn is None or tree_killer is None)
        ):
            raise ValueError("process spawner configuration is invalid")
        self._workspace = workspace
        self._executable = resolved_executable
        self._spawn = spawn or asyncio.create_subprocess_exec
        self._tree_killer = tree_killer or _kill_posix_process_group
        self._worker_env = normalized_env
        self._start_lock = asyncio.Lock()
        self._start_task: asyncio.Task[asyncio.subprocess.Process] | None = None
        self._cleanup_task: asyncio.Task[None] | None = None

    async def __call__(
        self,
        *,
        executable: str,
        argv: tuple[str, ...],
        cwd: str,
        env: Mapping[str, str],
    ) -> AsyncioSpawnedProcess:
        resolved_cwd = self._validate_call(executable, argv, cwd, env)
        options: dict[str, Any] = {
            "cwd": str(resolved_cwd),
            "env": dict(self._worker_env),
            "stdin": asyncio.subprocess.PIPE,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
        }
        if os.name == "nt":
            options["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            )
        else:
            options["start_new_session"] = True

        async with self._start_lock:
            if self._start_task is not None or self._cleanup_task is not None:
                raise RuntimeError("process start is already active")
            task = asyncio.create_task(
                self._spawn(str(self._executable), *argv, **options)
            )
            self._start_task = task
        try:
            process = await asyncio.shield(task)
        except asyncio.CancelledError:
            self._schedule_cleanup(task)
            raise
        except BaseException:
            if self._start_task is task:
                self._start_task = None
            raise
        if self._start_task is task:
            self._start_task = None
        try:
            return AsyncioSpawnedProcess(process, tree_killer=self._tree_killer)
        except BaseException:
            cleanup = asyncio.create_task(self._terminate_created_process(process))
            self._cleanup_task = cleanup
            cleanup.add_done_callback(self._cleanup_finished)
            raise

    async def abort_start(self) -> None:
        async with self._start_lock:
            task = self._start_task
            cleanup = self._cleanup_task
            if task is not None and cleanup is None:
                cleanup = asyncio.create_task(self._cleanup_started_process(task))
                self._cleanup_task = cleanup
        if cleanup is not None:
            await asyncio.shield(cleanup)

    def _validate_call(
        self,
        executable: str,
        argv: tuple[str, ...],
        cwd: str,
        env: Mapping[str, str],
    ) -> Path:
        try:
            resolved_executable = Path(executable).resolve(strict=True)
            resolved_cwd = Path(cwd).resolve(strict=True)
            resolved_cwd.relative_to(self._workspace)
            valid = (
                resolved_executable == self._executable
                and resolved_cwd.is_dir()
                and type(argv) is tuple
                and argv in _ARGV_PROFILES
                and dict(env) == dict(self._worker_env)
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            valid = False
        if not valid:
            raise RuntimeError("process request is not allowlisted")
        return resolved_cwd

    def _schedule_cleanup(
        self, task: asyncio.Task[asyncio.subprocess.Process]
    ) -> None:
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(
                self._cleanup_started_process(task)
            )

    async def _cleanup_started_process(
        self, task: asyncio.Task[asyncio.subprocess.Process]
    ) -> None:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except BaseException:
                break
        process: asyncio.subprocess.Process | None = None
        if task.done() and not task.cancelled():
            try:
                process = task.result()
            except BaseException:
                pass
        if process is not None:
            await self._terminate_created_process(process)
        async with self._start_lock:
            if self._start_task is task:
                self._start_task = None
            if self._cleanup_task is asyncio.current_task():
                self._cleanup_task = None

    async def _terminate_created_process(
        self, process: asyncio.subprocess.Process
    ) -> None:
        child = AsyncioSpawnedProcess(process, tree_killer=self._tree_killer)
        child.kill()
        wait_task = asyncio.create_task(child.wait())
        while not wait_task.done():
            try:
                await asyncio.shield(wait_task)
            except asyncio.CancelledError:
                continue
            except BaseException:
                break
        if wait_task.done():
            try:
                wait_task.result()
            except BaseException:
                pass

    def _cleanup_finished(self, task: asyncio.Task[None]) -> None:
        try:
            task.result()
        except BaseException:
            pass
        if self._cleanup_task is task:
            self._cleanup_task = None


async def _kill_posix_process_group(
    process: asyncio.subprocess.Process,
) -> None:
    """Terminate a POSIX process group even after its root has exited."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        if process.returncode is None:
            process.kill()


def _positive_int(value: object) -> bool:
    return type(value) is int and value > 0


async def _read_limited(reader: asyncio.StreamReader, limit: int) -> bytes:
    output = bytearray()
    while True:
        chunk = await reader.read(_READ_CHUNK)
        if not chunk:
            return bytes(output)
        if len(output) <= limit:
            remaining = limit - len(output) + 1
            output.extend(chunk[:remaining])
