"""C3 sealed-result and orphan recovery; disposable state, no provider calls."""
from __future__ import annotations

import asyncio
import json
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.application.durable_runtime import PreparedTask
from src.application.gate5a4 import Gate5A4Runtime, GitPatchVerificationPipeline, _VERIFIER_IDENTITIES
from src.contracts import IngressSource, VerificationBundleStatus
from src.core.policy import InMemoryPolicyStore, TrustedVerifierRegistry, task_contract_digest
from src.models.task import TaskStatus
from src.orchestrator.state_manager import StateManager
from src.storage import SQLiteStore, SnapshotConflictError, StoreCorruptionError
from src.storage.outbox import message_fingerprint, message_id_for
from src.contracts.models import canonical_json_digest
from tests.test_sqlite_store import contract_for, envelope


DESTINATION = "sha256:" + "d" * 64
ANSWER = "Готовый проверенный ответ из сохранённого результата."


def runtime(root: Path) -> Gate5A4Runtime:
    root.mkdir(exist_ok=True)
    value = object.__new__(Gate5A4Runtime)
    registry = TrustedVerifierRegistry({level: {identity} for level, identity in _VERIFIER_IDENTITIES.items()})
    value._store = SQLiteStore(root / "tasks.sqlite3", verifier_registry=registry)
    value._state = StateManager(registry)
    value._policy_store = InMemoryPolicyStore()
    value._revisions = {}
    value._attempts = {}
    value._destination_refs = {"tenant-a": DESTINATION}
    value._clock = lambda: datetime.now(UTC)
    value._pipeline = GitPatchVerificationPipeline(worktree=root, git_executable=Path(shutil.which("git")),
                                                  python_executable=Path(sys.executable))
    value._worker_slots = asyncio.Semaphore(2)
    value._worker = SimpleNamespace()
    return value


async def seal(value, stage=TaskStatus.DRAFT):
    incoming = envelope(source=IngressSource.API)
    contract = contract_for(incoming)
    prepared = PreparedTask(contract, incoming.envelope_revision)
    task = await value._begin_task(contract, incoming)
    task = await value._start_worker(contract, task)
    message = json.dumps({"answer": ANSWER}, ensure_ascii=False, separators=(",", ":"))
    task = await value._record_worker_result(contract, task, message, result_kind="answer")
    if stage is not TaskStatus.DRAFT:
        candidate = value._candidate(task, message)
        l1 = await value._pipeline.l1(candidate)
        task = await value._required_update(task.id, status=TaskStatus.L1_VALIDATED,
            verification_bundle=value._bundle(task, l1=l1, status=VerificationBundleStatus.DRAFT))
        if stage is TaskStatus.L2_VERIFIED:
            l2 = await value._pipeline.l2(candidate)
            task = await value._required_update(task.id, status=TaskStatus.L2_VERIFIED,
                verification_bundle=value._bundle(task, l1=l1, l2=l2, status=VerificationBundleStatus.DRAFT))
    return prepared, incoming, task


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", [TaskStatus.DRAFT, TaskStatus.L1_VALIDATED, TaskStatus.L2_VERIFIED])
async def test_restart_finishes_exact_sealed_answer_without_worker(tmp_path, stage):
    first = runtime(tmp_path)
    prepared, incoming, task = await seal(first, stage)
    restarted = runtime(tmp_path)
    assert await restarted.recover_prepared(prepared, incoming) is False
    snapshot = restarted._store.read_task(task.tenant_id, task.id)
    assert snapshot.projection.status is TaskStatus.ANSWERED
    assert snapshot.projection.result_digest == task.result_digest
    assert snapshot.projection.result_revision == task.result_revision
    answer = restarted._store.read_verified_answer(task.tenant_id, task.id,
        task_revision=snapshot.revision, task_projection_digest=snapshot.snapshot_digest,
        contract_digest=task.contract_digest, result_revision=task.result_revision, result_digest=task.result_digest)
    assert answer.user_message == ANSWER
    third = runtime(tmp_path)
    assert await third.recover_prepared(prepared, incoming) is False
    assert await third.is_task_terminal(task.tenant_id, task.id, task.contract_digest)
    assert third._store.read_task(task.tenant_id, task.id) == snapshot
    with sqlite3.connect(first._store._path) as db:
        assert db.execute("SELECT count(*) FROM outbox_messages").fetchone()[0] == 1
        assert ANSWER.encode() not in db.execute("SELECT payload FROM sealed_answers").fetchone()[0]


@pytest.mark.asyncio
async def test_result_seal_and_event_rollback_together(tmp_path, monkeypatch):
    value = runtime(tmp_path)
    incoming = envelope(source=IngressSource.API); contract = contract_for(incoming)
    task = await value._start_worker(contract, await value._begin_task(contract, incoming))
    original = value._store._seal_answer
    def fail(*args):
        raise StoreCorruptionError("synthetic write failure")
    monkeypatch.setattr(value._store, "_seal_answer", fail)
    with pytest.raises(StoreCorruptionError):
        await value._record_worker_result(contract, task, json.dumps({"answer": ANSWER}), result_kind="answer")
    assert value._store.read_task(task.tenant_id, task.id).projection.status is TaskStatus.PARSING
    assert value._store.read_sealed_answer(task.tenant_id, task.id) is None
    monkeypatch.setattr(value._store, "_seal_answer", original)
    with sqlite3.connect(value._store._path) as db:
        assert db.execute("SELECT count(*) FROM audit_events").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_corrupt_seal_requires_attention_and_keeps_evidence(tmp_path):
    value = runtime(tmp_path); prepared, incoming, task = await seal(value)
    with sqlite3.connect(value._store._path) as db:
        db.execute("UPDATE sealed_answers SET payload=?", (b"tampered",))
    restarted = runtime(tmp_path)
    assert await restarted.recover_prepared(prepared, incoming) is False
    snapshot = restarted._store.read_task(task.tenant_id, task.id)
    assert snapshot.projection.status is TaskStatus.ESCALATE
    assert snapshot.projection.result_digest == task.result_digest
    with pytest.raises(StoreCorruptionError):
        restarted._store.read_sealed_answer(task.tenant_id, task.id)
    assert restarted._store.read_sealed_answer("other-tenant", task.id) is None


@pytest.mark.asyncio
async def test_terminal_store_failure_then_second_restart_keeps_same_result(tmp_path, monkeypatch):
    value = runtime(tmp_path); prepared, incoming, task = await seal(value, TaskStatus.L2_VERIFIED)
    restarted = runtime(tmp_path)
    def fail(*args, **kwargs):
        raise StoreCorruptionError("synthetic write failure")
    monkeypatch.setattr(restarted._store, "save_task_and_enqueue_status", fail)
    with pytest.raises(StoreCorruptionError):
        await restarted._recover_answer(prepared, incoming, restarted._store.read_task(task.tenant_id, task.id))
    third = runtime(tmp_path)
    assert await third.recover_prepared(prepared, incoming) is False
    assert third._store.read_task(task.tenant_id, task.id).projection.status is TaskStatus.ANSWERED
    assert third._store.read_task(task.tenant_id, task.id).projection.result_digest == task.result_digest


@pytest.mark.asyncio
async def test_orphan_recovery_uses_core_snapshot_and_is_idempotent(tmp_path):
    value = runtime(tmp_path)
    incoming = envelope(source=IngressSource.API); contract = contract_for(incoming)
    task = await value._begin_task(contract, incoming)
    assert value._store.list_recoverable_tasks(task.tenant_id)[0].projection.task_id == task.id
    with pytest.raises(SnapshotConflictError):
        value._store.mark_recovery_attention(task.tenant_id, task.id, "sha256:" + "f" * 64,
                                             destination_ref=DESTINATION)
    assert await value.fail_recovery(PreparedTask(contract, incoming.envelope_revision), incoming)
    before = value._store.read_task(task.tenant_id, task.id)
    assert before.projection.status is TaskStatus.REJECTED
    assert await value.fail_recovery(PreparedTask(contract, incoming.envelope_revision), incoming)
    assert value._store.read_task(task.tenant_id, task.id) == before
    assert value._store.list_recoverable_tasks(task.tenant_id) == ()


@pytest.mark.asyncio
async def test_rehashed_outbox_content_cannot_replace_encrypted_sealed_answer(tmp_path):
    value = runtime(tmp_path); prepared, incoming, task = await seal(value)
    assert await value.recover_prepared(prepared, incoming) is False
    with sqlite3.connect(value._store._path) as db:
        raw = json.loads(db.execute("SELECT message_json FROM outbox_messages").fetchone()[0])
        raw["user_message"] = "Подменённый результат."
        fields = {key: raw[key] for key in ("tenant_id", "task_id", "task_revision", "task_projection_digest",
            "contract_digest", "result_revision", "result_digest", "destination_ref", "user_message")}
        fields["task_status"] = TaskStatus.ANSWERED
        fingerprint = message_fingerprint(**fields)
        identifier = message_id_for(fingerprint)
        raw.update(message_fingerprint=fingerprint, message_id=str(identifier))
        db.execute("UPDATE outbox_messages SET message_id=?,message_fingerprint=?,message_json=?,message_digest=?",
            (str(identifier), fingerprint, json.dumps(raw), canonical_json_digest(raw)))
    with pytest.raises(StoreCorruptionError):
        value._store.read_outbox_message(task.tenant_id, identifier)
