from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from src.application.durable_telegram_state import (
    DurableTelegramStateError,
    SQLiteTelegramState,
)
from src.contracts.models import canonical_json_digest
from src.security.dpapi import protect_current_user, unprotect_current_user


def _encode(value):
    return json.dumps(
        value, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()


def _decode(value):
    return json.loads(value)


def _store(tmp_path, *, clock=lambda: datetime.now(UTC), max_jobs=40):
    return SQLiteTelegramState(
        tmp_path / "runtime.sqlite3",
        encode=_encode,
        decode=_decode,
        clock=clock,
        max_jobs=max_jobs,
    )


def test_chunked_dpapi_roundtrip_supports_large_effect_payload():
    from src.application.durable_telegram_state import DpapiJsonCodec

    value = {"content": "x" * (3 * 1024 * 1024)}
    codec = DpapiJsonCodec()
    protected = codec.encode(value)
    assert protected.startswith(b"NBDP1")
    assert codec.decode(protected) == value


def test_queue_survives_reopen_and_uses_lease_cas(tmp_path):
    task_id = uuid4()
    binding = canonical_json_digest({"task": str(task_id)})
    store = _store(tmp_path)
    inserted = store.enqueue(
        kind="draft",
        tenant_id="owner",
        task_id=task_id,
        binding_digest=binding,
        payload={"instruction": "safe"},
    )

    reopened = _store(tmp_path)
    owner = uuid4()
    leased = reopened.claim(lease_owner=owner, lease_seconds=30)

    assert leased is not None
    assert leased.job_id == inserted.job_id
    assert leased.payload == {"instruction": "safe"}
    assert reopened.queue_counts() == (1, 0)
    with pytest.raises(DurableTelegramStateError, match="runtime_job_lease_lost"):
        reopened.ack(leased, lease_owner=uuid4())
    reopened.ack(leased, lease_owner=owner)
    assert reopened.queue_counts() == (0, 0)


def test_expired_lease_is_reclaimed_without_aba(tmp_path):
    now = datetime(2026, 7, 24, tzinfo=UTC)
    current = [now]
    store = _store(tmp_path, clock=lambda: current[0])
    task_id = uuid4()
    store.enqueue(
        kind="draft",
        tenant_id="owner",
        task_id=task_id,
        binding_digest=canonical_json_digest({"task": str(task_id)}),
        payload={"instruction": "safe"},
    )
    first_owner = uuid4()
    first = store.claim(lease_owner=first_owner, lease_seconds=5)
    current[0] += timedelta(seconds=6)
    second_owner = uuid4()
    second = store.claim(lease_owner=second_owner, lease_seconds=5)

    assert first is not None and second is not None
    assert first.job_id == second.job_id
    assert first.lease_id != second.lease_id
    with pytest.raises(DurableTelegramStateError, match="runtime_job_lease_lost"):
        store.ack(first, lease_owner=first_owner)
    store.ack(second, lease_owner=second_owner)


def test_expired_lease_cannot_release_or_fail_before_reclaim(tmp_path):
    now = datetime(2026, 7, 24, tzinfo=UTC)
    current = [now]
    store = _store(tmp_path, clock=lambda: current[0])
    task_id = uuid4()
    store.enqueue(
        kind="draft",
        tenant_id="owner",
        task_id=task_id,
        binding_digest=canonical_json_digest({"task": str(task_id)}),
        payload={"instruction": "safe"},
    )
    owner = uuid4()
    stale = store.claim(lease_owner=owner, lease_seconds=5)
    assert stale is not None
    current[0] += timedelta(seconds=6)

    with pytest.raises(DurableTelegramStateError, match="runtime_job_lease_lost"):
        store.release(stale, lease_owner=owner)
    with pytest.raises(DurableTelegramStateError, match="runtime_job_lease_lost"):
        store.fail(
            stale,
            lease_owner=owner,
            failure_code="stale_worker",
        )

    reclaimed = store.claim(lease_owner=uuid4(), lease_seconds=5)
    assert reclaimed is not None
    assert reclaimed.job_id == stale.job_id
    assert reclaimed.attempt_count == 2
    assert store.dead_letter_count() == 0


def test_expired_leases_dead_letter_after_three_claims(tmp_path):
    now = datetime(2026, 7, 24, tzinfo=UTC)
    current = [now]
    store = _store(tmp_path, clock=lambda: current[0])
    task_id = uuid4()
    store.enqueue(
        kind="draft",
        tenant_id="owner",
        task_id=task_id,
        binding_digest=canonical_json_digest({"task": str(task_id)}),
        payload={"instruction": "safe"},
    )

    attempts = []
    for _ in range(3):
        job = store.claim(lease_owner=uuid4(), lease_seconds=5)
        assert job is not None
        attempts.append(job.attempt_count)
        current[0] += timedelta(seconds=6)

    assert attempts == [1, 2, 3]
    assert store.claim(lease_owner=uuid4(), lease_seconds=5) is None
    assert store.dead_letter_count() == 1


def test_queue_is_bounded_and_idempotent(tmp_path):
    store = _store(tmp_path, max_jobs=1)
    first_id = uuid4()
    binding = canonical_json_digest({"task": str(first_id)})
    first = store.enqueue(
        kind="draft",
        tenant_id="owner",
        task_id=first_id,
        binding_digest=binding,
        payload={"instruction": "same"},
    )
    duplicate = store.enqueue(
        kind="draft",
        tenant_id="owner",
        task_id=first_id,
        binding_digest=binding,
        payload={"instruction": "same"},
    )
    assert duplicate.job_id == first.job_id

    second_id = uuid4()
    with pytest.raises(DurableTelegramStateError, match="runtime_queue_full"):
        store.enqueue(
            kind="draft",
            tenant_id="owner",
            task_id=second_id,
            binding_digest=canonical_json_digest({"task": str(second_id)}),
            payload={"instruction": "second"},
        )


def test_capability_is_encrypted_boundary_with_expiry_and_tenant_scope(tmp_path):
    now = datetime(2026, 7, 24, tzinfo=UTC)
    current = [now]
    store = _store(tmp_path, clock=lambda: current[0])
    token = canonical_json_digest({"token": "one"})
    store.put_capability(
        kind="task",
        token_digest=token,
        tenant_id="owner",
        payload={"instruction": "private"},
        expires_at=now + timedelta(minutes=5),
    )

    assert store.read_capability(
        kind="task", token_digest=token, tenant_id="other"
    ) is None
    assert store.read_capability(
        kind="task", token_digest=token, tenant_id="owner"
    ) == {"instruction": "private"}
    current[0] += timedelta(minutes=6)
    assert store.read_capability(
        kind="task", token_digest=token, tenant_id="owner"
    ) is None


def test_progress_reference_is_replaced_and_popped(tmp_path):
    store = _store(tmp_path)
    task_id = uuid4()
    store.save_progress(
        tenant_id="owner", task_id=task_id, chat_id=10, message_id=1
    )
    store.save_progress(
        tenant_id="owner", task_id=task_id, chat_id=10, message_id=2
    )
    ref = store.pop_progress(tenant_id="owner", task_id=task_id)
    assert ref is not None and ref.message_id == 2
    assert store.pop_progress(tenant_id="owner", task_id=task_id) is None


def test_backup_is_consistent_and_never_overwrites(tmp_path):
    store = _store(tmp_path)
    backup = store.backup(tmp_path / "backup.sqlite3")
    assert backup.is_file()
    assert SQLiteTelegramState(
        backup, encode=_encode, decode=_decode
    ).quick_check()
    with pytest.raises(ValueError, match="must be new"):
        store.backup(backup)


@pytest.mark.skipif(__import__("os").name != "nt", reason="Windows DPAPI only")
def test_dpapi_roundtrip_and_wrong_entropy_fail_closed():
    protected = protect_current_user(b"private", entropy=b"nobus-test-entropy")
    assert protected != b"private"
    assert (
        unprotect_current_user(protected, entropy=b"nobus-test-entropy")
        == b"private"
    )
    with pytest.raises(Exception):
        unprotect_current_user(protected, entropy=b"nobus-other-entropy")


def test_completed_effect_delivery_can_be_requeued_after_attempt_limit(tmp_path):
    store = _store(tmp_path)
    task_id = uuid4()
    store.enqueue(
        kind="effect",
        tenant_id="owner",
        task_id=task_id,
        binding_digest=canonical_json_digest({"effect": str(task_id)}),
        payload={"capability_token": "safe-token"},
    )
    lease_owner = uuid4()
    first = store.claim(lease_owner=lease_owner)
    assert first is not None
    store.release(first, lease_owner=lease_owner)
    second = store.claim(lease_owner=lease_owner)
    assert second is not None
    store.release(second, lease_owner=lease_owner)
    exhausted = store.claim(lease_owner=lease_owner)
    assert exhausted is not None and exhausted.attempt_count == 3

    store.retry_effect_delivery(exhausted, lease_owner=lease_owner)

    assert store.queue_counts() == (0, 1)
    replay = store.claim(lease_owner=lease_owner)
    assert replay is not None
    assert replay.job_id == exhausted.job_id
    assert replay.attempt_count == 1

    draft_id = uuid4()
    draft = store.enqueue(
        kind="draft",
        tenant_id="owner",
        task_id=draft_id,
        binding_digest=canonical_json_digest({"draft": str(draft_id)}),
        payload={"instruction": "safe"},
    )
    assert draft.kind == "draft"
