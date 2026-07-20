"""Adversarial tests for result sealing and L1-L4 completion policy."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from src.contracts import (
    HumanApprovalRecord,
    RiskLevel,
    VerificationBundle,
    VerificationBundleStatus,
    VerificationLevel,
    VerificationLevelStatus,
)
from src.core import PolicyViolation, TrustedVerifierRegistry, validate_completion
from src.models.task import Task, TaskSource, TaskStatus
from src.orchestrator.state_manager import StateManager


REGISTRY = TrustedVerifierRegistry(
    {
        1: {"verifier:l1"},
        2: {"verifier:l2"},
        3: {"verifier:l3"},
    }
)
BASE_TIME = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def make_level(
    level: int,
    *,
    status: VerificationLevelStatus = VerificationLevelStatus.PASSED,
    identity: str | None = None,
    method: str | None = None,
    evidence_ref: str | None = None,
    evidence_digest: str | None = None,
    verified_at: datetime | None = None,
) -> VerificationLevel:
    return VerificationLevel(
        status=status,
        verifier_identity=identity or f"verifier:l{level}",
        method=method or f"method:l{level}",
        verified_at=verified_at or BASE_TIME + timedelta(minutes=level),
        evidence_refs=(evidence_ref or f"evidence/l{level}.json",),
        evidence_digest=evidence_digest or f"sha256:{str(level) * 64}",
    )


def make_bundle(
    task: Task,
    stage: int = 3,
    *,
    failed_level: int | None = None,
    levels: tuple[VerificationLevel | None, ...] | None = None,
    **overrides: object,
) -> VerificationBundle:
    if levels is None:
        built: list[VerificationLevel | None] = []
        for level in range(1, 4):
            if level > stage:
                built.append(None)
            else:
                built.append(
                    make_level(
                        level,
                        status=(
                            VerificationLevelStatus.FAILED
                            if failed_level == level
                            else VerificationLevelStatus.PASSED
                        ),
                    )
                )
        levels = tuple(built)
    data: dict[str, object] = {
        "tenant_id": task.tenant_id,
        "task_id": task.id,
        "contract_digest": task.contract_digest,
        "result_revision": task.result_revision,
        "result_digest": task.result_digest,
        "executor_identity": task.agent_id,
        "l1": levels[0],
        "l2": levels[1],
        "l3": levels[2],
        "status": (
            VerificationBundleStatus.REJECTED
            if failed_level is not None
            else VerificationBundleStatus.APPROVED
            if stage == 3
            else VerificationBundleStatus.DRAFT
        ),
    }
    data.update(overrides)
    return VerificationBundle(**data)  # type: ignore[arg-type]


def make_approval(task: Task, **overrides: object) -> HumanApprovalRecord:
    data: dict[str, object] = {
        "tenant_id": task.tenant_id,
        "task_id": task.id,
        "contract_digest": task.contract_digest,
        "result_revision": task.result_revision,
        "result_digest": task.result_digest,
        "approver_identity": "owner:1",
        "approved_at": datetime.now(UTC),
        "evidence_ref": "telegram/callback/1",
    }
    data.update(overrides)
    return HumanApprovalRecord(**data)  # type: ignore[arg-type]


async def create_draft(
    manager: StateManager,
    *,
    risk: RiskLevel = RiskLevel.LOW,
    tenant_id: str = "tenant-a",
    result: dict[str, object] | None = None,
) -> Task:
    task = await manager.create(
        source=TaskSource.API.value,
        external_chat_id=None,
        intent="audit",
        payload={"scope": "test"},
        risk=risk,
        tenant_id=tenant_id,
    )
    await manager.update(task.id, status=TaskStatus.PARSING)
    draft = await manager.update(
        task.id,
        status=TaskStatus.DRAFT,
        agent_id="worker:codex",
        result=result or {"value": "A"},
        context={"trace": "safe"},
    )
    assert draft is not None
    return draft


async def advance_to(manager: StateManager, task: Task, stage: int) -> Task:
    current = task
    targets = (
        TaskStatus.L1_VALIDATED,
        TaskStatus.L2_VERIFIED,
        TaskStatus.L3_APPROVED,
    )
    for level in range(1, stage + 1):
        if current.status == targets[level - 1]:
            continue
        updated = await manager.update(
            current.id,
            status=targets[level - 1],
            verification_bundle=make_bundle(current, level),
        )
        assert updated is not None
        current = updated
    return current


def validate_full_bundle(task: Task, bundle: VerificationBundle) -> None:
    validate_completion(
        bundle,
        task_id=task.id,
        tenant_id=task.tenant_id,
        contract_digest=task.contract_digest,
        result_revision=task.result_revision,
        result_digest=task.result_digest,
        executor_identity=task.agent_id,
        verifier_registry=REGISTRY,
    )


@pytest.mark.asyncio
async def test_low_risk_result_completes_only_after_sequential_l1_l2_l3() -> None:
    manager = StateManager(REGISTRY)
    task = await create_draft(manager)
    task = await advance_to(manager, task, 3)
    completed = await manager.update(task.id, status=TaskStatus.COMPLETED)

    assert completed is not None
    assert completed.status == TaskStatus.COMPLETED
    assert completed.result_revision == 1
    assert completed.result_digest


@pytest.mark.asyncio
async def test_draft_requires_non_empty_result_and_frozen_executor_atomically() -> None:
    manager = StateManager(REGISTRY)
    task = await manager.create(
        source=TaskSource.API.value,
        external_chat_id=None,
        intent="audit",
        payload={},
    )
    parsing = await manager.update(task.id, status=TaskStatus.PARSING)
    assert parsing is not None

    invalid_updates = (
        {"status": TaskStatus.DRAFT, "agent_id": "worker:codex"},
        {
            "status": TaskStatus.DRAFT,
            "agent_id": "worker:codex",
            "result": {},
        },
        {"status": TaskStatus.DRAFT, "result": {"value": "A"}},
    )
    for update in invalid_updates:
        with pytest.raises(PolicyViolation, match="DRAFT requires"):
            await manager.update(task.id, **update)  # type: ignore[arg-type]
        assert await manager.get(task.id) == parsing

    draft = await manager.update(
        task.id,
        status=TaskStatus.DRAFT,
        agent_id="worker:codex",
        result={"value": "A"},
    )
    assert draft is not None
    assert draft.agent_id == "worker:codex"
    assert draft.result_digest is not None


@pytest.mark.asyncio
async def test_verification_requires_injected_registry_and_trusted_roles() -> None:
    no_registry = StateManager()
    task = await create_draft(no_registry)
    with pytest.raises(PolicyViolation, match="registry"):
        await no_registry.update(
            task.id,
            status=TaskStatus.L1_VALIDATED,
            verification_bundle=make_bundle(task, 1),
        )

    manager = StateManager(REGISTRY)
    task = await create_draft(manager)
    fake_l1 = make_level(1, identity="verifier:fake")
    with pytest.raises(PolicyViolation, match="not trusted"):
        await manager.update(
            task.id,
            status=TaskStatus.L1_VALIDATED,
            verification_bundle=make_bundle(task, 1, levels=(fake_l1, None, None)),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tenant_id", "tenant-b"),
        ("task_id", UUID("99999999-9999-4999-8999-999999999999")),
        ("contract_digest", "sha256:" + "a" * 64),
        ("result_revision", 2),
        ("result_digest", "sha256:" + "b" * 64),
    ],
)
async def test_bundle_is_bound_to_task_tenant_contract_and_result_revision(
    field: str, value: object
) -> None:
    manager = StateManager(REGISTRY)
    task = await create_draft(manager)
    with pytest.raises(PolicyViolation, match="binding"):
        await manager.update(
            task.id,
            status=TaskStatus.L1_VALIDATED,
            verification_bundle=make_bundle(task, 1, **{field: value}),
        )


@pytest.mark.asyncio
async def test_executor_and_verifiers_must_be_independent() -> None:
    manager = StateManager(REGISTRY)
    task = await create_draft(manager)
    registry = TrustedVerifierRegistry({1: {"worker:codex"}, 2: set(), 3: set()})
    manager_with_bad_roles = StateManager(registry)
    task = await create_draft(manager_with_bad_roles)
    self_check = make_level(1, identity="worker:codex")
    with pytest.raises(PolicyViolation, match="own result"):
        await manager_with_bad_roles.update(
            task.id,
            status=TaskStatus.L1_VALIDATED,
            verification_bundle=make_bundle(task, 1, levels=(self_check, None, None)),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("duplicate", ["identity", "method", "ref", "digest"])
async def test_each_level_requires_independent_integrity_evidence(
    duplicate: str,
) -> None:
    manager = StateManager(REGISTRY)
    task = await create_draft(manager)
    l1 = make_level(1)
    kwargs: dict[str, object] = {}
    if duplicate == "identity":
        kwargs["identity"] = l1.verifier_identity
        registry = TrustedVerifierRegistry(
            {1: {"verifier:l1"}, 2: {"verifier:l1"}, 3: {"verifier:l3"}}
        )
        manager = StateManager(registry)
        task = await create_draft(manager)
    elif duplicate == "method":
        kwargs["method"] = l1.method
    elif duplicate == "ref":
        kwargs["evidence_ref"] = l1.evidence_refs[0]
    else:
        kwargs["evidence_digest"] = l1.evidence_digest
    l2 = make_level(2, **kwargs)  # type: ignore[arg-type]
    await manager.update(
        task.id,
        status=TaskStatus.L1_VALIDATED,
        verification_bundle=make_bundle(task, 1, levels=(l1, None, None)),
    )
    current = await manager.get(task.id)
    assert current is not None
    with pytest.raises(PolicyViolation, match="independent|method|reused"):
        await manager.update(
            task.id,
            status=TaskStatus.L2_VERIFIED,
            verification_bundle=make_bundle(current, 2, levels=(l1, l2, None)),
        )


@pytest.mark.asyncio
async def test_verification_timestamps_must_be_sequential() -> None:
    manager = StateManager(REGISTRY)
    task = await create_draft(manager)
    l1 = make_level(1)
    l2 = make_level(2, verified_at=BASE_TIME)
    await manager.update(
        task.id,
        status=TaskStatus.L1_VALIDATED,
        verification_bundle=make_bundle(task, 1, levels=(l1, None, None)),
    )
    current = await manager.get(task.id)
    assert current is not None
    with pytest.raises(PolicyViolation, match="timestamps"):
        await manager.update(
            task.id,
            status=TaskStatus.L2_VERIFIED,
            verification_bundle=make_bundle(current, 2, levels=(l1, l2, None)),
        )


@pytest.mark.asyncio
async def test_result_and_context_are_sealed_at_draft() -> None:
    manager = StateManager(REGISTRY)
    task = await create_draft(manager)
    original_updated_at = task.updated_at

    for update in ({"result": {"value": "B"}}, {"context": {"trace": "changed"}}):
        with pytest.raises(PolicyViolation, match="sealed"):
            await manager.update(task.id, **update)  # type: ignore[arg-type]
        stored = await manager.get(task.id)
        assert stored is not None
        assert stored.updated_at == original_updated_at
        assert stored.result == {"value": "A"}
        assert stored.context == {"trace": "safe"}


@pytest.mark.asyncio
async def test_result_a_cannot_become_b_after_l3_or_at_completion() -> None:
    manager = StateManager(REGISTRY)
    task = await advance_to(manager, await create_draft(manager), 3)
    with pytest.raises(PolicyViolation, match="sealed"):
        await manager.update(task.id, result={"value": "B"})
    with pytest.raises(PolicyViolation, match="sealed"):
        await manager.update(
            task.id,
            status=TaskStatus.COMPLETED,
            result={"value": "B"},
        )


@pytest.mark.asyncio
async def test_rework_resets_active_evidence_and_seals_a_new_revision() -> None:
    manager = StateManager(REGISTRY)
    first = await advance_to(manager, await create_draft(manager), 1)
    old_bundle = first.verification_bundle
    old_digest = first.result_digest

    reset = await manager.update(first.id, status=TaskStatus.REWORK)
    assert reset is not None
    assert reset.result_revision == 1
    assert reset.result_digest is None
    assert reset.verification_bundle is None
    assert reset.verification_history == (old_bundle,)

    with pytest.raises(PolicyViolation, match="non-empty result"):
        await manager.update(first.id, status=TaskStatus.DRAFT)
    assert await manager.get(first.id) == reset

    second = await manager.update(
        first.id,
        status=TaskStatus.DRAFT,
        result={"value": "B"},
        context={"trace": "new"},
    )
    assert second is not None
    assert second.result_revision == 2
    assert second.result_digest != old_digest
    with pytest.raises(PolicyViolation, match="binding"):
        await manager.update(
            second.id,
            status=TaskStatus.L1_VALIDATED,
            verification_bundle=old_bundle,
        )


@pytest.mark.asyncio
async def test_failed_verification_is_saved_then_archived_on_rework() -> None:
    manager = StateManager(REGISTRY)
    task = await create_draft(manager)
    failed = make_bundle(task, 1, failed_level=1)
    rejected = await manager.update(
        task.id,
        status=TaskStatus.REJECTED,
        verification_bundle=failed,
    )
    assert rejected is not None
    assert rejected.verification_bundle == failed
    assert rejected.verification_bundle.l1.status == VerificationLevelStatus.FAILED

    reset = await manager.update(task.id, status=TaskStatus.REWORK)
    assert reset is not None
    assert reset.verification_bundle is None
    assert reset.verification_history[-1] == failed


@pytest.mark.asyncio
async def test_rejected_record_only_allows_clean_atomic_rework() -> None:
    manager = StateManager(REGISTRY)
    task = await create_draft(manager)
    failed = make_bundle(task, 1, failed_level=1)
    rejected = await manager.update(
        task.id,
        status=TaskStatus.REJECTED,
        verification_bundle=failed,
        error_message="l1_failed",
    )
    assert rejected is not None

    attacks = (
        {},
        {"status": TaskStatus.FAILED},
        {"error_message": "changed"},
        {"result": {"value": "changed"}},
        {"context": {"trace": "changed"}},
        {"agent_id": "worker:other"},
        {"verification_bundle": failed},
        {"human_approval": make_approval(rejected)},
        {"status": TaskStatus.REWORK, "error_message": "changed"},
    )
    for update in attacks:
        with pytest.raises(PolicyViolation, match="REJECTED audit record"):
            await manager.update(task.id, **update)  # type: ignore[arg-type]
        assert await manager.get(task.id) == rejected

    reset = await manager.update(task.id, status=TaskStatus.REWORK)
    assert reset is not None
    assert reset.status == TaskStatus.REWORK
    assert reset.verification_bundle is None
    assert reset.verification_history[-1] == failed


@pytest.mark.asyncio
async def test_rejection_during_verification_requires_failed_level_evidence() -> None:
    manager = StateManager(REGISTRY)
    task = await create_draft(manager)
    with pytest.raises(PolicyViolation, match="failure evidence"):
        await manager.update(task.id, status=TaskStatus.REJECTED)


@pytest.mark.asyncio
async def test_high_risk_completion_requires_result_bound_l4() -> None:
    manager = StateManager(REGISTRY)
    task = await advance_to(
        manager,
        await create_draft(manager, risk=RiskLevel.HIGH),
        3,
    )
    with pytest.raises(PolicyViolation, match="HUMAN_APPROVED"):
        await manager.update(task.id, status=TaskStatus.COMPLETED)
    waiting = await manager.update(task.id, status=TaskStatus.WAITING_HUMAN)
    assert waiting is not None
    approved = await manager.update(
        task.id,
        status=TaskStatus.HUMAN_APPROVED,
        human_approval=make_approval(waiting),
    )
    assert approved is not None
    completed = await manager.update(task.id, status=TaskStatus.COMPLETED)
    assert completed is not None
    assert completed.status == TaskStatus.COMPLETED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "terminal", [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ESCALATE]
)
async def test_external_effect_uses_locked_executing_path(
    terminal: TaskStatus,
) -> None:
    manager = StateManager(REGISTRY)
    task = await advance_to(
        manager,
        await create_draft(manager, risk=RiskLevel.HIGH),
        3,
    )
    waiting = await manager.update(task.id, status=TaskStatus.WAITING_HUMAN)
    assert waiting is not None
    approved = await manager.update(
        task.id,
        status=TaskStatus.HUMAN_APPROVED,
        human_approval=make_approval(waiting),
    )
    assert approved is not None
    executing = await manager.update(task.id, status=TaskStatus.EXECUTING)
    assert executing is not None
    assert executing.status == TaskStatus.EXECUTING

    with pytest.raises(PolicyViolation, match="sealed"):
        await manager.update(task.id, result={"value": "changed"})
    with pytest.raises(PolicyViolation, match="executor"):
        await manager.update(task.id, agent_id="worker:other")
    with pytest.raises(PolicyViolation, match="audit-locked"):
        await manager.update(
            task.id,
            verification_bundle=make_bundle(
                executing,
                3,
                levels=(make_level(1), make_level(2), make_level(3, method="other")),
            ),
        )

    finished = await manager.update(task.id, status=terminal)
    assert finished is not None
    assert finished.status == terminal


@pytest.mark.asyncio
async def test_executing_requires_saved_bound_approval() -> None:
    manager = StateManager(REGISTRY)
    task = await advance_to(manager, await create_draft(manager), 3)
    with pytest.raises(PolicyViolation):
        await manager.update(task.id, status=TaskStatus.EXECUTING)


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", [TaskStatus.FAILED, TaskStatus.ESCALATE])
async def test_human_approved_cannot_skip_executing_for_effect_failure(
    terminal: TaskStatus,
) -> None:
    manager = StateManager(REGISTRY)
    task = await advance_to(
        manager,
        await create_draft(manager, risk=RiskLevel.HIGH),
        3,
    )
    waiting = await manager.update(task.id, status=TaskStatus.WAITING_HUMAN)
    assert waiting is not None
    approved = await manager.update(
        task.id,
        status=TaskStatus.HUMAN_APPROVED,
        human_approval=make_approval(waiting),
    )
    assert approved is not None
    with pytest.raises(PolicyViolation, match="invalid task transition"):
        await manager.update(task.id, status=terminal)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tenant_id", "tenant-b"),
        ("contract_digest", "sha256:" + "e" * 64),
        ("result_revision", 2),
        ("result_digest", "sha256:" + "f" * 64),
        ("approver_identity", "worker:codex"),
        ("approver_identity", "verifier:l1"),
        ("approver_identity", "verifier:l2"),
        ("approver_identity", "verifier:l3"),
    ],
)
async def test_l4_record_cannot_approve_another_result_or_self(
    field: str, value: object
) -> None:
    manager = StateManager(REGISTRY)
    task = await advance_to(
        manager,
        await create_draft(manager, risk=RiskLevel.HIGH),
        3,
    )
    waiting = await manager.update(task.id, status=TaskStatus.WAITING_HUMAN)
    assert waiting is not None
    with pytest.raises(PolicyViolation, match="binding|independent"):
        await manager.update(
            task.id,
            status=TaskStatus.HUMAN_APPROVED,
            human_approval=make_approval(waiting, **{field: value}),
        )


@pytest.mark.asyncio
async def test_l4_timestamp_must_be_inside_server_update_window() -> None:
    manager = StateManager(REGISTRY)
    task = await advance_to(
        manager,
        await create_draft(manager, risk=RiskLevel.HIGH),
        3,
    )
    waiting = await manager.update(task.id, status=TaskStatus.WAITING_HUMAN)
    assert waiting is not None
    stale = waiting.updated_at - timedelta(seconds=1)
    with pytest.raises(PolicyViolation, match="window"):
        await manager.update(
            task.id,
            status=TaskStatus.HUMAN_APPROVED,
            human_approval=make_approval(waiting, approved_at=stale),
        )


@pytest.mark.asyncio
async def test_completion_cannot_replace_saved_l3_bundle() -> None:
    manager = StateManager(REGISTRY)
    task = await advance_to(manager, await create_draft(manager), 3)
    replacement = make_bundle(
        task,
        3,
        levels=(make_level(1), make_level(2), make_level(3, method="other")),
    )
    with pytest.raises(PolicyViolation, match="audit-locked"):
        await manager.update(
            task.id,
            status=TaskStatus.COMPLETED,
            verification_bundle=replacement,
        )


@pytest.mark.asyncio
async def test_terminal_record_and_returned_aliases_are_immutable_at_boundary() -> None:
    manager = StateManager(REGISTRY)
    task = await advance_to(manager, await create_draft(manager), 3)
    completed = await manager.update(task.id, status=TaskStatus.COMPLETED)
    assert completed is not None
    completed.result["value"] = "mutated"  # type: ignore[index]
    completed.context["trace"] = "mutated"
    stored = await manager.get(task.id)
    assert stored is not None
    assert stored.result == {"value": "A"}
    assert stored.context == {"trace": "safe"}
    with pytest.raises(PolicyViolation, match="terminal"):
        await manager.update(task.id, result={"value": "B"})


@pytest.mark.asyncio
async def test_non_json_result_cannot_be_sealed() -> None:
    manager = StateManager(REGISTRY)
    task = await manager.create(
        source=TaskSource.API.value,
        external_chat_id=None,
        intent="audit",
        payload={},
    )
    await manager.update(task.id, status=TaskStatus.PARSING)
    with pytest.raises(PolicyViolation, match="strict JSON"):
        await manager.update(
            task.id,
            status=TaskStatus.DRAFT,
            agent_id="worker:codex",
            result={"raw": b"secret"},
        )


def test_verification_contract_rejects_bool_revision_and_bad_digest() -> None:
    with pytest.raises(ValidationError):
        VerificationBundle(
            tenant_id="tenant-a",
            task_id=UUID("11111111-1111-4111-8111-111111111111"),
            contract_digest="sha256:" + "a" * 64,
            result_revision=True,
            result_digest="sha256:" + "b" * 64,
            executor_identity="worker",
            l1=None,
            l2=None,
            l3=None,
            status=VerificationBundleStatus.DRAFT,
        )
    with pytest.raises(ValidationError, match="sha256"):
        VerificationLevel(
            status=VerificationLevelStatus.PASSED,
            method="test",
            verifier_identity="verifier",
            verified_at=BASE_TIME,
            evidence_refs=("evidence",),
            evidence_digest="not-a-digest",
        )
