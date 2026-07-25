from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.transport.telegram.bindings import (
    TelegramBindingError,
    load_telegram_bindings,
)
from src.transport.telegram.gateway import (
    InMemoryCallbackTokenStore,
    InMemoryUpdateIdStore,
    TelegramGateway,
)
from src.transport.telegram import TrustedIngressResult
from src.transport.telegram.models import ActorBinding, IngressStatus


BOT_ID = 123
BOT_USERNAME = "Nobusspacebot"
USER_ID = 42
GROUP_ID = -100123456789
AUTH_DIGEST = "sha256:" + "a" * 64


def _group_config() -> dict[str, object]:
    proof = {
        "actor_identity": "telegram:owner",
        "bot_id": BOT_ID,
        "bot_username": BOT_USERNAME,
        "challenge_digest": AUTH_DIGEST,
        "chat_id": GROUP_ID,
        "proof": "telegram_owner_challenge_v1",
        "purpose": "business_notes",
        "role": "owner",
        "schema_version": 2,
        "tenant_id": "owner",
        "update_id": 10,
        "user_id": USER_ID,
    }
    auth_ref = "sha256:" + hashlib.sha256(
        json.dumps(
            proof, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    return {
        "version": 2,
        "bot_id": BOT_ID,
        "bot_username": BOT_USERNAME,
        "bindings": [
            {
                "user_id": USER_ID,
                "chat_id": GROUP_ID,
                "purpose": "business_notes",
                "tenant_id": "owner",
                "actor_identity": "telegram:owner",
                "role": "owner",
                "auth_context_ref": auth_ref,
                "proof": {
                    "kind": "telegram_owner_challenge_v1",
                    "update_id": 10,
                    "challenge_digest": AUTH_DIGEST,
                },
            }
        ],
    }


def test_v2_loads_exact_owner_business_notes_group(tmp_path: Path) -> None:
    path = tmp_path / "bindings.json"
    path.write_text(json.dumps(_group_config()), encoding="utf-8")

    bindings = load_telegram_bindings(
        path,
        expected_bot_id=BOT_ID,
        expected_bot_username=BOT_USERNAME,
        expected_tenant_id="owner",
        expected_actor_identity="telegram:owner",
        expected_role="owner",
    )

    assert tuple(bindings) == ((USER_ID, GROUP_ID),)
    assert bindings[(USER_ID, GROUP_ID)].purpose == "business_notes"


@pytest.mark.parametrize(
    "version,chat_id",
    [(1, GROUP_ID), (2, USER_ID)],
)
def test_group_binding_purpose_is_fail_closed(
    tmp_path: Path, version: int, chat_id: int
) -> None:
    value = _group_config()
    value["version"] = version
    value["bindings"][0]["chat_id"] = chat_id  # type: ignore[index]
    path = tmp_path / "bindings.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(TelegramBindingError):
        load_telegram_bindings(
            path,
            expected_bot_id=BOT_ID,
            expected_bot_username=BOT_USERNAME,
            expected_tenant_id="owner",
            expected_actor_identity="telegram:owner",
            expected_role="owner",
        )


def _gateway() -> TelegramGateway:
    return TelegramGateway(
        actor_bindings={
            (USER_ID, GROUP_ID): ActorBinding(
                tenant_id="owner",
                actor_identity="telegram:owner",
                role="owner",
                auth_context_ref=AUTH_DIGEST,
                purpose="business_notes",
            )
        },
        update_id_store=InMemoryUpdateIdStore(),
        callback_token_store=InMemoryCallbackTokenStore({}),
    )


def _topic_update(thread_id: object) -> dict[str, object]:
    return {
        "update_id": 77,
        "message": {
            "message_id": 9,
            "message_thread_id": thread_id,
            "from": {"id": USER_ID},
            "chat": {"id": GROUP_ID},
            "text": "Позвонить поставщику завтра.",
        },
    }


def test_topic_and_purpose_cross_trusted_ingress() -> None:
    result = _gateway().process_update(_topic_update(23))

    assert result.status is IngressStatus.ACCEPTED
    assert result.payload is not None
    assert result.payload.binding_purpose == "business_notes"
    assert result.payload.message_thread_id == 23
    assert result.envelope is not None
    assert ":thread:23:message:9" in result.envelope.external_message_id


def test_binding_purpose_is_bound_into_trusted_result() -> None:
    result = _gateway().process_update(_topic_update(23))
    value = result.model_dump(mode="python")
    value["payload"]["binding_purpose"] = "owner_private"

    with pytest.raises(ValidationError):
        TrustedIngressResult.model_validate(value)


@pytest.mark.parametrize("thread_id", [0, -1, True, "23"])
def test_invalid_topic_id_is_rejected(thread_id: object) -> None:
    result = _gateway().process_update(_topic_update(thread_id))
    assert result.status is IngressStatus.REJECTED
    assert result.reason == "invalid message_thread_id"
