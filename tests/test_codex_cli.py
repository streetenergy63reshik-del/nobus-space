"""Adversarial tests for the fake-only Codex CLI boundary."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from src.contracts import TaskContract
from src.workers import CodexCliAdapter, CodexCliError, ProcessOutput


@dataclass
class FakeProcess:
    output: ProcessOutput = ProcessOutput(
        b'{"type":"agent_message","status":"success","message":"done"}\n',
        b"",
        0,
    )
    delay: float = 0
    failure: BaseException | None = None
    killed: bool = False
    waited: bool = False
    wait_started: bool = False
    wait_delay: float = 0
    stdin: bytes | None = None
    limits: tuple[int, int] | None = None

    async def communicate(
        self, *, stdin: bytes, stdout_limit: int, stderr_limit: int
    ) -> ProcessOutput:
        self.stdin = stdin
        self.limits = (stdout_limit, stderr_limit)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.failure is not None:
            raise self.failure
        return self.output

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> int:
        self.wait_started = True
        if self.wait_delay:
            await asyncio.sleep(self.wait_delay)
        self.waited = True
        return self.output.returncode


@dataclass
class FakeSpawner:
    process: FakeProcess
    failure: Exception | None = None
    delay: float = 0
    aborted: bool = False
    call: dict[str, Any] = field(default_factory=dict)

    async def __call__(
        self,
        *,
        executable: str,
        argv: tuple[str, ...],
        cwd: str,
        env: Mapping[str, str],
    ) -> FakeProcess:
        self.call = {
            "executable": executable,
            "argv": argv,
            "cwd": cwd,
            "env": dict(env),
        }
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.failure is not None:
            raise self.failure
        return self.process

    async def abort_start(self) -> None:
        self.aborted = True


@pytest.fixture
def worker_files(tmp_path: Path) -> tuple[Path, Path, Path]:
    workspace = tmp_path / "workspace"
    allowed = workspace / "repo"
    allowed.mkdir(parents=True)
    executable = tmp_path / "codex.exe"
    executable.touch()
    return workspace, allowed, executable


def make_contract(allowed: Path, **overrides: object) -> TaskContract:
    data: dict[str, object] = {
        "task_id": uuid4(),
        "idempotency_key": "tenant-a:worker:1",
        "tenant_id": "tenant-a",
        "source": "api",
        "instruction": "Inspect the repository; $(touch escaped) is plain input.",
        "allowed_paths": [str(allowed)],
        "permissions": ["repo.read", "process.run_allowlisted"],
        "risk": "low",
        "acceptance_criteria": ["Return one safe summary."],
        "timeout_seconds": 1,
        "quality_profile": "code-default@1",
    }
    data.update(overrides)
    return TaskContract(**data)


def adapter_for(
    files: tuple[Path, Path, Path], process: FakeProcess | None = None, **limits: int
) -> tuple[CodexCliAdapter, FakeSpawner]:
    workspace, _, executable = files
    spawner = FakeSpawner(process or FakeProcess())
    return (
        CodexCliAdapter(
            workspace_root=workspace,
            executable=executable,
            spawner=spawner,
            **limits,
        ),
        spawner,
    )


@pytest.mark.asyncio
async def test_executes_only_fixed_argv_and_utf8_prompt(
    worker_files: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, allowed, executable = worker_files
    monkeypatch.setenv("TOP_SECRET_TOKEN", "do-not-inherit")
    adapter, spawner = adapter_for(worker_files)

    result = await adapter.execute(
        make_contract(
            allowed,
            instruction="Проверь; --danger && calc.exe",
            acceptance_criteria=["Критерий один"],
        )
    )

    assert result.message == "done"
    assert spawner.call["executable"] == str(executable.resolve())
    assert spawner.call["argv"] == (
        "exec",
        "--json",
        "--sandbox",
        "read-only",
        "-",
    )
    assert spawner.call["cwd"] == str(allowed.resolve())
    assert spawner.call["env"] == {
        "LANG": "C.UTF-8",
        "NO_COLOR": "1",
        "PYTHONUTF8": "1",
        "TERM": "dumb",
    }
    assert "TOP_SECRET_TOKEN" not in spawner.call["env"]
    assert json.loads(spawner.process.stdin.decode("utf-8")) == {
        "instruction": "Проверь; --danger && calc.exe",
        "acceptance_criteria": ["Критерий один"],
    }


@pytest.mark.asyncio
async def test_write_permission_selects_only_fixed_workspace_profile(
    worker_files: tuple[Path, Path, Path]
) -> None:
    _, allowed, _ = worker_files
    adapter, spawner = adapter_for(worker_files)

    await adapter.execute(
        make_contract(
            allowed,
            permissions=[
                "repo.read",
                "repo.write_allowlisted",
                "process.run_allowlisted",
            ],
        )
    )

    assert spawner.call["argv"] == (
        "exec",
        "--json",
        "--sandbox",
        "workspace-write",
        "-",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "permissions",
    [
        ["repo.read"],
        ["repo.read", "process.run_allowlisted", "shell.any"],
        ["repo.read", "process.run_allowlisted", "external.read_allowlisted"],
        ["repo.read", "process.run_allowlisted", "external.write_l4"],
        ["repo.read", "process.run_allowlisted", "artifact.write_allowlisted"],
        ["process.run_allowlisted", "repo.write_allowlisted"],
    ],
)
async def test_unknown_missing_and_external_permissions_fail_closed(
    worker_files: tuple[Path, Path, Path], permissions: list[str]
) -> None:
    _, allowed, _ = worker_files
    adapter, spawner = adapter_for(worker_files)

    with pytest.raises(CodexCliError) as caught:
        await adapter.execute(make_contract(allowed, permissions=permissions))

    assert caught.value.code == "worker_forbidden"
    assert not spawner.call


@pytest.mark.asyncio
async def test_all_paths_must_exist_and_stay_inside_workspace(
    worker_files: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    _, allowed, _ = worker_files
    adapter, spawner = adapter_for(worker_files)
    outside = tmp_path / "outside"
    outside.mkdir()

    for paths in ([str(outside)], [str(allowed), str(outside)], [str(allowed / "missing")]):
        with pytest.raises(CodexCliError) as caught:
            await adapter.execute(make_contract(allowed, allowed_paths=paths))
        assert caught.value.code == "worker_forbidden"
    assert not spawner.call


@pytest.mark.asyncio
async def test_nul_and_oversized_prompt_never_reach_process(
    worker_files: tuple[Path, Path, Path]
) -> None:
    _, allowed, _ = worker_files
    adapter, spawner = adapter_for(worker_files, prompt_limit=80)

    with pytest.raises(CodexCliError) as nul:
        await adapter.execute(make_contract(allowed, instruction="bad\x00input"))
    assert nul.value.code == "worker_forbidden"
    with pytest.raises(CodexCliError) as large:
        await adapter.execute(make_contract(allowed, instruction="x" * 200))
    assert large.value.code == "worker_forbidden"
    assert not spawner.call


@pytest.mark.asyncio
async def test_timeout_kills_and_waits_without_leaking_details(
    worker_files: tuple[Path, Path, Path]
) -> None:
    _, allowed, _ = worker_files
    process = FakeProcess(delay=2)
    adapter, _ = adapter_for(worker_files, process)

    with pytest.raises(CodexCliError) as caught:
        await adapter.execute(make_contract(allowed))

    assert caught.value.code == "worker_timeout"
    assert process.killed and process.waited
    assert str(allowed) not in str(caught.value)


@pytest.mark.asyncio
async def test_cancellation_kills_and_waits_then_propagates(
    worker_files: tuple[Path, Path, Path]
) -> None:
    _, allowed, _ = worker_files
    process = FakeProcess(delay=10)
    adapter, _ = adapter_for(worker_files, process)
    task = asyncio.create_task(adapter.execute(make_contract(allowed)))
    await asyncio.sleep(0)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert process.killed and process.waited


@pytest.mark.asyncio
async def test_repeated_cancellation_cannot_interrupt_cleanup_drain(
    worker_files: tuple[Path, Path, Path]
) -> None:
    _, allowed, _ = worker_files
    process = FakeProcess(delay=10, wait_delay=0.05)
    workspace, _, executable = worker_files
    spawner = FakeSpawner(process)
    adapter = CodexCliAdapter(
        workspace_root=workspace,
        executable=executable,
        spawner=spawner,
        cleanup_timeout=0.5,
    )
    task = asyncio.create_task(adapter.execute(make_contract(allowed)))
    await asyncio.sleep(0)

    task.cancel()
    while not process.wait_started:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert process.killed and process.waited


@pytest.mark.asyncio
async def test_cancellation_during_timeout_cleanup_is_not_lost(
    worker_files: tuple[Path, Path, Path]
) -> None:
    _, allowed, _ = worker_files
    process = FakeProcess(delay=2, wait_delay=0.05)
    workspace, _, executable = worker_files
    adapter = CodexCliAdapter(
        workspace_root=workspace,
        executable=executable,
        spawner=FakeSpawner(process),
        cleanup_timeout=0.5,
    )
    task = asyncio.create_task(adapter.execute(make_contract(allowed)))
    while not process.wait_started:
        await asyncio.sleep(0.01)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert process.killed and process.waited


@pytest.mark.asyncio
async def test_start_and_runtime_failures_have_stable_safe_errors(
    worker_files: tuple[Path, Path, Path]
) -> None:
    _, allowed, _ = worker_files
    secret = "token=raw-secret C:\\private\\repo stderr-details"
    adapter, spawner = adapter_for(worker_files)
    spawner.failure = RuntimeError(secret)
    with pytest.raises(CodexCliError) as start:
        await adapter.execute(make_contract(allowed))
    assert start.value.code == "worker_start_failed"
    assert secret not in str(start.value)
    assert start.value.__context__ is None
    assert spawner.aborted

    process = FakeProcess(failure=RuntimeError(secret))
    adapter, _ = adapter_for(worker_files, process)
    with pytest.raises(CodexCliError) as runtime:
        await adapter.execute(make_contract(allowed))
    assert runtime.value.code == "worker_failed"
    assert secret not in str(runtime.value)
    assert runtime.value.__context__ is None
    assert process.killed and process.waited


@pytest.mark.asyncio
async def test_start_timeout_has_timeout_code_without_raw_details(
    worker_files: tuple[Path, Path, Path]
) -> None:
    _, allowed, _ = worker_files
    adapter, spawner = adapter_for(worker_files)
    spawner.delay = 2

    with pytest.raises(CodexCliError) as caught:
        await adapter.execute(make_contract(allowed))

    assert caught.value.code == "worker_timeout"
    assert str(allowed) not in str(caught.value)
    assert spawner.aborted


@pytest.mark.asyncio
async def test_cleanup_wait_has_a_separate_hard_bound(
    worker_files: tuple[Path, Path, Path]
) -> None:
    _, allowed, _ = worker_files
    process = FakeProcess(delay=2, wait_delay=10)
    workspace, _, executable = worker_files
    spawner = FakeSpawner(process)
    adapter = CodexCliAdapter(
        workspace_root=workspace,
        executable=executable,
        spawner=spawner,
        cleanup_timeout=0.01,
    )

    with pytest.raises(CodexCliError) as caught:
        await adapter.execute(make_contract(allowed))

    assert caught.value.code == "worker_timeout"
    assert process.killed


@pytest.mark.asyncio
async def test_nonzero_exit_and_stderr_never_leak(
    worker_files: tuple[Path, Path, Path]
) -> None:
    _, allowed, _ = worker_files
    leaked = b"secret-token C:\\private\\workspace exception text"
    process = FakeProcess(output=ProcessOutput(b"", leaked, 7))
    adapter, _ = adapter_for(worker_files, process)

    with pytest.raises(CodexCliError) as caught:
        await adapter.execute(make_contract(allowed))

    assert caught.value.code == "worker_failed"
    assert leaked.decode() not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stdout",
    [
        b"not-json\n",
        b'{"type":"unknown"}\n',
        b'{"type":"agent_message","status":"success","message":"one"}\n'
        b'{"type":"agent_message","status":"success","message":"two"}\n',
        b'{"type":"started"}\n',
        b'{"type":"agent_message","status":"failed","message":"no"}\n',
        b'{"type":"agent_message","status":"success","message":"ok","extra":1}\n',
        b'{"type":"agent_message","status":"failed","status":"success","message":"no"}\n',
        b'{"type":"agent_message","status":"success","message":"ok"}\n'
        b'{"type":"started"}\n',
        b'{"type":"started"}\n{"type":"started"}\n'
        b'{"type":"agent_message","status":"success","message":"ok"}\n',
        b"\xff\n",
    ],
)
async def test_malformed_unknown_duplicate_or_missing_terminal_is_rejected(
    worker_files: tuple[Path, Path, Path], stdout: bytes
) -> None:
    _, allowed, _ = worker_files
    process = FakeProcess(output=ProcessOutput(stdout, b"", 0))
    adapter, _ = adapter_for(worker_files, process)

    with pytest.raises(CodexCliError) as caught:
        await adapter.execute(make_contract(allowed))

    assert caught.value.code == "worker_protocol_error"
    assert stdout.decode("utf-8", "ignore") not in str(caught.value)


@pytest.mark.asyncio
async def test_stdout_and_stderr_hard_limits_are_enforced(
    worker_files: tuple[Path, Path, Path]
) -> None:
    _, allowed, _ = worker_files
    for output in (
        ProcessOutput(b"x" * 33, b"", 0),
        ProcessOutput(b"", b"secret" * 6, 0),
    ):
        process = FakeProcess(output=output)
        adapter, _ = adapter_for(
            worker_files, process, stdout_limit=32, stderr_limit=32
        )
        with pytest.raises(CodexCliError) as caught:
            await adapter.execute(make_contract(allowed))
        assert caught.value.code == "worker_output_too_large"
        assert process.limits == (32, 32)


def test_configuration_requires_resolved_existing_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(CodexCliError) as caught:
        CodexCliAdapter(
            workspace_root=workspace,
            executable=tmp_path / "missing-codex",
            spawner=FakeSpawner(FakeProcess()),
        )
    assert caught.value.code == "worker_configuration_invalid"
    assert str(tmp_path) not in str(caught.value)


def test_configuration_rejects_relative_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    executable = tmp_path / "codex.exe"
    executable.touch()
    monkeypatch.chdir(tmp_path)

    with pytest.raises(CodexCliError) as caught:
        CodexCliAdapter(
            workspace_root=workspace,
            executable="codex.exe",
            spawner=FakeSpawner(FakeProcess()),
        )

    assert caught.value.code == "worker_configuration_invalid"


@pytest.mark.asyncio
async def test_server_timeout_cap_is_fail_closed(
    worker_files: tuple[Path, Path, Path]
) -> None:
    _, allowed, _ = worker_files
    adapter, spawner = adapter_for(worker_files)

    with pytest.raises(CodexCliError) as caught:
        await adapter.execute(make_contract(allowed, timeout_seconds=901))

    assert caught.value.code == "worker_forbidden"
    assert not spawner.call


def test_server_timeout_configuration_cannot_exceed_900(
    worker_files: tuple[Path, Path, Path]
) -> None:
    workspace, _, executable = worker_files
    with pytest.raises(CodexCliError) as caught:
        CodexCliAdapter(
            workspace_root=workspace,
            executable=executable,
            spawner=FakeSpawner(FakeProcess()),
            max_timeout_seconds=901,
        )
    assert caught.value.code == "worker_configuration_invalid"
