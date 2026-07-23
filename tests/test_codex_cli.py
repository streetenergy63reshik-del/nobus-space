"""Adversarial tests for the fake-only Codex CLI boundary."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from src.contracts import TaskContract
from src.workers import CodexCliAdapter, CodexCliError, CodexCliResult, ProcessOutput
from src.workers.codex_cli import build_worker_env


_SUCCESS_STDOUT = (
    b'{"type":"thread.started","thread_id":"0199a213-81c0-7800-8aa1-bbab2a035a53"}\n'
    b'{"type":"turn.started"}\n'
    b'{"type":"item.completed","item":{"id":"item_1","type":"agent_message","text":"done"}}\n'
    b'{"type":"turn.completed","usage":{"input_tokens":10,"cached_input_tokens":0,'
    b'"output_tokens":2,"reasoning_output_tokens":0}}\n'
)


@dataclass
class FakeProcess:
    output: ProcessOutput = ProcessOutput(_SUCCESS_STDOUT, b"", 0)
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
        "ingress_digest": "sha256:" + "1" * 64,
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
            instruction="Р В РЎСџР РЋР вЂљР В РЎвЂўР В Р вЂ Р В Р’ВµР РЋР вЂљР РЋР Р‰; --danger && calc.exe",
            acceptance_criteria=["Р В РЎв„ўР РЋР вЂљР В РЎвЂР РЋРІР‚С™Р В Р’ВµР РЋР вЂљР В РЎвЂР В РІвЂћвЂ“ Р В РЎвЂўР В РўвЂР В РЎвЂР В Р вЂ¦"],
        )
    )

    assert result.message == "done"
    assert spawner.call["executable"] == str(executable.resolve())
    assert spawner.call["argv"] == (
        "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--model",
        "gpt-5.6-terra",
        "--config",
        'model_reasoning_effort="medium"',
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
    assert spawner.call["cwd"] == str(allowed.resolve())
    assert spawner.call["env"] == {
        "LANG": "C.UTF-8",
        "NO_COLOR": "1",
        "PYTHONUTF8": "1",
        "TERM": "dumb",
    }
    assert "TOP_SECRET_TOKEN" not in spawner.call["env"]
    prompt = json.loads(spawner.process.stdin.decode("utf-8"))
    assert set(prompt) == {
        "instruction",
        "acceptance_criteria",
        "response_protocol",
    }
    assert prompt["instruction"].endswith("; --danger && calc.exe")
    assert len(prompt["acceptance_criteria"]) == 1
    assert '{"answer":"..."}' in prompt["response_protocol"]
    assert "instruction's language" in prompt["response_protocol"]
    assert "omit internal identifiers" in prompt["response_protocol"]
    assert "Never modify files." in prompt["response_protocol"]

@pytest.mark.asyncio
async def test_exact_write_permission_selects_workspace_write_profile(
    worker_files: tuple[Path, Path, Path]
) -> None:
    _, allowed, _ = worker_files
    adapter, spawner = adapter_for(worker_files)

    result = await adapter.execute(
        make_contract(
            allowed,
            permissions=["repo.read", "repo.write", "process.run_allowlisted"],
        )
    )

    assert result.message == "done"
    assert spawner.call["argv"][-3:] == ("--sandbox", "workspace-write", "-")

@pytest.mark.asyncio
async def test_project_codex_config_fails_closed_before_spawn(
    worker_files: tuple[Path, Path, Path]
) -> None:
    _, allowed, _ = worker_files
    config_dir = allowed / ".codex"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        "[mcp_servers.ambient]\nurl = 'https://example.invalid'\n",
        encoding="utf-8",
    )
    adapter, spawner = adapter_for(worker_files)
    with pytest.raises(CodexCliError) as caught:
        await adapter.execute(make_contract(allowed))
    assert caught.value.code == "worker_forbidden"
    assert not spawner.call


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
async def test_official_stream_preserves_unicode_line_separators(
    worker_files: tuple[Path, Path, Path]
) -> None:
    _, allowed, _ = worker_files
    message = "one\u2028two\u2029three"
    stdout = _SUCCESS_STDOUT.replace(b"done", message.encode("utf-8"))
    process = FakeProcess(output=ProcessOutput(stdout, b"", 0))
    adapter, _ = adapter_for(worker_files, process)
    result = await adapter.execute(make_contract(allowed))
    assert result.message == message


@pytest.mark.asyncio
async def test_official_stream_accepts_safe_command_events(
    worker_files: tuple[Path, Path, Path]
) -> None:
    _, allowed, _ = worker_files
    stdout = (
        b'{"type":"thread.started","thread_id":"thread-1"}\n'
        b'{"type":"turn.started"}\n'
        b'{"type":"item.started","item":{"id":"cmd-1","type":"command_execution","status":"in_progress"}}\n'
        b'{"type":"item.completed","item":{"id":"cmd-1","type":"command_execution","status":"completed","exit_code":0}}\n'
        b'{"type":"item.completed","item":{"id":"msg-1","type":"agent_message","text":"safe"}}\n'
        b'{"type":"turn.completed","usage":{"input_tokens":2,"output_tokens":1}}\n'
    )
    process = FakeProcess(output=ProcessOutput(stdout, b"", 0))
    adapter, _ = adapter_for(worker_files, process)

    result = await adapter.execute(make_contract(allowed))

    assert result.message == "safe"


@pytest.mark.asyncio
async def test_official_stream_accepts_bounded_todo_list_events(
    worker_files: tuple[Path, Path, Path]
) -> None:
    _, allowed, _ = worker_files
    stdout = (
        b'{"type":"thread.started","thread_id":"thread-1"}\n'
        b'{"type":"turn.started"}\n'
        b'{"type":"item.started","item":{"id":"todo-1","type":"todo_list","items":[{"text":"Inspect","completed":false}]}}\n'
        b'{"type":"item.updated","item":{"id":"todo-1","type":"todo_list","items":[{"text":"Inspect","completed":true}]}}\n'
        b'{"type":"item.completed","item":{"id":"msg-1","type":"agent_message","text":"safe"}}\n'
        b'{"type":"item.completed","item":{"id":"todo-1","type":"todo_list","items":[{"text":"Inspect","completed":true}]}}\n'
        b'{"type":"turn.completed","usage":{"input_tokens":2,"output_tokens":1}}\n'
    )
    adapter, _ = adapter_for(
        worker_files, FakeProcess(output=ProcessOutput(stdout, b"", 0))
    )

    result = await adapter.execute(make_contract(allowed))

    assert result.message == "safe"


@pytest.mark.asyncio
async def test_workspace_write_accepts_strict_file_change_event(
    worker_files: tuple[Path, Path, Path]
) -> None:
    _, allowed, _ = worker_files
    stdout = (
        b'{"type":"thread.started","thread_id":"thread-1"}\n'
        b'{"type":"turn.started"}\n'
        b'{"type":"item.completed","item":{"id":"file-1","type":"file_change","changes":[{"path":"safe.txt","kind":"add"}],"status":"completed"}}\n'
        b'{"type":"item.completed","item":{"id":"msg-1","type":"agent_message","text":"safe"}}\n'
        b'{"type":"turn.completed","usage":{"input_tokens":2,"output_tokens":1}}\n'
    )
    adapter, _ = adapter_for(
        worker_files, FakeProcess(output=ProcessOutput(stdout, b"", 0))
    )

    result = await adapter.execute(
        make_contract(
            allowed,
            permissions=["repo.read", "repo.write", "process.run_allowlisted"],
        )
    )

    assert result.message == "safe"


@pytest.mark.asyncio
async def test_workspace_write_rejects_file_change_outside_working_directory(
    worker_files: tuple[Path, Path, Path]
) -> None:
    _, allowed, _ = worker_files
    stdout = (
        b'{"type":"thread.started","thread_id":"thread-1"}\n'
        b'{"type":"turn.started"}\n'
        b'{"type":"item.completed","item":{"id":"file-1","type":"file_change","changes":[{"path":"../escape.txt","kind":"add"}],"status":"completed"}}\n'
        b'{"type":"item.completed","item":{"id":"msg-1","type":"agent_message","text":"safe"}}\n'
        b'{"type":"turn.completed","usage":{"input_tokens":2,"output_tokens":1}}\n'
    )
    adapter, _ = adapter_for(
        worker_files, FakeProcess(output=ProcessOutput(stdout, b"", 0))
    )

    with pytest.raises(CodexCliError) as caught:
        await adapter.execute(
            make_contract(
                allowed,
                permissions=["repo.read", "repo.write", "process.run_allowlisted"],
            )
        )

    assert caught.value.code == "worker_protocol_error"


@pytest.mark.asyncio
async def test_read_only_rejects_file_change_event(
    worker_files: tuple[Path, Path, Path]
) -> None:
    _, allowed, _ = worker_files
    stdout = (
        b'{"type":"thread.started","thread_id":"thread-1"}\n'
        b'{"type":"turn.started"}\n'
        b'{"type":"item.completed","item":{"id":"file-1","type":"file_change","changes":[{"path":"safe.txt","kind":"add"}],"status":"completed"}}\n'
        b'{"type":"item.completed","item":{"id":"msg-1","type":"agent_message","text":"safe"}}\n'
        b'{"type":"turn.completed","usage":{"input_tokens":2,"output_tokens":1}}\n'
    )
    adapter, _ = adapter_for(
        worker_files, FakeProcess(output=ProcessOutput(stdout, b"", 0))
    )

    with pytest.raises(CodexCliError) as caught:
        await adapter.execute(make_contract(allowed))

    assert caught.value.code == "worker_protocol_error"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stdout",
    [
        b"not-json\n",
        b'{"type":"unknown"}\n',
        b'{"type":"agent_message","status":"success","message":"old fake"}\n',
        b'{"type":"thread.started","thread_id":"thread-1"}\n' b'{"type":"turn.started"}\n',
        b'{"type":"thread.started","thread_id":"thread-1"}\n' b'{"type":"turn.started"}\n' b'{"type":"item.completed","item":{"id":"msg-1","type":"agent_message","text":"one"}}\n' b'{"type":"item.completed","item":{"id":"msg-2","type":"agent_message","text":"two"}}\n',
        b'{"type":"thread.started","thread_id":"thread-1"}\n' b'{"type":"turn.started"}\n' b'{"type":"item.completed","item":{"id":"file-1","type":"file_change"}}\n',
        b'{"type":"thread.started","thread_id":"thread-1"}\n' b'{"type":"turn.started"}\n' b'{"type":"error","message":"private detail"}\n',
        b'{"type":"thread.started","thread_id":"thread-1"}\n' b'{"type":"turn.started"}\n' b'{"type":"item.completed","item":{"id":"msg-1","type":"agent_message","text":"ok","extra":1}}\n',
        b'{"type":"thread.started","type":"turn.started"}\n',
        b'{"type":"thread.started","thread_id":"thread-1"}\n' b'{"type":"turn.started"}\n' b'{"type":"item.completed","item":{"id":"msg-1","type":"agent_message","text":"ok"}}\n' b'{"type":"turn.completed","usage":{"input_tokens":true,"output_tokens":1}}\n',
        _SUCCESS_STDOUT + b'{"type":"turn.started"}\n',
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

def test_live_worker_env_is_exact_and_rejects_extra_keys(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    system_root = tmp_path / "windows"
    workspace = tmp_path / "workspace"
    temp_root = workspace / "temp"
    path_entry = system_root / "System32"
    for path in (codex_home, path_entry, temp_root):
        path.mkdir(parents=True)
    environment = build_worker_env(
        codex_home=codex_home,
        system_root=system_root,
        temp_root=temp_root,
        workspace_root=workspace,
        path_entries=(path_entry,),
    )
    assert set(environment) == {
        "LANG",
        "NO_COLOR",
        "PYTHONUTF8",
        "TERM",
        "CODEX_HOME",
        "PATH",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
    }
    assert environment["PATH"] == str(path_entry.resolve())

    executable = tmp_path / "codex.exe"
    executable.touch()
    with pytest.raises(CodexCliError) as caught:
        CodexCliAdapter(
            workspace_root=workspace,
            executable=executable,
            spawner=FakeSpawner(FakeProcess()),
            worker_env={**environment, "TOKEN": "forbidden"},
        )
    assert caught.value.code == "worker_configuration_invalid"


def test_live_worker_env_rejects_temp_outside_workspace(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    system_root = tmp_path / "windows"
    workspace = tmp_path / "workspace"
    outside_temp = tmp_path / "outside-temp"
    path_entry = system_root / "System32"
    for path in (codex_home, workspace, outside_temp, path_entry):
        path.mkdir(parents=True, exist_ok=True)

    with pytest.raises(CodexCliError) as caught:
        build_worker_env(
            codex_home=codex_home,
            system_root=system_root,
            temp_root=outside_temp,
            workspace_root=workspace,
            path_entries=(path_entry,),
        )

    assert caught.value.code == "worker_configuration_invalid"

@pytest.mark.asyncio
async def test_gate5a4_contract_is_accepted_as_read_only(
    worker_files: tuple[Path, Path, Path],
) -> None:
    from src.application.gate5a4 import Gate5A4Runtime
    from tests.test_contracts import make_envelope

    _, allowed, _ = worker_files
    runtime = object.__new__(Gate5A4Runtime)
    runtime._allowed_path = str(allowed)  # type: ignore[attr-defined]
    contract = runtime._contract("Prepare a bounded patch.", make_envelope())
    adapter, spawner = adapter_for(worker_files)

    result = await adapter.execute(contract)

    assert result.message == "done"
    assert contract.permissions == ("repo.read", "process.run_allowlisted")
    assert contract.risk.value == "medium"
    assert "read-only" in spawner.call["argv"]
    assert "workspace-write" not in spawner.call["argv"]


@pytest.mark.asyncio
async def test_gate5a4_worker_probe_validates_live_protocol(tmp_path: Path) -> None:
    from src.application.gate5a4 import Gate5A4Runtime

    class ProbeWorker:
        def __init__(self, message: str) -> None:
            self.message = message
            self.contract: object | None = None

        async def execute(self, contract: object) -> CodexCliResult:
            self.contract = contract
            return CodexCliResult(message=self.message)

    worker = ProbeWorker("NOBUS_CODEX_WORKER_READY")
    runtime = object.__new__(Gate5A4Runtime)
    runtime._allowed_path = str(tmp_path)  # type: ignore[attr-defined]
    runtime._worker = worker  # type: ignore[attr-defined]

    await runtime.probe_worker()

    assert worker.contract is not None
    assert worker.contract.timeout_seconds == 45  # type: ignore[attr-defined]
    assert worker.contract.permissions == (  # type: ignore[attr-defined]
        "repo.read",
        "process.run_allowlisted",
    )


@pytest.mark.asyncio
async def test_gate5a4_worker_probe_fails_closed_on_wrong_sentinel(
    tmp_path: Path,
) -> None:
    from src.application.gate5a4 import Gate5A4Runtime

    class WrongWorker:
        async def execute(self, contract: object) -> CodexCliResult:
            return CodexCliResult(message="unexpected")

    runtime = object.__new__(Gate5A4Runtime)
    runtime._allowed_path = str(tmp_path)  # type: ignore[attr-defined]
    runtime._worker = WrongWorker()  # type: ignore[attr-defined]

    with pytest.raises(CodexCliError) as caught:
        await runtime.probe_worker()

    assert caught.value.code == "worker_protocol_error"


@pytest.mark.asyncio
async def test_gate5a4_worker_probe_preserves_timeout_code(tmp_path: Path) -> None:
    from src.application.gate5a4 import Gate5A4Runtime

    class TimeoutWorker:
        async def execute(self, contract: object) -> CodexCliResult:
            raise CodexCliError("worker_timeout")

    runtime = object.__new__(Gate5A4Runtime)
    runtime._allowed_path = str(tmp_path)  # type: ignore[attr-defined]
    runtime._worker = TimeoutWorker()  # type: ignore[attr-defined]

    with pytest.raises(CodexCliError) as caught:
        await runtime.probe_worker()

    assert caught.value.code == "worker_timeout"

@pytest.mark.asyncio
async def test_gate5a4_retries_one_transient_read_only_worker_failure() -> None:
    from src.application.gate5a4 import Gate5A4Runtime

    class FlakyWorker:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self, contract: object) -> CodexCliResult:
            self.calls += 1
            if self.calls == 1:
                raise CodexCliError("worker_failed")
            return CodexCliResult(message='{"answer":"Работает."}')

    worker = FlakyWorker()
    runtime = object.__new__(Gate5A4Runtime)
    runtime._worker = worker  # type: ignore[attr-defined]

    result = await runtime._execute_worker(SimpleNamespace(timeout_seconds=1))  # type: ignore[arg-type]

    assert result.message == '{"answer":"Работает."}'
    assert worker.calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "expected_calls"),
    (("worker_failed", 2), ("worker_timeout", 1), ("worker_forbidden", 1)),
)
async def test_gate5a4_worker_retry_is_bounded_and_policy_aware(
    code: str, expected_calls: int
) -> None:
    from src.application.gate5a4 import Gate5A4Runtime

    class FailingWorker:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self, contract: object) -> CodexCliResult:
            self.calls += 1
            raise CodexCliError(code)

    worker = FailingWorker()
    runtime = object.__new__(Gate5A4Runtime)
    runtime._worker = worker  # type: ignore[attr-defined]

    with pytest.raises(CodexCliError) as caught:
        await runtime._execute_worker(SimpleNamespace(timeout_seconds=1))  # type: ignore[arg-type]

    assert caught.value.code == code
    assert worker.calls == expected_calls


@pytest.mark.asyncio
async def test_gate5a4_retry_shares_the_original_worker_deadline() -> None:
    from src.application.gate5a4 import Gate5A4Runtime

    class LateFailureWorker:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self, contract: object) -> CodexCliResult:
            self.calls += 1
            if self.calls == 1:
                await asyncio.sleep(0.04)
                raise CodexCliError("worker_failed")
            await asyncio.sleep(1)
            return CodexCliResult(message='{"answer":"too late"}')

    worker = LateFailureWorker()
    runtime = object.__new__(Gate5A4Runtime)
    runtime._worker = worker  # type: ignore[attr-defined]
    loop = asyncio.get_running_loop()
    started = loop.time()

    with pytest.raises(CodexCliError) as caught:
        await runtime._execute_worker(  # type: ignore[arg-type]
            SimpleNamespace(timeout_seconds=0.08)
        )

    assert caught.value.code == "worker_timeout"
    assert worker.calls == 2
    assert loop.time() - started < 0.3
