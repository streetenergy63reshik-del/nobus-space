"""Run the authenticated Nobus Space Telegram control-plane.

Delivery is intentionally at-least-once and restricted to safe idempotent
control replies: a crash after send but before checkpoint may duplicate one.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application.telegram_control import TelegramControlPlane  # noqa: E402
from src.security.windows_credentials import (  # noqa: E402
    CredentialStoreError,
    read_generic_credential,
)
from src.transport.telegram import (  # noqa: E402
    InMemoryCallbackTokenStore,
    InMemoryUpdateIdStore,
    TelegramGateway,
)
from src.transport.telegram.bindings import (  # noqa: E402
    TelegramBindingError,
    load_telegram_bindings,
)
from src.transport.telegram.bot_api import (  # noqa: E402
    TelegramBotApi,
    TelegramBotApiError,
    TelegramPollingBoundary,
)
from src.transport.telegram.sqlite_checkpoint import (  # noqa: E402
    SQLitePollingCheckpointError,
    SQLitePollingCheckpointStore,
)


_CREDENTIAL_TARGET = "NobusSpace/TelegramBot/MVP1"
_EXPECTED_USERNAME = "Nobusspacebot"
_BINDING_PATH = ROOT / "telegram-bindings.local.json"
_CHECKPOINT_PATH = ROOT / "telegram-runtime.local.sqlite3"
_ANNOUNCEMENT = (
    "Nobus Space MVP-1: первый polling cycle пройден.\n"
    "Telegram identity: verified\n"
    "Owner binding: active\n"
    "Команды: /status, /help"
)


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--serve", action="store_true")
    parser.add_argument("--announce", action="store_true")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--bootstrap-next-offset", type=int)
    values = parser.parse_args(argv)
    if not 0 <= values.timeout <= 50 or (values.serve and values.timeout == 0):
        parser.error("timeout must be 0..50 for once and 1..50 for serve")
    if values.bootstrap_next_offset is not None and not (
        0 < values.bootstrap_next_offset <= 9_223_372_036_854_775_807
    ):
        parser.error("bootstrap offset is out of range")
    return values


async def _run(values: argparse.Namespace) -> dict[str, object]:
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
        bindings = load_telegram_bindings(
            _BINDING_PATH,
            expected_bot_id=identity.bot_id,
            expected_bot_username=identity.username,
            expected_tenant_id="owner",
            expected_actor_identity="telegram:owner",
            expected_role="owner",
        )
        checkpoint = SQLitePollingCheckpointStore(
            _CHECKPOINT_PATH,
            consumer_id="nobusspacebot-owner",
        )
        if values.bootstrap_next_offset is not None:
            _bootstrap_checkpoint(checkpoint, values.bootstrap_next_offset)
        gateway = TelegramGateway(
            actor_bindings=bindings,
            update_id_store=InMemoryUpdateIdStore(),
            callback_token_store=InMemoryCallbackTokenStore({}),
        )
        control = TelegramControlPlane(gateway, api)
        polling = TelegramPollingBoundary(api, control.handle, checkpoint)
        acknowledged = await _poll_once_and_announce(
            polling,
            api,
            bindings,
            timeout=values.timeout,
            announce=values.announce,
        )
        if values.serve:
            while True:
                acknowledged += await _poll_once_and_announce(
                    polling,
                    api,
                    bindings,
                    timeout=values.timeout,
                    announce=False,
                )
        return {
            "status": "PASS",
            "mode": "once" if values.once else "serve",
            "announced": bool(values.announce),
            "acknowledged": acknowledged,
        }
    finally:
        await api.aclose()


async def _poll_once_and_announce(
    polling: TelegramPollingBoundary,
    api: TelegramBotApi,
    bindings: Mapping[tuple[int, int], object],
    *,
    timeout: int,
    announce: bool,
) -> int:
    result = await polling.poll_once(timeout=timeout, limit=20)
    if result.retry_required:
        raise TelegramBotApiError("telegram_handler_failed")
    if announce:
        if len(bindings) != 1:
            raise TelegramBindingError("telegram_binding_configuration_invalid")
        await api.send_message(next(iter(bindings))[1], _ANNOUNCEMENT)
    return result.acknowledged


def _bootstrap_checkpoint(
    checkpoint: SQLitePollingCheckpointStore, next_offset: int
) -> None:
    lease = checkpoint.acquire(uuid4(), datetime.now(UTC))
    if lease is None:
        raise SQLitePollingCheckpointError("polling checkpoint is invalid")
    failed = False
    try:
        current = checkpoint.load(lease)
        if current is None:
            failed = checkpoint.advance(
                lease=lease,
                expected=None,
                next_offset=next_offset,
            ) is not True
        elif current != next_offset:
            failed = True
    finally:
        released = checkpoint.release(lease)
    if failed or released is not True:
        raise SQLitePollingCheckpointError("polling checkpoint is invalid")


def main() -> int:
    result: dict[str, object] | None = None
    failure = ""
    try:
        result = asyncio.run(_run(_arguments()))
    except KeyboardInterrupt:
        result = {"status": "STOPPED"}
    except CredentialStoreError as error:
        failure = error.code
    except TelegramBindingError as error:
        failure = error.code
    except TelegramBotApiError as error:
        failure = error.code
    except SQLitePollingCheckpointError:
        failure = "telegram_checkpoint_failed"
    except Exception:
        failure = "telegram_control_failed"
    if result is None:
        result = {"status": "FAIL", "code": failure or "telegram_control_failed"}
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return 0 if result["status"] in {"PASS", "STOPPED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
