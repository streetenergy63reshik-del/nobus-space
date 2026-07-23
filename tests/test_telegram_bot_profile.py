"""Offline profile configuration tests for Telegram Bot API."""

from __future__ import annotations

import json

import httpx
import pytest

from src.transport.telegram.bot_api import TelegramBotApi, TelegramBotApiError


TOKEN = "123456:" + "A" * 32


@pytest.mark.asyncio
async def test_configure_profile_uses_only_validated_fixed_methods() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"ok": True, "result": True})

    api = TelegramBotApi(token=TOKEN, transport=httpx.MockTransport(handler))
    try:
        await api.configure_profile(
            name="Nobus Space",
            description="Оркестратор задач владельца.",
            short_description="Задачи и подтверждения из Telegram.",
            commands=(("status", "Состояние системы"), ("task", "Создать задачу")),
        )
    finally:
        await api.aclose()

    assert [request.url.path.rsplit("/", 1)[-1] for request in calls] == [
        "setMyName",
        "setMyDescription",
        "setMyShortDescription",
        "setMyCommands",
    ]
    assert json.loads(calls[-1].content) == {
        "commands": [
            {"command": "status", "description": "Состояние системы"},
            {"command": "task", "description": "Создать задачу"},
        ]
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "commands",
    [
        (("Bad", "description"),),
        (("task", "one"), ("task", "two")),
        (("task", ""),),
        tuple(),
    ],
)
async def test_configure_profile_rejects_invalid_payload_before_network(
    commands: tuple[tuple[str, str], ...],
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"ok": True, "result": True})

    api = TelegramBotApi(token=TOKEN, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(TelegramBotApiError) as caught:
            await api.configure_profile(
                name="Nobus Space",
                description="Description",
                short_description="Short",
                commands=commands,
            )
    finally:
        await api.aclose()
    assert caught.value.code == "telegram_configuration_invalid"
    assert calls == 0


@pytest.mark.asyncio
async def test_configure_profile_rejects_non_true_provider_result() -> None:
    api = TelegramBotApi(
        token=TOKEN,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"ok": True, "result": False}
            )
        ),
    )
    try:
        with pytest.raises(TelegramBotApiError) as caught:
            await api.configure_profile(
                name="Nobus Space",
                description="Description",
                short_description="Short",
                commands=(("status", "Status"),),
            )
    finally:
        await api.aclose()
    assert caught.value.code == "telegram_protocol_error"
