"""Telegram API regressions for bounded inline confirmation buttons."""

from __future__ import annotations

import json

import httpx
import pytest

from src.transport.telegram.bot_api import TelegramBotApiError
from tests.test_telegram_bot_api import api_for, response


@pytest.mark.asyncio
async def test_send_message_renders_one_bounded_inline_keyboard() -> None:
    payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return response({"message_id": 7, "chat": {"id": 42}})

    api = api_for(handler)
    try:
        message_id = await api.send_message(
            42,
            "Подтвердите",
            buttons=(("✅ Применить", "a" * 32), ("❌ Отмена", "b" * 32)),
        )
    finally:
        await api.aclose()

    assert message_id == 7
    assert payloads[0]["reply_markup"] == {
        "inline_keyboard": [[
            {"text": "✅ Применить", "callback_data": "a" * 32},
            {"text": "❌ Отмена", "callback_data": "b" * 32},
        ]]
    }


@pytest.mark.asyncio
async def test_send_message_rejects_oversized_callback_before_network() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response({"message_id": 1, "chat": {"id": 42}})

    api = api_for(handler)
    try:
        with pytest.raises(TelegramBotApiError):
            await api.send_message(42, "x", buttons=(("ok", "x" * 65),))
    finally:
        await api.aclose()
    assert calls == 0
