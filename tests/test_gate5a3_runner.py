"""Runner-level regression tests for Telegram Gate 5A.3."""

from __future__ import annotations

import pytest

from scripts.run_telegram_control import (
    _poll_once_and_announce,
    _task_destinations,
)
from src.transport.telegram import ActorBinding, PollingCheckpointUpdateIdStore
from src.transport.telegram.bindings import TelegramBindingError
from src.transport.telegram.bot_api import PollBatchResult, TelegramBotApiError


AUTH_REF = "sha256:" + "a" * 64


class FakePolling:
    def __init__(self, result: PollBatchResult) -> None:
        self._result = result

    async def poll_once(self, *, timeout: int, limit: int) -> PollBatchResult:
        assert timeout == 0 and limit == 20
        return self._result


class FakeApi:
    async def send_message(self, chat_id: int, text: str) -> int:
        raise AssertionError("announcement was not requested")


class FakeControl:
    def __init__(self) -> None:
        self.calls = 0

    async def deliver_pending(self) -> int:
        self.calls += 1
        return 1


def binding(tenant_id: str = "owner") -> ActorBinding:
    return ActorBinding(
        tenant_id=tenant_id,
        actor_identity="telegram:owner",
        role="owner",
        auth_context_ref=AUTH_REF,
    )


def test_polling_checkpoint_store_allows_outer_checkpoint_retry() -> None:
    store = PollingCheckpointUpdateIdStore()
    assert store.claim(7)
    assert store.claim(7)
    assert not store.claim(-1)
    assert not store.claim(True)  # type: ignore[arg-type]


def test_task_destinations_are_tenant_bound_and_deterministic() -> None:
    first = _task_destinations({(42, 42): binding()})
    second = _task_destinations({(42, 42): binding()})
    assert first == second
    refs, destinations = first
    assert destinations["owner"] == (refs["owner"], 42)
    assert refs["owner"].startswith("sha256:")


def test_business_notes_binding_is_not_a_task_destination() -> None:
    refs, destinations = _task_destinations(
        {
            (42, 42): binding(),
            (42, -1001): ActorBinding(
                tenant_id="owner",
                actor_identity="telegram:owner",
                role="owner",
                auth_context_ref=AUTH_REF,
                purpose="business_notes",
            ),
        }
    )
    assert destinations == {"owner": (refs["owner"], 42)}


def test_task_destinations_reject_one_tenant_with_two_chats() -> None:
    with pytest.raises(TelegramBindingError):
        _task_destinations(
            {
                (42, 42): binding(),
                (43, 43): ActorBinding(
                    tenant_id="owner",
                    actor_identity="telegram:second",
                    role="owner",
                    auth_context_ref="sha256:" + "b" * 64,
                ),
            }
        )


@pytest.mark.asyncio
async def test_successful_poll_drains_outbox_before_return() -> None:
    control = FakeControl()
    acknowledged = await _poll_once_and_announce(
        FakePolling(PollBatchResult(8, 1, False)),  # type: ignore[arg-type]
        FakeApi(),  # type: ignore[arg-type]
        {(42, 42): object()},
        control=control,  # type: ignore[arg-type]
        timeout=0,
        announce=False,
    )
    assert acknowledged == 1
    assert control.calls == 1


@pytest.mark.asyncio
async def test_retry_required_poll_never_drains_outbox() -> None:
    control = FakeControl()
    with pytest.raises(TelegramBotApiError):
        await _poll_once_and_announce(
            FakePolling(PollBatchResult(None, 0, True)),  # type: ignore[arg-type]
            FakeApi(),  # type: ignore[arg-type]
            {(42, 42): object()},
            control=control,  # type: ignore[arg-type]
            timeout=0,
            announce=False,
        )
    assert control.calls == 0
