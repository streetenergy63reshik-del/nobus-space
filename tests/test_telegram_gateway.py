"""Adversarial tests for the isolated Telegram ingress boundary."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from pydantic import ValidationError

from src.transport.telegram.gateway import (
    InMemoryCallbackTokenStore,
    InMemoryUpdateIdStore,
    TelegramGateway,
)
from src.transport.telegram.models import (
    ActorBinding,
    CallbackQuery,
    IngressStatus,
    TextMessage,
    VoiceMessage,
)


USER_A = 111111
CHAT_A = 222222
USER_B = 333333
CHAT_B = 444444
CALLBACK_TOKEN = "AbcdEFgh_12345678"


def make_gateway(
    *,
    bindings: dict[tuple[int, int], ActorBinding] | None = None,
    callback_tokens: dict[str, tuple[int, int]] | None = None,
    update_store: InMemoryUpdateIdStore | None = None,
) -> TelegramGateway:
    return TelegramGateway(
        actor_bindings=bindings
        or {(USER_A, CHAT_A): ActorBinding(tenant_id="tenant-a", role="owner")},
        update_id_store=update_store or InMemoryUpdateIdStore(),
        callback_token_store=InMemoryCallbackTokenStore(
            callback_tokens
            if callback_tokens is not None
            else {CALLBACK_TOKEN: (USER_A, CHAT_A)}
        ),
        max_text_length=100,
        max_voice_duration=60,
    )


@pytest.fixture
def gateway() -> TelegramGateway:
    return make_gateway()


def make_text_update(
    text: Any = "hello", *, update_id: Any = 1, user_id: Any = USER_A, chat_id: Any = CHAT_A
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 100,
            "from": {"id": user_id},
            "chat": {"id": chat_id},
            "text": text,
        },
    }


def make_voice_update(
    *, update_id: int = 2, duration: Any = 10, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    voice: dict[str, Any] = {
        "file_id": " voice-file ",
        "file_unique_id": " unique-file ",
        "duration": duration,
        "mime_type": " audio/ogg ",
        "file_size": 123,
    }
    voice.update(extra or {})
    return {
        "update_id": update_id,
        "message": {
            "message_id": 101,
            "from": {"id": USER_A},
            "chat": {"id": CHAT_A},
            "voice": voice,
        },
    }


def make_callback_update(
    data: Any = CALLBACK_TOKEN, *, update_id: int = 3
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": " query-id ",
            "from": {"id": USER_A},
            "message": {"chat": {"id": CHAT_A}},
            "data": data,
        },
    }


def test_text_is_normalized_and_bound_to_server_owned_tenant(
    gateway: TelegramGateway,
) -> None:
    result = gateway.process_update(make_text_update("  hello world  "))
    assert result.status == IngressStatus.ACCEPTED
    assert isinstance(result.payload, TextMessage)
    assert result.payload.text == "hello world"
    assert result.payload.tenant_id == "tenant-a"
    assert result.payload.actor_role == "owner"


def test_allowlist_uses_exact_pairs_not_cartesian_product() -> None:
    gateway = make_gateway(
        bindings={
            (USER_A, CHAT_A): ActorBinding(tenant_id="tenant-a", role="owner"),
            (USER_B, CHAT_B): ActorBinding(tenant_id="tenant-b", role="operator"),
        }
    )
    result = gateway.process_update(
        make_text_update(user_id=USER_A, chat_id=CHAT_B)
    )
    assert result.status == IngressStatus.REJECTED
    assert result.reason == "user/chat pair not in allowlist"


def test_binding_configuration_is_copied_and_immutable() -> None:
    bindings = {(USER_A, CHAT_A): ActorBinding(tenant_id="tenant-a", role="owner")}
    gateway = make_gateway(bindings=bindings)
    bindings[(USER_B, CHAT_B)] = ActorBinding(tenant_id="tenant-b", role="owner")
    result = gateway.process_update(
        make_text_update(update_id=8, user_id=USER_B, chat_id=CHAT_B)
    )
    assert result.status == IngressStatus.REJECTED


def test_update_claim_is_atomic_under_concurrency() -> None:
    gateway = make_gateway()
    update = make_text_update()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(gateway.process_update, [update] * 32))
    assert sum(result.status == IngressStatus.ACCEPTED for result in results) == 1
    assert sum(result.reason == "duplicate update_id" for result in results) == 31


def test_malformed_claimed_update_is_not_reprocessed(gateway: TelegramGateway) -> None:
    malformed = {"update_id": 7, "message": None}
    assert gateway.process_update(malformed).reason == "malformed message"
    assert gateway.process_update(malformed).reason == "duplicate update_id"


def test_voice_copies_only_allowlisted_metadata(gateway: TelegramGateway) -> None:
    result = gateway.process_update(
        make_voice_update(extra={"api_token": "must-not-cross", "nested": {"secret": 1}})
    )
    assert result.status == IngressStatus.ACCEPTED
    assert isinstance(result.payload, VoiceMessage)
    assert result.payload.file_id == "voice-file"
    assert result.payload.metadata.file_unique_id == "unique-file"
    assert result.payload.metadata.mime_type == "audio/ogg"
    assert result.payload.metadata.file_size == 123
    serialized = result.model_dump(mode="json")
    assert "api_token" not in str(serialized)
    assert "must-not-cross" not in str(serialized)


@pytest.mark.parametrize(
    "extra",
    [
        {"file_unique_id": True},
        {"mime_type": 42},
        {"file_size": True},
        {"file_size": -1},
    ],
)
def test_invalid_allowlisted_voice_metadata_is_rejected(
    gateway: TelegramGateway, extra: dict[str, Any]
) -> None:
    result = gateway.process_update(make_voice_update(extra=extra))
    assert result.status == IngressStatus.REJECTED
    assert result.reason == "invalid voice metadata"


def test_callback_exposes_only_one_time_opaque_token() -> None:
    gateway = make_gateway()
    result = gateway.process_update(make_callback_update())
    assert result.status == IngressStatus.ACCEPTED
    assert isinstance(result.payload, CallbackQuery)
    assert result.payload.callback_token == CALLBACK_TOKEN
    assert not hasattr(result.payload, "action")
    assert not hasattr(result.payload, "task_reference")
    assert not hasattr(result.payload, "idempotency_key")

    replay = gateway.process_update(make_callback_update(update_id=4))
    assert replay.status == IngressStatus.REJECTED
    assert replay.reason == "invalid or used callback token"


@pytest.mark.parametrize(
    "data",
    [
        "confirm:task-42:key-abc",
        "short",
        " token_with_spaces ",
        "x" * 65,
        123,
        None,
    ],
)
def test_structured_or_malformed_callback_data_is_rejected(data: Any) -> None:
    result = make_gateway().process_update(make_callback_update(data))
    assert result.status == IngressStatus.REJECTED
    assert result.reason == "malformed callback token"


def test_unissued_callback_token_is_rejected() -> None:
    result = make_gateway(callback_tokens={}).process_update(make_callback_update())
    assert result.status == IngressStatus.REJECTED
    assert result.reason == "invalid or used callback token"


def test_callback_token_is_bound_to_exact_actor_pair() -> None:
    result = make_gateway(
        callback_tokens={CALLBACK_TOKEN: (USER_B, CHAT_B)}
    ).process_update(make_callback_update())
    assert result.status == IngressStatus.REJECTED
    assert result.reason == "invalid or used callback token"


@pytest.mark.parametrize(
    "bindings",
    [
        {"short": (USER_A, CHAT_A)},
        {"confirm:task:key": (USER_A, CHAT_A)},
        {"x" * 65: (USER_A, CHAT_A)},
        {CALLBACK_TOKEN: (True, CHAT_A)},
        {CALLBACK_TOKEN: (1.0, CHAT_A)},
        {CALLBACK_TOKEN: (USER_A,)},
        {CALLBACK_TOKEN: (USER_A, CHAT_A, 5)},
        {CALLBACK_TOKEN: [USER_A, CHAT_A]},
    ],
)
def test_callback_store_rejects_invalid_configuration(
    bindings: dict[Any, Any],
) -> None:
    with pytest.raises(ValueError):
        InMemoryCallbackTokenStore(bindings)


def test_callback_store_takes_immutable_snapshot() -> None:
    bindings = {CALLBACK_TOKEN: (USER_A, CHAT_A)}
    store = InMemoryCallbackTokenStore(bindings)
    bindings[CALLBACK_TOKEN] = (USER_B, CHAT_B)
    bindings["OtherToken_123456"] = (USER_B, CHAT_B)
    assert store.claim(CALLBACK_TOKEN, USER_A, CHAT_A)
    assert not store.claim("OtherToken_123456", USER_B, CHAT_B)


def test_gateway_does_not_store_bot_token_or_render_allowlisted_ids(
    gateway: TelegramGateway,
) -> None:
    rendered = repr(gateway)
    assert "token" not in gateway.__dict__
    assert str(USER_A) not in rendered
    assert str(CHAT_A) not in rendered


def test_normalized_models_forbid_extra_and_are_frozen() -> None:
    message = TextMessage(
        update_id=1,
        tenant_id="tenant-a",
        actor_role="owner",
        user_id=USER_A,
        chat_id=CHAT_A,
        message_id=1,
        text="hello",
    )
    with pytest.raises(ValidationError):
        TextMessage.model_validate({**message.model_dump(), "secret": "no"})
    with pytest.raises(ValidationError):
        message.text = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("update_id", [None, True, -1, "1"])
def test_invalid_update_id_is_rejected_without_claim(update_id: Any) -> None:
    result = make_gateway().process_update(make_text_update(update_id=update_id))
    assert result.status == IngressStatus.REJECTED
    assert result.update_id is None
    assert result.reason == "missing or invalid update_id"


@pytest.mark.parametrize("user_id,chat_id", [(True, CHAT_A), (USER_A, True), (0, 0)])
def test_invalid_or_unbound_actor_is_rejected(user_id: Any, chat_id: Any) -> None:
    result = make_gateway().process_update(
        make_text_update(user_id=user_id, chat_id=chat_id)
    )
    assert result.status == IngressStatus.REJECTED


@pytest.mark.parametrize("text,reason", [(None, "invalid text type"), (" ", "empty text"), ("x" * 101, "text exceeds max length")])
def test_invalid_text_is_rejected(text: Any, reason: str) -> None:
    result = make_gateway().process_update(make_text_update(text))
    assert result.status == IngressStatus.REJECTED
    assert result.reason == reason


@pytest.mark.parametrize("duration", [True, -1, 61, "10"])
def test_invalid_voice_duration_is_rejected(duration: Any) -> None:
    result = make_gateway().process_update(make_voice_update(duration=duration))
    assert result.status == IngressStatus.REJECTED
    assert result.reason == "voice exceeds max duration or invalid duration"


def test_ambiguous_and_unknown_updates_are_safe() -> None:
    gateway = make_gateway()
    ambiguous = make_text_update(update_id=10)
    ambiguous["callback_query"] = make_callback_update()["callback_query"]
    assert gateway.process_update(ambiguous).reason == "ambiguous update"
    unknown = gateway.process_update({"update_id": 11, "edited_message": {}})
    assert unknown.status == IngressStatus.IGNORED
    assert unknown.reason == "unknown update type"
