"""Adversarial tests for read-only Telegram owner discovery."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from src.transport.telegram.discovery import (
    UntrustedStartCandidate,
    start_candidates,
)


CHALLENGE = "A" * 32


def valid_update() -> dict[str, Any]:
    return {
        "update_id": 10,
        "message": {
            "text": f"/start {CHALLENGE}",
            "entities": [{"type": "bot_command", "offset": 0, "length": 6}],
            "from": {"id": 42, "is_bot": False},
            "chat": {"id": 42, "type": "private"},
        },
    }


def set_command(update: dict[str, Any], command: str, *, length: int) -> None:
    update["message"]["text"] = f"{command} {CHALLENGE}"
    update["message"]["entities"][0]["length"] = length


def test_accepts_exact_private_challenge_and_addressed_command() -> None:
    first = valid_update()
    second = deepcopy(first)
    second["update_id"] = 11
    set_command(second, "/start@Nobusspacebot", length=20)
    assert start_candidates(
        (first, second),
        bot_username="Nobusspacebot",
        challenge=CHALLENGE,
    ) == (
        UntrustedStartCandidate(10, 42, 42),
        UntrustedStartCandidate(11, 42, 42),
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["message"].update({"text": "hello"}),
        lambda value: value["message"].update({"entities": []}),
        lambda value: value["message"]["entities"][0].update({"offset": False}),
        lambda value: value["message"]["from"].update({"id": True}),
        lambda value: value["message"]["from"].update({"is_bot": True}),
        lambda value: value["message"]["chat"].update({"id": 99}),
        lambda value: value["message"]["chat"].update({"type": "group"}),
        lambda value: set_command(value, "/start@OtherBot", length=15),
        lambda value: set_command(value, "/start@", length=7),
        lambda value: value["message"].update(
            {"text": f" /start {CHALLENGE}"}
        ),
        lambda value: value["message"].update(
            {"text": f"/start {'B' * 32}"}
        ),
    ],
)
def test_rejects_spoofed_or_ambiguous_identity(mutate: Any) -> None:
    update = valid_update()
    mutate(update)
    assert start_candidates(
        (update,),
        bot_username="Nobusspacebot",
        challenge=CHALLENGE,
    ) == ()


@pytest.mark.parametrize("challenge", ["", "short", "!" * 32])
def test_rejects_invalid_challenge_contract(challenge: str) -> None:
    assert start_candidates(
        (valid_update(),),
        bot_username="Nobusspacebot",
        challenge=challenge,
    ) == ()
