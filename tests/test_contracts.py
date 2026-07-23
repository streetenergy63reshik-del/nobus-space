"""Contract and ordering tests for Gate 1."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from src.contracts import (
    IngressKind,
    IngressSource,
    TaskContract,
    TrustedIngressEnvelope,
    WorkerEvent,
    WorkerEventType,
)
from src.core import (
    canonical_json_digest,
    DuplicateIdempotencyKeyError,
    EventBindingError,
    EventSequenceError,
    InMemoryPolicyStore,
    task_contract_digest,
)


TASK_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_TASK_ID = UUID("22222222-2222-4222-8222-222222222222")
ATTEMPT_ID = UUID("33333333-3333-4333-8333-333333333333")
OTHER_ATTEMPT_ID = UUID("44444444-4444-4444-8444-444444444444")
INGRESS_ID = UUID("55555555-5555-4555-8555-555555555555")


def make_envelope(
    *,
    tenant_id: str = "tenant-a",
    idempotency_key: str = "tenant-a:audit:1",
    source: IngressSource = IngressSource.API,
) -> TrustedIngressEnvelope:
    data = {
        "ingress_id": INGRESS_ID,
        "tenant_id": tenant_id,
        "source": source,
        "actor_identity": "api:test-client",
        "external_message_id": "request:test-1",
        "idempotency_key": idempotency_key,
        "received_at": datetime(2026, 7, 21, tzinfo=UTC),
        "kind": IngressKind.SYSTEM_JOB,
        "content_ref": "sha256:" + "2" * 64,
        "auth_context_ref": "sha256:" + "3" * 64,
    }
    revision = canonical_json_digest(
        TrustedIngressEnvelope.model_construct(
            **data, envelope_revision="sha256:" + "0" * 64
        ).model_dump(mode="json", exclude={"envelope_revision"})
    )
    return TrustedIngressEnvelope(**data, envelope_revision=revision)


def make_contract(**overrides: object) -> TaskContract:
    data: dict[str, object] = {
        "task_id": TASK_ID,
        "idempotency_key": "tenant-a:audit:1",
        "tenant_id": "tenant-a",
        "source": "api",
        "instruction": "Audit the test snapshot.",
        "allowed_paths": ["workspace/./input", r"C:\repo\artifacts"],
        "permissions": ["read"],
        "risk": "low",
        "acceptance_criteria": ["Return evidence refs."],
        "timeout_seconds": 60,
        "quality_profile": "standard",
    }
    data.update(overrides)
    if "ingress_digest" not in overrides:
        data["ingress_digest"] = make_envelope(
            tenant_id=str(data["tenant_id"]),
            idempotency_key=str(data["idempotency_key"]),
            source=IngressSource(str(data["source"])),
        ).envelope_revision
    return TaskContract(**data)


def register_contract(store: InMemoryPolicyStore, contract: TaskContract) -> None:
    store.register_contract(
        contract,
        make_envelope(
            tenant_id=contract.tenant_id,
            idempotency_key=contract.idempotency_key,
            source=IngressSource(contract.source),
        ),
    )


def make_event(sequence: object, **overrides: object) -> WorkerEvent:
    data: dict[str, object] = {
        "event_id": uuid4(),
        "tenant_id": "tenant-a",
        "task_id": TASK_ID,
        "attempt_id": ATTEMPT_ID,
        "contract_digest": task_contract_digest(make_contract()),
        "worker_identity": "worker:codex",
        "sequence": sequence,
        "event_type": "progress",
        "emitted_at": datetime.now(UTC),
        "payload": {"stage": "running", "percent": 25},
    }
    data.update(overrides)
    return WorkerEvent(**data)  # type: ignore[arg-type]


def bound_store() -> InMemoryPolicyStore:
    store = InMemoryPolicyStore()
    contract = make_contract()
    register_contract(store, contract)
    store.bind_worker(
        TASK_ID,
        "tenant-a",
        ATTEMPT_ID,
        task_contract_digest(contract),
        "worker:codex",
    )
    return store


def test_valid_task_contract_normalizes_paths_and_has_stable_digest() -> None:
    contract = make_contract()

    assert contract.allowed_paths == ("workspace/input", r"C:\repo\artifacts")
    digest = task_contract_digest(contract)
    assert digest == task_contract_digest(make_contract())
    assert len(digest) == 71
    assert digest.startswith("sha256:")
    assert digest == digest.lower()


def test_canonical_json_digest_has_golden_wire_format() -> None:
    assert canonical_json_digest({"b": 1, "a": "ёж"}) == (
        "sha256:80f4dc5ece6e2f6110dc2623c0a5ec3fdf74a2dd35a25f43b694a9c4407d85b0"
    )


def test_missing_tenant_and_path_traversal_are_rejected() -> None:
    with pytest.raises(ValidationError, match="tenant_id must not be empty"):
        make_contract(tenant_id="  ")
    for path in ("../secret", "safe/../secret", r"safe\..\secret"):
        with pytest.raises(ValidationError, match="path traversal"):
            make_contract(allowed_paths=[path])


@pytest.mark.parametrize(
    "ingress_digest",
    [None, "", "a" * 64, "sha256:" + "A" * 64, "sha256:bad"],
)
def test_task_contract_requires_exact_ingress_digest(
    ingress_digest: object,
) -> None:
    with pytest.raises(ValidationError):
        make_contract(ingress_digest=ingress_digest)


@pytest.mark.parametrize("timeout", [0, 14_401, True, 1.0])
def test_timeout_requires_a_real_bounded_integer(timeout: object) -> None:
    with pytest.raises(ValidationError):
        make_contract(timeout_seconds=timeout)


def test_idempotency_is_scoped_to_tenant() -> None:
    store = InMemoryPolicyStore()
    register_contract(store, make_contract())
    with pytest.raises(DuplicateIdempotencyKeyError):
        register_contract(store, make_contract(task_id=OTHER_TASK_ID))

    register_contract(
        store, make_contract(task_id=OTHER_TASK_ID, tenant_id="tenant-b")
    )


def test_every_contract_requires_exact_ingress_without_partial_mutation() -> None:
    store = InMemoryPolicyStore()
    contract = make_contract()
    with pytest.raises(TypeError):
        store.register_contract(contract)
    with pytest.raises(EventBindingError, match="binding mismatch"):
        store.register_contract(
            contract,
            make_envelope(source=IngressSource.SCHEDULER),
        )

    register_contract(store, contract)


def test_task_id_cannot_be_rebound_to_another_tenant() -> None:
    store = InMemoryPolicyStore()
    register_contract(store, make_contract())
    with pytest.raises(EventBindingError, match="another tenant"):
        register_contract(
            store,
            make_contract(
                tenant_id="tenant-b",
                idempotency_key="tenant-b:audit:1",
            )
        )


def test_task_id_cannot_be_registered_again_with_another_idempotency_key() -> None:
    store = InMemoryPolicyStore()
    register_contract(store, make_contract())
    with pytest.raises(EventBindingError, match="already registered"):
        register_contract(
            store, make_contract(idempotency_key="tenant-a:audit:2")
        )


def test_worker_event_requires_registered_task_tenant_and_worker() -> None:
    store = bound_store()
    store.accept_event(make_event(1))

    with pytest.raises(EventBindingError, match="tenant/task/contract"):
        store.accept_event(make_event(2, tenant_id="tenant-b"))
    with pytest.raises(EventBindingError, match="attempt/worker"):
        store.accept_event(make_event(2, worker_identity="worker:fake"))
    with pytest.raises(EventBindingError, match="tenant/task/contract"):
        store.accept_event(make_event(2, task_id=OTHER_TASK_ID))
    with pytest.raises(EventBindingError, match="attempt/worker"):
        store.accept_event(make_event(2, attempt_id=OTHER_ATTEMPT_ID))
    with pytest.raises(EventBindingError, match="tenant/task/contract"):
        store.accept_event(make_event(2, contract_digest="sha256:" + "f" * 64))


def test_worker_event_sequence_must_strictly_increase() -> None:
    store = bound_store()
    store.accept_event(make_event(1))
    store.accept_event(make_event(2))
    for sequence in (2, 1):
        with pytest.raises(EventSequenceError):
            store.accept_event(make_event(sequence))


def test_worker_event_sequence_is_scoped_per_attempt() -> None:
    store = bound_store()
    contract_digest = task_contract_digest(make_contract())
    store.bind_worker(
        TASK_ID,
        "tenant-a",
        OTHER_ATTEMPT_ID,
        contract_digest,
        "worker:codex",
    )
    store.accept_event(make_event(1))
    store.accept_event(make_event(1, attempt_id=OTHER_ATTEMPT_ID))


def test_worker_event_id_replay_is_rejected() -> None:
    store = bound_store()
    event_id = uuid4()
    store.accept_event(make_event(1, event_id=event_id))
    with pytest.raises(EventSequenceError, match="event_id replay"):
        store.accept_event(make_event(2, event_id=event_id))
    store.accept_event(make_event(2))


@pytest.mark.parametrize("sequence", [True, 1.0])
def test_worker_event_sequence_requires_a_real_integer(sequence: object) -> None:
    with pytest.raises(ValidationError):
        make_event(sequence)


def test_worker_event_requires_closed_type_aware_time_and_exact_digest() -> None:
    with pytest.raises(ValidationError):
        make_event(1, event_type="log")
    with pytest.raises(ValidationError, match="timezone-aware"):
        make_event(1, emitted_at=datetime.now())
    for bad_digest in ("a" * 64, "sha256:" + "A" * 64, "sha256:bad"):
        with pytest.raises(ValidationError, match="sha256"):
            make_event(1, contract_digest=bad_digest)


@pytest.mark.parametrize(
    ("event_type", "payload"),
    [
        ("started", {"lease_ref": "lease/1"}),
        ("progress", {"stage": "tests", "percent": 50.5}),
        ("waiting_input", {"question_ref": "question/1"}),
        ("artifact_ready", {"artifact_refs": ["artifact/1"]}),
        (
            "result_ready",
            {
                "result_ref": "result/1",
                "result_revision": 1,
                "result_digest": "sha256:" + "a" * 64,
            },
        ),
        ("usage", {"provider": "local", "input_units": 10}),
        (
            "failed",
            {
                "error_code": "worker_failed",
                "safe_message": "Worker failed",
                "retryable": False,
            },
        ),
        ("cancelled", {"reason_code": "owner_cancelled"}),
    ],
)
def test_worker_event_accepts_each_closed_payload(
    event_type: str, payload: dict[str, object]
) -> None:
    event = make_event(1, event_type=event_type, payload=payload)
    assert event.event_type == WorkerEventType(event_type)


@pytest.mark.parametrize(
    ("event_type", "payload"),
    [
        ("started", {"lease_ref": "lease/1", "extra": True}),
        ("progress", {"stage": "tests", "percent": 101}),
        ("waiting_input", {}),
        ("artifact_ready", {"artifact_refs": []}),
        (
            "result_ready",
            {"result_ref": "result/1", "result_revision": True, "result_digest": "sha256:" + "a" * 64},
        ),
        ("usage", {"provider": "local"}),
        ("failed", {"error_code": "x", "safe_message": "x", "retryable": 1}),
        ("cancelled", {"reason_code": " "}),
    ],
)
def test_worker_event_rejects_wrong_payload_for_type(
    event_type: str, payload: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        make_event(1, event_type=event_type, payload=payload)


@pytest.mark.parametrize(
    "secret_key",
    [
        "tokenValue",
        "passwordText",
        "apiKeyData",
        "authHeader",
        "cookieJar",
        "nested-clientSecret-value",
    ],
)
def test_worker_event_rejects_adversarial_secret_keys(secret_key: str) -> None:
    with pytest.raises(ValidationError, match="secret fields"):
        make_event(1, payload={"nested": [{secret_key: "not-allowed"}]})


@pytest.mark.parametrize(
    "bad_value",
    [b"raw", datetime.now(UTC), float("nan"), float("inf"), ("tuple",)],
)
def test_worker_event_payload_is_strict_json(bad_value: object) -> None:
    with pytest.raises(ValidationError, match="JSON-compatible|NaN"):
        make_event(1, payload={"value": bad_value})


def test_mutated_worker_payload_is_revalidated_by_store() -> None:
    event = make_event(1)
    event.payload["tokenValue"] = "not-allowed"
    with pytest.raises(ValidationError, match="secret fields"):
        bound_store().accept_event(event)


def test_contract_collections_are_immutable() -> None:
    contract = make_contract()
    with pytest.raises(AttributeError):
        contract.allowed_paths.append("../secret")  # type: ignore[attr-defined]
