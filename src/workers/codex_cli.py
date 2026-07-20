"""Fail-closed, fake-first boundary for a future Codex CLI process."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from src.contracts import TaskContract


_READ_ARGV = ("exec", "--json", "--sandbox", "read-only", "-")
_WRITE_ARGV = ("exec", "--json", "--sandbox", "workspace-write", "-")
_KNOWN_PERMISSIONS = frozenset(
    {
        "repo.read",
        "repo.write_allowlisted",
        "process.run_allowlisted",
    }
)
_WRITE_PERMISSIONS = frozenset({"repo.write_allowlisted"})
_SAFE_ENV = MappingProxyType(
    {"LANG": "C.UTF-8", "NO_COLOR": "1", "PYTHONUTF8": "1", "TERM": "dumb"}
)
_ERROR_MESSAGES = {
    "worker_configuration_invalid": "Codex worker configuration is invalid.",
    "worker_forbidden": "Codex worker request is not allowed.",
    "worker_start_failed": "Codex worker could not be started.",
    "worker_timeout": "Codex worker timed out.",
    "worker_failed": "Codex worker failed.",
    "worker_protocol_error": "Codex worker returned invalid output.",
    "worker_output_too_large": "Codex worker output is too large.",
}


class CodexCliError(RuntimeError):
    """Public worker failure containing a stable code and no raw details."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(_ERROR_MESSAGES[code])


class CodexCliResult(BaseModel):
    """Validated terminal result from the closed JSONL protocol."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    message: str


@dataclass(frozen=True)
class ProcessOutput:
    """Bounded output returned by an injected process implementation."""

    stdout: bytes
    stderr: bytes
    returncode: int


class SpawnedProcess(Protocol):
    """Small process surface required by the adapter."""

    async def communicate(
        self, *, stdin: bytes, stdout_limit: int, stderr_limit: int
    ) -> ProcessOutput: ...

    def kill(self) -> None: ...

    async def wait(self) -> int: ...


class ProcessSpawner(Protocol):
    """Injected cancellation-safe launcher with no live implementation here."""

    async def __call__(
        self,
        *,
        executable: str,
        argv: tuple[str, ...],
        cwd: str,
        env: Mapping[str, str],
    ) -> SpawnedProcess: ...

    async def abort_start(self) -> None:
        """Kill and wait for any process created before ``__call__`` returned."""
        ...


class CodexCliAdapter:
    """Validate one TaskContract and run it through an injected fake process."""

    def __init__(
        self,
        *,
        workspace_root: str | Path,
        executable: str | Path,
        spawner: ProcessSpawner,
        prompt_limit: int = 64 * 1024,
        stdout_limit: int = 128 * 1024,
        stderr_limit: int = 16 * 1024,
        max_timeout_seconds: int = 900,
        cleanup_timeout: float = 1.0,
    ) -> None:
        try:
            configured_executable = Path(executable)
            workspace = Path(workspace_root).resolve(strict=True)
            resolved_executable = configured_executable.resolve(strict=True)
            valid = (
                workspace.is_dir()
                and configured_executable.is_absolute()
                and resolved_executable.is_file()
                and resolved_executable.is_absolute()
                and callable(spawner)
                and callable(getattr(spawner, "abort_start", None))
                and all(
                    isinstance(limit, int) and not isinstance(limit, bool) and limit > 0
                    for limit in (prompt_limit, stdout_limit, stderr_limit)
                )
                and isinstance(max_timeout_seconds, int)
                and not isinstance(max_timeout_seconds, bool)
                and 1 <= max_timeout_seconds <= 900
                and isinstance(cleanup_timeout, (int, float))
                and not isinstance(cleanup_timeout, bool)
                and cleanup_timeout > 0
            )
        except (OSError, RuntimeError, TypeError):
            valid = False
        if not valid:
            raise CodexCliError("worker_configuration_invalid")

        self._workspace = workspace
        self._executable = resolved_executable
        self._spawner = spawner
        self._prompt_limit = prompt_limit
        self._stdout_limit = stdout_limit
        self._stderr_limit = stderr_limit
        self._max_timeout_seconds = max_timeout_seconds
        self._cleanup_timeout = float(cleanup_timeout)

    async def execute(self, contract: TaskContract) -> CodexCliResult:
        """Execute a validated contract without inheriting ambient authority."""
        permissions = frozenset(contract.permissions)
        if (
            not permissions.issubset(_KNOWN_PERMISSIONS)
            or not {"repo.read", "process.run_allowlisted"}.issubset(permissions)
            or contract.timeout_seconds > self._max_timeout_seconds
        ):
            raise CodexCliError("worker_forbidden")

        cwd = self._resolve_working_directory(contract.allowed_paths)
        prompt = self._build_prompt(contract)
        argv = _WRITE_ARGV if permissions & _WRITE_PERMISSIONS else _READ_ARGV
        deadline = asyncio.get_running_loop().time() + contract.timeout_seconds

        process: SpawnedProcess | None = None
        start_failed = False
        start_timed_out = False
        try:
            process = await asyncio.wait_for(
                self._spawner(
                    executable=str(self._executable),
                    argv=argv,
                    cwd=str(cwd),
                    env=dict(_SAFE_ENV),
                ),
                timeout=contract.timeout_seconds,
            )
        except asyncio.CancelledError:
            await self._abort_start()
            raise
        except TimeoutError:
            start_timed_out = True
        except Exception:
            start_failed = True
        if start_timed_out:
            if await self._abort_start():
                raise asyncio.CancelledError()
            raise CodexCliError("worker_timeout")
        if start_failed or process is None:
            if await self._abort_start():
                raise asyncio.CancelledError()
            raise CodexCliError("worker_start_failed")

        output: ProcessOutput | None = None
        failure_code: str | None = None
        try:
            output = await asyncio.wait_for(
                process.communicate(
                    stdin=prompt,
                    stdout_limit=self._stdout_limit,
                    stderr_limit=self._stderr_limit,
                ),
                timeout=max(0, deadline - asyncio.get_running_loop().time()),
            )
        except asyncio.CancelledError:
            await self._terminate(process)
            raise
        except TimeoutError:
            failure_code = "worker_timeout"
        except Exception:
            failure_code = "worker_failed"

        if failure_code is not None:
            if await self._terminate(process):
                raise asyncio.CancelledError()
            raise CodexCliError(failure_code)
        if not isinstance(output, ProcessOutput):
            raise CodexCliError("worker_failed")
        if (
            type(output.stdout) is not bytes
            or type(output.stderr) is not bytes
            or type(output.returncode) is not int
        ):
            raise CodexCliError("worker_failed")
        if (
            len(output.stdout) > self._stdout_limit
            or len(output.stderr) > self._stderr_limit
        ):
            raise CodexCliError("worker_output_too_large")
        if output.returncode != 0:
            raise CodexCliError("worker_failed")
        return self._parse_stdout(output.stdout)

    def _resolve_working_directory(self, allowed_paths: tuple[str, ...]) -> Path:
        resolved: list[Path] = []
        try:
            for raw in allowed_paths:
                candidate = Path(raw)
                if not candidate.is_absolute():
                    candidate = self._workspace / candidate
                candidate = candidate.resolve(strict=True)
                candidate.relative_to(self._workspace)
                if not candidate.is_dir():
                    raise ValueError
                resolved.append(candidate)
        except (OSError, RuntimeError, TypeError, ValueError):
            resolved = []
        if not resolved:
            raise CodexCliError("worker_forbidden")
        return resolved[0]

    def _build_prompt(self, contract: TaskContract) -> bytes:
        values = (contract.instruction, *contract.acceptance_criteria)
        if any("\x00" in value for value in values):
            raise CodexCliError("worker_forbidden")
        prompt = json.dumps(
            {
                "instruction": contract.instruction,
                "acceptance_criteria": list(contract.acceptance_criteria),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(prompt) > self._prompt_limit:
            raise CodexCliError("worker_forbidden")
        return prompt

    def _parse_stdout(self, raw: bytes) -> CodexCliResult:
        invalid = False
        terminal: CodexCliResult | None = None
        started = False
        try:
            text = raw.decode("utf-8", errors="strict")
            for line in text.splitlines():
                if not line:
                    continue
                if terminal is not None:
                    raise ValueError
                value = json.loads(line, object_pairs_hook=self._unique_object)
                if not isinstance(value, dict):
                    raise ValueError
                if value == {"type": "started"}:
                    if started:
                        raise ValueError
                    started = True
                    continue
                if set(value) != {"type", "status", "message"}:
                    raise ValueError
                if value["type"] != "agent_message" or value["status"] != "success":
                    raise ValueError
                message = value["message"]
                if (
                    not isinstance(message, str)
                    or not message.strip()
                    or "\x00" in message
                    or terminal is not None
                ):
                    raise ValueError
                terminal = CodexCliResult(message=message.strip())
            if terminal is None:
                raise ValueError
        except Exception:
            invalid = True
        if invalid or terminal is None:
            raise CodexCliError("worker_protocol_error")
        return terminal

    @staticmethod
    def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON object key")
            result[key] = value
        return result

    async def _terminate(self, process: SpawnedProcess) -> bool:
        try:
            process.kill()
        except BaseException:
            pass
        return await self._drain_cleanup(process.wait())

    async def _abort_start(self) -> bool:
        return await self._drain_cleanup(self._spawner.abort_start())

    async def _drain_cleanup(
        self, operation: Coroutine[Any, Any, object]
    ) -> bool:
        task = asyncio.create_task(operation)
        deadline = asyncio.get_running_loop().time() + self._cleanup_timeout
        cancelled = False
        while not task.done():
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                task.cancel()
                break
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=remaining)
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
        else:
            task.add_done_callback(self._consume_cleanup_result)
        return cancelled

    @staticmethod
    def _consume_cleanup_result(task: asyncio.Task[object]) -> None:
        try:
            task.result()
        except BaseException:
            pass
