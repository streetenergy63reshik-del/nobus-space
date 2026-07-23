"""Adversarial tests for actor-bound single-use voice confirmation."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from src.contracts.models import canonical_json_digest
from src.transport.telegram import (
    ActorBinding,
    CallbackQuery,
    InMemoryCallbackTokenStore,
    InMemoryUpdateIdStore,
    IngressStatus,
    TelegramGateway,
    VoiceMessage,
)
from src.voice import (
    InMemoryVoiceConfirmationStore,
    VoiceConfirmationStatus,
    VoicePreview,
)


USER_A = 101
CHAT_A = 201
USER_B = 102
CHAT_B = 202
TOKEN = "A" * 43
AUTH_A = "sha256:" + "a" * 64
AUTH_B = "sha256:" + "b" * 64
BASE_TIME = datetime(2026, 7, 21, 9, 0, tzinfo=UTC)
AUDIO = b"bounded fake audio"
AUDIO_DIGEST = hashlib.sha256(AUDIO).hexdigest()


class Clock:
    def __init__(self, value: datetime = BASE_TIME) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


def actor_binding(
    *,
    tenant: str = "tenant-a",
    identity: str = "telegram:owner-a",
    role: str = "owner",
    auth_ref: str = AUTH_A,
) -> ActorBinding:
    return ActorBinding(
        tenant_id=tenant,
        actor_identity=identity,
        role=role,
        auth_context_ref=auth_ref,
    )


def voice_update(*, update_id: int = 1, user_id: int = USER_A, chat_id: int = CHAT_A) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 11,
            "from": {"id": user_id},
            "chat": {"id": chat_id},
            "voice": {
                "file_id": "opaque-file-id",
                "file_unique_id": "stable-file-id",
                "duration": 2,
                "file_size": len(AUDIO),
            },
        },
    }


def callback_update(
    token: str,
    *,
    update_id: int = 2,
    user_id: int = USER_A,
    chat_id: int = CHAT_A,
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"query-{update_id}",
            "from": {"id": user_id},
            "message": {"message_id": 100 + update_id, "chat": {"id": chat_id}},
            "data": token,
        },
    }


def gateway(
    store: Any,
    clock: Clock,
    *,
    bindings: dict[tuple[int, int], ActorBinding] | None = None,
) -> TelegramGateway:
    return TelegramGateway(
        actor_bindings=bindings or {(USER_A, CHAT_A): actor_binding()},
        update_id_store=InMemoryUpdateIdStore(),
        callback_token_store=store,
        clock=clock,
    )


def preview(transcript: str = "Р СџРЎР‚Р С•Р Р†Р ВµРЎР‚РЎРЉ Р В»Р С•Р С”Р В°Р В»РЎРЉР Р…РЎвЂ№Р в„– РЎР‚Р ВµР С—Р С•Р В·Р С‘РЎвЂљР С•РЎР‚Р С‘Р в„–") -> VoicePreview:
    return VoicePreview(
        transcript=transcript,
        language="ru",
        confidence=0.98,
        sha256=AUDIO_DIGEST,
        size=len(AUDIO),
    )


def issue(
    store: InMemoryVoiceConfirmationStore,
    clock: Clock,
    *,
    source_gateway: TelegramGateway | None = None,
    ttl_seconds: int = 300,
):
    ingress = (source_gateway or gateway(store, clock)).process_update(voice_update())
    assert ingress.status is IngressStatus.ACCEPTED
    assert isinstance(ingress.payload, VoiceMessage)
    assert ingress.envelope is not None
    challenge = store.issue(
        message=ingress.payload,
        envelope=ingress.envelope,
        preview=preview(),
        ttl_seconds=ttl_seconds,
    )
    return ingress, challenge


def test_full_gateway_flow_confirms_exact_preview_once() -> None:
    clock = Clock()
    store = InMemoryVoiceConfirmationStore(clock=clock, token_factory=lambda: TOKEN)
    app_gateway = gateway(store, clock)
    voice_ingress, challenge = issue(store, clock, source_gateway=app_gateway)
    token = challenge.callback_token.get_secret_value()

    clock.advance(1)
    callback_ingress = app_gateway.process_update(callback_update(token))
    assert callback_ingress.status is IngressStatus.ACCEPTED
    assert isinstance(callback_ingress.payload, CallbackQuery)
    assert callback_ingress.envelope is not None

    result = store.confirm(
        callback=callback_ingress.payload,
        envelope=callback_ingress.envelope,
    )

    assert result.status is VoiceConfirmationStatus.CONFIRMED
    assert result.confirmation is not None
    assert result.confirmation.tenant_id == "tenant-a"
    assert result.confirmation.actor_identity == "telegram:owner-a"
    assert result.confirmation.actor_role == "owner"
    assert result.confirmation.auth_context_ref == AUTH_A
    assert result.confirmation.user_id == USER_A
    assert result.confirmation.chat_id == CHAT_A
    assert result.confirmation.voice_envelope_revision == voice_ingress.envelope.envelope_revision
    assert result.confirmation.voice_content_ref == voice_ingress.envelope.content_ref
    assert result.confirmation.audio_sha256 == AUDIO_DIGEST
    assert result.confirmation.transcript == "Р СџРЎР‚Р С•Р Р†Р ВµРЎР‚РЎРЉ Р В»Р С•Р С”Р В°Р В»РЎРЉР Р…РЎвЂ№Р в„– РЎР‚Р ВµР С—Р С•Р В·Р С‘РЎвЂљР С•РЎР‚Р С‘Р в„–"
    assert result.confirmation.transcript_digest == canonical_json_digest(
        {"transcript": "Р СџРЎР‚Р С•Р Р†Р ВµРЎР‚РЎРЉ Р В»Р С•Р С”Р В°Р В»РЎРЉР Р…РЎвЂ№Р в„– РЎР‚Р ВµР С—Р С•Р В·Р С‘РЎвЂљР С•РЎР‚Р С‘Р в„–"}
    )
    assert result.confirmation.language == "ru"
    assert result.confirmation.confidence == 0.98
    assert result.confirmation.callback_token_digest == (
        "sha256:" + hashlib.sha256(TOKEN.encode()).hexdigest()
    )
    assert TOKEN not in result.model_dump_json()
    assert TOKEN not in repr(challenge)

    replay = app_gateway.process_update(callback_update(token, update_id=3))
    assert replay.status is IngressStatus.REJECTED
    assert replay.reason == "invalid or used callback token"


def test_confirm_requires_gateway_claim() -> None:
    clock = Clock()
    store = InMemoryVoiceConfirmationStore(clock=clock, token_factory=lambda: TOKEN)
    _, challenge = issue(store, clock)
    token = challenge.callback_token.get_secret_value()
    generic = gateway(
        InMemoryCallbackTokenStore({token: (USER_A, CHAT_A)}), clock
    ).process_update(callback_update(token))
    assert isinstance(generic.payload, CallbackQuery) and generic.envelope is not None

    result = store.confirm(callback=generic.payload, envelope=generic.envelope)

    assert result.status is VoiceConfirmationStatus.REJECTED
    assert result.confirmation is None


def test_foreign_pair_does_not_consume_token() -> None:
    clock = Clock()
    store = InMemoryVoiceConfirmationStore(clock=clock, token_factory=lambda: TOKEN)
    issue(store, clock)
    bindings = {
        (USER_A, CHAT_A): actor_binding(),
        (USER_B, CHAT_B): actor_binding(
            tenant="tenant-b", identity="telegram:owner-b", auth_ref=AUTH_B
        ),
    }
    app_gateway = gateway(store, clock, bindings=bindings)

    foreign = app_gateway.process_update(
        callback_update(TOKEN, update_id=10, user_id=USER_B, chat_id=CHAT_B)
    )
    correct = app_gateway.process_update(callback_update(TOKEN, update_id=11))

    assert foreign.status is IngressStatus.REJECTED
    assert correct.status is IngressStatus.ACCEPTED


def test_changed_server_binding_fails_closed_after_gateway_claim() -> None:
    clock = Clock()
    store = InMemoryVoiceConfirmationStore(clock=clock, token_factory=lambda: TOKEN)
    issue(store, clock)
    changed_gateway = gateway(
        store,
        clock,
        bindings={
            (USER_A, CHAT_A): actor_binding(
                tenant="tenant-b", identity="telegram:other", auth_ref=AUTH_B
            )
        },
    )
    ingress = changed_gateway.process_update(callback_update(TOKEN))
    assert isinstance(ingress.payload, CallbackQuery) and ingress.envelope is not None

    result = store.confirm(callback=ingress.payload, envelope=ingress.envelope)

    assert result.status is VoiceConfirmationStatus.REJECTED
    assert result.confirmation is None


def test_tampered_callback_envelope_is_rejected_without_exception_text() -> None:
    clock = Clock()
    store = InMemoryVoiceConfirmationStore(clock=clock, token_factory=lambda: TOKEN)
    issue(store, clock)
    ingress = gateway(store, clock).process_update(callback_update(TOKEN))
    assert isinstance(ingress.payload, CallbackQuery) and ingress.envelope is not None
    tampered = ingress.envelope.model_copy(update={"tenant_id": "tenant-b"})

    result = store.confirm(callback=ingress.payload, envelope=tampered)

    assert result.status is VoiceConfirmationStatus.REJECTED
    assert result.message == "Voice confirmation is invalid or expired."
    assert "tenant" not in result.model_dump_json()


def test_token_is_exactly_once_under_concurrent_claims() -> None:
    clock = Clock()
    store = InMemoryVoiceConfirmationStore(clock=clock, token_factory=lambda: TOKEN)
    issue(store, clock)

    with ThreadPoolExecutor(max_workers=16) as pool:
        claims = list(pool.map(lambda _: store.claim(TOKEN, USER_A, CHAT_A), range(100)))

    assert claims.count(True) == 1
    assert claims.count(False) == 99


def test_expired_token_is_rejected_and_swept() -> None:
    clock = Clock()
    store = InMemoryVoiceConfirmationStore(clock=clock, token_factory=lambda: TOKEN)
    issue(store, clock, ttl_seconds=1)
    clock.advance(1)

    assert not store.claim(TOKEN, USER_A, CHAT_A)
    assert store.sweep_expired() == 0
    assert store.sweep_expired() == 0


def test_confirmed_tombstone_has_bounded_retention() -> None:
    clock = Clock()
    store = InMemoryVoiceConfirmationStore(
        clock=clock,
        token_factory=lambda: TOKEN,
        confirmed_retention_seconds=10,
    )
    issue(store, clock)
    ingress = gateway(store, clock).process_update(callback_update(TOKEN))
    assert isinstance(ingress.payload, CallbackQuery) and ingress.envelope is not None
    first = store.confirm(callback=ingress.payload, envelope=ingress.envelope)
    second = store.confirm(callback=ingress.payload, envelope=ingress.envelope)
    assert first.status is VoiceConfirmationStatus.CONFIRMED
    assert second.status is VoiceConfirmationStatus.ALREADY_USED

    clock.advance(9)
    assert store.sweep_expired() == 0
    clock.advance(1)
    assert store.sweep_expired() == 1


def test_capacity_is_bounded_and_expiry_frees_space() -> None:
    clock = Clock()
    tokens = iter(("A" * 43, "B" * 43))
    store = InMemoryVoiceConfirmationStore(
        clock=clock, token_factory=lambda: next(tokens), max_entries=1
    )
    app_gateway = gateway(store, clock)
    issue(store, clock, ttl_seconds=1, source_gateway=app_gateway)
    ingress = app_gateway.process_update(voice_update(update_id=9))
    assert isinstance(ingress.payload, VoiceMessage) and ingress.envelope is not None
    with pytest.raises(RuntimeError, match="capacity"):
        store.issue(message=ingress.payload, envelope=ingress.envelope, preview=preview())

    clock.advance(1)
    replacement = store.issue(
        message=ingress.payload, envelope=ingress.envelope, preview=preview()
    )
    assert replacement.callback_token.get_secret_value() == "B" * 43


def test_collision_is_bounded_and_does_not_overwrite_original() -> None:
    clock = Clock()
    store = InMemoryVoiceConfirmationStore(clock=clock, token_factory=lambda: TOKEN)
    app_gateway = gateway(store, clock)
    issue(store, clock, source_gateway=app_gateway)
    ingress = app_gateway.process_update(voice_update(update_id=9))
    assert isinstance(ingress.payload, VoiceMessage) and ingress.envelope is not None

    with pytest.raises(RuntimeError, match="collision"):
        store.issue(message=ingress.payload, envelope=ingress.envelope, preview=preview())
    assert store.claim(TOKEN, USER_A, CHAT_A)


@pytest.mark.parametrize("ttl", [True, False, 0, -1, 901, 1.5, "60"])
def test_invalid_ttl_rejected_without_entry(ttl: Any) -> None:
    clock = Clock()
    store = InMemoryVoiceConfirmationStore(clock=clock, token_factory=lambda: TOKEN)
    ingress = gateway(store, clock).process_update(voice_update())
    assert isinstance(ingress.payload, VoiceMessage) and ingress.envelope is not None

    with pytest.raises(ValueError):
        store.issue(
            message=ingress.payload,
            envelope=ingress.envelope,
            preview=preview(),
            ttl_seconds=ttl,
        )
    assert not store.claim(TOKEN, USER_A, CHAT_A)


@pytest.mark.parametrize(
    "token",
    ["short", "x" * 65, "x" * 31, "bad+token" + "x" * 30, 123, None],
)
def test_invalid_token_factory_output_fails_safely(token: Any) -> None:
    clock = Clock()
    store = InMemoryVoiceConfirmationStore(clock=clock, token_factory=lambda: token)
    ingress = gateway(store, clock).process_update(voice_update())
    assert isinstance(ingress.payload, VoiceMessage) and ingress.envelope is not None

    with pytest.raises(RuntimeError, match="token factory"):
        store.issue(message=ingress.payload, envelope=ingress.envelope, preview=preview())


def test_malformed_preview_digest_and_transcript_are_rejected() -> None:
    clock = Clock()
    store = InMemoryVoiceConfirmationStore(clock=clock, token_factory=lambda: TOKEN)
    ingress = gateway(store, clock).process_update(voice_update())
    assert isinstance(ingress.payload, VoiceMessage) and ingress.envelope is not None
    bad_digest = preview().model_copy(update={"sha256": "not-a-digest"})
    empty = preview().model_copy(update={"transcript": "   "})

    with pytest.raises(ValueError, match="audio digest"):
        store.issue(message=ingress.payload, envelope=ingress.envelope, preview=bad_digest)
    with pytest.raises(ValueError, match="transcript"):
        store.issue(message=ingress.payload, envelope=ingress.envelope, preview=empty)


def test_tampered_voice_envelope_cannot_issue_token() -> None:
    clock = Clock()
    store = InMemoryVoiceConfirmationStore(clock=clock, token_factory=lambda: TOKEN)
    ingress = gateway(store, clock).process_update(voice_update())
    assert isinstance(ingress.payload, VoiceMessage) and ingress.envelope is not None
    tampered = ingress.envelope.model_copy(update={"content_ref": "sha256:" + "f" * 64})

    with pytest.raises(ValueError, match="trusted voice preview is invalid"):
        store.issue(message=ingress.payload, envelope=tampered, preview=preview())
    assert not store.claim(TOKEN, USER_A, CHAT_A)


def test_same_preview_cannot_receive_two_live_tokens() -> None:
    clock = Clock()
    tokens = iter(("A" * 43, "B" * 43))
    store = InMemoryVoiceConfirmationStore(
        clock=clock, token_factory=lambda: next(tokens)
    )
    ingress, _ = issue(store, clock)
    assert isinstance(ingress.payload, VoiceMessage) and ingress.envelope is not None

    with pytest.raises(RuntimeError, match="already issued"):
        store.issue(message=ingress.payload, envelope=ingress.envelope, preview=preview())


def test_model_copy_cannot_bypass_envelope_revision_validation() -> None:
    clock = Clock()
    store = InMemoryVoiceConfirmationStore(clock=clock, token_factory=lambda: TOKEN)
    ingress = gateway(store, clock).process_update(voice_update())
    assert isinstance(ingress.payload, VoiceMessage) and ingress.envelope is not None
    tampered = ingress.envelope.model_copy(
        update={"envelope_revision": "sha256:" + "f" * 64}
    )

    with pytest.raises(ValueError, match="trusted voice preview is invalid"):
        store.issue(message=ingress.payload, envelope=tampered, preview=preview())
    assert not store.claim(TOKEN, USER_A, CHAT_A)

def test_naive_or_backward_clock_fails_closed() -> None:
    naive_clock = Clock(BASE_TIME.replace(tzinfo=None))
    store = InMemoryVoiceConfirmationStore(
        clock=naive_clock, token_factory=lambda: TOKEN
    )
    ingress = gateway(
        store,
        Clock(BASE_TIME),
    ).process_update(voice_update())
    assert isinstance(ingress.payload, VoiceMessage) and ingress.envelope is not None
    with pytest.raises(ValueError, match="clock"):
        store.issue(message=ingress.payload, envelope=ingress.envelope, preview=preview())
    assert not store.claim(TOKEN, USER_A, CHAT_A)

    earlier = Clock(BASE_TIME - timedelta(seconds=1))
    store = InMemoryVoiceConfirmationStore(clock=earlier, token_factory=lambda: TOKEN)
    with pytest.raises(ValueError, match="backwards"):
        store.issue(message=ingress.payload, envelope=ingress.envelope, preview=preview())


def test_observed_clock_rollback_fails_closed_until_time_catches_up() -> None:
    clock = Clock()
    store = InMemoryVoiceConfirmationStore(clock=clock, token_factory=lambda: TOKEN)
    issue(store, clock, ttl_seconds=300)
    clock.advance(240)
    assert store.sweep_expired() == 0

    clock.value = BASE_TIME + timedelta(seconds=60)
    assert not store.claim(TOKEN, USER_A, CHAT_A)
    clock.value = BASE_TIME + timedelta(seconds=241)
    assert store.claim(TOKEN, USER_A, CHAT_A)


def test_provider_language_is_normalized_and_bounded() -> None:
    clock = Clock()
    store = InMemoryVoiceConfirmationStore(clock=clock, token_factory=lambda: TOKEN)
    ingress = gateway(store, clock).process_update(voice_update())
    assert isinstance(ingress.payload, VoiceMessage) and ingress.envelope is not None
    huge = preview().model_copy(update={"language": "x" * 1_000_000})

    with pytest.raises(ValueError, match="language"):
        store.issue(message=ingress.payload, envelope=ingress.envelope, preview=huge)
    assert not store.claim(TOKEN, USER_A, CHAT_A)

    normalized = preview().model_copy(update={"language": "RU"})
    store.issue(message=ingress.payload, envelope=ingress.envelope, preview=normalized)
    callback_ingress = gateway(store, clock).process_update(callback_update(TOKEN))
    assert isinstance(callback_ingress.payload, CallbackQuery)
    assert callback_ingress.envelope is not None
    result = store.confirm(
        callback=callback_ingress.payload, envelope=callback_ingress.envelope
    )
    assert result.confirmation is not None
    assert result.confirmation.language == "ru"


def test_unexpired_tombstone_is_minimal_and_never_evicted() -> None:
    clock = Clock()
    tokens = iter(("A" * 43, "B" * 43))
    store = InMemoryVoiceConfirmationStore(
        clock=clock,
        token_factory=lambda: next(tokens),
        max_entries=2,
        max_active_entries_per_tenant=1,
        max_confirmed_entries=2,
        max_confirmed_entries_per_tenant=1,
    )
    app_gateway = gateway(store, clock)
    first_voice, first_challenge = issue(
        store, clock, source_gateway=app_gateway
    )
    first_callback = app_gateway.process_update(callback_update("A" * 43))
    assert isinstance(first_callback.payload, CallbackQuery)
    assert first_callback.envelope is not None
    first_result = store.confirm(
        callback=first_callback.payload, envelope=first_callback.envelope
    )
    assert first_result.status is VoiceConfirmationStatus.CONFIRMED
    assert store._entries == {}
    assert "Проверь локальный репозиторий" not in repr(store._tombstones)
    assert first_challenge.callback_token.get_secret_value() not in repr(
        store._tombstones
    )

    assert isinstance(first_voice.payload, VoiceMessage)
    assert first_voice.envelope is not None
    with pytest.raises(RuntimeError, match="already issued"):
        store.issue(
            message=first_voice.payload,
            envelope=first_voice.envelope,
            preview=preview(),
        )
    second_voice = app_gateway.process_update(voice_update(update_id=3))
    assert isinstance(second_voice.payload, VoiceMessage)
    assert second_voice.envelope is not None
    with pytest.raises(RuntimeError, match="retention capacity"):
        store.issue(
            message=second_voice.payload,
            envelope=second_voice.envelope,
            preview=preview("Вторая локальная команда"),
        )

    old_replay = store.confirm(
        callback=first_callback.payload, envelope=first_callback.envelope
    )
    assert old_replay.status is VoiceConfirmationStatus.ALREADY_USED
    assert len(store._tombstones) == 1


def test_active_capacity_is_tenant_scoped() -> None:
    clock = Clock()
    tokens = iter(("A" * 43, "B" * 43))
    store = InMemoryVoiceConfirmationStore(
        clock=clock,
        token_factory=lambda: next(tokens),
        max_entries=2,
        max_active_entries_per_tenant=1,
        max_confirmed_entries=4,
        max_confirmed_entries_per_tenant=2,
    )
    bindings = {
        (USER_A, CHAT_A): actor_binding(),
        (USER_B, CHAT_B): actor_binding(
            tenant="tenant-b", identity="telegram:owner-b", auth_ref=AUTH_B
        ),
    }
    app_gateway = gateway(store, clock, bindings=bindings)
    first = app_gateway.process_update(voice_update())
    assert isinstance(first.payload, VoiceMessage) and first.envelope is not None
    store.issue(message=first.payload, envelope=first.envelope, preview=preview())

    second_a = app_gateway.process_update(voice_update(update_id=2))
    assert isinstance(second_a.payload, VoiceMessage) and second_a.envelope is not None
    with pytest.raises(RuntimeError, match="tenant voice confirmation capacity"):
        store.issue(
            message=second_a.payload,
            envelope=second_a.envelope,
            preview=preview("Вторая команда tenant A"),
        )

    first_b = app_gateway.process_update(
        voice_update(update_id=3, user_id=USER_B, chat_id=CHAT_B)
    )
    assert isinstance(first_b.payload, VoiceMessage) and first_b.envelope is not None
    challenge_b = store.issue(
        message=first_b.payload,
        envelope=first_b.envelope,
        preview=preview("Первая команда tenant B"),
    )
    assert challenge_b.callback_token.get_secret_value() == "B" * 43
    assert len(store._entries) == 2

def test_injected_failures_have_no_raw_exception_chain() -> None:
    leaked = "secret token C:\\private\\voice.ogg"

    def bad_clock() -> datetime:
        raise RuntimeError(leaked)

    clock = Clock()
    ingress = gateway(InMemoryCallbackTokenStore({}), clock).process_update(
        voice_update()
    )
    assert isinstance(ingress.payload, VoiceMessage) and ingress.envelope is not None
    store = InMemoryVoiceConfirmationStore(clock=bad_clock, token_factory=lambda: TOKEN)
    with pytest.raises(ValueError) as clock_error:
        store.issue(message=ingress.payload, envelope=ingress.envelope, preview=preview())
    assert clock_error.value.__context__ is None
    assert leaked not in str(clock_error.value)

    def bad_token() -> str:
        raise RuntimeError(leaked)

    store = InMemoryVoiceConfirmationStore(clock=clock, token_factory=bad_token)
    with pytest.raises(RuntimeError) as token_error:
        store.issue(message=ingress.payload, envelope=ingress.envelope, preview=preview())
    assert token_error.value.__context__ is None
    assert leaked not in str(token_error.value)

def test_models_are_frozen_strict_and_challenge_masks_capability() -> None:
    clock = Clock()
    store = InMemoryVoiceConfirmationStore(clock=clock, token_factory=lambda: TOKEN)
    _, challenge = issue(store, clock)

    assert challenge.model_dump_json().count("**********") == 1
    assert TOKEN not in challenge.model_dump_json()
    with pytest.raises(ValidationError):
        challenge.expires_at = BASE_TIME  # type: ignore[misc]
    with pytest.raises(ValidationError):
        type(challenge).model_validate({**challenge.model_dump(), "extra": "no"})


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_entries": True},
        {"max_entries": 0},
        {"max_entries": 100_001},
        {"confirmed_retention_seconds": False},
        {"confirmed_retention_seconds": 0},
        {"confirmed_retention_seconds": 86_401},
        {"max_active_entries_per_tenant": 0},
        {"max_entries": 1, "max_active_entries_per_tenant": 2},
        {"max_confirmed_entries": True},
        {"max_confirmed_entries": 0},
        {"max_confirmed_entries_per_tenant": 0},
        {"max_confirmed_entries": 2, "max_confirmed_entries_per_tenant": 3},
    ],
)
def test_store_limits_are_strict(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        InMemoryVoiceConfirmationStore(**kwargs)
