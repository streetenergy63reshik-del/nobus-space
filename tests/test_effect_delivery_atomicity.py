from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from src.application.durable_telegram_state import (
    DurableTelegramStateError,
)
from src.contracts.models import canonical_json_digest
from tests.test_durable_telegram_state import _store


def _capability_payload(token: str, *, state: str) -> dict[str, object]:
    effect_payload = {"safe": True}
    return {
        "token": token,
        "kind": "artifact",
        "tenant_id": "owner",
        "user_id": 7,
        "chat_id": 7,
        "payload": effect_payload,
        "effect_digest": canonical_json_digest(effect_payload),
        "state": state,
        "result": {"message": "Готово.", "filename": None},
    }


def _token_digest(token: str) -> str:
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def _effect_task_id(tenant_id: str, token: str) -> UUID:
    return UUID(
        bytes=hashlib.sha256(f"{tenant_id}:{token}".encode()).digest()[:16],
        version=4,
    )


def test_delivered_effect_job_and_capability_are_acked_atomically(
    tmp_path,
) -> None:
    now = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
    store = _store(tmp_path, clock=lambda: now)
    token = "safe-capability-token"
    store.put_capability(
        kind="action",
        token_digest=_token_digest(token),
        tenant_id="owner",
        payload=_capability_payload(token, state="delivered"),
        expires_at=now + timedelta(hours=1),
    )
    job = store.enqueue(
        kind="effect",
        tenant_id="owner",
        task_id=_effect_task_id("owner", token),
        binding_digest=canonical_json_digest({"capability_token": token}),
        payload={"capability_token": token},
    )
    lease_owner = uuid4()
    leased = store.claim(lease_owner=lease_owner)
    assert leased is not None and leased.job_id == job.job_id

    store.ack_effect_delivery(
        leased,
        lease_owner=lease_owner,
        capability_token=token,
        tenant_id="owner",
        user_id=7,
        chat_id=7,
    )

    assert store.queue_counts() == (0, 0)
    assert (
        store.read_capability(
            kind="action",
            token_digest=_token_digest(token),
            tenant_id="owner",
        )
        is None
    )



def test_effect_ack_rejects_capability_from_another_job(tmp_path) -> None:
    now = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
    store = _store(tmp_path, clock=lambda: now)
    token_a = "capability-token-a"
    token_b = "capability-token-b"
    for token in (token_a, token_b):
        store.put_capability(
            kind="action",
            token_digest=_token_digest(token),
            tenant_id="owner",
            payload=_capability_payload(token, state="delivered"),
            expires_at=now + timedelta(hours=1),
        )
    payload = {"capability_token": token_a}
    store.enqueue(
        kind="effect",
        tenant_id="owner",
        task_id=_effect_task_id("owner", token_a),
        binding_digest=canonical_json_digest(payload),
        payload=payload,
    )
    lease_owner = uuid4()
    leased = store.claim(lease_owner=lease_owner)
    assert leased is not None

    with pytest.raises(
        DurableTelegramStateError,
        match="runtime_effect_job_binding_invalid",
    ):
        store.ack_effect_delivery(
            leased,
            lease_owner=lease_owner,
            capability_token=token_b,
            tenant_id="owner",
            user_id=7,
            chat_id=7,
        )

    assert store.queue_counts() == (1, 0)
    for token in (token_a, token_b):
        assert store.read_capability(
            kind="action",
            token_digest=_token_digest(token),
            tenant_id="owner",
        ) is not None

def test_undelivered_capability_leaves_job_and_capability_intact(
    tmp_path,
) -> None:
    now = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
    store = _store(tmp_path, clock=lambda: now)
    token = "pending-capability-token"
    store.put_capability(
        kind="action",
        token_digest=_token_digest(token),
        tenant_id="owner",
        payload=_capability_payload(token, state="completed"),
        expires_at=now + timedelta(hours=1),
    )
    store.enqueue(
        kind="effect",
        tenant_id="owner",
        task_id=_effect_task_id("owner", token),
        binding_digest=canonical_json_digest({"capability_token": token}),
        payload={"capability_token": token},
    )
    lease_owner = uuid4()
    leased = store.claim(lease_owner=lease_owner)
    assert leased is not None

    with pytest.raises(
        DurableTelegramStateError,
        match="runtime_effect_delivery_invalid",
    ):
        store.ack_effect_delivery(
            leased,
            lease_owner=lease_owner,
            capability_token=token,
            tenant_id="owner",
            user_id=7,
            chat_id=7,
        )

    assert store.queue_counts() == (1, 0)
    assert store.read_capability(
        kind="action",
        token_digest=_token_digest(token),
        tenant_id="owner",
    ) is not None


def test_delivery_phase_has_finite_persisted_retry_budget(tmp_path) -> None:
    clock = [datetime(2026, 7, 24, 12, 0, tzinfo=UTC)]
    store = _store(tmp_path, clock=lambda: clock[0])
    store.enqueue(
        kind="effect",
        tenant_id="owner",
        task_id=uuid4(),
        binding_digest=canonical_json_digest({"effect": "delivery"}),
        payload={"capability_token": "safe-token"},
    )
    owner = uuid4()
    leased = store.claim(lease_owner=owner)
    assert leased is not None
    store.retry_effect_delivery(
        leased,
        lease_owner=owner,
        delay_seconds=30,
    )
    clock[0] += timedelta(seconds=31)
    leased = store.claim(lease_owner=owner)
    assert leased is not None and leased.attempt_count == 1
    for expected_attempt in (2, 3):
        store.retry_effect_delivery(
            leased,
            lease_owner=owner,
            delay_seconds=30,
        )
        clock[0] += timedelta(seconds=31)
        leased = store.claim(lease_owner=owner)
        assert leased is not None
        assert leased.attempt_count == expected_attempt
    store.retry_effect_delivery(
        leased,
        lease_owner=owner,
        delay_seconds=30,
    )
    clock[0] += timedelta(seconds=31)

    assert store.claim(lease_owner=uuid4()) is None
    assert store.dead_letter_count() == 1


def test_second_exhausted_execution_recovery_is_dead_lettered(
    tmp_path,
) -> None:
    clock = [datetime(2026, 7, 24, 12, 0, tzinfo=UTC)]
    store = _store(tmp_path, clock=lambda: clock[0])
    store.enqueue(
        kind="effect",
        tenant_id="owner",
        task_id=uuid4(),
        binding_digest=canonical_json_digest({"effect": "execution"}),
        payload={"capability_token": "safe-token"},
    )
    owner = uuid4()
    for _ in range(2):
        leased = store.claim(lease_owner=owner, lease_seconds=30)
        assert leased is not None
        store.release(leased, lease_owner=owner)
    third = store.claim(lease_owner=owner, lease_seconds=30)
    assert third is not None and third.attempt_count == 3
    clock[0] += timedelta(seconds=31)

    for _ in range(2):
        recovered = store.claim(lease_owner=owner, lease_seconds=30)
        assert recovered is not None
        store.release(recovered, lease_owner=owner)
    recovered_third = store.claim(lease_owner=owner, lease_seconds=30)
    assert recovered_third is not None
    assert recovered_third.attempt_count == 3
    clock[0] += timedelta(seconds=31)

    assert store.claim(lease_owner=uuid4()) is None
    assert store.dead_letter_count() == 1
