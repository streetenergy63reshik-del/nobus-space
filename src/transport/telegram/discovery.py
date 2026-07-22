"""Pure parsing for untrusted owner candidates from Telegram /start updates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_CHALLENGE_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")


@dataclass(frozen=True)
class UntrustedStartCandidate:
    update_id: int
    user_id: int
    chat_id: int


def start_candidates(
    updates: tuple[dict[str, Any], ...],
    *,
    bot_username: str,
    challenge: str,
) -> tuple[UntrustedStartCandidate, ...]:
    expected = bot_username.removeprefix("@").casefold()
    if not expected or not isinstance(challenge, str) or _CHALLENGE_RE.fullmatch(challenge) is None:
        return ()
    candidates: list[UntrustedStartCandidate] = []
    for update in updates:
        candidate = _start_candidate(update, expected, challenge)
        if candidate is not None:
            candidates.append(candidate)
    return tuple(candidates)


def _start_candidate(
    update: object,
    expected_bot_username: str,
    challenge: str,
) -> UntrustedStartCandidate | None:
    if type(update) is not dict or not _non_negative_int(update.get("update_id")):
        return None
    message = update.get("message")
    if type(message) is not dict:
        return None
    text = message.get("text")
    if (
        not isinstance(text, str)
        or not text
        or len(text) > 4096
        or "\x00" in text
        or text != text.lstrip()
    ):
        return None
    parts = text.split(maxsplit=1)
    if len(parts) != 2 or parts[1] != challenge:
        return None
    command_token = parts[0]
    command = command_token
    target: str | None = None
    if "@" in command:
        command, target = command.split("@", 1)
    if (
        command.casefold() != "/start"
        or target == ""
        or (target is not None and target.casefold() != expected_bot_username)
    ):
        return None
    entities = message.get("entities")
    if type(entities) is not list or not entities:
        return None
    entity = entities[0]
    if (
        type(entity) is not dict
        or entity.get("type") != "bot_command"
        or type(entity.get("offset")) is not int
        or entity["offset"] != 0
        or type(entity.get("length")) is not int
        or entity["length"] != len(command_token)
    ):
        return None
    actor = message.get("from")
    chat = message.get("chat")
    if (
        type(actor) is not dict
        or type(chat) is not dict
        or not _positive_int(actor.get("id"))
        or actor.get("is_bot") is not False
        or type(chat.get("id")) is not int
        or chat.get("type") != "private"
        or chat["id"] != actor["id"]
    ):
        return None
    return UntrustedStartCandidate(
        update_id=update["update_id"],
        user_id=actor["id"],
        chat_id=chat["id"],
    )


def _positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def _non_negative_int(value: object) -> bool:
    return type(value) is int and value >= 0
