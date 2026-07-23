"""Bounded read-only access to Codex account rate-limit metadata."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from src.workers.codex_cli import (
    _RATE_LIMIT_ARGV,
    _SAFE_ENV,
    _validated_worker_env,
    build_worker_env,
)
from src.workers.windows_job import WindowsJobLauncher


_WEEK_MINUTES = 7 * 24 * 60
_MAX_MESSAGES = 32
_MAX_RESPONSE_BYTES = 64 * 1024
_STDERR_LIMIT = 16 * 1024
_CREATE_FLAGS = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW


class CodexRateLimitError(RuntimeError):
    """Public failure that never includes provider or credential details."""


@dataclass(frozen=True, slots=True)
class WeeklyLimitSnapshot:
    """One validated seven-day Codex rate-limit window."""

    used_percent: int
    resets_at: int | None


class _Writer(Protocol):
    def write(self, data: bytes) -> None: ...

    async def drain(self) -> None: ...


class _Process(Protocol):
    stdin: _Writer | None
    stdout: asyncio.StreamReader | None
    stderr: asyncio.StreamReader | None


Spawn = Callable[..., Awaitable[_Process]]
Terminate = Callable[[_Process], Awaitable[None]]


class CodexRateLimitClient:
    """Fetch one account snapshot without starting a model turn or tools."""

    def __init__(
        self,
        *,
        workspace_root: str | Path,
        executable: str | Path,
        spawn: Spawn,
        terminate: Terminate,
        worker_env: Mapping[str, str] = _SAFE_ENV,
        timeout_seconds: float = 15,
    ) -> None:
        try:
            workspace = Path(workspace_root).resolve(strict=True)
            binary = Path(executable).resolve(strict=True)
            environment = _validated_worker_env(worker_env)
            valid = (
                workspace.is_dir()
                and binary.is_file()
                and callable(spawn)
                and callable(terminate)
                and isinstance(timeout_seconds, (int, float))
                and not isinstance(timeout_seconds, bool)
                and 0 < timeout_seconds <= 60
            )
        except (OSError, RuntimeError, TypeError):
            valid = False
        if not valid:
            raise ValueError("Codex rate-limit client configuration is invalid")
        self._workspace = workspace
        self._executable = binary
        self._spawn = spawn
        self._terminate = terminate
        self._worker_env = environment
        self._timeout = float(timeout_seconds)
        self._lock = asyncio.Lock()

    async def fetch_weekly(self) -> WeeklyLimitSnapshot:
        """Return the exact seven-day Codex bucket or fail closed."""
        async with self._lock:
            process: _Process | None = None
            snapshot: WeeklyLimitSnapshot | None = None
            cancelled = False
            try:
                async with asyncio.timeout(self._timeout):
                    process = await self._spawn_process()
                    stdin, stdout, stderr = (
                        process.stdin,
                        process.stdout,
                        process.stderr,
                    )
                    if stdin is None or stdout is None or stderr is None:
                        raise CodexRateLimitError("rate_limit_unavailable")
                    stderr_task = asyncio.create_task(
                        _read_bounded(stderr, _STDERR_LIMIT)
                    )
                    try:
                        await _send(
                            stdin,
                            {
                                "method": "initialize",
                                "id": 0,
                                "params": {
                                    "clientInfo": {
                                        "name": "nobus_orchestrator",
                                        "title": "Nobus Orchestrator",
                                        "version": "0.1.0",
                                    }
                                },
                            },
                        )
                        initialized = await _response(stdout, 0)
                        if not isinstance(initialized.get("result"), dict):
                            raise CodexRateLimitError("rate_limit_unavailable")
                        await _send(stdin, {"method": "initialized", "params": {}})
                        await _send(
                            stdin, {"method": "account/rateLimits/read", "id": 1}
                        )
                        snapshot = _weekly_snapshot(await _response(stdout, 1))
                    finally:
                        stderr_task.cancel()
                        await asyncio.gather(stderr_task, return_exceptions=True)
            except asyncio.CancelledError:
                cancelled = True
            except Exception:
                pass
            finally:
                if process is not None:
                    cancelled = await self._cleanup(process) or cancelled
            if cancelled:
                raise asyncio.CancelledError()
            if snapshot is None:
                raise CodexRateLimitError("rate_limit_unavailable")
            return snapshot

    async def _spawn_process(self) -> _Process:
        options: dict[str, Any] = {
            "cwd": str(self._workspace),
            "env": dict(self._worker_env),
            "stdin": asyncio.subprocess.PIPE,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
        }
        if os.name == "nt":
            options["creationflags"] = _CREATE_FLAGS
        else:
            options["start_new_session"] = True
        return await self._spawn(str(self._executable), *_RATE_LIMIT_ARGV, **options)

    async def _cleanup(self, process: _Process) -> bool:
        task = asyncio.create_task(self._terminate(process))
        cancelled = False
        while not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=5)
            except asyncio.CancelledError:
                cancelled = True
                continue
            except Exception:
                task.cancel()
                break
        if task.done():
            try:
                task.result()
            except BaseException:
                pass
        return cancelled


def build_codex_rate_limit_client(
    *,
    workspace_root: str | Path,
    executable: str | Path,
    codex_home: str | Path,
    system_root: str | Path,
    temp_root: str | Path,
    path_entries: tuple[str | Path, ...],
) -> CodexRateLimitClient:
    """Build the live client on the existing Windows Job Object boundary."""
    environment = build_worker_env(
        codex_home=codex_home,
        system_root=system_root,
        temp_root=temp_root,
        workspace_root=workspace_root,
        path_entries=path_entries,
    )
    launcher = WindowsJobLauncher(
        workspace_root=workspace_root,
        target_executable=executable,
        worker_env=environment,
    )
    return CodexRateLimitClient(
        workspace_root=workspace_root,
        executable=executable,
        spawn=launcher,
        terminate=launcher.kill_tree,  # type: ignore[arg-type]
        worker_env=environment,
    )


async def _send(writer: _Writer, value: dict[str, object]) -> None:
    writer.write(
        json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode() + b"\n"
    )
    await writer.drain()


async def _response(reader: asyncio.StreamReader, request_id: int) -> dict[str, object]:
    total = 0
    for _ in range(_MAX_MESSAGES):
        line = await reader.readline()
        total += len(line)
        if not line or total > _MAX_RESPONSE_BYTES:
            break
        try:
            value = json.loads(line, object_pairs_hook=_unique_object)
        except (TypeError, ValueError):
            break
        if isinstance(value, dict) and value.get("id") == request_id:
            if "error" in value:
                break
            return value
    raise CodexRateLimitError("rate_limit_unavailable")


def _weekly_snapshot(response: dict[str, object]) -> WeeklyLimitSnapshot:
    result = response.get("result")
    if not isinstance(result, dict):
        raise CodexRateLimitError("rate_limit_unavailable")
    buckets = result.get("rateLimitsByLimitId")
    candidates: list[object] = []
    if isinstance(buckets, dict):
        candidates.append(buckets.get("codex"))
    candidates.append(result.get("rateLimits"))
    for bucket in candidates:
        if not isinstance(bucket, dict):
            continue
        for key in ("primary", "secondary"):
            window = bucket.get(key)
            if not isinstance(window, dict):
                continue
            used = window.get("usedPercent")
            duration = window.get("windowDurationMins")
            reset = window.get("resetsAt")
            if (
                type(used) is int
                and 0 <= used <= 100
                and duration == _WEEK_MINUTES
                and (reset is None or type(reset) is int and reset > 0)
            ):
                return WeeklyLimitSnapshot(used_percent=used, resets_at=reset)
    raise CodexRateLimitError("weekly_limit_unavailable")


async def _read_bounded(reader: asyncio.StreamReader, limit: int) -> bytes:
    output = bytearray()
    while True:
        chunk = await reader.read(4096)
        if not chunk:
            return bytes(output)
        if len(output) <= limit:
            output.extend(chunk[: limit - len(output) + 1])


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result
