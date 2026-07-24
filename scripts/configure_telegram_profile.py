"""Idempotently apply the Nobus Space Telegram bot product profile."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_telegram_control import _CREDENTIAL_TARGET, _EXPECTED_USERNAME  # noqa: E402
from src.security.windows_credentials import CredentialStoreError, read_generic_credential  # noqa: E402
from src.transport.telegram.bot_api import TelegramBotApi, TelegramBotApiError  # noqa: E402


_COMMANDS = (
    ("start", "Как ставить задачи"),
    ("status", "Состояние оркестратора"),
    ("limit", "Недельный лимит Codex"),
    ("file", "\u041f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442 \u0441 \u043a\u043e\u043c\u043f\u044c\u044e\u0442\u0435\u0440\u0430"),
    ("help", "Помощь и безопасность"),
)


async def _run() -> None:
    credential = read_generic_credential(_CREDENTIAL_TARGET)
    if credential.username.casefold() != f"@{_EXPECTED_USERNAME}".casefold():
        raise CredentialStoreError("credential_unavailable")
    api = TelegramBotApi(
        token=credential.secret.get_secret_value(),
        transport=httpx.AsyncHTTPTransport(retries=0, trust_env=False),
        request_timeout=60,
    )
    try:
        identity = await api.get_me()
        if identity.username.casefold() != _EXPECTED_USERNAME.casefold():
            raise TelegramBotApiError("telegram_protocol_error")
        await api.configure_profile(
            name="Nobus Space",
            description=(
                "Личный Telegram-оркестратор: принимает текстовые и голосовые задачи, "
                "показывает последствия и запрашивает подтверждение рискованных действий."
            ),
            short_description="Личный оркестратор задач с контролем результата и риска.",
            commands=_COMMANDS,
        )
    finally:
        await api.aclose()


def main() -> int:
    try:
        asyncio.run(_run())
    except (CredentialStoreError, TelegramBotApiError):
        result = {"status": "FAIL", "code": "telegram_profile_failed"}
    except Exception:
        result = {"status": "FAIL", "code": "telegram_profile_failed"}
    else:
        result = {"status": "PASS", "profile": "nobus-space-mvp1"}
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
