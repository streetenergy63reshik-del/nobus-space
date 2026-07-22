"""Read-only live discovery for the Nobus Space Telegram bot owner."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.security.windows_credentials import (  # noqa: E402
    CredentialStoreError,
    GenericCredential,
    read_generic_credential,
)
from src.transport.telegram.bot_api import (  # noqa: E402
    TelegramBotApi,
    TelegramBotApiError,
)
from src.transport.telegram.discovery import start_candidates  # noqa: E402


_CREDENTIAL_TARGET = "NobusSpace/TelegramBot/MVP1"
_EXPECTED_USERNAME = "Nobusspacebot"
_CHALLENGE_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")


def _live_transport() -> httpx.AsyncBaseTransport:
    return httpx.AsyncHTTPTransport(retries=0, trust_env=False)


async def _discover(
    challenge: str,
    *,
    credential_reader: Callable[[str], GenericCredential] = read_generic_credential,
    transport_factory: Callable[[], httpx.AsyncBaseTransport] = _live_transport,
) -> dict[str, object]:
    if not isinstance(challenge, str) or _CHALLENGE_RE.fullmatch(challenge) is None:
        raise CredentialStoreError("credential_configuration_invalid")
    credential = credential_reader(_CREDENTIAL_TARGET)
    if credential.username.casefold() != f"@{_EXPECTED_USERNAME}".casefold():
        raise CredentialStoreError("credential_unavailable")
    api = TelegramBotApi(
        token=credential.secret.get_secret_value(),
        transport=transport_factory(),
        request_timeout=20,
    )
    try:
        identity = await api.get_me()
        if identity.username.casefold() != _EXPECTED_USERNAME.casefold():
            raise TelegramBotApiError("telegram_protocol_error")
        updates = await api.peek_updates(limit=100)
        candidates = start_candidates(
            updates,
            bot_username=identity.username,
            challenge=challenge,
        )
        return {
            "status": "PASS",
            "candidate_state": "UNTRUSTED_AWAITING_L4",
            "bot_id": identity.bot_id,
            "bot_username": identity.username,
            "updates_seen": len(updates),
            "untrusted_candidates": [
                {
                    "update_id": item.update_id,
                    "user_id": item.user_id,
                    "chat_id": item.chat_id,
                }
                for item in candidates
            ],
        }
    finally:
        await api.aclose()


def main() -> int:
    failure = ""
    result: dict[str, object] | None = None
    challenge = sys.argv[1] if len(sys.argv) == 2 else ""
    try:
        result = asyncio.run(_discover(challenge))
    except CredentialStoreError as error:
        failure = error.code
    except TelegramBotApiError as error:
        failure = error.code
    except BaseException:
        failure = "live_discovery_failed"
    if result is None:
        result = {"status": "FAIL", "code": failure or "live_discovery_failed"}
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
