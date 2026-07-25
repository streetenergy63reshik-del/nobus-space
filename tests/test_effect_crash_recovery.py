from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from src.contracts.models import canonical_json_digest
from tests.test_durable_telegram_state import _store


def test_third_effect_lease_power_loss_recovers_instead_of_dead_letter(
    tmp_path,
) -> None:
    clock = [datetime(2026, 7, 24, 12, 0, tzinfo=UTC)]
    store = _store(tmp_path, clock=lambda: clock[0])
    task_id = uuid4()
    store.enqueue(
        kind="effect",
        tenant_id="owner",
        task_id=task_id,
        binding_digest=canonical_json_digest({"effect": str(task_id)}),
        payload={"capability_token": "safe-token"},
    )
    lease_owner = uuid4()
    first = store.claim(lease_owner=lease_owner, lease_seconds=30)
    assert first is not None
    store.release(first, lease_owner=lease_owner)
    second = store.claim(lease_owner=lease_owner, lease_seconds=30)
    assert second is not None
    store.release(second, lease_owner=lease_owner)
    third = store.claim(lease_owner=lease_owner, lease_seconds=30)
    assert third is not None and third.attempt_count == 3

    # Power loss: no release, no delayed-retry write.
    clock[0] += timedelta(seconds=31)
    recovered = store.claim(lease_owner=uuid4(), lease_seconds=30)

    assert recovered is not None
    assert recovered.job_id == third.job_id
    assert recovered.attempt_count == 1
    assert store.dead_letter_count() == 0
