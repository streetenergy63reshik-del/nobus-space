"""Idempotently apply the Nobus Space Telegram bot product profile."""

from __future__ import annotations

import argparse
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
    ("status", "Состояние и очередь"),
    ("limit", "Недельный лимит Codex"),
    ("notes", "Резюме Заметок бизнеса"),
    ("file", "Получить файл с компьютера"),
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
                "Мобильный оркестратор: выполняет текстовые и голосовые задачи, "
                "работает с файлами, интернетом, Google и Заметками бизнеса. "
                "Подтверждение запрашивает только для необратимых действий."
            ),
            short_description="Мобильный ИИ-оркестратор задач, файлов, Google и бизнеса.",
            commands=_COMMANDS,
        )
    finally:
        await api.aclose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply the Nobus Space Telegram product profile."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform the external Telegram write",
    )
    args = parser.parse_args(argv)
    if not args.apply:
        parser.error("external profile write requires explicit --apply")
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
