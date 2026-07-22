"""Adversarial tests for the durable Telegram polling checkpoint."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import httpx
import pytest

from src.transport.telegram.bot_api import TelegramBotApi, TelegramPollingBoundary
from src.transport.telegram.sqlite_checkpoint import (
    SQLitePollingCheckpointError,
    SQLitePollingCheckpointStore,
)


TOKEN = "123456:" + "A" * 32
NOW = datetime(2026, 7, 22, 12, tzinfo=UTC)


class Clock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def store(path: Path, clock: Clock | None = None) -> SQLitePollingCheckpointStore:
    return SQLitePollingCheckpointStore(
        path,
        consumer_id="telegram-mvp-1",
        lease_duration_seconds=60,
        clock=clock or Clock(),
    )


def test_checkpoint_survives_restart_and_preserves_monotonic_offset(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.sqlite3"
    clock = Clock()
    first = store(path, clock)
    lease = first.acquire(uuid4(), NOW)
    assert lease is not None
    assert first.load(lease) is None
    assert first.advance(lease=lease, expected=None, next_offset=11)
    assert not first.advance(lease=lease, expected=None, next_offset=12)
    assert first.release(lease)

    restarted = store(path, clock)
    next_lease = restarted.acquire(uuid4(), NOW)
    assert next_lease is not None
    assert next_lease.lease_id != lease.lease_id
    assert restarted.load(next_lease) == 11
    assert restarted.advance(lease=next_lease, expected=11, next_offset=12)
    assert restarted.release(next_lease)


def test_active_lease_blocks_second_instance_and_expiry_reclaims_it(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.sqlite3"
    clock = Clock()
    first = store(path, clock)
    second = store(path, clock)
    stale = first.acquire(uuid4(), NOW)
    assert stale is not None
    assert second.acquire(uuid4(), NOW + timedelta(seconds=59)) is None

    clock.value = NOW + timedelta(seconds=60)
    current = second.acquire(uuid4(), clock.value)
    assert current is not None
    assert current.lease_id != stale.lease_id
    assert not first.advance(lease=stale, expected=None, next_offset=1)
    assert not first.release(stale)
    assert second.release(current)


def test_caller_future_time_cannot_reclaim_or_poison_lease(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    clock = Clock()
    first = store(path, clock)
    second = store(path, clock)
    lease = first.acquire(uuid4(), NOW)
    assert lease is not None
    assert second.acquire(uuid4(), NOW + timedelta(days=365)) is None
    assert first.load(lease) is None
    assert first.release(lease)


def test_two_concurrent_acquires_have_exactly_one_winner(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    store(path)
    barrier = Barrier(2)

    def acquire() -> object:
        candidate = store(path)
        barrier.wait()
        return candidate.acquire(uuid4(), NOW)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _: acquire(), range(2)))
    assert sum(result is not None for result in results) == 1


def test_expired_lease_cannot_load_or_advance(tmp_path: Path) -> None:
    clock = Clock()
    checkpoint = store(tmp_path / "state.sqlite3", clock)
    lease = checkpoint.acquire(uuid4(), NOW)
    assert lease is not None
    clock.value = lease.expires_at
    with pytest.raises(SQLitePollingCheckpointError):
        checkpoint.load(lease)
    assert not checkpoint.advance(lease=lease, expected=None, next_offset=1)


def test_clock_rollback_fails_closed_without_mutation(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    clock = Clock()
    checkpoint = store(path, clock)
    lease = checkpoint.acquire(uuid4(), NOW)
    assert lease is not None
    clock.value = NOW - timedelta(microseconds=1)
    with pytest.raises(SQLitePollingCheckpointError, match="checkpoint is invalid"):
        checkpoint.advance(lease=lease, expected=None, next_offset=1)

    clock.value = NOW
    assert checkpoint.load(lease) is None
    assert checkpoint.release(lease)


@pytest.mark.parametrize(
    "column,value",
    [
        ("offset", 999),
        ("lease_owner", str(uuid4())),
        ("revision", 999),
        ("state_digest", "sha256:" + "0" * 64),
    ],
)
def test_tampered_state_is_detected(
    tmp_path: Path, column: str, value: object
) -> None:
    path = tmp_path / "state.sqlite3"
    checkpoint = store(path)
    lease = checkpoint.acquire(uuid4(), NOW)
    assert lease is not None
    with sqlite3.connect(path) as connection:
        connection.execute(
            f"UPDATE telegram_polling_checkpoints SET {column} = ?",
            (value,),
        )
    with pytest.raises(SQLitePollingCheckpointError, match="checkpoint is invalid"):
        checkpoint.load(lease)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"consumer_id": ""},
        {"consumer_id": "Tenant/secret"},
        {"consumer_id": "valid", "lease_duration_seconds": True},
        {"consumer_id": "valid", "lease_duration_seconds": 301},
        {"consumer_id": "valid", "busy_timeout_ms": False},
    ],
)
def test_configuration_rejects_ambiguous_values(
    tmp_path: Path, kwargs: dict[str, object]
) -> None:
    with pytest.raises(SQLitePollingCheckpointError, match="checkpoint is invalid"):
        SQLitePollingCheckpointStore(tmp_path / "state.sqlite3", **kwargs)  # type: ignore[arg-type]


def test_naive_timestamps_and_invalid_offsets_have_stable_errors(
    tmp_path: Path,
) -> None:
    checkpoint = store(tmp_path / "state.sqlite3")
    with pytest.raises(SQLitePollingCheckpointError) as caught:
        checkpoint.acquire(uuid4(), datetime(2026, 7, 22))
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None

    lease = checkpoint.acquire(uuid4(), NOW)
    assert lease is not None
    for value in (True, -1):
        with pytest.raises(SQLitePollingCheckpointError):
            checkpoint.advance(lease=lease, expected=None, next_offset=value)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_polling_boundary_resumes_from_persisted_offset(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.sqlite3"
    requested_offsets: list[int | None] = []
    batches = iter(([{"update_id": 10}, {"update_id": 11}], []))

    def transport(request: httpx.Request) -> httpx.Response:
        requested_offsets.append(json.loads(request.content).get("offset"))
        return httpx.Response(200, json={"ok": True, "result": next(batches)})

    handled: list[int] = []

    async def handler(update: dict[str, object]) -> bool:
        handled.append(update["update_id"])  # type: ignore[arg-type]
        return True

    api = TelegramBotApi(token=TOKEN, transport=httpx.MockTransport(transport))
    clock = Clock()
    try:
        first = TelegramPollingBoundary(
            api, handler, store(path, clock), clock=clock
        )
        result = await first.poll_once(timeout=0)
        assert result.next_offset == 12
        restarted = TelegramPollingBoundary(
            api, handler, store(path, clock), clock=clock
        )
        result = await restarted.poll_once(timeout=0)
        assert result.next_offset == 12
    finally:
        await api.aclose()
    assert requested_offsets == [None, 12]
    assert handled == [10, 11]


@pytest.mark.asyncio
async def test_cancellation_releases_durable_lease_for_restart(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.sqlite3"
    entered = asyncio.Event()

    async def handler(update: dict[str, object]) -> bool:
        entered.set()
        await asyncio.Event().wait()
        return True

    api = TelegramBotApi(
        token=TOKEN,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"ok": True, "result": [{"update_id": 1}]}
            )
        ),
    )
    clock = Clock()
    boundary = TelegramPollingBoundary(
        api, handler, store(path, clock), clock=clock
    )
    task = asyncio.create_task(boundary.poll_once(timeout=0))
    await entered.wait()
    task.cancel()
    try:
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        await api.aclose()

    restarted = store(path, clock)
    lease = restarted.acquire(uuid4(), NOW)
    assert lease is not None
    assert restarted.load(lease) is None
    assert restarted.release(lease)
