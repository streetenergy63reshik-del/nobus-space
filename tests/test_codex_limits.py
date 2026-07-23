"""Offline tests for the bounded Codex account limit client."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from src.workers.codex_cli import _RATE_LIMIT_ARGV
from src.workers.codex_limits import CodexRateLimitClient, CodexRateLimitError


class FakeWriter:
    def __init__(self) -> None:
        self.data = bytearray()

    def write(self, data: bytes) -> None:
        self.data.extend(data)

    async def drain(self) -> None:
        return None


def reader(data: bytes = b"", *, eof: bool = True) -> asyncio.StreamReader:
    stream = asyncio.StreamReader()
    stream.feed_data(data)
    if eof:
        stream.feed_eof()
    return stream


@dataclass
class FakeProcess:
    stdout_bytes: bytes
    stdin: FakeWriter = field(default_factory=FakeWriter)
    terminated: bool = False

    def __post_init__(self) -> None:
        self.stdout = reader(self.stdout_bytes)
        self.stderr = reader()


def response(*, duration: int = 10_080, used: object = 14) -> bytes:
    values = (
        {"method": "remoteControl/status/changed", "params": {"status": "disabled"}},
        {"id": 0, "result": {"userAgent": "test"}},
        {
            "id": 1,
            "result": {
                "rateLimits": {
                    "primary": {
                        "usedPercent": 99,
                        "windowDurationMins": 300,
                        "resetsAt": 1,
                    }
                },
                "rateLimitsByLimitId": {
                    "codex_bengalfox": {
                        "primary": {
                            "usedPercent": 0,
                            "windowDurationMins": 10_080,
                            "resetsAt": 2,
                        }
                    },
                    "codex": {
                        "primary": {
                            "usedPercent": used,
                            "windowDurationMins": duration,
                            "resetsAt": 1_785_400_820,
                        }
                    },
                },
            },
        },
    )
    return b"".join(
        json.dumps(value, separators=(",", ":")).encode() + b"\n"
        for value in values
    )


@pytest.fixture
def paths(tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    executable = tmp_path / "codex.exe"
    executable.touch()
    return workspace, executable


def client(
    paths: tuple[Path, Path], process: FakeProcess
) -> tuple[CodexRateLimitClient, list[tuple[tuple[object, ...], dict[str, object]]]]:
    workspace, executable = paths
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def spawn(*args: object, **kwargs: object) -> FakeProcess:
        calls.append((args, kwargs))
        return process

    async def terminate(candidate: Any) -> None:
        assert candidate is process
        process.terminated = True

    return (
        CodexRateLimitClient(
            workspace_root=workspace,
            executable=executable,
            spawn=spawn,
            terminate=terminate,
        ),
        calls,
    )


@pytest.mark.asyncio
async def test_fetch_weekly_uses_exact_codex_bucket_and_no_model_turn(
    paths: tuple[Path, Path],
) -> None:
    process = FakeProcess(response())
    adapter, calls = client(paths, process)

    snapshot = await adapter.fetch_weekly()

    assert (snapshot.used_percent, snapshot.resets_at) == (14, 1_785_400_820)
    assert calls[0][0][1:] == _RATE_LIMIT_ARGV
    sent = [json.loads(line) for line in process.stdin.data.splitlines()]
    assert [item["method"] for item in sent] == [
        "initialize",
        "initialized",
        "account/rateLimits/read",
    ]
    assert all("thread" not in item["method"] for item in sent)
    assert process.terminated


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("duration", "used"),
    [(300, 14), (10_080, True), (10_080, 101)],
)
async def test_invalid_or_non_weekly_window_fails_closed_and_cleans_up(
    paths: tuple[Path, Path], duration: int, used: object
) -> None:
    process = FakeProcess(response(duration=duration, used=used))
    adapter, _ = client(paths, process)

    with pytest.raises(CodexRateLimitError, match="rate_limit_unavailable"):
        await adapter.fetch_weekly()

    assert process.terminated


@pytest.mark.asyncio
async def test_cancellation_still_terminates_app_server(
    paths: tuple[Path, Path],
) -> None:
    process = FakeProcess(b"")
    process.stdout = reader(eof=False)
    adapter, _ = client(paths, process)
    task = asyncio.create_task(adapter.fetch_weekly())
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert process.terminated
