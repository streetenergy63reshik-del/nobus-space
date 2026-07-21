"""Durability and adversarial checks for the local SQLite store."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from src.contracts import (
    HumanApprovalRecord,
    IngressKind,
    IngressSource,
    TaskContract,
    TrustedIngressEnvelope,
    VerificationBundle,
    VerificationBundleStatus,
    VerificationLevel,
    VerificationLevelStatus,
    WorkerEvent,
)
from src.contracts.models import canonical_json_digest
from src.core.policy import TrustedVerifierRegistry
from src.models.task import Task, TaskStatus
from src.orchestrator.state_manager import StateManager
from src.storage import (
    AuditEventConflictError,
    AuditEventOrderError,
    IngressClaimConflictError,
    SQLiteStore,
    SnapshotConflictError,
    StoreCorruptionError,
)


REGISTRY = TrustedVerifierRegistry(
    {
        1: {"verifier:l1"},
        2: {"verifier:l2"},
        3: {"verifier:l3"},
    }
)


def envelope(**overrides: object) -> TrustedIngressEnvelope:
    values: dict[str, object] = {
        "schema_version": "1",
        "ingress_id": uuid4(),
        "tenant_id": "tenant-a",
        "source": IngressSource.TELEGRAM,
        "actor_identity": "telegram:user:7",
        "external_message_id": "update:11",
        "idempotency_key": "idem-11",
        "received_at": datetime.now(UTC),
        "kind": IngressKind.TEXT,
        "content_ref": "sha256:" + "b" * 64,
        "auth_context_ref": "sha256:" + "c" * 64,
    }
    values.update(overrides)
    values["envelope_revision"] = canonical_json_digest(
        TrustedIngressEnvelope.model_construct(
            **values, envelope_revision="sha256:" + "0" * 64
        ).model_dump(mode="json", exclude={"envelope_revision"})
    )
    return TrustedIngressEnvelope.model_validate(values)


def contract_for(
    incoming: TrustedIngressEnvelope,
    *,
    task_id: UUID | None = None,
    instruction: str = "normalized private command",
    **overrides: object,
) -> TaskContract:
    values: dict[str, object] = {
        "task_id": task_id or uuid4(),
        "idempotency_key": incoming.idempotency_key,
        "ingress_digest": incoming.envelope_revision,
        "tenant_id": incoming.tenant_id,
        "source": incoming.source.value,
        "instruction": instruction,
        "allowed_paths": ("workspace",),
        "permissions": ("read",),
        "risk": "low",
        "acceptance_criteria": ("Return verified metadata.",),
        "timeout_seconds": 60,
        "quality_profile": "standard",
    }
    values.update(overrides)
    return TaskContract.model_validate(values)


def runtime_task(contract: TaskContract) -> Task:
    return asyncio.run(StateManager().create_from_contract(contract))


def bound_values(
    *, tenant_id: str = "tenant-a", task_id: UUID | None = None
) -> tuple[TrustedIngressEnvelope, TaskContract, Task]:
    incoming = envelope(tenant_id=tenant_id)
    contract = contract_for(incoming, task_id=task_id)
    return incoming, contract, runtime_task(contract)


def persist(store: SQLiteStore, *, tenant_id: str = "tenant-a") -> Task:
    incoming, contract, task = bound_values(tenant_id=tenant_id)
    created, snapshot = store.claim_ingress_with_task(incoming, contract, task)
    assert created is True
    assert snapshot.projection.task_id == task.id
    return task


def event(task: Task, attempt_id: UUID, sequence: int, **overrides: object) -> WorkerEvent:
    values: dict[str, object] = {
        "event_id": uuid4(),
        "tenant_id": task.tenant_id,
        "task_id": task.id,
        "attempt_id": attempt_id,
        "contract_digest": task.contract_digest,
        "worker_identity": "worker:local",
        "sequence": sequence,
        "event_type": "progress",
        "emitted_at": datetime.now(UTC),
        "payload": {"stage": f"stage-{sequence}"},
    }
    values.update(overrides)
    return WorkerEvent.model_validate(values)


def verification_bundle(
    task: Task, level_count: int, *, failed_level: int | None = None
) -> VerificationBundle:
    levels = tuple(
        VerificationLevel(
            status=(
                VerificationLevelStatus.FAILED
                if level == failed_level
                else VerificationLevelStatus.PASSED
            ),
            method=f"method-{level}",
            verifier_identity=f"verifier:l{level}",
            verified_at=datetime(2026, 7, 21, 1, level, tzinfo=UTC),
            evidence_refs=(f"evidence:l{level}",),
            evidence_digest=canonical_json_digest({"level": level}),
        )
        if level <= level_count
        else None
        for level in (1, 2, 3)
    )
    return VerificationBundle(
        tenant_id=task.tenant_id,
        task_id=task.id,
        contract_digest=task.contract_digest,
        result_revision=task.result_revision,
        result_digest=task.result_digest,
        executor_identity=task.agent_id,
        l1=levels[0],
        l2=levels[1],
        l3=levels[2],
        status=(
            VerificationBundleStatus.REJECTED
            if failed_level is not None
            else (
                VerificationBundleStatus.APPROVED
                if level_count == 3
                else VerificationBundleStatus.DRAFT
            )
        ),
    )


def persisted_draft(
    path: Path,
) -> tuple[SQLiteStore, StateManager, Task, int]:
    incoming = envelope()
    contract = contract_for(incoming)
    manager = StateManager(REGISTRY)
    task = asyncio.run(manager.create_from_contract(contract))
    store = SQLiteStore(path, verifier_registry=REGISTRY)
    store.claim_ingress_with_task(incoming, contract, task)
    parsing = asyncio.run(manager.update(task.id, status=TaskStatus.PARSING))
    assert parsing is not None
    store.save_task(parsing, expected_revision=1)
    draft = asyncio.run(
        manager.update(
            task.id,
            status=TaskStatus.DRAFT,
            agent_id="worker:local",
            result={
                "output_digest": canonical_json_digest({"output": "ok"}),
                "summary": "not stored",
            },
        )
    )
    assert draft is not None
    store.save_task(draft, expected_revision=2)
    return store, manager, draft, 3


def test_schema_init_is_idempotent_and_configures_safety_pragmas(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    SQLiteStore(path)
    SQLiteStore(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall() == [
            ("audit_events",),
            ("ingress_claims",),
            ("outbox_messages",),
            ("outbox_receipts",),
            ("task_snapshots",),
        ]


def test_atomic_claim_restart_replay_returns_original_projection(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    incoming, contract, task = bound_values()
    created, original = SQLiteStore(path).claim_ingress_with_task(
        incoming, contract, task
    )
    assert created is True
    assert original.projection.task_id == task.id
    assert original.projection.status is TaskStatus.PENDING

    replay = envelope(ingress_id=uuid4(), received_at=datetime.now(UTC))
    replay_contract = contract_for(replay)
    created, recovered = SQLiteStore(path).claim_ingress_with_task(
        replay, replay_contract, runtime_task(replay_contract)
    )
    assert created is False
    assert recovered == original


@pytest.mark.parametrize(
    "override",
    [
        {"source": IngressSource.API},
        {"actor_identity": "api:user:8"},
        {"external_message_id": "update:12"},
        {"kind": IngressKind.CALLBACK},
        {"content_ref": "sha256:" + "d" * 64},
        {"auth_context_ref": "sha256:" + "e" * 64},
    ],
)
def test_stable_fingerprint_binds_every_trusted_fact(
    tmp_path: Path, override: dict[str, object]
) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    incoming, contract, task = bound_values()
    store.claim_ingress_with_task(incoming, contract, task)
    forged = envelope(**override)
    forged_contract = contract_for(forged)
    with pytest.raises(IngressClaimConflictError):
        store.claim_ingress_with_task(
            forged, forged_contract, runtime_task(forged_contract)
        )


def test_new_claim_rejects_unrelated_same_tenant_contract_and_task(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    incoming = envelope()
    unrelated_envelope = envelope(idempotency_key="unrelated")
    unrelated_contract = contract_for(unrelated_envelope)
    with pytest.raises(IngressClaimConflictError, match="binding"):
        store.claim_ingress_with_task(
            incoming, unrelated_contract, runtime_task(unrelated_contract)
        )


@pytest.mark.parametrize(
    "task_update",
    [
        {"id": uuid4()},
        {"tenant_id": "tenant-b"},
        {"source": "api"},
        {"contract_digest": "sha256:" + "f" * 64},
        {"risk": "high"},
    ],
)
def test_new_claim_rejects_task_contract_binding_mismatch(
    tmp_path: Path, task_update: dict[str, object]
) -> None:
    incoming, contract, task = bound_values()
    forged = Task.model_validate(
        {**task.model_dump(mode="json"), **task_update}
    )
    with pytest.raises(IngressClaimConflictError, match="binding"):
        SQLiteStore(tmp_path / "state.sqlite3").claim_ingress_with_task(
            incoming, contract, forged
        )


@pytest.mark.parametrize(
    "task_update",
    [
        {"intent": "forged instruction"},
        {"payload": {"ingress_digest": "sha256:" + "f" * 64}},
        {"status": TaskStatus.PARSING},
    ],
)
def test_new_claim_rejects_forged_initial_runtime_projection(
    tmp_path: Path, task_update: dict[str, object]
) -> None:
    incoming, contract, task = bound_values()
    forged = Task.model_validate({**task.model_dump(mode="json"), **task_update})
    store = SQLiteStore(tmp_path / "state.sqlite3")
    with pytest.raises(IngressClaimConflictError, match="binding"):
        store.claim_ingress_with_task(incoming, contract, forged)
    assert store.read_task(task.tenant_id, task.id) is None


def test_concurrent_claim_has_one_winner(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    incoming, contract, task = bound_values()
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(
                lambda _: store.claim_ingress_with_task(
                    incoming, contract, task
                )[0],
                range(16),
            )
        )
    assert results.count(True) == 1
    assert results.count(False) == 15


def test_database_and_wal_exclude_raw_task_and_ingress_content(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    secret_instruction = "RAW-INSTRUCTION-MUST-NOT-PERSIST"
    incoming = envelope(
        actor_identity="RAW-ACTOR-MUST-NOT-PERSIST",
        external_message_id="RAW-MESSAGE-MUST-NOT-PERSIST",
    )
    contract = contract_for(incoming, instruction=secret_instruction)
    task = runtime_task(contract)
    assert task.payload
    store = SQLiteStore(path)
    store.claim_ingress_with_task(incoming, contract, task)
    updated = task.model_copy(
        update={
            "intent": "RAW-UPDATED-INTENT",
            "external_chat_id": "RAW-CHAT-ID",
            "payload": {"raw_payload": "RAW-PAYLOAD"},
            "status": TaskStatus.PARSING,
            "agent_id": "worker:server",
            "result": {"raw_result": "RAW-RESULT"},
            "context": {"raw_context": "RAW-CONTEXT"},
            "error_message": "RAW-ERROR-TEXT",
            "updated_at": task.updated_at + timedelta(seconds=1),
        }
    )
    store.save_task(updated, expected_revision=1)
    raw = b"".join(
        candidate.read_bytes()
        for candidate in path.parent.glob(f"{path.name}*")
        if candidate.is_file()
    )
    for forbidden in (
        secret_instruction,
        incoming.actor_identity,
        incoming.external_message_id,
        incoming.content_ref,
        incoming.auth_context_ref,
        "acceptance_criteria",
        "allowed_paths",
        "RAW-UPDATED-INTENT",
        "RAW-CHAT-ID",
        "RAW-PAYLOAD",
        "RAW-RESULT",
        "RAW-CONTEXT",
        "RAW-ERROR-TEXT",
    ):
        assert forbidden.encode() not in raw


def test_ingress_and_initial_projection_rollback_together(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    store = SQLiteStore(path)
    incoming, contract, task = bound_values()
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TRIGGER reject_claim BEFORE INSERT ON ingress_claims
               BEGIN SELECT RAISE(ABORT, 'forced'); END"""
        )
    with pytest.raises(IngressClaimConflictError):
        store.claim_ingress_with_task(incoming, contract, task)
    assert store.read_task(task.tenant_id, task.id) is None


def test_replay_rejects_tampered_claim_task_binding(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    store = SQLiteStore(path)
    first = bound_values()
    second_envelope = envelope(
        external_message_id="update:22", idempotency_key="idem-22"
    )
    second_contract = contract_for(second_envelope)
    second = (second_envelope, second_contract, runtime_task(second_contract))
    store.claim_ingress_with_task(*first)
    store.claim_ingress_with_task(*second)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """UPDATE ingress_claims SET task_id = ?
               WHERE tenant_id = ? AND idempotency_key = ?""",
            (str(second[2].id), first[0].tenant_id, first[0].idempotency_key),
        )
    replay = envelope(ingress_id=uuid4(), received_at=datetime.now(UTC))
    replay_contract = contract_for(replay)
    with pytest.raises(StoreCorruptionError):
        store.claim_ingress_with_task(
            replay, replay_contract, runtime_task(replay_contract)
        )


def test_save_task_is_update_only_compare_and_swap(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    store = SQLiteStore(path)
    task = persist(store)
    changed = task.model_copy(
        update={
            "status": TaskStatus.PARSING,
            "updated_at": task.updated_at + timedelta(seconds=1),
            "payload": {"raw": "still not persisted"},
        }
    )
    second = store.save_task(changed, expected_revision=1)
    assert second.revision == 2
    assert second.projection.status is TaskStatus.PARSING
    assert SQLiteStore(path).read_task(task.tenant_id, task.id) == second
    with pytest.raises(SnapshotConflictError):
        store.save_task(changed, expected_revision=1)


def test_save_task_cannot_insert_without_ingress_claim(tmp_path: Path) -> None:
    _, _, task = bound_values()
    store = SQLiteStore(tmp_path / "state.sqlite3")
    with pytest.raises(SnapshotConflictError):
        store.save_task(task, expected_revision=1)
    with pytest.raises(ValueError, match="positive"):
        store.save_task(task, expected_revision=0)


@pytest.mark.parametrize("expected_revision", [True, -1, 0, 1.5, "1"])
def test_save_task_requires_strict_positive_revision(
    tmp_path: Path, expected_revision: object
) -> None:
    _, _, task = bound_values()
    with pytest.raises(ValueError, match="expected_revision"):
        SQLiteStore(tmp_path / "state.sqlite3").save_task(
            task, expected_revision=expected_revision  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "update",
    [
        {"tenant_id": "tenant-b"},
        {"contract_digest": "sha256:" + "f" * 64},
        {"source": "api"},
        {"risk": "high"},
        {"created_at": datetime(2000, 1, 1, tzinfo=UTC)},
    ],
)
def test_save_task_rejects_immutable_binding_change(
    tmp_path: Path, update: dict[str, object]
) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    task = persist(store)
    forged = Task.model_validate({**task.model_dump(mode="json"), **update})
    with pytest.raises(SnapshotConflictError):
        store.save_task(forged, expected_revision=1)


def test_policy_recoverable_low_risk_completion_flow(tmp_path: Path) -> None:
    incoming = envelope()
    contract = contract_for(incoming)
    manager = StateManager(REGISTRY)
    task = asyncio.run(manager.create_from_contract(contract))
    path = tmp_path / "state.sqlite3"
    store = SQLiteStore(path, verifier_registry=REGISTRY)
    store.claim_ingress_with_task(incoming, contract, task)
    revision = 1

    for status, update in (
        (TaskStatus.PARSING, {}),
        (
            TaskStatus.DRAFT,
            {
                "agent_id": "worker:local",
                "result": {
                    "output_digest": canonical_json_digest({"output": "ok"}),
                    "summary": "raw summary is not checkpointed",
                },
            },
        ),
    ):
        task = asyncio.run(manager.update(task.id, status=status, **update))
        assert task is not None
        revision += 1
        snapshot = store.save_task(task, expected_revision=revision - 1)
        assert snapshot.revision == revision

    for status, level_count in (
        (TaskStatus.L1_VALIDATED, 1),
        (TaskStatus.L2_VERIFIED, 2),
        (TaskStatus.L3_APPROVED, 3),
    ):
        bundle = verification_bundle(task, level_count)
        task = asyncio.run(
            manager.update(task.id, status=status, verification_bundle=bundle)
        )
        assert task is not None
        revision += 1
        store.save_task(task, expected_revision=revision - 1)

    task = asyncio.run(manager.update(task.id, status=TaskStatus.COMPLETED))
    assert task is not None
    completed = store.save_task(task, expected_revision=revision)
    assert completed.projection.status is TaskStatus.COMPLETED
    assert completed.projection.agent_id == "worker:local"
    assert completed.projection.output_digest is not None
    assert completed.projection.verification_bundle is not None
    assert completed.projection.verification_bundle.l3 is not None
    assert (
        SQLiteStore(path, verifier_registry=REGISTRY).read_task(task.tenant_id, task.id)
        == completed
    )
    with pytest.raises(SnapshotConflictError):
        store.save_task(
            task.model_copy(
                update={
                    "status": TaskStatus.PENDING,
                    "updated_at": task.updated_at + timedelta(seconds=1),
                }
            ),
            expected_revision=completed.revision,
        )


def test_storage_rejects_forward_skip_backward_and_terminal_transition(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3", verifier_registry=REGISTRY)
    task = persist(store)
    with pytest.raises(SnapshotConflictError):
        store.save_task(
            task.model_copy(update={"status": TaskStatus.COMPLETED}),
            expected_revision=1,
        )

    parsing = task.model_copy(
        update={
            "status": TaskStatus.PARSING,
            "updated_at": task.updated_at + timedelta(seconds=1),
        }
    )
    store.save_task(parsing, expected_revision=1)
    with pytest.raises(SnapshotConflictError):
        store.save_task(
            parsing.model_copy(
                update={
                    "status": TaskStatus.PENDING,
                    "updated_at": parsing.updated_at + timedelta(seconds=1),
                }
            ),
            expected_revision=2,
        )


def test_storage_rejects_executor_and_same_revision_result_replacement(
    tmp_path: Path,
) -> None:
    incoming = envelope()
    contract = contract_for(incoming)
    manager = StateManager(REGISTRY)
    task = asyncio.run(manager.create_from_contract(contract))
    store = SQLiteStore(tmp_path / "state.sqlite3", verifier_registry=REGISTRY)
    store.claim_ingress_with_task(incoming, contract, task)
    task = asyncio.run(manager.update(task.id, status=TaskStatus.PARSING))
    assert task is not None
    store.save_task(task, expected_revision=1)
    task = asyncio.run(
        manager.update(
            task.id,
            status=TaskStatus.DRAFT,
            agent_id="worker:local",
            result={"output_digest": canonical_json_digest({"output": "ok"})},
        )
    )
    assert task is not None
    store.save_task(task, expected_revision=2)

    next_time = task.updated_at + timedelta(seconds=1)
    with pytest.raises(SnapshotConflictError, match="executor"):
        store.save_task(
            task.model_copy(
                update={
                    "status": TaskStatus.L1_VALIDATED,
                    "agent_id": "worker:forged",
                    "verification_bundle": verification_bundle(task, 1),
                    "updated_at": next_time,
                }
            ),
            expected_revision=3,
        )
    with pytest.raises(SnapshotConflictError, match="result"):
        store.save_task(
            task.model_copy(
                update={
                    "status": TaskStatus.L1_VALIDATED,
                    "result_digest": "sha256:" + "f" * 64,
                    "verification_bundle": verification_bundle(task, 1),
                    "updated_at": next_time,
                }
            ),
            expected_revision=3,
        )


def test_draft_without_output_digest_persists_only_core_result_digest(
    tmp_path: Path,
) -> None:
    incoming = envelope()
    contract = contract_for(incoming)
    manager = StateManager(REGISTRY)
    task = asyncio.run(manager.create_from_contract(contract))
    store = SQLiteStore(tmp_path / "state.sqlite3", verifier_registry=REGISTRY)
    store.claim_ingress_with_task(incoming, contract, task)
    task = asyncio.run(manager.update(task.id, status=TaskStatus.PARSING))
    assert task is not None
    store.save_task(task, expected_revision=1)
    draft = asyncio.run(
        manager.update(
            task.id,
            status=TaskStatus.DRAFT,
            agent_id="worker:local",
            result={"value": "A"},
        )
    )
    assert draft is not None
    snapshot = store.save_task(draft, expected_revision=2)
    assert snapshot.projection.result_digest == draft.result_digest
    assert snapshot.projection.output_digest is None


def test_active_result_survives_deferred_and_waiting_flow(tmp_path: Path) -> None:
    store, manager, task, revision = persisted_draft(tmp_path / "state.sqlite3")
    original_digest = task.result_digest
    original_output = task.result["output_digest"] if task.result else None
    for status in (
        TaskStatus.DEFERRED,
        TaskStatus.IN_PROGRESS,
        TaskStatus.WAITING_INPUT,
    ):
        task = asyncio.run(manager.update(task.id, status=status))
        assert task is not None
        snapshot = store.save_task(task, expected_revision=revision)
        revision += 1
        assert snapshot.projection.result_digest == original_digest
        assert snapshot.projection.output_digest == original_output


def test_high_risk_l4_executing_to_failed_preserves_result(tmp_path: Path) -> None:
    incoming = envelope()
    contract = contract_for(incoming, risk="high")
    manager = StateManager(REGISTRY)
    task = asyncio.run(manager.create_from_contract(contract))
    store = SQLiteStore(tmp_path / "state.sqlite3", verifier_registry=REGISTRY)
    store.claim_ingress_with_task(incoming, contract, task)
    revision = 1

    task = asyncio.run(manager.update(task.id, status=TaskStatus.PARSING))
    assert task is not None
    store.save_task(task, expected_revision=revision)
    revision += 1
    task = asyncio.run(
        manager.update(
            task.id,
            status=TaskStatus.DRAFT,
            agent_id="worker:local",
            result={"value": "A"},
        )
    )
    assert task is not None
    store.save_task(task, expected_revision=revision)
    revision += 1
    sealed_digest = task.result_digest

    for status, level_count in (
        (TaskStatus.L1_VALIDATED, 1),
        (TaskStatus.L2_VERIFIED, 2),
        (TaskStatus.L3_APPROVED, 3),
    ):
        task = asyncio.run(
            manager.update(
                task.id,
                status=status,
                verification_bundle=verification_bundle(task, level_count),
            )
        )
        assert task is not None
        store.save_task(task, expected_revision=revision)
        revision += 1

    task = asyncio.run(manager.update(task.id, status=TaskStatus.WAITING_HUMAN))
    assert task is not None
    store.save_task(task, expected_revision=revision)
    revision += 1
    approval = HumanApprovalRecord(
        tenant_id=task.tenant_id,
        task_id=task.id,
        contract_digest=task.contract_digest,
        result_revision=task.result_revision,
        result_digest=task.result_digest,
        approver_identity="owner:human",
        approved_at=datetime.now(UTC),
        evidence_ref="approval:telegram-callback",
    )
    task = asyncio.run(
        manager.update(
            task.id,
            status=TaskStatus.HUMAN_APPROVED,
            human_approval=approval,
        )
    )
    assert task is not None
    store.save_task(task, expected_revision=revision)
    revision += 1
    for status in (TaskStatus.EXECUTING, TaskStatus.FAILED):
        task = asyncio.run(manager.update(task.id, status=status))
        assert task is not None
        snapshot = store.save_task(task, expected_revision=revision)
        revision += 1
        assert snapshot.projection.result_digest == sealed_digest


def test_real_draft_to_rework_clears_active_result_without_stale_output(
    tmp_path: Path,
) -> None:
    store, manager, draft, revision = persisted_draft(tmp_path / "state.sqlite3")
    reset = asyncio.run(manager.update(draft.id, status=TaskStatus.REWORK))
    assert reset is not None
    assert reset.result is not None and "output_digest" in reset.result
    assert reset.result_digest is None
    snapshot = store.save_task(reset, expected_revision=revision)
    assert snapshot.projection.status is TaskStatus.REWORK
    assert snapshot.projection.result_revision == draft.result_revision
    assert snapshot.projection.result_digest is None
    assert snapshot.projection.output_digest is None
    assert snapshot.projection.verification_history == ()
    for expected_revision, status in enumerate(
        (TaskStatus.IN_PROGRESS, TaskStatus.WAITING_INPUT, TaskStatus.FAILED),
        start=snapshot.revision,
    ):
        reset = asyncio.run(manager.update(reset.id, status=status))
        assert reset is not None
        continued = store.save_task(reset, expected_revision=expected_revision)
        assert continued.projection.result_revision == draft.result_revision
        assert continued.projection.result_digest is None
        assert continued.projection.output_digest is None


def test_new_draft_after_rework_advances_and_reseals_result_revision(
    tmp_path: Path,
) -> None:
    store, manager, draft, revision = persisted_draft(tmp_path / "state.sqlite3")
    reset = asyncio.run(manager.update(draft.id, status=TaskStatus.REWORK))
    assert reset is not None
    reset_snapshot = store.save_task(reset, expected_revision=revision)
    with pytest.raises(SnapshotConflictError, match="executor"):
        store.save_task(
            reset.model_copy(
                update={
                    "status": TaskStatus.IN_PROGRESS,
                    "agent_id": "worker:replacement",
                    "updated_at": reset.updated_at + timedelta(seconds=1),
                }
            ),
            expected_revision=reset_snapshot.revision,
        )
    with pytest.raises(SnapshotConflictError, match="executor"):
        store.save_task(
            reset.model_copy(
                update={
                    "status": TaskStatus.DRAFT,
                    "agent_id": "worker:replacement",
                    "updated_at": reset.updated_at + timedelta(seconds=1),
                }
            ),
            expected_revision=reset_snapshot.revision,
        )
    redraft = asyncio.run(
        manager.update(
            reset.id,
            status=TaskStatus.DRAFT,
            agent_id="worker:replacement",
            result={"value": "B"},
        )
    )
    assert redraft is not None
    snapshot = store.save_task(redraft, expected_revision=revision + 1)
    assert snapshot.projection.result_revision == draft.result_revision + 1
    assert snapshot.projection.result_digest == redraft.result_digest
    assert snapshot.projection.output_digest is None
    assert snapshot.projection.agent_id == "worker:replacement"


def test_real_l1_and_rejected_to_rework_archive_exact_evidence(tmp_path: Path) -> None:
    store, manager, task, revision = persisted_draft(tmp_path / "state.sqlite3")
    l1_bundle = verification_bundle(task, 1)
    l1 = asyncio.run(
        manager.update(
            task.id,
            status=TaskStatus.L1_VALIDATED,
            verification_bundle=l1_bundle,
        )
    )
    assert l1 is not None
    revision += 1
    store.save_task(l1, expected_revision=revision - 1)

    failed_l2 = verification_bundle(l1, 2, failed_level=2)
    rejected = asyncio.run(
        manager.update(
            l1.id,
            status=TaskStatus.REJECTED,
            verification_bundle=failed_l2,
        )
    )
    assert rejected is not None
    revision += 1
    store.save_task(rejected, expected_revision=revision - 1)

    reset = asyncio.run(manager.update(rejected.id, status=TaskStatus.REWORK))
    assert reset is not None
    revision += 1
    snapshot = store.save_task(reset, expected_revision=revision - 1)
    assert snapshot.projection.verification_bundle is None
    assert snapshot.projection.verification_history == (failed_l2,)
    assert snapshot.projection.result_digest is None
    assert snapshot.projection.output_digest is None


def test_forged_history_is_rejected_outside_and_inside_rework(tmp_path: Path) -> None:
    store, manager, draft, revision = persisted_draft(tmp_path / "state.sqlite3")
    l1_bundle = verification_bundle(draft, 1)
    l1 = asyncio.run(
        manager.update(
            draft.id,
            status=TaskStatus.L1_VALIDATED,
            verification_bundle=l1_bundle,
        )
    )
    assert l1 is not None
    with pytest.raises(SnapshotConflictError, match="history"):
        store.save_task(
            l1.model_copy(update={"verification_history": (l1_bundle,)}),
            expected_revision=revision,
        )

    store.save_task(l1, expected_revision=revision)
    reset = asyncio.run(manager.update(l1.id, status=TaskStatus.REWORK))
    assert reset is not None
    with pytest.raises(SnapshotConflictError, match="exact"):
        store.save_task(
            reset.model_copy(
                update={"verification_history": (l1_bundle, l1_bundle)}
            ),
            expected_revision=revision + 1,
        )


def test_events_are_durable_ordered_and_tenant_scoped(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    store = SQLiteStore(path)
    task = persist(store)
    attempt_id = uuid4()
    first, second = event(task, attempt_id, 1), event(task, attempt_id, 2)
    store.append_event(first)
    SQLiteStore(path).append_event(second)
    assert SQLiteStore(path).read_events(task.tenant_id, task.id, attempt_id) == (
        first,
        second,
    )
    assert SQLiteStore(path).read_events("tenant-b", task.id, attempt_id) == ()


def test_events_reject_duplicate_gap_and_binding_conflicts(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    task = persist(store)
    attempt_id = uuid4()
    first = event(task, attempt_id, 1)
    store.append_event(first)
    with pytest.raises(AuditEventConflictError):
        store.append_event(first)
    with pytest.raises(AuditEventOrderError):
        store.append_event(event(task, attempt_id, 3))
    with pytest.raises(AuditEventConflictError):
        store.append_event(event(task, attempt_id, 2, worker_identity="worker:other"))
    with pytest.raises(AuditEventConflictError):
        store.append_event(
            event(task, uuid4(), 1, contract_digest="sha256:" + "f" * 64)
        )


def test_concurrent_same_sequence_event_has_one_append(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    task = persist(store)
    attempt_id = uuid4()

    def append(candidate: WorkerEvent) -> str:
        try:
            store.append_event(candidate)
        except (AuditEventConflictError, AuditEventOrderError):
            return "rejected"
        return "accepted"

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(append, [event(task, attempt_id, 1) for _ in range(8)])
        )
    assert results.count("accepted") == 1
    assert results.count("rejected") == 7


def test_event_id_uniqueness_is_tenant_scoped(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "state.sqlite3")
    shared_id, shared_event_id, attempt_id = uuid4(), uuid4(), uuid4()
    first_values = bound_values(tenant_id="tenant-a", task_id=shared_id)
    second_values = bound_values(tenant_id="tenant-b", task_id=shared_id)
    first, second = first_values[2], second_values[2]
    store.claim_ingress_with_task(*first_values)
    store.claim_ingress_with_task(*second_values)
    store.append_event(event(first, attempt_id, 1, event_id=shared_event_id))
    store.append_event(event(second, attempt_id, 1, event_id=shared_event_id))
    assert len(store.read_events("tenant-a", shared_id, attempt_id)) == 1
    assert len(store.read_events("tenant-b", shared_id, attempt_id)) == 1


@pytest.mark.parametrize(
    ("column", "forged"),
    [
        ("contract_digest", "sha256:" + "f" * 64),
        ("revision", "broken"),
        ("updated_at", "2000-01-01T00:00:00+00:00"),
        ("projection_digest", "sha256:" + "f" * 64),
    ],
)
def test_read_task_rejects_tampered_row_bindings(
    tmp_path: Path, column: str, forged: object
) -> None:
    path = tmp_path / "state.sqlite3"
    store = SQLiteStore(path)
    task = persist(store)
    with sqlite3.connect(path) as connection:
        connection.execute(
            f"UPDATE task_snapshots SET {column} = ?",  # closed test-only set
            (forged,),
        )
    with pytest.raises(StoreCorruptionError):
        store.read_task(task.tenant_id, task.id)


@pytest.mark.parametrize(
    "field", ["tenant_id", "task_id", "contract_digest", "updated_at"]
)
def test_read_task_rejects_tampered_projection_bindings(
    tmp_path: Path, field: str
) -> None:
    path = tmp_path / "state.sqlite3"
    store = SQLiteStore(path)
    task = persist(store)
    with sqlite3.connect(path) as connection:
        raw = connection.execute(
            "SELECT projection_json FROM task_snapshots"
        ).fetchone()[0]
        data = json.loads(raw)
        data[field] = {
            "tenant_id": "tenant-b",
            "task_id": str(uuid4()),
            "contract_digest": "sha256:" + "f" * 64,
            "updated_at": "2000-01-01T00:00:00Z",
        }[field]
        connection.execute(
            "UPDATE task_snapshots SET projection_json = ?",
            (json.dumps(data),),
        )
    with pytest.raises(StoreCorruptionError):
        store.read_task(task.tenant_id, task.id)


@pytest.mark.parametrize(
    ("column", "forged"),
    [
        ("sequence", 2),
        ("event_id", str(uuid4())),
        ("contract_digest", "sha256:" + "f" * 64),
        ("worker_identity", "worker:forged"),
        ("event_digest", "sha256:" + "f" * 64),
    ],
)
def test_read_events_rejects_tampered_row_bindings(
    tmp_path: Path, column: str, forged: object
) -> None:
    path = tmp_path / "state.sqlite3"
    store = SQLiteStore(path)
    task, attempt_id = persist(store), uuid4()
    store.append_event(event(task, attempt_id, 1))
    with sqlite3.connect(path) as connection:
        connection.execute(
            f"UPDATE audit_events SET {column} = ?",  # closed test-only set
            (forged,),
        )
    with pytest.raises(StoreCorruptionError):
        store.read_events(task.tenant_id, task.id, attempt_id)


def test_malformed_database_and_bad_path_errors_are_sanitized(tmp_path: Path) -> None:
    malformed = tmp_path / "private-state.sqlite3"
    malformed.write_bytes(b"not a sqlite database; private material")
    blocked_parent = tmp_path / "private-parent"
    blocked_parent.write_text("not a directory", encoding="utf-8")
    for path in (malformed, blocked_parent / "state.sqlite3"):
        with pytest.raises(StoreCorruptionError) as raised:
            SQLiteStore(path)
        assert str(raised.value) == "durable store is invalid"
        assert raised.value.__cause__ is None
        assert str(path) not in str(raised.value)


def test_read_connections_release_database_file_without_gc(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    store = SQLiteStore(path)
    task_id = uuid4()
    attempt_id = uuid4()
    message_id = uuid4()

    for _ in range(25):
        assert store.read_task("tenant-a", task_id) is None
        assert store.read_events("tenant-a", task_id, attempt_id) == ()
        assert store.read_outbox_message("tenant-a", message_id) is None
        assert store.read_outbox_receipts("tenant-a", message_id) == ()

    moved = tmp_path / "moved.sqlite3"
    path.replace(moved)
    moved.replace(path)