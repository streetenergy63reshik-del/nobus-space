"""Security regressions for one-shot product callback actions."""

from __future__ import annotations

from src.application.telegram_actions import (
    InMemoryTelegramActionStore,
    TelegramAction,
)
from src.transport.telegram import CallbackQuery


def callback(token: str, *, user_id: int = 1, chat_id: int = 1) -> CallbackQuery:
    return CallbackQuery(
        update_id=1,
        tenant_id="owner",
        actor_identity="telegram:owner",
        actor_role="owner",
        auth_context_ref="sha256:" + "a" * 64,
        user_id=user_id,
        chat_id=chat_id,
        query_id="query-1",
        callback_token=token,
    )


def test_action_is_actor_bound_and_one_shot_after_gateway_claim() -> None:
    store = InMemoryTelegramActionStore()
    token = store.issue(
        action=TelegramAction.APPLY_PATCH,
        capability_token="c" * 32,
        user_id=1,
        chat_id=1,
        ttl_seconds=60,
    )

    assert not store.claim(token, 2, 1)
    assert store.claim(token, 1, 1)
    result = store.consume(callback(token))
    assert result is not None
    assert result.action is TelegramAction.APPLY_PATCH
    assert result.capability_token == "c" * 32
    assert store.consume(callback(token)) is None
    assert not store.claim(token, 1, 1)


def test_action_cannot_be_consumed_before_gateway_claim() -> None:
    store = InMemoryTelegramActionStore()
    token = store.issue(
        action=TelegramAction.CANCEL_VOICE,
        capability_token="v" * 32,
        user_id=1,
        chat_id=1,
        ttl_seconds=60,
    )
    assert store.consume(callback(token)) is None
