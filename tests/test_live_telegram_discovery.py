"""Offline orchestration tests for the live Telegram discovery script."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from scripts import live_telegram_discovery
from src.security.windows_credentials import GenericCredential


TOKEN = "123456:" + "A" * 32
CHALLENGE = "B" * 32


class TrackingTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.closed = False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("/getMe"):
            result: Any = {
                "id": 123,
                "is_bot": True,
                "username": "Nobusspacebot",
                "first_name": "Nobus",
            }
        else:
            result = [
                {
                    "update_id": 10,
                    "message": {
                        "text": f"/start {CHALLENGE}",
                        "entities": [
                            {"type": "bot_command", "offset": 0, "length": 6}
                        ],
                        "from": {"id": 42, "is_bot": False},
                        "chat": {"id": 42, "type": "private"},
                    },
                }
            ]
        return httpx.Response(200, json={"ok": True, "result": result})

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_discovery_uses_only_read_methods_and_closes_transport() -> None:
    transport = TrackingTransport()

    def credential_reader(target: str) -> GenericCredential:
        assert target == "NobusSpace/TelegramBot/MVP1"
        return GenericCredential("@Nobusspacebot", SecretStr(TOKEN))

    result = await live_telegram_discovery._discover(
        CHALLENGE,
        credential_reader=credential_reader,
        transport_factory=lambda: transport,
    )

    assert result["candidate_state"] == "UNTRUSTED_AWAITING_L4"
    assert result["untrusted_candidates"] == [
        {"update_id": 10, "user_id": 42, "chat_id": 42}
    ]
    assert [request.url.path.rsplit("/", 1)[-1] for request in transport.requests] == [
        "getMe",
        "getUpdates",
    ]
    assert json.loads(transport.requests[0].content) == {}
    assert json.loads(transport.requests[1].content) == {"limit": 100, "timeout": 0}
    assert transport.closed


def test_live_transport_disables_ambient_trust(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = object()
    calls: list[dict[str, Any]] = []

    def factory(**options: Any) -> object:
        calls.append(options)
        return sentinel

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", factory)
    assert live_telegram_discovery._live_transport() is sentinel
    assert calls == [{"retries": 0, "trust_env": False}]
