"""Offline verification of the isolated Gate 5A.4 patch transaction."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.application.fake_vertical import VerificationInput
from src.application.gate5a4 import GitPatchVerificationPipeline
from src.contracts import VerificationLevelStatus
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