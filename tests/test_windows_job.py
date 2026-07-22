"""Offline tests for the gated Windows Job Object launcher."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from src.workers.windows_job import WindowsJobLauncher, _CREATE_FLAGS
from src.workers.windows_job_helper import _validated


READ_ARGV = ("exec", "--json", "--sandbox", "read-only", "-")
SAFE_ENV = {"LANG": "C.UTF-8", "NO_COLOR": "1", "PYTHONUTF8": "1", "TERM": "dumb"}


@dataclass(eq=False)
class FakeProcess:
    pid: int = 4242
    returncode: int | None = None
    killed: bool = False
    completed: asyncio.Event = field(default_factory=asyncio.Event)

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        self.completed.set()

    async def wait(self) -> int:
        await self.completed.wait()
        return self.returncode or 0


class FakeApi:
    def __init__(self, *, fail_assign: bool = False) -> None:
        self.fail_assign = fail_assign
        self.calls: list[tuple[object, ...]] = []
        self._next_job = 10

    def create_job(self) -> int:
        job = self._next_job
        self._next_job += 1
        self.calls.append(("create_job",))
        return job

    def create_gate(self) -> tuple[int, str]:
        self.calls.append(("create_gate",))
        return 20, "Local\\NobusOrchestrator-" + "a" * 32

    def assign(self, job: int, process_id: int) -> None:
        self.calls.append(("assign", job, process_id))
        if self.fail_assign:
            raise OSError("private process detail")

    def signal(self, gate: int) -> None:
        self.calls.append(("signal", gate))

    def terminate(self, job: int) -> None:
        self.calls.append(("terminate", job))

    def close(self, handle: int) -> None:
        self.calls.append(("close", handle))


@pytest.fixture
def paths(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    workspace = tmp_path / "workspace"
    cwd = workspace / "repo"
    cwd.mkdir(parents=True)
    target = tmp_path / "codex.exe"
    python = tmp_path / "python.exe"
    helper = tmp_path / "helper.py"
    for path in (target, python, helper):
        path.touch()
    return workspace, cwd, target, python, helper


def options(cwd: Path) -> dict[str, object]:
    return {
        "cwd": str(cwd.resolve()),
        "env": SAFE_ENV,
        "stdin": asyncio.subprocess.PIPE,
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
        "creationflags": _CREATE_FLAGS,
    }


def launcher(
    paths: tuple[Path, Path, Path, Path, Path],
    api: FakeApi,
    spawn: Any,
) -> WindowsJobLauncher:
    workspace, _, target, python, helper = paths
    return WindowsJobLauncher(
        workspace_root=workspace,
        target_executable=target,
        python_executable=python,
        helper_script=helper,
        spawn=spawn,
        api=api,
    )


@pytest.mark.asyncio
async def test_helper_is_bound_before_gate_signal(
    paths: tuple[Path, Path, Path, Path, Path]
) -> None:
    api = FakeApi()
    process = FakeProcess()
    spawn_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def spawn(*args: object, **kwargs: object) -> FakeProcess:
        spawn_calls.append((args, kwargs))
        api.calls.append(("spawn",))
        return process

    boundary = launcher(paths, api, spawn)
    _, cwd, target, python, helper = paths
    returned = await boundary(str(target.resolve()), *READ_ARGV, **options(cwd))
    assert returned is process
    assert [call[0] for call in api.calls[:6]] == [
        "create_job", "create_gate", "spawn", "assign", "signal", "close"
    ]
    args, passed = spawn_calls[0]
    assert args == (
        str(python.resolve()), "-I", str(helper.resolve()),
        "Local\\NobusOrchestrator-" + "a" * 32,
        "--", str(target.resolve()), *READ_ARGV,
    )
    assert passed == options(cwd)

    process.returncode = 125
    process.completed.set()
    await boundary.kill_tree(process)  # type: ignore[arg-type]
    assert ("terminate", 10) in api.calls
    assert ("close", 10) in api.calls


@pytest.mark.asyncio
async def test_normal_exit_closes_job_and_kills_inherited_descendants(
    paths: tuple[Path, Path, Path, Path, Path]
) -> None:
    api = FakeApi()
    process = FakeProcess()

    async def spawn(*args: object, **kwargs: object) -> FakeProcess:
        return process

    boundary = launcher(paths, api, spawn)
    _, cwd, target, _, _ = paths
    await boundary(str(target.resolve()), *READ_ARGV, **options(cwd))
    process.returncode = 0
    process.completed.set()
    for _ in range(20):
        if ("close", 10) in api.calls:
            break
        await asyncio.sleep(0)
    assert ("close", 10) in api.calls
    for _ in range(20):
        if not boundary._reapers:
            break
        await asyncio.sleep(0)
    assert boundary._reapers == set()


@pytest.mark.asyncio
async def test_cancelled_reaper_still_closes_owned_job(
    paths: tuple[Path, Path, Path, Path, Path]
) -> None:
    api = FakeApi()
    process = FakeProcess()

    async def spawn(*args: object, **kwargs: object) -> FakeProcess:
        return process

    boundary = launcher(paths, api, spawn)
    _, cwd, target, _, _ = paths
    await boundary(str(target.resolve()), *READ_ARGV, **options(cwd))
    reaper = next(iter(boundary._reapers))
    reaper.cancel()
    with pytest.raises(asyncio.CancelledError):
        await reaper
    await asyncio.sleep(0)
    assert boundary._jobs == {}
    assert boundary._reapers == set()
    assert ("close", 10) in api.calls


@pytest.mark.asyncio
async def test_assignment_failure_kills_helper_and_sanitizes_error(
    paths: tuple[Path, Path, Path, Path, Path]
) -> None:
    api = FakeApi(fail_assign=True)
    process = FakeProcess()

    async def spawn(*args: object, **kwargs: object) -> FakeProcess:
        return process

    boundary = launcher(paths, api, spawn)
    _, cwd, target, _, _ = paths
    with pytest.raises(RuntimeError, match="Job Object launch failed") as caught:
        await boundary(str(target.resolve()), *READ_ARGV, **options(cwd))
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert process.killed
    assert ("terminate", 10) in api.calls
    assert ("close", 20) in api.calls
    assert ("close", 10) in api.calls


@pytest.mark.asyncio
async def test_non_allowlisted_call_has_no_os_side_effect(
    paths: tuple[Path, Path, Path, Path, Path]
) -> None:
    api = FakeApi()
    called = False

    async def spawn(*args: object, **kwargs: object) -> FakeProcess:
        nonlocal called
        called = True
        return FakeProcess()

    boundary = launcher(paths, api, spawn)
    _, cwd, target, _, _ = paths
    with pytest.raises(RuntimeError, match="not allowlisted"):
        await boundary(
            str(target.resolve()), "exec", "--danger", **options(cwd)
        )
    assert not called
    assert api.calls == []


@pytest.mark.asyncio
async def test_same_pid_cannot_replace_existing_job_identity(
    paths: tuple[Path, Path, Path, Path, Path]
) -> None:
    api = FakeApi()
    first = FakeProcess(pid=4242)
    second = FakeProcess(pid=4242)
    processes = iter((first, second))

    async def spawn(*args: object, **kwargs: object) -> FakeProcess:
        return next(processes)

    boundary = launcher(paths, api, spawn)
    _, cwd, target, _, _ = paths
    await boundary(str(target.resolve()), *READ_ARGV, **options(cwd))
    await boundary(str(target.resolve()), *READ_ARGV, **options(cwd))
    assert len(boundary._jobs) == 2

    first.returncode = 125
    first.completed.set()
    await boundary.kill_tree(first)  # type: ignore[arg-type]
    assert boundary._jobs.get(second) == 11  # type: ignore[arg-type]
    second.returncode = 125
    second.completed.set()
    await boundary.kill_tree(second)  # type: ignore[arg-type]
    assert boundary._jobs == {}


def test_helper_validation_rejects_profile_and_gate_tampering(
    paths: tuple[Path, Path, Path, Path, Path]
) -> None:
    _, _, target, _, _ = paths
    gate = "Local\\NobusOrchestrator-" + "a" * 32
    assert _validated([gate, "--", str(target.resolve()), *READ_ARGV]) == (
        gate,
        (str(target.resolve()), *READ_ARGV),
    )
    for argv in (
        ["Global\\NobusOrchestrator-" + "a" * 32, "--", str(target), *READ_ARGV],
        [gate, "--", str(target), "exec", "--danger"],
        [gate, "--", "relative.exe", *READ_ARGV],
    ):
        with pytest.raises(ValueError, match="invalid"):
            _validated(argv)
