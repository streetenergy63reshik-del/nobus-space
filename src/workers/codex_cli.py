"""Fail-closed, fake-first boundary for a future Codex CLI process."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Coroutine, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from src.contracts import TaskContract


_READ_ARGV = (
    "exec",
    "--json",
    "--ephemeral",
    "--ignore-user-config",
    "--ignore-rules",
    "--config",
    'web_search="disabled"',
    "--config",
    "mcp_servers={}",
    "--config",
    'shell_environment_policy.inherit="all"',
    "--config",
    'shell_environment_policy.include_only=["PATH","SYSTEMROOT","TEMP","TMP","LANG","NO_COLOR","PYTHONUTF8","TERM"]',
    "--config",
    "shell_environment_policy.experimental_use_profile=false",
    "--sandbox",
    "read-only",
    "-",
)
_WRITE_ARGV = (*_READ_ARGV[:-3], "--sandbox", "workspace-write", "-")
_KNOWN_PERMISSIONS = frozenset(
    {
        "repo.read",
        "repo.write",
        "process.run_allowlisted",
    }
)
_SAFE_ENV = MappingProxyType(
    {"LANG": "C.UTF-8", "NO_COLOR": "1", "PYTHONUTF8": "1", "TERM": "dumb"}
)
_RUNTIME_ENV_KEYS = frozenset(
    {*_SAFE_ENV, "CODEX_HOME", "PATH", "SYSTEMROOT", "TEMP", "TMP"}
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
        worker_env: Mapping[str, str] = _SAFE_ENV,
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
            normalized_env = _validated_worker_env(worker_env)
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
        self._worker_env = normalized_env

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

        deadline = asyncio.get_running_loop().time() + contract.timeout_seconds

        argv = _WRITE_ARGV if "repo.write" in permissions else _READ_ARGV
        process: SpawnedProcess | None = None
        start_failed = False
        start_timed_out = False
        try:
            process = await asyncio.wait_for(
                self._spawner(
                    executable=str(self._executable),
                    argv=argv,
                    cwd=str(cwd),
                    env=dict(self._worker_env),
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
        return self._parse_stdout(
            output.stdout,
            allow_file_changes="repo.write" in permissions,
            working_directory=cwd,
        )

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
        selected = resolved[0]
        try:
            current = selected
            while True:
                config = current / ".codex" / "config.toml"
                if config.exists() or config.is_symlink():
                    raise ValueError
                if current == self._workspace:
                    break
                current = current.parent
        except (OSError, RuntimeError, ValueError):
            raise CodexCliError("worker_forbidden") from None
        return selected

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

    def _parse_stdout(
        self,
        raw: bytes,
        *,
        allow_file_changes: bool,
        working_directory: Path,
    ) -> CodexCliResult:
        invalid = False
        terminal: CodexCliResult | None = None
        thread_started = False
        turn_started = False
        turn_completed = False
        todo_id: str | None = None
        todo_completed = False
        safe_item_types = {
            "agent_message",
            "command_execution",
            "reasoning",
        }

        try:
            text = raw.decode("utf-8", errors="strict")
            for line in text.split("\n"):
                if not line:
                    continue
                value = json.loads(line, object_pairs_hook=self._unique_object)
                if not isinstance(value, dict) or not isinstance(
                    value.get("type"), str
                ):
                    raise ValueError
                event_type = value["type"]
                if turn_completed:
                    raise ValueError
                if event_type == "thread.started":
                    thread_id = value.get("thread_id")
                    if (
                        thread_started
                        or set(value) != {"type", "thread_id"}
                        or not isinstance(thread_id, str)
                        or not thread_id.strip()
                        or len(thread_id) > 128
                        or "\x00" in thread_id
                    ):
                        raise ValueError
                    thread_started = True
                    continue
                if event_type == "turn.started":
                    if (
                        not thread_started
                        or turn_started
                        or set(value) != {"type"}
                    ):
                        raise ValueError
                    turn_started = True
                    continue
                if event_type in {"item.started", "item.updated", "item.completed"}:
                    if not thread_started or not turn_started:
                        raise ValueError
                    item = value.get("item")
                    if set(value) != {"type", "item"} or not isinstance(item, dict):
                        raise ValueError
                    item_id = item.get("id")
                    item_type = item.get("type")
                    if (
                        not isinstance(item_id, str)
                        or not item_id
                        or not isinstance(item_type, str)
                    ):
                        raise ValueError
                    if terminal is not None and not (
                        item_type == "todo_list" and event_type == "item.completed"
                    ):
                        raise ValueError
                    if item_type == "file_change":
                        self._validate_file_change(
                            item,
                            event_type=event_type,
                            allowed=allow_file_changes,
                            working_directory=working_directory,
                        )
                        continue
                    if item_type == "todo_list":
                        self._validate_todo_list(item)
                        if event_type == "item.started":
                            if todo_id is not None or terminal is not None:
                                raise ValueError
                            todo_id = item_id
                        elif event_type == "item.updated":
                            if (
                                todo_id != item_id
                                or todo_completed
                                or terminal is not None
                            ):
                                raise ValueError
                        elif event_type == "item.completed":
                            if todo_id != item_id or todo_completed:
                                raise ValueError
                            todo_completed = True
                        else:
                            raise ValueError
                        continue
                    if item_type not in safe_item_types:
                        raise ValueError
                    if item_type == "agent_message":
                        message = item.get("text")
                        if (
                            terminal is not None
                            or event_type != "item.completed"
                            or set(item) != {"id", "type", "text"}
                            or not isinstance(message, str)
                            or not message.strip()
                            or "\x00" in message
                        ):
                            raise ValueError
                        terminal = CodexCliResult(message=message.strip())
                    continue
                if event_type == "turn.completed":
                    usage = value.get("usage")
                    if (
                        not thread_started
                        or not turn_started
                        or terminal is None
                        or (todo_id is not None and not todo_completed)
                        or set(value) != {"type", "usage"}
                        or not isinstance(usage, dict)
                        or not {"input_tokens", "output_tokens"}.issubset(usage)
                        or any(
                            not isinstance(key, str)
                            or type(amount) is not int
                            or amount < 0
                            for key, amount in usage.items()
                        )
                    ):
                        raise ValueError
                    turn_completed = True
                    continue
                raise ValueError
            if (
                not thread_started
                or not turn_started
                or not turn_completed
                or terminal is None
            ):
                raise ValueError
        except Exception:
            invalid = True
        if invalid or terminal is None:
            raise CodexCliError("worker_protocol_error")
        return terminal

    @staticmethod
    def _validate_file_change(
        item: dict[str, object],
        *,
        event_type: str,
        allowed: bool,
        working_directory: Path,
    ) -> None:
        if not allowed or event_type != "item.completed":
            raise ValueError
        if set(item) != {"id", "type", "changes", "status"}:
            raise ValueError
        changes = item.get("changes")
        if (
            item.get("status") != "completed"
            or not isinstance(changes, list)
            or not changes
            or len(changes) > 1_000
        ):
            raise ValueError
        for change in changes:
            if not isinstance(change, dict) or set(change) != {"path", "kind"}:
                raise ValueError
            path = change.get("path")
            kind = change.get("kind")
            if (
                not isinstance(path, str)
                or not path
                or "\x00" in path
                or len(path) > 4_096
                or kind not in {"add", "delete", "update"}
            ):
                raise ValueError
            candidate = Path(path)
            if not candidate.is_absolute():
                candidate = working_directory / candidate
            try:
                candidate.resolve(strict=False).relative_to(working_directory)
            except (OSError, RuntimeError, ValueError):
                raise ValueError from None

    @staticmethod
    def _validate_todo_list(item: dict[str, object]) -> None:
        if set(item) != {"id", "type", "items"}:
            raise ValueError
        entries = item.get("items")
        if not isinstance(entries, list) or len(entries) > 1_000:
            raise ValueError
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"text", "completed"}:
                raise ValueError
            text = entry.get("text")
            if (
                not isinstance(text, str)
                or not text
                or "\x00" in text
                or len(text) > 4_096
                or type(entry.get("completed")) is not bool
            ):
                raise ValueError

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

def build_worker_env(
    *,
    codex_home: str | Path,
    system_root: str | Path,
    temp_root: str | Path,
    workspace_root: str | Path,
    path_entries: tuple[str | Path, ...],
) -> Mapping[str, str]:
    """Build the smallest live environment needed for Codex auth and temp I/O."""
    try:
        workspace = Path(workspace_root).resolve(strict=True)
        temp = Path(temp_root).resolve(strict=True)
        temp.relative_to(workspace)
        if temp == workspace or not temp.is_dir() or not path_entries:
            raise ValueError
        resolved_path_entries = tuple(
            str(Path(entry).resolve(strict=True)) for entry in path_entries
        )
        if any(not Path(entry).is_dir() for entry in resolved_path_entries):
            raise ValueError
    except (OSError, RuntimeError, TypeError, ValueError):
        raise CodexCliError("worker_configuration_invalid") from None
    values = {
        **_SAFE_ENV,
        "CODEX_HOME": str(Path(codex_home).resolve(strict=True)),
        "PATH": os.pathsep.join(dict.fromkeys(resolved_path_entries)),
        "SYSTEMROOT": str(Path(system_root).resolve(strict=True)),
        "TEMP": str(temp),
        "TMP": str(temp),
    }
    return _validated_worker_env(values)


def _validated_worker_env(value: Mapping[str, str]) -> Mapping[str, str]:
    try:
        normalized = dict(value)
        if set(normalized) == set(_SAFE_ENV):
            if normalized != dict(_SAFE_ENV):
                raise ValueError
            return MappingProxyType(normalized)
        if set(normalized) != _RUNTIME_ENV_KEYS:
            raise ValueError
        if any(normalized[key] != expected for key, expected in _SAFE_ENV.items()):
            raise ValueError
        for key in ("CODEX_HOME", "SYSTEMROOT", "TEMP", "TMP"):
            path = Path(normalized[key])
            if not path.is_absolute() or not path.resolve(strict=True).is_dir():
                raise ValueError
        entries = normalized["PATH"].split(os.pathsep)
        if not entries or any(
            not Path(entry).is_absolute()
            or not Path(entry).resolve(strict=True).is_dir()
            for entry in entries
        ):
            raise ValueError
        if Path(normalized["TEMP"]).resolve() != Path(normalized["TMP"]).resolve():
            raise ValueError
    except (KeyError, OSError, RuntimeError, TypeError, ValueError):
        raise CodexCliError("worker_configuration_invalid") from None
    return MappingProxyType(normalized)
