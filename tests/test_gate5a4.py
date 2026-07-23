"""Offline verification of the isolated Gate 5A.4 patch transaction."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.application.durable_runtime import PreparedTask
from src.application.fake_vertical import VerificationInput
from src.application.gate5a4 import Gate5A4Runtime, GitPatchVerificationPipeline
from src.application.patch_confirmation import PatchProposal, patch_proposal_digest
from src.contracts import TaskContract, VerificationLevelStatus
from src.core.policy import task_contract_digest
from src.models.task import TaskStatus
from src.contracts.models import canonical_json_digest


def _git() -> Path:
    value = shutil.which("git")
    assert value is not None
    return Path(value)


def _repo(path: Path) -> None:
    subprocess.run((_git(), "init", "-b", "agent/telegram-live"), cwd=path, check=True)
    subprocess.run((_git(), "config", "core.autocrlf", "false"), cwd=path, check=True)
    (path / "safe.txt").write_bytes(b"before\n")
    subprocess.run((_git(), "add", "safe.txt"), cwd=path, check=True)
    subprocess.run(
        (
            _git(), "-c", "user.name=Test", "-c", "user.email=test@localhost",
            "commit", "-m", "baseline",
        ),
        cwd=path,
        check=True,
    )


def _candidate(message: str) -> VerificationInput:
    return VerificationInput(
        tenant_id="owner",
        task_id=uuid4(),
        contract_digest="sha256:" + "a" * 64,
        result_revision=1,
        result_digest="sha256:" + "b" * 64,
        output_digest=canonical_json_digest({"message": message}),
        worker_message=message,
    )


def _message() -> str:
    patch = (
        "diff --git a/safe.txt b/safe.txt\n"
        "--- a/safe.txt\n"
        "+++ b/safe.txt\n"
        "@@ -1 +1 @@\n"
        "-before\n"
        "+after\n"
    )
    return json.dumps(
        {"summary": "Change safe text.", "patch": patch, "paths": ["safe.txt"]},
        separators=(",", ":"),
    )


@pytest.mark.asyncio
async def test_patch_pipeline_checks_tests_and_commits_in_isolated_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo(tmp_path)
    pipeline = GitPatchVerificationPipeline(
        worktree=tmp_path,
        git_executable=_git(),
        python_executable=Path(__import__("sys").executable),
    )

    async def tests_pass() -> None:
        return None

    monkeypatch.setattr(pipeline, "_run_tests", tests_pass)
    candidate = _candidate(_message())

    assert (await pipeline.l1(candidate)).status is VerificationLevelStatus.PASSED
    assert (await pipeline.l2(candidate)).status is VerificationLevelStatus.PASSED
    assert (await pipeline.l3(candidate)).status is VerificationLevelStatus.PASSED
    assert subprocess.run(
        (_git(), "status", "--porcelain"), cwd=tmp_path, check=True,
        capture_output=True, text=True,
    ).stdout == "M  safe.txt\n"
    await pipeline.commit(candidate.task_id, candidate)
    await pipeline.finalize(candidate.task_id)
    assert (tmp_path / "safe.txt").read_bytes() == b"after\n"
    assert subprocess.run(
        (_git(), "status", "--porcelain"), cwd=tmp_path, check=True,
        capture_output=True, text=True,
    ).stdout == ""


@pytest.mark.asyncio
async def test_failed_l2_restores_clean_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo(tmp_path)
    pipeline = GitPatchVerificationPipeline(
        worktree=tmp_path,
        git_executable=_git(),
        python_executable=Path(__import__("sys").executable),
    )

    async def tests_fail() -> None:
        raise RuntimeError("test failure")

    monkeypatch.setattr(pipeline, "_run_tests", tests_fail)
    candidate = _candidate(_message())

    assert (await pipeline.l1(candidate)).status is VerificationLevelStatus.PASSED
    assert (await pipeline.l2(candidate)).status is VerificationLevelStatus.FAILED
    assert (tmp_path / "safe.txt").read_bytes() == b"before\n"
    assert subprocess.run(
        (_git(), "status", "--porcelain"), cwd=tmp_path, check=True,
        capture_output=True, text=True,
    ).stdout == ""
    assert not pipeline._journal_path.exists()

    async def tests_pass() -> None:
        return None

    monkeypatch.setattr(pipeline, "_run_tests", tests_pass)
    next_candidate = _candidate(_message())
    assert (
        await pipeline.l1(next_candidate)
    ).status is VerificationLevelStatus.PASSED
    assert (
        await pipeline.l2(next_candidate)
    ).status is VerificationLevelStatus.PASSED
    await pipeline.discard(next_candidate.task_id)


@pytest.mark.asyncio
async def test_l1_rejects_wrong_branch_and_never_changes_files(tmp_path: Path) -> None:
    subprocess.run((_git(), "init", "-b", "main"), cwd=tmp_path, check=True)
    (tmp_path / "safe.txt").write_bytes(b"before\n")
    subprocess.run((_git(), "add", "safe.txt"), cwd=tmp_path, check=True)
    subprocess.run(
        (_git(), "-c", "user.name=Test", "-c", "user.email=test@localhost", "commit", "-m", "baseline"),
        cwd=tmp_path,
        check=True,
    )
    pipeline = GitPatchVerificationPipeline(
        worktree=tmp_path,
        git_executable=_git(),
        python_executable=Path(__import__("sys").executable),
    )

    result = await pipeline.l1(_candidate(_message()))

    assert result.status is VerificationLevelStatus.FAILED
    assert (tmp_path / "safe.txt").read_bytes() == b"before\n"

@pytest.mark.asyncio
async def test_discard_rolls_back_only_own_authorized_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo(tmp_path)
    pipeline = GitPatchVerificationPipeline(
        worktree=tmp_path,
        git_executable=_git(),
        python_executable=Path(__import__("sys").executable),
    )

    async def tests_pass() -> None:
        return None

    monkeypatch.setattr(pipeline, "_run_tests", tests_pass)
    candidate = _candidate(_message())
    baseline = subprocess.run(
        (_git(), "rev-parse", "HEAD"), cwd=tmp_path, check=True,
        capture_output=True, text=True,
    ).stdout.strip()

    assert (await pipeline.l1(candidate)).status is VerificationLevelStatus.PASSED
    assert (await pipeline.l2(candidate)).status is VerificationLevelStatus.PASSED
    assert (await pipeline.l3(candidate)).status is VerificationLevelStatus.PASSED
    assert subprocess.run(
        (_git(), "rev-parse", "HEAD"), cwd=tmp_path, check=True,
        capture_output=True, text=True,
    ).stdout.strip() == baseline

    await pipeline.commit(candidate.task_id, candidate)
    assert subprocess.run(
        (_git(), "rev-parse", "HEAD"), cwd=tmp_path, check=True,
        capture_output=True, text=True,
    ).stdout.strip() != baseline

    await pipeline.discard(candidate.task_id)
    assert subprocess.run(
        (_git(), "rev-parse", "HEAD"), cwd=tmp_path, check=True,
        capture_output=True, text=True,
    ).stdout.strip() == baseline
    assert (tmp_path / "safe.txt").read_bytes() == b"before\n"
    assert subprocess.run(
        (_git(), "status", "--porcelain"), cwd=tmp_path, check=True,
        capture_output=True, text=True,
    ).stdout == ""

@pytest.mark.asyncio
async def test_restart_reconciles_authorized_commit_to_durable_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo(tmp_path)
    pipeline = GitPatchVerificationPipeline(
        worktree=tmp_path,
        git_executable=_git(),
        python_executable=Path(__import__("sys").executable),
    )

    async def tests_pass() -> None:
        return None

    monkeypatch.setattr(pipeline, "_run_tests", tests_pass)
    candidate = _candidate(_message())
    baseline = subprocess.run(
        (_git(), "rev-parse", "HEAD"), cwd=tmp_path, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    assert (await pipeline.l1(candidate)).status is VerificationLevelStatus.PASSED
    assert (await pipeline.l2(candidate)).status is VerificationLevelStatus.PASSED
    assert (await pipeline.l3(candidate)).status is VerificationLevelStatus.PASSED
    await pipeline.commit(candidate.task_id, candidate)

    restarted = GitPatchVerificationPipeline(
        worktree=tmp_path,
        git_executable=_git(),
        python_executable=Path(__import__("sys").executable),
    )
    projection = SimpleNamespace(
        status=TaskStatus.EXECUTING,
        human_approval=object(),
    )
    store = SimpleNamespace(
        read_task=lambda tenant_id, task_id: SimpleNamespace(projection=projection)
    )

    restarted.reconcile(store)

    assert subprocess.run(
        (_git(), "rev-parse", "HEAD"), cwd=tmp_path, check=True,
        capture_output=True, text=True,
    ).stdout.strip() == baseline
    assert (tmp_path / "safe.txt").read_bytes() == b"before\n"
    assert subprocess.run(
        (_git(), "status", "--porcelain"), cwd=tmp_path, check=True,
        capture_output=True, text=True,
    ).stdout == ""

@pytest.mark.asyncio
async def test_restart_restores_exact_paths_after_crash_before_ref_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class SimulatedCrash(BaseException):
        pass

    _repo(tmp_path)
    pipeline = GitPatchVerificationPipeline(
        worktree=tmp_path,
        git_executable=_git(),
        python_executable=Path(__import__("sys").executable),
    )

    async def tests_pass() -> None:
        return None

    monkeypatch.setattr(pipeline, "_run_tests", tests_pass)
    candidate = _candidate(_message())
    baseline = subprocess.run(
        (_git(), "rev-parse", "HEAD"), cwd=tmp_path, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    assert (await pipeline.l1(candidate)).status is VerificationLevelStatus.PASSED
    assert (await pipeline.l2(candidate)).status is VerificationLevelStatus.PASSED
    assert (await pipeline.l3(candidate)).status is VerificationLevelStatus.PASSED
    original = pipeline._run_git

    async def crash_on_ref(*args: str, stdin: str | None = None) -> str:
        if args and args[0] == "update-ref":
            raise SimulatedCrash()
        return await original(*args, stdin=stdin)

    monkeypatch.setattr(pipeline, "_run_git", crash_on_ref)
    with pytest.raises(SimulatedCrash):
        await pipeline.commit(candidate.task_id, candidate)

    restarted = GitPatchVerificationPipeline(
        worktree=tmp_path,
        git_executable=_git(),
        python_executable=Path(__import__("sys").executable),
    )
    store = SimpleNamespace(read_task=lambda tenant_id, task_id: None)
    restarted.reconcile(store)

    assert subprocess.run(
        (_git(), "rev-parse", "HEAD"), cwd=tmp_path, check=True,
        capture_output=True, text=True,
    ).stdout.strip() == baseline
    assert (tmp_path / "safe.txt").read_bytes() == b"before\n"
    assert subprocess.run(
        (_git(), "status", "--porcelain"), cwd=tmp_path, check=True,
        capture_output=True, text=True,
    ).stdout == ""

@pytest.mark.asyncio
async def test_restart_restores_exact_paths_after_crash_during_l2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class SimulatedCrash(BaseException):
        pass

    _repo(tmp_path)
    pipeline = GitPatchVerificationPipeline(
        worktree=tmp_path,
        git_executable=_git(),
        python_executable=Path(__import__("sys").executable),
    )

    async def crash_in_tests() -> None:
        raise SimulatedCrash()

    monkeypatch.setattr(pipeline, "_run_tests", crash_in_tests)
    candidate = _candidate(_message())
    baseline = subprocess.run(
        (_git(), "rev-parse", "HEAD"), cwd=tmp_path, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    assert (await pipeline.l1(candidate)).status is VerificationLevelStatus.PASSED
    with pytest.raises(SimulatedCrash):
        await pipeline.l2(candidate)

    restarted = GitPatchVerificationPipeline(
        worktree=tmp_path,
        git_executable=_git(),
        python_executable=Path(__import__("sys").executable),
    )
    restarted.reconcile(SimpleNamespace(read_task=lambda tenant_id, task_id: None))

    assert subprocess.run(
        (_git(), "rev-parse", "HEAD"), cwd=tmp_path, check=True,
        capture_output=True, text=True,
    ).stdout.strip() == baseline
    assert (tmp_path / "safe.txt").read_bytes() == b"before\n"
    assert subprocess.run(
        (_git(), "status", "--porcelain"), cwd=tmp_path, check=True,
        capture_output=True, text=True,
    ).stdout == ""


@pytest.mark.asyncio
async def test_informational_answer_passes_three_read_only_levels(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    pipeline = GitPatchVerificationPipeline(
        worktree=tmp_path,
        git_executable=_git(),
        python_executable=Path(__import__("sys").executable),
    )
    candidate = _candidate(
        json.dumps({"answer": "Система готова к безопасной работе."}, ensure_ascii=False)
    )

    assert (await pipeline.l1(candidate)).status is VerificationLevelStatus.PASSED
    assert (await pipeline.l2(candidate)).status is VerificationLevelStatus.PASSED
    assert (await pipeline.l3(candidate)).status is VerificationLevelStatus.PASSED
    await pipeline.finalize(candidate.task_id)

    assert subprocess.run(
        (_git(), "status", "--porcelain"), cwd=tmp_path, check=True,
        capture_output=True, text=True,
    ).stdout == ""
    assert candidate.task_id not in pipeline._answers


@pytest.mark.asyncio
async def test_informational_answer_l1_rejects_local_path_disclosure(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    pipeline = GitPatchVerificationPipeline(
        worktree=tmp_path,
        git_executable=_git(),
        python_executable=Path(__import__("sys").executable),
    )
    candidate = _candidate('{"answer":"Read C:\\\\Users\\\\owner\\\\secret.txt"}')

    assert (await pipeline.l1(candidate)).status is VerificationLevelStatus.FAILED


@pytest.mark.asyncio
async def test_l1_retries_one_transient_git_preflight_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo(tmp_path)
    pipeline = GitPatchVerificationPipeline(
        worktree=tmp_path,
        git_executable=_git(),
        python_executable=Path(__import__("sys").executable),
    )
    original = pipeline._require_clean_branch
    calls = 0

    async def flaky_preflight() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("transient process failure")
        await original()

    monkeypatch.setattr(pipeline, "_require_clean_branch", flaky_preflight)
    candidate = _candidate(json.dumps({"answer": "Голосовой контур работает."}))

    assert (await pipeline.l1(candidate)).status is VerificationLevelStatus.PASSED
    assert calls == 2


@pytest.mark.asyncio
async def test_l1_remains_failed_after_one_transient_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo(tmp_path)
    pipeline = GitPatchVerificationPipeline(
        worktree=tmp_path,
        git_executable=_git(),
        python_executable=Path(__import__("sys").executable),
    )
    calls = 0

    async def unavailable_preflight() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("persistent process failure")

    monkeypatch.setattr(pipeline, "_require_clean_branch", unavailable_preflight)
    candidate = _candidate(json.dumps({"answer": "Safe answer."}))

    assert (await pipeline.l1(candidate)).status is VerificationLevelStatus.FAILED
    assert calls == 2
    assert candidate.task_id not in pipeline._answers
    assert candidate.task_id not in pipeline._drafts

def _lock_only_runtime() -> Gate5A4Runtime:
    runtime = object.__new__(Gate5A4Runtime)
    runtime._worker_slots = asyncio.Semaphore(2)  # type: ignore[attr-defined]
    runtime._exclusive_lock = asyncio.Lock()  # type: ignore[attr-defined]
    return runtime


@pytest.mark.asyncio
async def test_exclusive_l4_waits_for_both_drafts_and_blocks_new_draft() -> None:
    runtime = _lock_only_runtime()
    release_drafts = asyncio.Event()
    release_exclusive = asyncio.Event()
    both_drafts_started = asyncio.Event()
    exclusive_started = asyncio.Event()
    later_draft_started = asyncio.Event()
    draft_count = 0

    async def draft(started: asyncio.Event | None = None) -> None:
        nonlocal draft_count
        async with runtime._worker_slots:  # type: ignore[attr-defined]
            draft_count += 1
            if draft_count == 2:
                both_drafts_started.set()
            if started is not None:
                started.set()
            await release_drafts.wait()

    async def exclusive() -> None:
        async with runtime._exclusive_worker_slots():
            exclusive_started.set()
            await release_exclusive.wait()

    first = asyncio.create_task(draft())
    second = asyncio.create_task(draft())
    await asyncio.wait_for(both_drafts_started.wait(), timeout=1)
    owner_apply = asyncio.create_task(exclusive())
    await asyncio.sleep(0)
    assert not exclusive_started.is_set()

    release_drafts.set()
    await asyncio.gather(first, second)
    await asyncio.wait_for(exclusive_started.wait(), timeout=1)
    later = asyncio.create_task(draft(later_draft_started))
    await asyncio.sleep(0)
    assert not later_draft_started.is_set()

    release_exclusive.set()
    await owner_apply
    await asyncio.wait_for(later_draft_started.wait(), timeout=1)
    await later


@pytest.mark.asyncio
async def test_two_exclusive_l4_operations_are_serialized() -> None:
    runtime = _lock_only_runtime()
    active = 0
    maximum = 0

    async def exclusive() -> None:
        nonlocal active, maximum
        async with runtime._exclusive_worker_slots():
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.01)
            active -= 1

    await asyncio.gather(exclusive(), exclusive())

    assert maximum == 1


@pytest.mark.asyncio
async def test_cancelled_partial_exclusive_acquire_releases_every_permit() -> None:
    runtime = _lock_only_runtime()
    await runtime._worker_slots.acquire()  # type: ignore[attr-defined]

    async def exclusive() -> None:
        async with runtime._exclusive_worker_slots():
            raise AssertionError("must remain blocked")

    owner_apply = asyncio.create_task(exclusive())
    for _ in range(10):
        await asyncio.sleep(0)
        if runtime._worker_slots._value == 0:  # type: ignore[attr-defined]
            break
    assert runtime._worker_slots._value == 0  # type: ignore[attr-defined]

    owner_apply.cancel()
    with pytest.raises(asyncio.CancelledError):
        await owner_apply
    runtime._worker_slots.release()  # type: ignore[attr-defined]

    await asyncio.wait_for(runtime._worker_slots.acquire(), timeout=1)  # type: ignore[attr-defined]
    await asyncio.wait_for(runtime._worker_slots.acquire(), timeout=1)  # type: ignore[attr-defined]
    runtime._worker_slots.release()  # type: ignore[attr-defined]
    runtime._worker_slots.release()  # type: ignore[attr-defined]


def _bound_gate_inputs() -> tuple[PreparedTask, PatchProposal]:
    task_id = uuid4()
    ingress_digest = "sha256:" + "1" * 64
    contract = TaskContract(
        task_id=task_id,
        idempotency_key=f"owner:gate-wrapper:{task_id}",
        ingress_digest=ingress_digest,
        tenant_id="owner",
        source="api",
        instruction="Prepare one bounded read-only result.",
        allowed_paths=(str(Path.cwd()),),
        permissions=("repo.read", "process.run_allowlisted"),
        risk="medium",
        acceptance_criteria=("Return one safe result.",),
        timeout_seconds=7_200,
        quality_profile="gate5a4-two-phase-patch@1",
    )
    prepared = PreparedTask(contract=contract, envelope_revision=ingress_digest)
    patch = (
        "diff --git a/safe.txt b/safe.txt\n"
        "--- a/safe.txt\n"
        "+++ b/safe.txt\n"
        "@@ -1 +1 @@\n"
        "-before\n"
        "+after\n"
    )
    values: dict[str, object] = {
        "tenant_id": contract.tenant_id,
        "task_id": task_id,
        "contract_digest": task_contract_digest(contract),
        "result_revision": 1,
        "result_digest": canonical_json_digest({"result": "draft"}),
        "output_digest": canonical_json_digest({"output": "draft"}),
        "summary": "Update safe.txt",
        "patch": patch,
        "paths": ("safe.txt",),
    }
    proposal = PatchProposal(
        **values,
        patch_digest=patch_proposal_digest({**values, "task_id": str(task_id)}),
    )
    return prepared, proposal


@pytest.mark.asyncio
async def test_real_gate_methods_enforce_draft_and_l4_slot_wrappers() -> None:
    runtime = _lock_only_runtime()
    prepared, proposal = _bound_gate_inputs()
    release_drafts = asyncio.Event()
    release_apply = asyncio.Event()
    two_drafts_started = asyncio.Event()
    apply_started = asyncio.Event()
    later_draft_started = asyncio.Event()
    draft_calls = 0

    async def blocked_prepared_task(contract: TaskContract) -> object:
        nonlocal draft_calls
        draft_calls += 1
        if draft_calls == 2:
            two_drafts_started.set()
        if draft_calls == 3:
            later_draft_started.set()
        await release_drafts.wait()
        raise RuntimeError("synthetic prepared lookup stop")

    async def blocked_proposal_task(candidate: PatchProposal) -> object:
        apply_started.set()
        await release_apply.wait()
        raise RuntimeError("synthetic proposal lookup stop")

    runtime._prepared_task = blocked_prepared_task  # type: ignore[method-assign]
    runtime._proposal_task = blocked_proposal_task  # type: ignore[method-assign]
    first = asyncio.create_task(runtime.draft_prepared(prepared))
    second = asyncio.create_task(runtime.draft_prepared(prepared))
    await asyncio.wait_for(two_drafts_started.wait(), timeout=1)
    owner_apply = asyncio.create_task(
        runtime.apply_proposal(
            proposal,
            approver_identity="telegram:owner",
            approval_evidence_ref="telegram-owner-confirmation:" + "a" * 64,
        )
    )
    await asyncio.sleep(0)
    assert not apply_started.is_set()

    release_drafts.set()
    await asyncio.gather(first, second)
    await asyncio.wait_for(apply_started.wait(), timeout=1)
    later = asyncio.create_task(runtime.draft_prepared(prepared))
    await asyncio.sleep(0)
    assert not later_draft_started.is_set()

    release_apply.set()
    assert (await owner_apply).status.value == "failed"
    await asyncio.wait_for(later_draft_started.wait(), timeout=1)
    await later

    assert (await runtime.reject_proposal(proposal)).status.value == "failed"
