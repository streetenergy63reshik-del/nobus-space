"""Live read-only Codex draft with owner-confirmed isolated Git application."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import threading
from dataclasses import dataclass
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.application.durable_runtime import DurableFakeRuntime, PreparedTask
from src.application.patch_confirmation import PatchProposal, patch_proposal_digest
from src.application.fake_vertical import FakeVerticalResponse, FakeVerticalStatus
from src.application.fake_vertical import VerificationInput
from src.contracts import (
    HumanApprovalRecord,
    RiskLevel,
    TaskContract,
    TrustedIngressEnvelope,
    VerificationLevel,
    VerificationLevelStatus,
    VerificationBundle,
    VerificationBundleStatus,
)
from src.contracts.models import canonical_json_digest
from src.core.policy import (
    InMemoryPolicyStore,
    TrustedVerifierRegistry,
    task_contract_digest,
)
from src.models.task import Task, TaskStatus
from src.orchestrator.state_manager import StateManager
from src.storage import SQLiteStore
from src.transport.telegram import TelegramGateway
from src.workers.asyncio_spawner import AsyncioProcessSpawner
from src.workers.codex_cli import CodexCliAdapter, build_worker_env
from src.workers.codex_patch import CodexPatchDraft, CodexPatchError, parse_codex_patch, validate_codex_patch_path
from src.workers.windows_job import WindowsJobLauncher


_VERIFIER_IDENTITIES = {
    1: "verifier:gate5a4:patch-preflight",
    2: "verifier:gate5a4:test-suite",
    3: "verifier:gate5a4:staged-audit",
}
_CRITERIA = (
    "Return exactly one JSON object with keys summary, patch, paths and no markdown fences.",
    "patch is a UTF-8 unified Git diff for text files only; paths exactly list changed files.",
    "Do not modify files, use network, inspect credentials, or access paths outside the repository.",
    "Keep the change minimal and include or update tests where behavior changes.",
)


class Gate5A4DraftOutcome(BaseModel):
    """Safe result of the read-only phase; raw patch remains process-memory only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: FakeVerticalStatus
    task_id: UUID | None = None
    proposal: PatchProposal | None = None
    message: str



class _CommitJournal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    tenant_id: str = Field(min_length=1, max_length=128)
    task_id: UUID
    baseline: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40,64}$")
    paths: tuple[str, ...] = Field(min_length=1, max_length=20)


class Gate5A4Runtime(DurableFakeRuntime):
    """Two-phase worker: read-only proposal first, exact patch approval second."""

    _EXECUTOR_IDENTITY = "worker:codex-cli-readonly-patch"

    def __init__(
        self, *, pipeline: "GitPatchVerificationPipeline", **values: object
    ) -> None:
        super().__init__(**values)
        self._pipeline = pipeline
        self._execution_lock = asyncio.Lock()

    def _contract(
        self, instruction: str, envelope: TrustedIngressEnvelope
    ) -> TaskContract:
        base = super()._contract(instruction, envelope)
        values = base.model_dump(mode="python")
        values.update(
            permissions=("repo.read", "process.run_allowlisted"),
            risk=RiskLevel.HIGH,
            acceptance_criteria=_CRITERIA,
            timeout_seconds=120,
            quality_profile="gate5a4-two-phase-patch@1",
        )
        return TaskContract.model_validate(values)

    async def execute_prepared(self, prepared: PreparedTask) -> FakeVerticalResponse:
        """Fail closed: a single task confirmation can never apply a patch."""
        return self._response(
            FakeVerticalStatus.REJECTED,
            "Exact patch confirmation is required.",
            task_id=getattr(getattr(prepared, "contract", None), "task_id", None),
        )

    async def draft_prepared(self, prepared: PreparedTask) -> Gate5A4DraftOutcome:
        """Run Codex read-only and persist only the L1/content-free task state."""
        async with self._execution_lock:
            task: Task | None = None
            try:
                prepared = PreparedTask.validate(prepared)
                contract = prepared.contract
                task = await self._prepared_task(contract)
                task = await self._start_worker(contract, task)
                worker_result = await self._worker.execute(contract)
                task = await self._record_worker_result(
                    contract, task, worker_result.message
                )
                candidate = self._candidate(task, worker_result.message)
                l1 = VerificationLevel.model_validate(
                    (await self._pipeline.l1(candidate)).model_dump()
                )
                passed = l1.status is VerificationLevelStatus.PASSED
                task = await self._required_update(
                    task.id,
                    status=TaskStatus.L1_VALIDATED if passed else TaskStatus.REJECTED,
                    verification_bundle=self._bundle(
                        task,
                        l1=l1,
                        status=(
                            VerificationBundleStatus.DRAFT
                            if passed
                            else VerificationBundleStatus.REJECTED
                        ),
                    ),
                    error_message=None if passed else "l1_failed",
                )
                if not passed:
                    return Gate5A4DraftOutcome(
                        status=FakeVerticalStatus.FAILED,
                        task_id=task.id,
                        message="Patch preflight rejected.",
                    )
                proposal = self._proposal(candidate)
                return Gate5A4DraftOutcome(
                    status=FakeVerticalStatus.COMPLETED,
                    task_id=task.id,
                    proposal=proposal,
                    message="Read-only patch draft is ready for exact confirmation.",
                )
            except asyncio.CancelledError:
                if task is not None:
                    await self._escalate(task)
                raise
            except Exception:
                if task is not None:
                    await self._escalate(task)
                return Gate5A4DraftOutcome(
                    status=FakeVerticalStatus.FAILED,
                    task_id=task.id if task is not None else None,
                    message="Read-only patch draft failed.",
                )

    async def apply_proposal(
        self,
        proposal: PatchProposal,
        *,
        approver_identity: str,
        approval_evidence_ref: str,
    ) -> FakeVerticalResponse:
        """Apply only an exact owner-approved proposal through L2/L3/L4."""
        async with self._execution_lock:
            task: Task | None = None
            try:
                proposal = PatchProposal.model_validate(
                    proposal.model_dump(mode="python")
                )
                if (
                    not isinstance(approver_identity, str)
                    or not approver_identity.strip()
                    or not isinstance(approval_evidence_ref, str)
                    or not approval_evidence_ref.strip()
                ):
                    raise ValueError("owner approval binding is invalid")
                task = await self._proposal_task(proposal)
                message = json.dumps(
                    {
                        "summary": proposal.summary,
                        "patch": proposal.patch,
                        "paths": list(proposal.paths),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                candidate = self._candidate(task, message)
                if candidate.output_digest != proposal.output_digest:
                    raise ValueError("proposal output binding mismatch")
                assert task.verification_bundle is not None
                l1 = task.verification_bundle.l1
                assert l1 is not None
                l2 = VerificationLevel.model_validate(
                    (await self._pipeline.l2(candidate)).model_dump()
                )
                passed = l2.status is VerificationLevelStatus.PASSED
                task = await self._required_update(
                    task.id,
                    status=TaskStatus.L2_VERIFIED if passed else TaskStatus.REJECTED,
                    verification_bundle=self._bundle(
                        task,
                        l1=l1,
                        l2=l2,
                        status=(
                            VerificationBundleStatus.DRAFT
                            if passed
                            else VerificationBundleStatus.REJECTED
                        ),
                    ),
                    error_message=None if passed else "l2_failed",
                )
                if not passed:
                    return self._response(
                        FakeVerticalStatus.FAILED,
                        "Patch tests failed and the worktree was restored.",
                        task_id=task.id,
                    )
                l3 = VerificationLevel.model_validate(
                    (await self._pipeline.l3(candidate)).model_dump()
                )
                passed = l3.status is VerificationLevelStatus.PASSED
                task = await self._required_update(
                    task.id,
                    status=TaskStatus.L3_APPROVED if passed else TaskStatus.REJECTED,
                    verification_bundle=self._bundle(
                        task,
                        l1=l1,
                        l2=l2,
                        l3=l3,
                        status=(
                            VerificationBundleStatus.APPROVED
                            if passed
                            else VerificationBundleStatus.REJECTED
                        ),
                    ),
                    error_message=None if passed else "l3_failed",
                )
                if not passed:
                    return self._response(
                        FakeVerticalStatus.FAILED,
                        "Patch audit failed and the worktree was restored.",
                        task_id=task.id,
                    )
                task = await self._required_update(task.id, status=TaskStatus.WAITING_HUMAN)
                approval = HumanApprovalRecord(
                    tenant_id=task.tenant_id,
                    task_id=task.id,
                    contract_digest=task.contract_digest,
                    result_revision=task.result_revision,
                    result_digest=task.result_digest,
                    approver_identity=approver_identity.strip(),
                    approved_at=datetime.now(UTC),
                    evidence_ref=approval_evidence_ref.strip(),
                )
                task = await self._required_update(
                    task.id,
                    status=TaskStatus.HUMAN_APPROVED,
                    human_approval=approval,
                )
                task = await self._required_update(task.id, status=TaskStatus.EXECUTING)
                await self._pipeline.commit(task.id, candidate)
                task = await self._complete(task)
                await self._pipeline.finalize(task.id)
                return self._response(
                    FakeVerticalStatus.COMPLETED,
                    "Exact patch was tested and committed in the isolated branch.",
                    task_id=task.id,
                    result_digest=task.result_digest,
                )
            except asyncio.CancelledError:
                if task is not None:
                    await self._pipeline.discard(task.id)
                    await self._escalate(task)
                raise
            except Exception:
                if task is not None:
                    await self._pipeline.discard(task.id)
                    await self._escalate(task)
                return self._response(
                    FakeVerticalStatus.FAILED,
                    "Exact patch application failed safely.",
                    task_id=task.id if task is not None else proposal.task_id,
                )

    async def reject_proposal(self, proposal: PatchProposal) -> FakeVerticalResponse:
        async with self._execution_lock:
            try:
                proposal = PatchProposal.model_validate(
                    proposal.model_dump(mode="python")
                )
                task = await self._proposal_task(proposal)
                await self._pipeline.discard(task.id)
                task = await self._required_update(
                    task.id,
                    status=TaskStatus.REJECTED,
                    error_message="patch_rejected_by_owner",
                )
                return self._response(
                    FakeVerticalStatus.REJECTED,
                    "Patch was rejected by the owner.",
                    task_id=task.id,
                )
            except Exception:
                return self._response(
                    FakeVerticalStatus.FAILED,
                    "Patch proposal is unavailable.",
                    task_id=getattr(proposal, "task_id", None),
                )

    async def _prepared_task(self, contract: TaskContract) -> Task:
        task = await self._state.get(contract.task_id)
        snapshot = self._store.read_task(contract.tenant_id, contract.task_id)
        if (
            task is None
            or snapshot is None
            or task.status is not TaskStatus.PENDING
            or snapshot.projection.status is not TaskStatus.PENDING
            or task.contract_digest != task_contract_digest(contract)
            or snapshot.projection.contract_digest != task.contract_digest
            or self._revisions.get(task.id) != snapshot.revision
        ):
            raise ValueError("prepared task binding mismatch")
        return task

    async def _proposal_task(self, proposal: PatchProposal) -> Task:
        task = await self._state.get(proposal.task_id)
        snapshot = self._store.read_task(proposal.tenant_id, proposal.task_id)
        if (
            task is None
            or snapshot is None
            or task.status is not TaskStatus.L1_VALIDATED
            or snapshot.projection.status is not TaskStatus.L1_VALIDATED
            or task.tenant_id != proposal.tenant_id
            or task.contract_digest != proposal.contract_digest
            or task.result_revision != proposal.result_revision
            or task.result_digest != proposal.result_digest
            or task.result is None
            or task.result.get("output_digest") != proposal.output_digest
            or task.verification_bundle is None
            or task.verification_bundle.l1 is None
            or task.verification_bundle.l1.status
            is not VerificationLevelStatus.PASSED
            or self._revisions.get(task.id) != snapshot.revision
        ):
            raise ValueError("patch proposal binding mismatch")
        return task

    @staticmethod
    def _candidate(task: Task, message: str) -> VerificationInput:
        if task.result is None or task.result_digest is None:
            raise ValueError("worker result binding unavailable")
        output_digest = task.result.get("output_digest")
        if not isinstance(output_digest, str):
            raise ValueError("worker output binding unavailable")
        return VerificationInput(
            tenant_id=task.tenant_id,
            task_id=task.id,
            contract_digest=task.contract_digest,
            result_revision=task.result_revision,
            result_digest=task.result_digest,
            output_digest=output_digest,
            worker_message=message,
        )

    def _proposal(self, candidate: VerificationInput) -> PatchProposal:
        draft = parse_codex_patch(candidate.worker_message, self._pipeline.root)
        values: dict[str, object] = {
            "tenant_id": candidate.tenant_id,
            "task_id": candidate.task_id,
            "contract_digest": candidate.contract_digest,
            "result_revision": candidate.result_revision,
            "result_digest": candidate.result_digest,
            "output_digest": candidate.output_digest,
            "summary": draft.summary,
            "patch": draft.patch,
            "paths": draft.paths,
        }
        return PatchProposal(
            **values,
            patch_digest=patch_proposal_digest({**values, "task_id": str(candidate.task_id)}),
        )

    @staticmethod
    def _bundle(
        task: Task,
        *,
        l1: VerificationLevel,
        l2: VerificationLevel | None = None,
        l3: VerificationLevel | None = None,
        status: VerificationBundleStatus,
    ) -> VerificationBundle:
        return VerificationBundle(
            tenant_id=task.tenant_id,
            task_id=task.id,
            contract_digest=task.contract_digest,
            result_revision=task.result_revision,
            result_digest=task.result_digest,
            executor_identity=task.agent_id,
            l1=l1,
            l2=l2,
            l3=l3,
            status=status,
        )

@dataclass(frozen=True)
class _DraftState:
    draft: CodexPatchDraft
    baseline: str
    applied_digest: str | None = None


@dataclass(frozen=True)
class _CommitState:
    baseline: str
    commit: str


class GitPatchVerificationPipeline:
    """Verify an exact patch, then commit only after the Core L4 transition."""

    def __init__(
        self,
        *,
        worktree: str | Path,
        git_executable: str | Path,
        python_executable: str | Path,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        command_timeout: int = 180,
    ) -> None:
        try:
            root = Path(worktree).resolve(strict=True)
            git = Path(git_executable).resolve(strict=True)
            python = Path(python_executable).resolve(strict=True)
            valid = (
                root.is_dir()
                and git.is_file()
                and python.is_file()
                and callable(clock)
                and type(command_timeout) is int
                and 30 <= command_timeout <= 600
            )
        except (OSError, RuntimeError, TypeError):
            valid = False
        if not valid:
            raise ValueError("Gate 5A.4 verifier configuration is invalid")
        self._root = root
        self._git = git
        self._python = python
        self._clock = clock
        self._timeout = command_timeout
        self._drafts: dict[UUID, _DraftState] = {}
        self._commits: dict[UUID, _CommitState] = {}
        self._journal_path = root.parent / ".runtime" / f"{root.name}-gate5a4-commit.json"

    @property
    def root(self) -> Path:
        return self._root

    async def l1(self, candidate: VerificationInput) -> VerificationLevel:
        try:
            draft = parse_codex_patch(candidate.worker_message, self._root)
            await self._require_clean_branch()
            await self._run_git(
                "apply", "--check", "--whitespace=error-all", "-", stdin=draft.patch
            )
            baseline = (await self._run_git("rev-parse", "--verify", "HEAD")).strip()
            if not 40 <= len(baseline) <= 64 or any(
                character not in "0123456789abcdef" for character in baseline
            ):
                raise RuntimeError("invalid baseline")
            self._drafts[candidate.task_id] = _DraftState(draft, baseline)
            return self._level(candidate, 1, True, "patch schema and git apply-check")
        except (CodexPatchError, RuntimeError):
            self._drafts.pop(candidate.task_id, None)
            return self._level(candidate, 1, False, "patch preflight rejected")

    async def l2(self, candidate: VerificationInput) -> VerificationLevel:
        state = self._matching_draft(candidate)
        if state is None:
            return self._level(candidate, 2, False, "patch binding unavailable")
        try:
            await self._require_exact_baseline(state.baseline)
            self._write_journal(
                _CommitJournal(
                    tenant_id=candidate.tenant_id,
                    task_id=candidate.task_id,
                    baseline=state.baseline,
                    paths=state.draft.paths,
                )
            )
            await self._run_git("apply", "--whitespace=error-all", "-", stdin=state.draft.patch)
            await self._run_git("diff", "--check")
            await self._require_changed_paths(state.draft.paths)
            await self._run_tests()
            await self._require_changed_paths(state.draft.paths)
            applied_digest = self._worktree_digest(state.draft.paths)
            self._drafts[candidate.task_id] = _DraftState(
                state.draft, state.baseline, applied_digest
            )
            return self._level(candidate, 2, True, "full local pytest after exact patch confirmation")
        except asyncio.CancelledError:
            await self._restore_paths(state, candidate.task_id)
            self._drafts.pop(candidate.task_id, None)
            raise
        except RuntimeError:
            await self._restore_paths(state, candidate.task_id)
            self._drafts.pop(candidate.task_id, None)
            return self._level(candidate, 2, False, "tests or patch application failed")

    async def l3(self, candidate: VerificationInput) -> VerificationLevel:
        state = self._matching_draft(candidate)
        if state is None:
            return self._level(candidate, 3, False, "patch binding unavailable")
        try:
            await self._require_exact_baseline(state.baseline, clean=False)
            await self._require_changed_paths(state.draft.paths)
            if (
                state.applied_digest is None
                or self._worktree_digest(state.draft.paths) != state.applied_digest
            ):
                raise RuntimeError("post-test content digest mismatch")
            await self._run_git("diff", "--check")
            await self._run_git("add", "--", *state.draft.paths)
            await self._run_git("diff", "--cached", "--check")
            await self._require_changed_paths(state.draft.paths, staged=True)
            if self._worktree_digest(state.draft.paths) != state.applied_digest:
                raise RuntimeError("staged content digest mismatch")
            return self._level(candidate, 3, True, "independent staged-path and content audit")
        except asyncio.CancelledError:
            await self._restore_paths(state, candidate.task_id)
            self._drafts.pop(candidate.task_id, None)
            raise
        except RuntimeError:
            await self._restore_paths(state, candidate.task_id)
            self._drafts.pop(candidate.task_id, None)
            return self._level(candidate, 3, False, "staged audit verification failed")

    async def commit(self, task_id: UUID, candidate: VerificationInput) -> None:
        """Create the local commit after an atomic HUMAN_APPROVED state exists."""
        state = self._matching_draft(candidate)
        if state is None or candidate.task_id != task_id:
            raise RuntimeError("patch binding unavailable")
        try:
            await self._require_exact_baseline(state.baseline, clean=False)
            await self._require_changed_paths(state.draft.paths, staged=True)
            if (
                state.applied_digest is None
                or self._worktree_digest(state.draft.paths) != state.applied_digest
            ):
                raise RuntimeError("pre-commit content digest mismatch")
            tree = (await self._run_git("write-tree")).strip()
            commit = (
                await self._run_git(
                    "-c", "user.name=Nobus Space",
                    "-c", "user.email=nobus-space@localhost",
                    "commit-tree", tree,
                    "-p", state.baseline,
                    "-m", f"feat: apply Telegram task {str(task_id)[:8]}",
                )
            ).strip()
            journal = _CommitJournal(
                tenant_id=candidate.tenant_id,
                task_id=task_id,
                baseline=state.baseline,
                commit=commit,
                paths=state.draft.paths,
            )
            self._write_journal(journal)
            self._commits[task_id] = _CommitState(state.baseline, commit)
            await self._run_git(
                "update-ref", "refs/heads/agent/telegram-live", commit, state.baseline,
            )
            status = await self._run_git(
                "status", "--porcelain=v1", "--untracked-files=all"
            )
            if commit == state.baseline or status.strip():
                raise RuntimeError("post-commit state mismatch")
            self._drafts.pop(task_id, None)
        except asyncio.CancelledError:
            await self._restore_paths(state, task_id)
            self._drafts.pop(task_id, None)
            raise
        except RuntimeError:
            await self._rollback_if_own_commit(task_id, state.baseline)
            await self._restore_paths(state, task_id)
            self._drafts.pop(task_id, None)
            raise

    async def finalize(self, task_id: UUID) -> None:
        self._drafts.pop(task_id, None)
        self._commits.pop(task_id, None)
        self._clear_journal(task_id)

    def _matching_draft(self, candidate: VerificationInput) -> _DraftState | None:
        state = self._drafts.get(candidate.task_id)
        if state is None:
            return None
        try:
            parsed = parse_codex_patch(candidate.worker_message, self._root)
        except CodexPatchError:
            return None
        return state if parsed == state.draft else None

    async def discard(self, task_id: UUID) -> None:
        state = self._drafts.pop(task_id, None)
        if state is not None:
            await self._restore_paths(state, task_id)
        commit = self._commits.get(task_id)
        if commit is not None:
            await self._rollback_if_own_commit(task_id, commit.baseline)
        self._commits.pop(task_id, None)
    async def _require_exact_baseline(
        self, baseline: str, *, clean: bool = True
    ) -> None:
        current = (await self._run_git("rev-parse", "--verify", "HEAD")).strip()
        if current != baseline:
            raise RuntimeError("worktree baseline changed")
        if clean:
            status = await self._run_git(
                "status", "--porcelain=v1", "--untracked-files=all"
            )
            if status.strip():
                raise RuntimeError("worktree is not clean")

    async def _require_changed_paths(
        self, paths: tuple[str, ...], *, staged: bool = False
    ) -> None:
        if staged:
            names = await self._run_git(
                "diff", "--cached", "--name-only", "--no-renames"
            )
            unstaged = await self._run_git("diff", "--name-only", "--no-renames")
            untracked = await self._run_git("ls-files", "--others", "--exclude-standard")
            if unstaged.strip() or untracked.strip():
                raise RuntimeError("unstaged change detected")
        else:
            names = await self._run_git("diff", "--name-only", "--no-renames")
            untracked = await self._run_git("ls-files", "--others", "--exclude-standard")
            if untracked.strip():
                names = f"{names.rstrip()}\n{untracked.rstrip()}\n"
        changed = tuple(line for line in names.splitlines() if line)
        if len(changed) != len(paths) or set(changed) != set(paths):
            raise RuntimeError("changed path manifest mismatch")

    def _worktree_digest(self, paths: tuple[str, ...]) -> str:
        manifest: list[dict[str, object]] = []
        for relative in paths:
            path = self._root.joinpath(*relative.split("/"))
            if path.is_symlink():
                raise RuntimeError("symlink path is forbidden")
            if path.exists():
                if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
                    raise RuntimeError("changed file is invalid")
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                manifest.append({"path": relative, "sha256": digest})
            else:
                manifest.append({"path": relative, "deleted": True})
        return canonical_json_digest(manifest)
    async def _require_clean_branch(self) -> None:
        top = (await self._run_git("rev-parse", "--show-toplevel")).strip()
        try:
            if Path(top).resolve(strict=True) != self._root:
                raise RuntimeError("unexpected repository identity")
        except (OSError, RuntimeError):
            raise RuntimeError("unexpected repository identity") from None
        branch = (await self._run_git("branch", "--show-current")).strip()
        if branch != "agent/telegram-live":
            raise RuntimeError("unexpected worktree branch")
        status = await self._run_git("status", "--porcelain=v1", "--untracked-files=all")
        if status.strip():
            raise RuntimeError("worktree is not clean")

    async def _run_tests(self) -> None:
        env = _test_environment(self._root)
        await self._run(
            self._python,
            ("-m", "pytest", "-q", "--disable-warnings", "-p", "no:cacheprovider"),
            env=env,
        )

    async def _run_git(self, *args: str, stdin: str | None = None) -> str:
        null_device = "NUL" if os.name == "nt" else "/dev/null"
        safe_args = (
            "-c", f"core.hooksPath={null_device}",
            "-c", "core.fsmonitor=false",
            "-c", "diff.external=",
            "-c", f"core.attributesFile={null_device}",
            *args,
        )
        return await self._run(
            self._git, safe_args, stdin=stdin, env=_git_environment()
        )

    async def _run(
        self,
        executable: Path,
        args: Sequence[str],
        *,
        stdin: str | None = None,
        env: Mapping[str, str],
    ) -> str:
        cancelled = threading.Event()
        holder: dict[str, subprocess.Popen[bytes]] = {}

        def invoke() -> tuple[int, bytes, bytes]:
            options: dict[str, object] = {
                "cwd": self._root,
                "env": dict(env),
                "stdin": subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "shell": False,
            }
            if os.name == "nt":
                options["creationflags"] = subprocess.CREATE_NO_WINDOW
            else:
                options["start_new_session"] = True
            process = subprocess.Popen((str(executable), *args), **options)
            holder["process"] = process
            if cancelled.is_set():
                self._terminate_process_tree(process)
            try:
                stdout, stderr = process.communicate(
                    input=stdin.encode("utf-8") if stdin is not None else None,
                    timeout=self._timeout,
                )
            except subprocess.TimeoutExpired:
                self._terminate_process_tree(process)
                stdout, stderr = process.communicate()
                return -1, stdout, stderr
            return process.returncode, stdout, stderr

        task = asyncio.create_task(asyncio.to_thread(invoke))
        was_cancelled = False
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            was_cancelled = True
            cancelled.set()
            process = holder.get("process")
            if process is not None:
                self._terminate_process_tree(process)
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
        try:
            returncode, stdout, stderr = task.result()
        except Exception:
            raise RuntimeError("bounded command failed") from None
        if was_cancelled:
            raise asyncio.CancelledError
        if (
            returncode != 0
            or not isinstance(stdout, bytes)
            or not isinstance(stderr, bytes)
            or len(stdout) > 256 * 1024
            or len(stderr) > 256 * 1024
        ):
            raise RuntimeError("bounded command rejected")
        try:
            return stdout.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise RuntimeError("bounded command rejected") from None

    def _terminate_process_tree(self, process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name == "nt":
                taskkill = Path(
                    os.environ.get("SYSTEMROOT", r"C:\Windows")
                ) / "System32" / "taskkill.exe"
                subprocess.run(
                    (str(taskkill), "/PID", str(process.pid), "/T", "/F"),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                    check=False,
                    shell=False,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                os.killpg(process.pid, 9)
        except (OSError, subprocess.SubprocessError):
            try:
                process.kill()
            except OSError:
                pass

    async def _restore_paths(self, state: _DraftState, task_id: UUID) -> None:
        try:
            current = (await self._run_git("rev-parse", "--verify", "HEAD")).strip()
            if current != state.baseline:
                return
            await self._run_git("reset", "--quiet", "--", *state.draft.paths)
            tracked: list[str] = []
            untracked: list[str] = []
            for relative in state.draft.paths:
                try:
                    await self._run_git("cat-file", "-e", f"{state.baseline}:{relative}")
                    tracked.append(relative)
                except RuntimeError:
                    untracked.append(relative)
            if tracked:
                await self._run_git(
                    "restore", "--source", state.baseline,
                    "--worktree", "--", *tracked
                )
            for relative in untracked:
                path = self._root.joinpath(*relative.split("/"))
                if path.is_file() and not path.is_symlink():
                    path.unlink()
            status = await self._run_git(
                "status", "--porcelain=v1", "--untracked-files=all"
            )
            if status.strip():
                raise RuntimeError("worktree restore incomplete")
            self._clear_journal(task_id, required=True)
        except (OSError, RuntimeError, asyncio.CancelledError):
            pass

    async def _rollback_if_own_commit(self, task_id: UUID, baseline: str) -> None:
        commit = self._commits.get(task_id)
        if commit is None:
            return
        try:
            current = (await self._run_git("rev-parse", "--verify", "HEAD")).strip()
            status = await self._run_git(
                "status", "--porcelain=v1", "--untracked-files=all"
            )
            if current == baseline and not status.strip():
                self._clear_journal(task_id)
                return
            if current != commit.commit or status.strip():
                return
            await self._run_git(
                "update-ref", "refs/heads/agent/telegram-live",
                baseline, commit.commit,
            )
            await self._run_git("reset", "--hard", "--quiet", baseline)
            self._clear_journal(task_id)
        except (RuntimeError, asyncio.CancelledError):
            pass
    def reconcile(self, store: SQLiteStore) -> None:
        """Resolve an interrupted authorized ref update before accepting new work."""
        journal = self._read_journal()
        if journal is None:
            return
        current = self._run_git_sync("rev-parse", "--verify", "HEAD").strip()
        status = self._run_git_sync(
            "status", "--porcelain=v1", "--untracked-files=all"
        )
        if current == journal.baseline:
            if status.strip():
                self._restore_journal_paths_sync(journal)
                status = self._run_git_sync(
                    "status", "--porcelain=v1", "--untracked-files=all"
                )
            if status.strip():
                raise RuntimeError("commit journal found foreign worktree changes")
            self._clear_journal(journal.task_id, required=True)
            return
        if status.strip():
            raise RuntimeError("commit journal found a dirty worktree")
        snapshot = store.read_task(journal.tenant_id, journal.task_id)
        if current != journal.commit or snapshot is None:
            raise RuntimeError("commit journal does not match durable state")
        projection = snapshot.projection
        if projection.status is TaskStatus.COMPLETED:
            self._clear_journal(journal.task_id, required=True)
            return
        if (
            projection.status is TaskStatus.EXECUTING
            and projection.human_approval is not None
        ):
            self._run_git_sync(
                "update-ref", "refs/heads/agent/telegram-live",
                journal.baseline, journal.commit,
            )
            self._run_git_sync("reset", "--hard", "--quiet", journal.baseline)
            self._clear_journal(journal.task_id, required=True)
            return
        raise RuntimeError("commit journal recovery is not authorized")

    def _restore_journal_paths_sync(self, journal: _CommitJournal) -> None:
        self._run_git_sync("reset", "--quiet", "--", *journal.paths)
        tracked: list[str] = []
        untracked: list[str] = []
        for relative in journal.paths:
            try:
                self._run_git_sync(
                    "cat-file", "-e", f"{journal.baseline}:{relative}"
                )
                tracked.append(relative)
            except RuntimeError:
                untracked.append(relative)
        if tracked:
            self._run_git_sync(
                "restore", "--source", journal.baseline,
                "--worktree", "--", *tracked,
            )
        for relative in untracked:
            path = self._root.joinpath(*relative.split("/"))
            resolved_parent = path.parent.resolve(strict=True)
            if (
                not resolved_parent.is_relative_to(self._root)
                or path.is_symlink()
                or (path.exists() and not path.is_file())
            ):
                raise RuntimeError("unsafe journal recovery path")
            path.unlink(missing_ok=True)
    def _write_journal(self, journal: _CommitJournal) -> None:
        path = self._journal_path
        temporary = path.with_suffix(".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            existing = self._read_journal()
            if existing is not None and existing.task_id != journal.task_id:
                raise RuntimeError("commit journal is already owned")
            for relative in journal.paths:
                validate_codex_patch_path(relative, self._root)
            if path.parent.is_symlink() or path.is_symlink() or temporary.exists():
                raise OSError("unsafe journal path")
            payload = json.dumps(
                journal.model_dump(mode="json"),
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                raise
            os.replace(temporary, path)
        except (OSError, TypeError, ValueError, CodexPatchError, RuntimeError):
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise RuntimeError("commit journal write failed") from None

    def _read_journal(self) -> _CommitJournal | None:
        path = self._journal_path
        if not path.exists():
            return None
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
                raise ValueError("unsafe journal")
            journal = _CommitJournal.model_validate_json(path.read_bytes())
            for relative in journal.paths:
                validate_codex_patch_path(relative, self._root)
            return journal
        except (OSError, ValueError, CodexPatchError):
            raise RuntimeError("commit journal is invalid") from None

    def _clear_journal(self, task_id: UUID, *, required: bool = False) -> None:
        try:
            journal = self._read_journal()
            if journal is None:
                return
            if journal.task_id != task_id:
                raise RuntimeError("commit journal task mismatch")
            self._journal_path.unlink()
        except (OSError, RuntimeError):
            if required:
                raise RuntimeError("commit journal cleanup failed") from None

    def _run_git_sync(self, *args: str) -> str:
        null_device = "NUL" if os.name == "nt" else "/dev/null"
        result = subprocess.run(
            (
                str(self._git),
                "-c", f"core.hooksPath={null_device}",
                "-c", "core.fsmonitor=false",
                "-c", "diff.external=",
                "-c", f"core.attributesFile={null_device}",
                *args,
            ),
            cwd=self._root,
            env=dict(_git_environment()),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=self._timeout,
            check=False,
            shell=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if (
            result.returncode != 0
            or len(result.stdout) > 256 * 1024
            or len(result.stderr) > 256 * 1024
        ):
            raise RuntimeError("journal reconciliation command failed")
        try:
            return result.stdout.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise RuntimeError("journal reconciliation command failed") from None
    def _level(
        self, candidate: VerificationInput, level: int, passed: bool, method: str
    ) -> VerificationLevel:
        verified_at = self._clock()
        if verified_at.tzinfo is None or verified_at.utcoffset() is None:
            raise ValueError("verifier clock is invalid")
        status = (
            VerificationLevelStatus.PASSED
            if passed
            else VerificationLevelStatus.FAILED
        )
        return VerificationLevel(
            status=status,
            method=method,
            verifier_identity=_VERIFIER_IDENTITIES[level],
            verified_at=verified_at.astimezone(UTC),
            evidence_refs=(f"evidence:gate5a4:l{level}:{status.value}",),
            evidence_digest=canonical_json_digest(
                {
                    "contract_digest": candidate.contract_digest,
                    "level": level,
                    "output_digest": candidate.output_digest,
                    "result_digest": candidate.result_digest,
                    "status": status.value,
                    "task_id": str(candidate.task_id),
                }
            ),
        )


def build_gate5a4_runtime(
    *,
    gateway: TelegramGateway,
    sqlite_path: str | Path,
    destination_refs: Mapping[str, str],
    worktree: str | Path,
    codex_executable: str | Path,
    git_executable: str | Path,
    python_executable: str | Path,
    codex_home: str | Path,
    system_root: str | Path,
    temp_root: str | Path,
    path_entries: tuple[str | Path, ...],
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> Gate5A4Runtime:
    """Build the live worker using the accepted process and durable boundaries."""
    root = Path(worktree).resolve(strict=True)
    worker_env = build_worker_env(
        codex_home=codex_home,
        system_root=system_root,
        temp_root=temp_root,
        workspace_root=root,
        path_entries=path_entries,
    )
    launcher = WindowsJobLauncher(
        workspace_root=root,
        target_executable=codex_executable,
        worker_env=worker_env,
    )
    spawner = AsyncioProcessSpawner(
        workspace_root=root,
        executable=codex_executable,
        spawn=launcher,
        tree_killer=launcher.kill_tree,
        worker_env=worker_env,
    )
    worker = CodexCliAdapter(
        workspace_root=root,
        executable=codex_executable,
        spawner=spawner,
        max_timeout_seconds=300,
        cleanup_timeout=15,
        stdout_limit=512 * 1024,
        worker_env=worker_env,
    )
    pipeline = GitPatchVerificationPipeline(
        worktree=root,
        git_executable=git_executable,
        python_executable=python_executable,
        clock=clock,
    )
    registry = TrustedVerifierRegistry(
        {level: {identity} for level, identity in _VERIFIER_IDENTITIES.items()}
    )
    store = SQLiteStore(sqlite_path, verifier_registry=registry)
    pipeline.reconcile(store)
    return Gate5A4Runtime(
        gateway=gateway,
        store=store,
        destination_refs=destination_refs,
        policy_store=InMemoryPolicyStore(),
        state_manager=StateManager(registry),
        worker=worker,
        verifiers=(pipeline.l1, pipeline.l2, pipeline.l3),
        pipeline=pipeline,
        allowed_path=root,
        clock=clock,
    )


def _git_environment() -> Mapping[str, str]:
    values = {
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": "NUL" if os.name == "nt" else "/dev/null",
        "LANG": "C.UTF-8",
        "NO_COLOR": "1",
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
    }
    return MappingProxyType(values)


def _test_environment(worktree: Path) -> Mapping[str, str]:
    values = dict(_git_environment())
    temp = worktree / ".runtime" / "test-tmp"
    temp.mkdir(parents=True, exist_ok=True)
    values.update(
        DEBUG="false",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONUTF8="1",
        TEMP=str(temp),
        TMP=str(temp),
    )
    return MappingProxyType(values)
