"""Offline tests for the allowlisted asyncio process implementation."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from src.workers.asyncio_spawner import (
    AsyncioProcessSpawner,
    AsyncioSpawnedProcess,
    _read_limited,
)


READ_ARGV = ("exec", "--json", "--sandbox", "read-only", "-")
SAFE_ENV = {"LANG": "C.UTF-8", "NO_COLOR": "1", "PYTHONUTF8": "1", "TERM": "dumb"}


class FakeWriter:
    def __init__(self) -> None:
        self.data = bytearray()
        self.closed = False

    def write(self, data: bytes) -> None:
        self.data.extend(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


def reader(data: bytes) -> asyncio.StreamReader:
    stream = asyncio.StreamReader()
    stream.feed_data(data)
    stream.feed_eof()
    return stream


@dataclass
class FakeChild:
    stdout_bytes: bytes = b'{"type":"agent_message","status":"success","message":"done"}\n'
    stderr_bytes: bytes = b""
    code: int = 0
    pid: int = 2_000_000_000
    stdin: FakeWriter = field(default_factory=FakeWriter)
    returncode: int | None = None
    killed: bool = False
    waited: bool = False

    def __post_init__(self) -> None:
        self.stdout = reader(self.stdout_bytes)
        self.stderr = reader(self.stderr_bytes)

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    async def wait(self) -> int:
        self.waited = True
        if self.returncode is None:
            self.returncode = self.code
        return self.returncode


@pytest.fixture
def worker_paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    workspace = tmp_path / "workspace"
    cwd = workspace / "repo"
    cwd.mkdir(parents=True)
    executable = tmp_path / "codex.exe"
    executable.touch()
    return workspace, cwd, executable


async def fake_tree_killer(process: Any) -> None:
    process.kill()


def allowed_call(paths: tuple[Path, Path, Path]) -> dict[str, Any]:
    _, cwd, executable = paths
    return {
        "executable": str(executable.resolve()),
        "argv": READ_ARGV,
        "cwd": str(cwd.resolve()),
        "env": SAFE_ENV,
    }


@pytest.mark.asyncio
async def test_spawns_only_fixed_profile_without_shell_or_ambient_env(
    worker_paths: tuple[Path, Path, Path],
) -> None:
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    child = FakeChild()

    async def spawn(*args: Any, **kwargs: Any) -> Any:
        calls.append((args, kwargs))
        return child

    async def kill_tree(process: Any) -> None:
        process.kill()

    workspace, _, executable = worker_paths
    spawner = AsyncioProcessSpawner(
        workspace_root=workspace,
        executable=executable,
        spawn=spawn,
        tree_killer=kill_tree,
    )
    process = await spawner(**allowed_call(worker_paths))
    output = await process.communicate(stdin=b"prompt", stdout_limit=1024, stderr_limit=64)

    assert output.stdout.endswith(b'"done"}\n')
    assert child.stdin.data == b"prompt"
    assert child.stdin.closed
    args, options = calls[0]
    assert args == (str(executable.resolve()), *READ_ARGV)
    assert options["cwd"] == str(worker_paths[1].resolve())
    assert options["env"] == SAFE_ENV
    assert "shell" not in options
    if os.name == "nt":
        assert options["creationflags"]
        assert "start_new_session" not in options
    else:
        assert options["start_new_session"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "override",
    [
        {"argv": ("exec", "--danger")},
        {"env": {**SAFE_ENV, "TOKEN": "forbidden"}},
        {"argv": list(READ_ARGV)},
    ],
)
async def test_rejects_non_allowlisted_profile_before_spawn(
    worker_paths: tuple[Path, Path, Path], override: dict[str, Any]
) -> None:
    called = False

    async def spawn(*args: Any, **kwargs: Any) -> Any:
        nonlocal called
        called = True
        return FakeChild()

    workspace, _, executable = worker_paths
    spawner = AsyncioProcessSpawner(
        workspace_root=workspace,
        executable=executable,
        spawn=spawn,
        tree_killer=fake_tree_killer,
    )
    with pytest.raises(RuntimeError, match="not allowlisted"):
        await spawner(**{**allowed_call(worker_paths), **override})
    assert not called


@pytest.mark.asyncio
async def test_output_is_bounded_to_limit_plus_one_for_adapter_classification() -> None:
    process = AsyncioSpawnedProcess(
        FakeChild(stdout_bytes=b"x" * 1024), tree_killer=lambda child: asyncio.sleep(0)
    )
    output = await process.communicate(stdin=b"", stdout_limit=64, stderr_limit=64)
    assert output.stdout == b"x" * 65


@pytest.mark.asyncio
async def test_overflow_is_discarded_while_pipe_is_drained_to_eof() -> None:
    stream = asyncio.StreamReader()
    stream.feed_data(b"x" * (256 * 1024))
    task = asyncio.create_task(_read_limited(stream, 64))
    for _ in range(20):
        if not stream._buffer:
            break
        await asyncio.sleep(0)
    assert not stream._buffer
    assert not task.done()
    stream.feed_eof()
    assert await task == b"x" * 65


@pytest.mark.skipif(os.name != "nt", reason="Windows-specific fail-closed guard")
def test_windows_default_launcher_is_rejected_without_job_object_guard(
    worker_paths: tuple[Path, Path, Path],
) -> None:
    workspace, _, executable = worker_paths
    with pytest.raises(ValueError, match="configuration"):
        AsyncioProcessSpawner(
            workspace_root=workspace,
            executable=executable,
        )


@pytest.mark.asyncio
async def test_cancelled_start_is_killed_even_if_abort_waiter_is_cancelled(
    worker_paths: tuple[Path, Path, Path]
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    child = FakeChild()

    async def spawn(*args: Any, **kwargs: Any) -> Any:
        entered.set()
        await release.wait()
        return child

    async def kill_tree(process: Any) -> None:
        process.kill()
        await process.wait()

    workspace, _, executable = worker_paths
    spawner = AsyncioProcessSpawner(
        workspace_root=workspace,
        executable=executable,
        spawn=spawn,
        tree_killer=kill_tree,
    )
    start = asyncio.create_task(spawner(**allowed_call(worker_paths)))
    await entered.wait()
    start.cancel()
    with pytest.raises(asyncio.CancelledError):
        await start

    abort = asyncio.create_task(spawner.abort_start())
    await asyncio.sleep(0)
    abort.cancel()
    with pytest.raises(asyncio.CancelledError):
        await abort
    assert spawner._cleanup_task is not None
    spawner._cleanup_task.cancel()
    await asyncio.sleep(0)
    release.set()
    for _ in range(20):
        if child.waited:
            break
        await asyncio.sleep(0)
    assert child.killed
    assert child.waited


@pytest.mark.asyncio
async def test_tree_killer_runs_even_when_parent_already_exited() -> None:
    child = FakeChild(returncode=0)
    seen: list[int] = []

    async def kill_tree(process: Any) -> None:
        seen.append(process.pid)

    wrapped = AsyncioSpawnedProcess(child, tree_killer=kill_tree)
    wrapped.kill()
    assert await wrapped.wait() == 0
    assert seen == [child.pid]


@pytest.mark.asyncio
async def test_spawn_failure_leaves_no_stale_start(
    worker_paths: tuple[Path, Path, Path]
) -> None:
    calls = 0

    async def spawn(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("private path must not escape")
        return FakeChild()

    workspace, _, executable = worker_paths
    spawner = AsyncioProcessSpawner(
        workspace_root=workspace,
        executable=executable,
        spawn=spawn,
        tree_killer=fake_tree_killer,
    )
    with pytest.raises(OSError):
        await spawner(**allowed_call(worker_paths))
    await spawner(**allowed_call(worker_paths))
    assert calls == 2
