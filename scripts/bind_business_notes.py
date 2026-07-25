"""Bind one exact owner group to the business-notes Telegram purpose."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_telegram_control import (  # noqa: E402
    _BINDING_PATH,
    _CREDENTIAL_TARGET,
    _EXPECTED_USERNAME,
)
from src.security.windows_credentials import (  # noqa: E402
    CredentialStoreError,
    read_generic_credential,
)
from src.transport.telegram.bindings import (  # noqa: E402
    StoredActorBinding,
    TelegramBindingConfig,
    TelegramChallengeProof,
    _proof_digest,
    load_telegram_bindings,
)
from src.transport.telegram.bot_api import (  # noqa: E402
    TelegramBotApi,
    TelegramBotApiError,
)


_MARKER = "#NOBUS-BIND-NOTES"
_TITLE = "Заметки бизнеса"


def _candidate(
    updates: list[dict[str, Any]], *, owner_user_id: int
) -> tuple[int, int] | None:
    matches: list[tuple[int, int]] = []
    for update in updates:
        message = update.get("message")
        sender = message.get("from") if isinstance(message, dict) else None
        chat = message.get("chat") if isinstance(message, dict) else None
        update_id = update.get("update_id")
        if (
            type(update_id) is int
            and isinstance(message, dict)
            and message.get("text") == _MARKER
            and isinstance(sender, dict)
            and sender.get("id") == owner_user_id
            and isinstance(chat, dict)
            and type(chat.get("id")) is int
            and chat["id"] < 0
            and chat.get("type") in {"group", "supergroup"}
            and chat.get("title") == _TITLE
        ):
            matches.append((update_id, chat["id"]))
    if not matches:
        return None
    chat_ids = {chat_id for _, chat_id in matches}
    if len(chat_ids) != 1:
        raise ValueError("ambiguous business notes binding")
    return max(matches)


def _v2_config(
    config: TelegramBindingConfig, *, update_id: int, chat_id: int
) -> TelegramBindingConfig:
    owner = next(
        item for item in config.bindings if item.purpose == "owner_private"
    )
    proof = TelegramChallengeProof(
        kind="telegram_owner_challenge_v1",
        update_id=update_id,
        challenge_digest="sha256:"
        + hashlib.sha256(_MARKER.encode("utf-8")).hexdigest(),
    )
    values = [
        item.model_copy(
            update={"auth_context_ref": "sha256:" + "0" * 64}
        )
        for item in config.bindings
        if item.purpose != "business_notes"
    ]
    values.append(
        StoredActorBinding(
            user_id=owner.user_id,
            chat_id=chat_id,
            purpose="business_notes",
            tenant_id=owner.tenant_id,
            actor_identity=owner.actor_identity,
            role=owner.role,
            auth_context_ref="sha256:" + "0" * 64,
            proof=proof,
        )
    )
    draft = TelegramBindingConfig(
        version=2,
        bot_id=config.bot_id,
        bot_username=config.bot_username,
        bindings=values,
    )
    bindings = [
        item.model_copy(update={"auth_context_ref": _proof_digest(draft, item)})
        for item in draft.bindings
    ]
    return draft.model_copy(update={"bindings": tuple(bindings)})


def _atomic_write(path: Path, config: TelegramBindingConfig) -> None:
    content = json.dumps(
        config.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


async def _bind() -> dict[str, object]:
    raw = json.loads(_BINDING_PATH.read_text(encoding="utf-8"))
    config = TelegramBindingConfig.model_validate(raw)
    owner = next(
        item for item in config.bindings if item.purpose == "owner_private"
    )
    load_telegram_bindings(
        _BINDING_PATH,
        expected_bot_id=config.bot_id,
        expected_bot_username=config.bot_username,
        expected_tenant_id=owner.tenant_id,
        expected_actor_identity=owner.actor_identity,
        expected_role=owner.role,
    )
    credential = read_generic_credential(_CREDENTIAL_TARGET)
    if credential.username.casefold() != f"@{_EXPECTED_USERNAME}".casefold():
        raise CredentialStoreError("credential_unavailable")
    api = TelegramBotApi(
        token=credential.secret.get_secret_value(),
        transport=httpx.AsyncHTTPTransport(retries=0, trust_env=False),
        request_timeout=30,
    )
    try:
        identity = await api.get_me()
        if (
            identity.bot_id != config.bot_id
            or identity.username.casefold() != config.bot_username.casefold()
        ):
            raise TelegramBotApiError("telegram_protocol_error")
        selected = _candidate(
            await api.peek_updates(limit=100),
            owner_user_id=owner.user_id,
        )
        if selected is None:
            return {"status": "WAITING_FOR_OWNER_MARKER"}
        update_id, chat_id = selected
        updated = _v2_config(
            config, update_id=update_id, chat_id=chat_id
        )
        _atomic_write(_BINDING_PATH, updated)
        load_telegram_bindings(
            _BINDING_PATH,
            expected_bot_id=updated.bot_id,
            expected_bot_username=updated.bot_username,
            expected_tenant_id=owner.tenant_id,
            expected_actor_identity=owner.actor_identity,
            expected_role=owner.role,
        )
        return {"status": "PASS", "purpose": "business_notes"}
    finally:
        await api.aclose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if not args.apply:
        parser.error("binding write requires explicit --apply")
    try:
        result = asyncio.run(_bind())
    except Exception:
        result = {"status": "FAIL", "code": "business_notes_binding_failed"}
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return 0 if result["status"] in {"PASS", "WAITING_FOR_OWNER_MARKER"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
