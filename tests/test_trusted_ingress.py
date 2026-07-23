"""Adversarial tests for the local trusted Telegram ingress contract."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Callable
from uuid import UUID

import pytest
from pydantic import ValidationError

import src.transport.telegram as telegram_transport
from src.contracts import IngressKind, TaskContract, TrustedIngressEnvelope
from src.core import (
    DuplicateIdempotencyKeyError,
    EventBindingError,
    InMemoryPolicyStore,
)
from src.transport.telegram import (
    ActorBinding,
    InMemoryCallbackTokenStore,
    InMemoryUpdateIdStore,
    IngressStatus,
    TelegramGateway,
    TextMessage,
    TrustedIngressResult,
    VoiceMessage,
)


USER_ID = 111
CHAT_ID = 222
INGRESS_ID = UUID("11111111-2222-4333-8444-555555555555")
RECEIVED_AT = datetime(2026, 7, 21, 1, 2, 3, tzinfo=UTC)
AUTH_CONTEXT_REF = "sha256:" + "a" * 64
TASK_ID = UUID("aaaaaaaa-1111-4111-8111-111111111111")


def binding(**overrides: str) -> ActorBinding:
    data = {
        "tenant_id": "tenant-a",
        "actor_identity": "telegram:owner",
        "role": "owner",
        "auth_context_ref": AUTH_CONTEXT_REF,
    }
    data.update(overrides)
    return ActorBinding(**data)


def gateway(
    *,
    actor_binding: ActorBinding | None = None,
    ingress_id: UUID = INGRESS_ID,
    received_at: datetime = RECEIVED_AT,
) -> TelegramGateway:
    return TelegramGateway(
        actor_bindings={(USER_ID, CHAT_ID): actor_binding or binding()},
        update_id_store=InMemoryUpdateIdStore(),
        callback_token_store=InMemoryCallbackTokenStore({}),
        ingress_id_factory=lambda: ingress_id,
        clock=lambda: received_at,
    )


def text_update(text: str = "hello") -> dict[str, object]:
    return {
        "update_id": 7,
        "message": {
            "message_id": 9,
            "from": {"id": USER_ID},
            "chat": {"id": CHAT_ID},
            "text": text,
        },
    }


def trusted(text: str = "hello") -> TrustedIngressEnvelope:
    result = gateway().process_update(text_update(text))
    assert result.envelope is not None
    return result.envelope


def telegram_contract(
    envelope: TrustedIngressEnvelope, **overrides: object
) -> TaskContract:
    data: dict[str, object] = {
        "task_id": TASK_ID,
        "idempotency_key": envelope.idempotency_key,
        "ingress_digest": envelope.envelope_revision,
        "tenant_id": envelope.tenant_id,
        "source": "telegram",
        "instruction": "hello",
        "allowed_paths": ("workspace",),
        "permissions": ("repo.read",),
        "risk": "low",
        "acceptance_criteria": ("Return one result.",),
        "timeout_seconds": 60,
        "quality_profile": "local-fake@1",
    }
    data.update(overrides)
    return TaskContract(**data)


def test_golden_envelope_digest_and_json_roundtrip() -> None:
    envelope = trusted()

    assert envelope.schema_version == "1"
    assert envelope.kind == IngressKind.TEXT
    assert envelope.actor_identity == "telegram:owner"
    assert envelope.external_message_id == (
        "update:7:user:111:chat:222:message:9"
    )
    assert envelope.auth_context_ref == AUTH_CONTEXT_REF
    assert envelope.content_ref == (
        "sha256:cbbbdcd27692344de5dbab3abcaba413fb0f45307267de7081401576df1cb176"
    )
    assert envelope.idempotency_key == (
        "sha256:5dcbd0e1a9f1c7572b29aac57ccc13aeb11c00dc656d97886afd635694a7f164"
    )
    assert envelope.envelope_revision == (
        "sha256:7a916b59ff2eb3021b2be9be2fad3bab78c3d5d7aa4603e786be2f1fc795944b"
    )
    assert (
        TrustedIngressEnvelope.model_validate_json(envelope.model_dump_json())
        == envelope
    )
    assert "hello" not in envelope.model_dump_json()


def test_envelope_rejects_unknown_field_naive_time_and_forged_revision() -> None:
    envelope = trusted()
    dumped = envelope.model_dump()
    with pytest.raises(ValidationError):
        TrustedIngressEnvelope.model_validate({**dumped, "extra": True})
    with pytest.raises(ValidationError, match="timezone-aware"):
        TrustedIngressEnvelope.model_validate(
            {**dumped, "received_at": RECEIVED_AT.replace(tzinfo=None)}
        )
    with pytest.raises(ValidationError, match="does not match"):
        TrustedIngressEnvelope.model_validate(
            {**dumped, "tenant_id": "tenant-b"}
        )


def test_public_boundary_cannot_mint_from_naked_normalized_payload() -> None:
    transport = gateway()
    result = transport.process_update(text_update())
    assert isinstance(result.payload, TextMessage)
    assert not hasattr(transport, "create_trusted_envelope")
    assert not hasattr(telegram_transport, "create_trusted_ingress")
    with pytest.raises(ValidationError, match="requires payload and envelope"):
        TrustedIngressResult(
            status=IngressStatus.ACCEPTED,
            update_id=result.update_id,
            payload=result.payload,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("text", "forged"),
        ("update_id", 8),
        ("user_id", 112),
        ("chat_id", 223),
        ("message_id", 10),
        ("tenant_id", "tenant-b"),
        ("actor_identity", "telegram:other"),
        ("actor_role", "operator"),
        ("auth_context_ref", "sha256:" + "b" * 64),
    ],
)
def test_result_rejects_mutated_payload_with_old_envelope(
    field: str, value: object
) -> None:
    result = gateway().process_update(text_update())
    assert isinstance(result.payload, TextMessage)

    with pytest.raises(ValidationError, match="binding mismatch"):
        TrustedIngressResult(
            status=IngressStatus.ACCEPTED,
            update_id=result.update_id,
            payload=result.payload.model_copy(update={field: value}),
            envelope=result.envelope,
        )


def _callback_update() -> dict[str, object]:
    return {
        "update_id": 8,
        "callback_query": {
            "id": "query-8",
            "from": {"id": USER_ID},
            "message": {"message_id": 108, "chat": {"id": CHAT_ID}},
            "data": "AbcdEFgh_12345678",
        },
    }


def _fail_once(first: object, second: object) -> Callable[[], object]:
    values = iter((first, second))

    def factory() -> object:
        value = next(values)
        if isinstance(value, Exception):
            raise value
        return value

    return factory


@pytest.mark.parametrize(
    ("ingress_values", "clock_values"),
    [
        ((RuntimeError("uuid failed"), INGRESS_ID), (RECEIVED_AT, RECEIVED_AT)),
        (("not-a-uuid", INGRESS_ID), (RECEIVED_AT, RECEIVED_AT)),
        ((INGRESS_ID, INGRESS_ID), (RuntimeError("clock failed"), RECEIVED_AT)),
        ((INGRESS_ID, INGRESS_ID), (RECEIVED_AT.replace(tzinfo=None), RECEIVED_AT)),
    ],
)
def test_server_metadata_failure_does_not_consume_update_or_callback_token(
    ingress_values: tuple[object, object],
    clock_values: tuple[object, object],
) -> None:
    token = "AbcdEFgh_12345678"
    transport = TelegramGateway(
        actor_bindings={(USER_ID, CHAT_ID): binding()},
        update_id_store=InMemoryUpdateIdStore(),
        callback_token_store=InMemoryCallbackTokenStore(
            {token: (USER_ID, CHAT_ID)}
        ),
        ingress_id_factory=_fail_once(*ingress_values),  # type: ignore[arg-type]
        clock=_fail_once(*clock_values),  # type: ignore[arg-type]
    )

    first = transport.process_update(_callback_update())
    second = transport.process_update(_callback_update())

    assert first.status == IngressStatus.REJECTED
    assert first.update_id is None
    assert first.reason == "trusted ingress unavailable"
    assert second.status == IngressStatus.ACCEPTED


def test_callback_content_is_bound_to_exact_payload() -> None:
    token = "AbcdEFgh_12345678"
    result = TelegramGateway(
        actor_bindings={(USER_ID, CHAT_ID): binding()},
        update_id_store=InMemoryUpdateIdStore(),
        callback_token_store=InMemoryCallbackTokenStore(
            {token: (USER_ID, CHAT_ID)}
        ),
        ingress_id_factory=lambda: INGRESS_ID,
        clock=lambda: RECEIVED_AT,
    ).process_update(_callback_update())
    assert result.payload is not None

    with pytest.raises(ValidationError, match="binding mismatch"):
        TrustedIngressResult(
            status=IngressStatus.ACCEPTED,
            update_id=result.update_id,
            payload=result.payload.model_copy(
                update={"callback_token": "ZbcdEFgh_12345678"}
            ),
            envelope=result.envelope,
        )


def test_voice_content_is_bound_to_exact_payload() -> None:
    result = gateway().process_update(
        {
            "update_id": 12,
            "message": {
                "message_id": 13,
                "from": {"id": USER_ID},
                "chat": {"id": CHAT_ID},
                "voice": {"file_id": "voice-13", "duration": 10},
            },
        }
    )
    assert isinstance(result.payload, VoiceMessage)

    with pytest.raises(ValidationError, match="binding mismatch"):
        TrustedIngressResult(
            status=IngressStatus.ACCEPTED,
            update_id=result.update_id,
            payload=result.payload.model_copy(update={"file_id": "voice-forged"}),
            envelope=result.envelope,
        )


def test_raw_identity_injection_cannot_override_server_binding() -> None:
    update = text_update()
    message = update["message"]
    assert isinstance(message, dict)
    message.update(
        tenant_id="tenant-b",
        actor_identity="telegram:attacker",
        actor_role="admin",
        auth_context_ref="sha256:" + "b" * 64,
        ingress_id="attacker-selected",
        received_at="1999-01-01T00:00:00Z",
    )

    result = gateway().process_update(update)

    assert result.envelope is not None
    assert result.envelope.tenant_id == "tenant-a"
    assert result.envelope.actor_identity == "telegram:owner"
    assert result.envelope.auth_context_ref == AUTH_CONTEXT_REF
    assert result.envelope.ingress_id == INGRESS_ID
    assert result.envelope.received_at == RECEIVED_AT


@pytest.mark.parametrize(
    "overrides",
    [
        {"tenant_id": "tenant-b"},
        {"idempotency_key": "sha256:" + "b" * 64},
        {"ingress_digest": "sha256:" + "b" * 64},
    ],
)
def test_policy_store_rejects_foreign_telegram_binding_without_mutation(
    overrides: dict[str, str],
) -> None:
    envelope = trusted()
    store = InMemoryPolicyStore()

    with pytest.raises(EventBindingError, match="binding mismatch"):
        store.register_contract(telegram_contract(envelope, **overrides), envelope)

    store.register_contract(telegram_contract(envelope), envelope)


def test_policy_store_requires_envelope_for_telegram_and_rejects_reuse() -> None:
    envelope = trusted()
    contract = telegram_contract(envelope)
    store = InMemoryPolicyStore()

    with pytest.raises(TypeError):
        store.register_contract(contract)
    store.register_contract(contract, envelope)
    with pytest.raises(DuplicateIdempotencyKeyError):
        store.register_contract(
            telegram_contract(
                envelope,
                task_id=UUID("bbbbbbbb-2222-4222-8222-222222222222"),
            ),
            envelope,
        )


def test_policy_store_rejects_foreign_envelope_without_mutation() -> None:
    expected = trusted("hello")
    foreign = trusted("different")
    store = InMemoryPolicyStore()

    with pytest.raises(EventBindingError, match="binding mismatch"):
        store.register_contract(telegram_contract(expected), foreign)

    store.register_contract(telegram_contract(expected), expected)


def test_policy_store_claims_telegram_contract_atomically() -> None:
    envelope = trusted()
    store = InMemoryPolicyStore()
    contracts = (
        telegram_contract(envelope),
        telegram_contract(
            envelope,
            task_id=UUID("bbbbbbbb-2222-4222-8222-222222222222"),
        ),
    )

    def register(contract: TaskContract) -> bool:
        try:
            store.register_contract(contract, envelope)
        except DuplicateIdempotencyKeyError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(register, contracts)) == [False, True]


def test_idempotency_is_stable_while_server_revision_changes() -> None:
    first = gateway().process_update(text_update()).envelope
    second = gateway(
        ingress_id=UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"),
        received_at=datetime(2026, 7, 21, 1, 2, 4, tzinfo=UTC),
    ).process_update(text_update()).envelope

    assert first is not None and second is not None
    assert first.idempotency_key == second.idempotency_key
    assert first.content_ref == second.content_ref
    assert first.envelope_revision != second.envelope_revision


def test_idempotency_is_bound_to_update_message_actor_and_tenant() -> None:
    base = gateway().process_update(text_update()).envelope
    assert base is not None

    for update, actor_binding in (
        (text_update(), binding(actor_identity="telegram:operator")),
        (text_update(), binding(tenant_id="tenant-b")),
        ({**text_update(), "update_id": 8}, binding()),
        (
            {
                **text_update(),
                "message": {**text_update()["message"], "message_id": 10},
            },
            binding(),
        ),
    ):
        changed = gateway(actor_binding=actor_binding).process_update(update).envelope
        assert changed is not None
        assert changed.idempotency_key != base.idempotency_key


@pytest.mark.parametrize("field", ["actor_identity", "tenant_id", "auth_context_ref"])
def test_actor_binding_rejects_empty_or_invalid_identity_fields(field: str) -> None:
    values = binding().model_dump()
    values[field] = " "
    with pytest.raises(ValidationError):
        ActorBinding.model_validate(values)


@pytest.mark.parametrize("field", ["actor_identity", "tenant_id", "actor_role"])
def test_normalized_payload_rejects_empty_identity_fields(field: str) -> None:
    transport = gateway()
    payload = transport.process_update(text_update()).payload
    assert isinstance(payload, TextMessage)

    with pytest.raises(ValidationError):
        TextMessage.model_validate({**payload.model_dump(), field: " "})
