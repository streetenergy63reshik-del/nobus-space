"""Offline tests for the authenticated Telegram control-plane."""

from __future__ import annotations

from typing import Any

import pytest

from src.application.telegram_control import TelegramControlPlane
from src.transport.telegram import (
    ActorBinding,
    InMemoryCallbackTokenStore,
    InMemoryUpdateIdStore,
    TelegramGateway,
)


USER_ID = 42
AUTH_REF = "sha256:" + "a" * 64


class FakeApi:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> int:
        if self.fail:
            raise RuntimeError("raw provider detail")
        self.sent.append((chat_id, text))
        return len(self.sent)


def control(api: FakeApi) -> TelegramControlPlane:
    gateway = TelegramGateway(
        actor_bindings={
            (USER_ID, USER_ID): ActorBinding(
                tenant_id="owner",
                actor_identity="telegram:owner",
                role="owner",
                auth_context_ref=AUTH_REF,
            )
        },
        update_id_store=InMemoryUpdateIdStore(),
        callback_token_store=InMemoryCallbackTokenStore({}),
    )
    return TelegramControlPlane(gateway, api)


def update(text: str, *, user_id: int = USER_ID, update_id: int = 1) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 10,
            "from": {"id": user_id},
            "chat": {"id": user_id},
            "text": text,
        },
    }


@pytest.mark.asyncio
async def test_status_and_help_reply_only_to_bound_chat() -> None:
    api = FakeApi()
    handler = control(api)
    assert await handler.handle(update("/status"))
    assert await handler.handle(update("/help", update_id=2))
    assert [chat for chat, _ in api.sent] == [USER_ID, USER_ID]
    assert "Telegram: online" in api.sent[0][1]
    assert "/status" in api.sent[1][1]


@pytest.mark.asyncio
async def test_unauthorized_actor_is_acked_without_reply() -> None:
    api = FakeApi()
    assert await control(api).handle(update("/status", user_id=99))
    assert api.sent == []


@pytest.mark.asyncio
async def test_send_failure_propagates_before_polling_ack() -> None:
    api = FakeApi(fail=True)
    with pytest.raises(RuntimeError, match="raw provider detail"):
        await control(api).handle(update("/status"))


@pytest.mark.asyncio
async def test_unknown_text_gets_bounded_safe_reply() -> None:
    api = FakeApi()
    assert await control(api).handle(update("delete everything"))
    assert len(api.sent) == 1
    assert "не поддерживается" in api.sent[0][1]
