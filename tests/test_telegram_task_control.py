"""Offline Gate 5A.3 tests for confirmed Telegram fake tasks."""

from __future__ import annotations

import asyncio
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from src.application.durable_runtime import DurableFakeRuntime
from src.application.gate5a3 import build_gate5a3_runtime
from src.application.task_confirmation import (
    InMemoryTaskConfirmationStore,
    TaskConfirmationStatus,
)
from src.application.telegram_control import TelegramControlPlane
from src.models.task import TaskStatus
from src.storage import OutboxMessage, SQLiteStore
from src.transport.telegram import (
    ActorBinding,
    InMemoryCallbackTokenStore,
    PollingCheckpointUpdateIdStore,
    TelegramGateway,
)


USER_ID = 42
SECOND_USER_ID = 43
TENANT_ID = "owner"
SECOND_TENANT_ID = "tenant-b"
AUTH_REF = "sha256:" + "a" * 64
SECOND_AUTH_REF = "sha256:" + "b" * 64
DESTINATION_REF = "sha256:" + "d" * 64
_TOKEN = re.compile(r"/confirm ([A-Za-z0-9_-]{32,64})")
_TASK_ID = re.compile(r"Task: ([0-9a-f-]{36})")


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


class FakeApi:
    def __init__(self) -> None:
        self.fail_next = False
        self.attempted: list[tuple[int, str]] = []
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> int:
        self.attempted.append((chat_id, text))
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("provider unavailable")
        self.sent.append((chat_id, text))
        return len(self.sent)


class FakeStatusSender:
    def __init__(self) -> None:
        self.fail = False
        self.attempted: list[OutboxMessage] = []
        self.delivered: list[OutboxMessage] = []

    async def __call__(self, message: OutboxMessage) -> bool:
        validated = OutboxMessage.model_validate(message.model_dump(mode="json"))
        self.attempted.append(validated)
        if self.fail:
            return False
        self.delivered.append(validated)
        return True


@dataclass
class Harness:
    control: TelegramControlPlane
    api: FakeApi
    sender: FakeStatusSender
    db_path: Path
    clock: MutableClock
    runtime: DurableFakeRuntime
    gateway: TelegramGateway
    confirmations: InMemoryTaskConfirmationStore


def build_harness(
    tmp_path: Path,
    *,
    clock: MutableClock | None = None,
    confirmation_limits: dict[str, int] | None = None,
) -> Harness:
    task_clock = clock or MutableClock()
    bindings = {
        (USER_ID, USER_ID): ActorBinding(
            tenant_id=TENANT_ID,
            actor_identity="telegram:owner",
            role="owner",
            auth_context_ref=AUTH_REF,
        ),
        (SECOND_USER_ID, SECOND_USER_ID): ActorBinding(
            tenant_id=SECOND_TENANT_ID,
            actor_identity="telegram:second-owner",
            role="owner",
            auth_context_ref=SECOND_AUTH_REF,
        ),
    }
    gateway = TelegramGateway(
        actor_bindings=bindings,
        update_id_store=PollingCheckpointUpdateIdStore(),
        callback_token_store=InMemoryCallbackTokenStore({}),
        clock=task_clock,
    )
    db_path = tmp_path / "gate5a3.sqlite3"
    runtime = build_gate5a3_runtime(
        gateway=gateway,
        sqlite_path=db_path,
        destination_refs={
            TENANT_ID: DESTINATION_REF,
            SECOND_TENANT_ID: "sha256:" + "e" * 64,
        },
        allowed_path=tmp_path,
        clock=task_clock,
    )
    api = FakeApi()
    sender = FakeStatusSender()
    confirmations = InMemoryTaskConfirmationStore(
        clock=task_clock,
        **(confirmation_limits or {}),
    )
    control = TelegramControlPlane(
        gateway,
        api,
        task_runtime=runtime,
        task_confirmations=confirmations,
        task_tenants=(TENANT_ID, SECOND_TENANT_ID),
        task_status_sender=sender,
    )
    return Harness(
        control,
        api,
        sender,
        db_path,
        task_clock,
        runtime,
        gateway,
        confirmations,
    )


def update(
    text: str,
    *,
    update_id: int,
    user_id: int = USER_ID,
    message_id: int | None = None,
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": message_id if message_id is not None else update_id,
            "from": {"id": user_id},
            "chat": {"id": user_id},
            "text": text,
        },
    }


def challenge(api: FakeApi) -> tuple[str, UUID]:
    text = api.sent[-1][1]
    token_match = _TOKEN.search(text)
    task_match = _TASK_ID.search(text)
    assert token_match is not None and task_match is not None
    return token_match.group(1), UUID(task_match.group(1))


@pytest.mark.asyncio
async def test_task_is_pending_until_owner_confirms_then_delivers_status(
    tmp_path: Path,
) -> None:
    harness = build_harness(tmp_path)
    instruction = "Сделай безопасную локальную проверку"

    assert await harness.control.handle(update(f"/task {instruction}", update_id=1))
    token, task_id = challenge(harness.api)
    pending = SQLiteStore(harness.db_path).read_task(TENANT_ID, task_id)
    assert pending is not None
    assert pending.projection.status is TaskStatus.PENDING
    assert harness.sender.attempted == []

    raw_db = harness.db_path.read_bytes()
    assert instruction.encode("utf-8") not in raw_db
    assert token.encode("ascii") not in raw_db

    assert await harness.control.handle(update(f"/confirm {token}", update_id=2))
    assert "Подтверждение принято" in harness.api.sent[-1][1]
    assert await harness.control.deliver_pending() == 1
    assert [message.task_status for message in harness.sender.delivered] == [
        TaskStatus.COMPLETED
    ]
    assert harness.sender.delivered[0].task_id == task_id


@pytest.mark.asyncio
async def test_cancel_is_terminal_and_token_replay_cannot_execute(tmp_path: Path) -> None:
    harness = build_harness(tmp_path)
    await harness.control.handle(update("/task отменить меня", update_id=1))
    token, task_id = challenge(harness.api)

    await harness.control.handle(update(f"/cancel {token}", update_id=2))
    snapshot = SQLiteStore(harness.db_path).read_task(TENANT_ID, task_id)
    assert snapshot is not None
    assert snapshot.projection.status is TaskStatus.REJECTED
    await harness.control.deliver_pending()
    assert harness.sender.delivered[-1].task_status is TaskStatus.REJECTED

    await harness.control.handle(update(f"/confirm {token}", update_id=3))
    assert "уже использован" in harness.api.sent[-1][1]
    assert len(harness.sender.delivered) == 1


@pytest.mark.asyncio
async def test_confirmation_is_bound_to_exact_actor_and_chat(tmp_path: Path) -> None:
    harness = build_harness(tmp_path)
    await harness.control.handle(update("/task actor binding", update_id=1))
    token, task_id = challenge(harness.api)

    await harness.control.handle(
        update(f"/confirm {token}", update_id=2, user_id=SECOND_USER_ID)
    )
    assert "принадлежит другому" in harness.api.sent[-1][1]
    snapshot = SQLiteStore(harness.db_path).read_task(TENANT_ID, task_id)
    assert snapshot is not None
    assert snapshot.projection.status is TaskStatus.PENDING

    await harness.control.handle(update(f"/confirm {token}", update_id=3))
    await harness.control.deliver_pending()
    assert harness.sender.delivered[-1].task_status is TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_preview_send_failure_replays_same_challenge_without_second_task(
    tmp_path: Path,
) -> None:
    harness = build_harness(tmp_path)
    request = update("/task retry safe preview", update_id=10)
    harness.api.fail_next = True

    with pytest.raises(RuntimeError, match="provider unavailable"):
        await harness.control.handle(request)
    first_attempt = harness.api.attempted[-1][1]

    assert await harness.control.handle(request)
    second_attempt = harness.api.sent[-1][1]
    assert second_attempt == first_attempt
    _, task_id = challenge(harness.api)
    assert SQLiteStore(harness.db_path).read_task(TENANT_ID, task_id) is not None


@pytest.mark.asyncio
async def test_restart_loses_raw_capability_and_fails_closed(tmp_path: Path) -> None:
    harness = build_harness(tmp_path)
    instruction = "restart-secret-instruction"
    await harness.control.handle(update(f"/task {instruction}", update_id=1))
    token, task_id = challenge(harness.api)

    restarted = build_harness(tmp_path)
    await restarted.control.handle(update(f"/confirm {token}", update_id=2))
    assert "недействителен" in restarted.api.sent[-1][1]
    snapshot = SQLiteStore(harness.db_path).read_task(TENANT_ID, task_id)
    assert snapshot is not None
    assert snapshot.projection.status is TaskStatus.PENDING
    raw_db = harness.db_path.read_bytes()
    assert instruction.encode() not in raw_db
    assert token.encode() not in raw_db


@pytest.mark.asyncio
async def test_expired_preview_is_rejected_before_next_command(tmp_path: Path) -> None:
    clock = MutableClock()
    harness = build_harness(tmp_path, clock=clock)
    await harness.control.handle(update("/task expire safely", update_id=1))
    _, task_id = challenge(harness.api)
    clock.advance(301)

    await harness.control.handle(update("/status", update_id=2))
    snapshot = SQLiteStore(harness.db_path).read_task(TENANT_ID, task_id)
    assert snapshot is not None
    assert snapshot.projection.status is TaskStatus.REJECTED
    await harness.control.deliver_pending()
    assert harness.sender.delivered[-1].task_status is TaskStatus.REJECTED


@pytest.mark.asyncio
async def test_failed_outbox_delivery_is_retried_without_reexecution(
    tmp_path: Path,
) -> None:
    harness = build_harness(tmp_path)
    await harness.control.handle(update("/task retry outbox", update_id=1))
    token, task_id = challenge(harness.api)
    await harness.control.handle(update(f"/confirm {token}", update_id=2))

    harness.sender.fail = True
    assert await harness.control.deliver_pending() == 0
    assert harness.sender.delivered == []
    harness.sender.fail = False
    harness.clock.advance(1_000)
    assert await harness.control.deliver_pending() == 1
    assert len(harness.sender.delivered) == 1
    assert harness.sender.delivered[0].task_id == task_id


@pytest.mark.asyncio
async def test_confirmation_reply_failure_replays_without_second_execution(
    tmp_path: Path,
) -> None:
    harness = build_harness(tmp_path)
    await harness.control.handle(update("/task reply failure", update_id=1))
    token, task_id = challenge(harness.api)
    harness.api.fail_next = True

    with pytest.raises(RuntimeError, match="provider unavailable"):
        await harness.control.handle(update(f"/confirm {token}", update_id=2))
    await harness.control.handle(update(f"/confirm {token}", update_id=2))
    assert "уже использован" in harness.api.sent[-1][1]
    assert await harness.control.deliver_pending() == 1
    assert await harness.control.deliver_pending() == 0
    assert [message.task_id for message in harness.sender.delivered] == [task_id]


@pytest.mark.asyncio
async def test_cancellation_after_consume_is_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = build_harness(tmp_path)
    await harness.control.handle(update("/task cancel after consume", update_id=1))
    token, task_id = challenge(harness.api)
    calls = 0

    async def cancel_after_consume(prepared: object) -> object:
        nonlocal calls
        calls += 1
        raise asyncio.CancelledError

    monkeypatch.setattr(harness.runtime, "execute_prepared", cancel_after_consume)
    with pytest.raises(asyncio.CancelledError):
        await harness.control.handle(update(f"/confirm {token}", update_id=2))
    await harness.control.handle(update(f"/confirm {token}", update_id=2))

    assert calls == 1
    assert "уже использован" in harness.api.sent[-1][1]
    snapshot = SQLiteStore(harness.db_path).read_task(TENANT_ID, task_id)
    assert snapshot is not None
    assert snapshot.projection.status is TaskStatus.PENDING
    assert await harness.control.deliver_pending() == 0


@pytest.mark.asyncio
async def test_retained_capacity_is_bounded_and_tenant_fair(tmp_path: Path) -> None:
    harness = build_harness(
        tmp_path,
        confirmation_limits={
            "max_entries": 2,
            "max_entries_per_tenant": 1,
            "retention_seconds": 3_600,
        },
    )
    await harness.control.handle(update("/task tenant a first", update_id=1))
    token_a, _ = challenge(harness.api)
    await harness.control.handle(update(f"/cancel {token_a}", update_id=2))

    await harness.control.handle(update("/task tenant a blocked", update_id=3))
    assert "не создан" in harness.api.sent[-1][1]

    await harness.control.handle(
        update("/task tenant b first", update_id=4, user_id=SECOND_USER_ID)
    )
    token_b, _ = challenge(harness.api)
    await harness.control.handle(
        update(f"/cancel {token_b}", update_id=5, user_id=SECOND_USER_ID)
    )
    assert harness.confirmations._entries == {}
    assert len(harness.confirmations._tombstones) == 2

    await harness.control.handle(
        update("/task tenant b blocked", update_id=6, user_id=SECOND_USER_ID)
    )
    assert "не создан" in harness.api.sent[-1][1]
    assert (
        len(harness.confirmations._entries)
        + len(harness.confirmations._tombstones)
        == 2
    )

    harness.clock.advance(3_601)
    await harness.control.handle(update("/task tenant a after retention", update_id=7))
    assert "/confirm " in harness.api.sent[-1][1]


def test_non_string_token_is_stably_rejected(tmp_path: Path) -> None:
    harness = build_harness(tmp_path)
    ingress = harness.gateway.process_update(update("/confirm placeholder", update_id=1))
    assert ingress.payload is not None and ingress.envelope is not None
    result = harness.confirmations.consume(
        token=123,  # type: ignore[arg-type]
        action=TaskConfirmationStatus.CONFIRMED,
        message=ingress.payload,  # type: ignore[arg-type]
        envelope=ingress.envelope,
    )
    assert result.status is TaskConfirmationStatus.REJECTED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "/task",
        "/task " + "x" * 2_001,
        "/task bad\x00instruction",
        "/confirm",
        "/cancel two tokens",
    ],
)
async def test_malformed_task_commands_are_bounded(tmp_path: Path, text: str) -> None:
    harness = build_harness(tmp_path)
    assert await harness.control.handle(update(text, update_id=1))
    assert len(harness.api.sent) == 1
    with sqlite3.connect(harness.db_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM task_snapshots"
        ).fetchone()
    assert count == (0,)
