"""Restart, recovery and adversarial checks for Gate 4F local wiring."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from src.application import DurableFakeRuntime, FakeVerticalStatus, VerificationInput
from src.contracts import VerificationLevel, VerificationLevelStatus
from src.contracts.models import canonical_json_digest
from src.core.policy import InMemoryPolicyStore, TrustedVerifierRegistry
from src.models.task import TaskStatus
from src.orchestrator.state_manager import StateManager
from src.storage import AuditEventConflictError, OutboxStatus, ReceiptType, SQLiteStore
from src.transport.telegram import (
    ActorBinding,
    InMemoryUpdateIdStore,
    TelegramGateway,
    TextMessage,
)
from src.voice import (
    InMemoryVoiceConfirmationStore,
    TranscriptResult,
    VoicePreviewService,
)
from src.workers import CodexCliAdapter, ProcessOutput


USER_ID = 111
CHAT_ID = 222
AUTH_CONTEXT_REF = "sha256:" + "a" * 64
DESTINATION_REF = "sha256:" + "d" * 64
TOKEN = "Gate4F_confirmation_token_1234567890abcd"


@dataclass
class MutableClock:
    value: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


@dataclass
class FakeProcess:
    output: ProcessOutput
    failure: BaseException | None = None

    async def communicate(
        self,
        *,
        stdin: bytes,
        stdout_limit: int,
        stderr_limit: int,
    ) -> ProcessOutput:
        if self.failure is not None:
            raise self.failure
        return self.output

    def kill(self) -> None:
        pass

    async def wait(self) -> int:
        return self.output.returncode


@dataclass
class FakeSpawner:
    process: FakeProcess
    calls: int = 0

    async def __call__(
        self,
        *,
        executable: str,
        argv: tuple[str, ...],
        cwd: str,
        env: Mapping[str, str],
    ) -> FakeProcess:
        self.calls += 1
        return self.process

    async def abort_start(self) -> None:
        pass


@dataclass
class FakeVerifier:
    level: int
    identity: str

    async def __call__(self, candidate: VerificationInput) -> VerificationLevel:
        return VerificationLevel(
            status=VerificationLevelStatus.PASSED,
            method=f"gate4f-l{self.level}",
            verifier_identity=self.identity,
            verified_at=datetime.now(UTC),
            evidence_refs=(f"evidence:gate4f:l{self.level}",),
            evidence_digest=canonical_json_digest(
                {
                    "level": self.level,
                    "result_digest": candidate.result_digest,
                    "output_digest": candidate.output_digest,
                }
            ),
        )


@dataclass
class FakeTranscriber:
    text: str = "проверить локальный проект"
    calls: int = 0

    async def transcribe(self, path: Path, *, max_chars: int) -> TranscriptResult:
        self.calls += 1
        return TranscriptResult(text=self.text, language="ru", confidence=0.99)


@dataclass
class RuntimeParts:
    runtime: DurableFakeRuntime
    store: SQLiteStore
    manager: StateManager
    spawner: FakeSpawner
    transcriber: FakeTranscriber
    confirmation: InMemoryVoiceConfirmationStore


def text_update(update_id: int = 1) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 10,
            "from": {"id": USER_ID},
            "chat": {"id": CHAT_ID},
            "text": "проверить локальный проект",
        },
    }


def voice_update(update_id: int = 2) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 11,
            "from": {"id": USER_ID},
            "chat": {"id": CHAT_ID},
            "voice": {
                "file_id": "opaque-file",
                "duration": 1,
                "file_size": 5,
                "mime_type": "audio/ogg",
            },
        },
    }


def callback_update(token: str, update_id: int = 3) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": "voice-confirm",
            "from": {"id": USER_ID},
            "message": {"chat": {"id": CHAT_ID}},
            "data": token,
        },
    }


def build_runtime(
    root: Path,
    db_path: Path,
    *,
    clock: MutableClock,
    worker_failure: BaseException | None = None,
    actor_tenant: str = "tenant-a",
    configured_tenant: str | None = None,
    destination_ref: str = DESTINATION_REF,
) -> RuntimeParts:
    allowed = root / "workspace" / "repo"
    allowed.mkdir(parents=True, exist_ok=True)
    executable = root / "codex.exe"
    executable.touch(exist_ok=True)
    process = FakeProcess(
        output=ProcessOutput(
            (
                "\n".join(
                    json.dumps(event)
                    for event in (
                        {"type": "thread.started", "thread_id": "thread-1"},
                        {"type": "turn.started"},
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "message-1",
                                "type": "agent_message",
                                "text": "safe local result",
                            },
                        },
                        {
                            "type": "turn.completed",
                            "usage": {"input_tokens": 1, "output_tokens": 1},
                        },
                    )
                )
                + "\n"
            ).encode(),
            b"",
            0,
        ),
        failure=worker_failure,
    )
    spawner = FakeSpawner(process)
    worker = CodexCliAdapter(
        workspace_root=allowed.parent,
        executable=executable.resolve(),
        spawner=spawner,
    )
    registry = TrustedVerifierRegistry(
        {1: {"verifier:l1"}, 2: {"verifier:l2"}, 3: {"verifier:l3"}}
    )
    manager = StateManager(registry)
    store = SQLiteStore(db_path, verifier_registry=registry)
    confirmation = InMemoryVoiceConfirmationStore(
        clock=clock,
        token_factory=lambda: TOKEN,
    )
    gateway = TelegramGateway(
        actor_bindings={
            (USER_ID, CHAT_ID): ActorBinding(
                tenant_id=actor_tenant,
                actor_identity="telegram:owner",
                role="owner",
                auth_context_ref=AUTH_CONTEXT_REF,
            )
        },
        update_id_store=InMemoryUpdateIdStore(),
        callback_token_store=confirmation,
        clock=clock,
    )
    transcriber = FakeTranscriber()
    voice_service = VoicePreviewService(
        transcriber=transcriber,
        temp_root=root / "voice-temp",
        max_bytes=1024,
        max_transcript_length=4096,
    )
    runtime = DurableFakeRuntime(
        gateway=gateway,
        policy_store=InMemoryPolicyStore(),
        state_manager=manager,
        worker=worker,
        verifiers=(
            FakeVerifier(1, "verifier:l1"),
            FakeVerifier(2, "verifier:l2"),
            FakeVerifier(3, "verifier:l3"),
        ),
        allowed_path=allowed,
        store=store,
        destination_refs={configured_tenant or actor_tenant: destination_ref},
        voice_service=voice_service,
        voice_confirmation=confirmation,
        clock=clock,
    )
    return RuntimeParts(runtime, store, manager, spawner, transcriber, confirmation)


@pytest.mark.asyncio
async def test_text_flow_persists_task_events_and_atomic_outbox(tmp_path: Path) -> None:
    clock = MutableClock()
    parts = build_runtime(tmp_path, tmp_path / "state.sqlite3", clock=clock)

    response = await parts.runtime.handle(text_update())

    assert response.status is FakeVerticalStatus.COMPLETED
    assert response.task_id is not None
    snapshot = parts.store.read_task("tenant-a", response.task_id)
    assert snapshot is not None
    assert snapshot.projection.status is TaskStatus.COMPLETED
    assert snapshot.projection.result_digest == response.result_digest
    attempt_id = parts.runtime._attempts[response.task_id]
    events = parts.store.read_events("tenant-a", response.task_id, attempt_id)
    assert [event.sequence for event in events] == [1, 2]
    assert [event.event_type.value for event in events] == ["started", "result_ready"]

    delivered = await parts.runtime.deliver_pending(
        "tenant-a",
        lambda message: _delivered(message),
    )
    assert len(delivered) == 1
    assert delivered[0].status is OutboxStatus.ACKED
    receipts = parts.store.read_outbox_receipts(
        "tenant-a",
        delivered[0].message_id,
    )
    assert len(receipts) == 1
    assert await parts.runtime.deliver_pending(
        "tenant-a",
        lambda message: _delivered(message),
    ) == ()


async def _delivered(message: object) -> bool:
    return True


@pytest.mark.asyncio
async def test_restart_recovers_completed_task_without_rerunning_worker(
    tmp_path: Path,
) -> None:
    clock = MutableClock()
    db_path = tmp_path / "state.sqlite3"
    first = build_runtime(tmp_path / "first", db_path, clock=clock)
    completed = await first.runtime.handle(text_update())
    assert completed.status is FakeVerticalStatus.COMPLETED

    restarted = build_runtime(tmp_path / "second", db_path, clock=clock)
    recovered = await restarted.runtime.handle(text_update())

    assert recovered.status is FakeVerticalStatus.RECOVERED
    assert recovered.task_id == completed.task_id
    assert recovered.result_digest == completed.result_digest
    assert restarted.spawner.calls == 0

    delivered = await restarted.runtime.deliver_pending(
        "tenant-a",
        lambda message: _delivered(message),
    )
    assert len(delivered) == 1
    assert delivered[0].status is OutboxStatus.ACKED

    third = build_runtime(tmp_path / "third", db_path, clock=clock)
    replay = await third.runtime.handle(text_update())
    assert replay.status is FakeVerticalStatus.RECOVERED
    assert third.spawner.calls == 0
    assert await third.runtime.deliver_pending(
        "tenant-a",
        lambda message: _delivered(message),
    ) == ()


@pytest.mark.asyncio
async def test_restart_does_not_blindly_repeat_interrupted_worker(tmp_path: Path) -> None:
    clock = MutableClock()
    db_path = tmp_path / "state.sqlite3"
    first = build_runtime(
        tmp_path / "first",
        db_path,
        clock=clock,
        worker_failure=asyncio.CancelledError(),
    )
    with pytest.raises(asyncio.CancelledError):
        await first.runtime.handle(text_update())

    restarted = build_runtime(tmp_path / "second", db_path, clock=clock)
    recovered = await restarted.runtime.handle(text_update())

    assert recovered.status is FakeVerticalStatus.RECOVERY_REQUIRED
    assert recovered.task_id is not None
    snapshot = restarted.store.read_task("tenant-a", recovered.task_id)
    assert snapshot is not None
    assert snapshot.projection.status is TaskStatus.PARSING
    assert restarted.spawner.calls == 0


@pytest.mark.asyncio
async def test_failed_durable_write_does_not_advance_memory(tmp_path: Path) -> None:
    clock = MutableClock()
    parts = build_runtime(tmp_path, tmp_path / "state.sqlite3", clock=clock)
    original = parts.store.save_task_and_append_event

    def fail_save(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("simulated durable failure")

    parts.store.save_task_and_append_event = fail_save  # type: ignore[method-assign]
    response = await parts.runtime.handle(text_update())
    parts.store.save_task_and_append_event = original  # type: ignore[method-assign]

    assert response.status is FakeVerticalStatus.FAILED
    assert response.task_id is not None
    memory = await parts.manager.get(response.task_id)
    stored = parts.store.read_task("tenant-a", response.task_id)
    assert memory is not None and memory.status is TaskStatus.PENDING
    assert stored is not None and stored.projection.status is TaskStatus.PENDING


@pytest.mark.asyncio
async def test_voice_preview_confirmation_becomes_durable_and_recovers(
    tmp_path: Path,
) -> None:
    clock = MutableClock()
    db_path = tmp_path / "state.sqlite3"
    first = build_runtime(tmp_path / "first", db_path, clock=clock)

    preview = await first.runtime.handle(voice_update(), voice_bytes=b"audio")
    assert preview.status is FakeVerticalStatus.NEEDS_VOICE_CONFIRMATION
    assert preview.voice_preview == "проверить локальный проект"
    assert preview.confirmation_challenge is not None
    token = preview.confirmation_challenge.callback_token.get_secret_value()

    completed = await first.runtime.handle(callback_update(token))
    assert completed.status is FakeVerticalStatus.COMPLETED
    assert first.transcriber.calls == 1
    persisted = db_path.read_bytes()
    assert "проверить локальный проект".encode() not in persisted
    assert token.encode() not in persisted
    assert b"audio" not in persisted

    restarted = build_runtime(tmp_path / "second", db_path, clock=clock)
    recovered = await restarted.runtime.handle(voice_update())

    assert recovered.status is FakeVerticalStatus.RECOVERED
    assert recovered.task_id == completed.task_id
    assert restarted.transcriber.calls == 0
    assert restarted.spawner.calls == 0


@pytest.mark.asyncio
async def test_foreign_voice_callback_cannot_create_task(tmp_path: Path) -> None:
    clock = MutableClock()
    parts = build_runtime(tmp_path, tmp_path / "state.sqlite3", clock=clock)
    preview = await parts.runtime.handle(voice_update(), voice_bytes=b"audio")
    assert preview.confirmation_challenge is not None
    token = preview.confirmation_challenge.callback_token.get_secret_value()
    attack = callback_update(token)
    attack["callback_query"]["from"]["id"] = USER_ID + 1

    result = await parts.runtime.handle(attack)

    assert result.status is FakeVerticalStatus.REJECTED
    assert parts.spawner.calls == 0


@pytest.mark.asyncio
async def test_cancelled_delivery_is_reclaimed_after_restart(tmp_path: Path) -> None:
    clock = MutableClock()
    db_path = tmp_path / "state.sqlite3"
    first = build_runtime(tmp_path / "first", db_path, clock=clock)
    completed = await first.runtime.handle(text_update())
    assert completed.status is FakeVerticalStatus.COMPLETED

    async def cancelled(message: object) -> bool:
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await first.runtime.deliver_pending(
            "tenant-a",
            cancelled,
            lease_seconds=60,
        )

    clock.advance(61)
    restarted = build_runtime(tmp_path / "second", db_path, clock=clock)
    delivered = await restarted.runtime.deliver_pending(
        "tenant-a",
        lambda message: _delivered(message),
        lease_seconds=60,
    )

    assert len(delivered) == 1
    assert delivered[0].status is OutboxStatus.ACKED
    assert delivered[0].attempt_count == 2


@pytest.mark.asyncio
async def test_before_commit_failure_keeps_state_manager_unchanged(
    tmp_path: Path,
) -> None:
    clock = MutableClock()
    parts = build_runtime(tmp_path, tmp_path / "state.sqlite3", clock=clock)
    ingress = parts.runtime._gateway.process_update(text_update())
    assert ingress.envelope is not None and isinstance(ingress.payload, TextMessage)
    contract = parts.runtime._contract(ingress.payload.text, ingress.envelope)

    def reject(candidate: object) -> None:
        raise RuntimeError("not committed")

    with pytest.raises(RuntimeError, match="not committed"):
        await parts.manager.create_from_contract(contract, before_commit=reject)
    assert await parts.manager.get(contract.task_id) is None


@pytest.mark.asyncio
async def test_unconfigured_tenant_never_reaches_worker_or_storage(
    tmp_path: Path,
) -> None:
    clock = MutableClock()
    parts = build_runtime(
        tmp_path,
        tmp_path / "state.sqlite3",
        clock=clock,
        actor_tenant="tenant-b",
        configured_tenant="tenant-a",
    )

    response = await parts.runtime.handle(text_update())

    assert response.status is FakeVerticalStatus.FAILED
    assert response.task_id is None
    assert parts.spawner.calls == 0

@pytest.mark.asyncio
async def test_delivery_cannot_cross_configured_tenant_boundary(tmp_path: Path) -> None:
    clock = MutableClock()
    db_path = tmp_path / "state.sqlite3"
    tenant_b = build_runtime(
        tmp_path / "tenant-b",
        db_path,
        clock=clock,
        actor_tenant="tenant-b",
        configured_tenant="tenant-b",
    )
    completed = await tenant_b.runtime.handle(text_update())
    assert completed.status is FakeVerticalStatus.COMPLETED

    tenant_a = build_runtime(
        tmp_path / "tenant-a",
        db_path,
        clock=clock,
        actor_tenant="tenant-a",
        configured_tenant="tenant-a",
    )
    sender_called = False

    async def sender(message: object) -> bool:
        nonlocal sender_called
        sender_called = True
        return True

    with pytest.raises(ValueError, match="tenant delivery is not configured"):
        await tenant_a.runtime.deliver_pending("tenant-b", sender)
    assert sender_called is False
@pytest.mark.asyncio
async def test_terminal_outbox_failure_leaves_preterminal_state(tmp_path: Path) -> None:
    clock = MutableClock()
    parts = build_runtime(tmp_path, tmp_path / "state.sqlite3", clock=clock)
    original = parts.store.save_task_and_enqueue_status

    def fail_completion(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("simulated atomic completion failure")

    parts.store.save_task_and_enqueue_status = fail_completion  # type: ignore[method-assign]
    response = await parts.runtime.handle(text_update())
    parts.store.save_task_and_enqueue_status = original  # type: ignore[method-assign]

    assert response.status is FakeVerticalStatus.FAILED
    assert response.task_id is not None
    stored = parts.store.read_task("tenant-a", response.task_id)
    memory = await parts.manager.get(response.task_id)
    assert stored is not None and stored.projection.status is TaskStatus.L3_APPROVED
    assert memory is not None and memory.status is TaskStatus.L3_APPROVED
    assert await parts.runtime.deliver_pending(
        "tenant-a",
        lambda message: _delivered(message),
    ) == ()
@pytest.mark.asyncio
async def test_event_append_failure_rolls_back_task_transition(tmp_path: Path) -> None:
    clock = MutableClock()
    parts = build_runtime(tmp_path, tmp_path / "state.sqlite3", clock=clock)
    original = parts.store._append_event_row

    def fail_event(*args: Any, **kwargs: Any) -> None:
        raise AuditEventConflictError("simulated audit event failure")

    parts.store._append_event_row = fail_event  # type: ignore[method-assign]
    response = await parts.runtime.handle(text_update())
    parts.store._append_event_row = original  # type: ignore[method-assign]

    assert response.status is FakeVerticalStatus.FAILED
    assert response.task_id is not None
    stored = parts.store.read_task("tenant-a", response.task_id)
    memory = await parts.manager.get(response.task_id)
    assert stored is not None and stored.projection.status is TaskStatus.PENDING
    assert memory is not None and memory.status is TaskStatus.PENDING
@pytest.mark.asyncio
async def test_stale_destination_is_nacked_without_calling_sender(tmp_path: Path) -> None:
    clock = MutableClock()
    db_path = tmp_path / "state.sqlite3"
    stale_destination = "sha256:" + "e" * 64
    original = build_runtime(
        tmp_path / "original",
        db_path,
        clock=clock,
        destination_ref=stale_destination,
    )
    completed = await original.runtime.handle(text_update())
    assert completed.status is FakeVerticalStatus.COMPLETED

    restarted = build_runtime(
        tmp_path / "restarted",
        db_path,
        clock=clock,
        destination_ref=DESTINATION_REF,
    )
    sender_called = False

    async def sender(message: object) -> bool:
        nonlocal sender_called
        sender_called = True
        return True

    outcomes = await restarted.runtime.deliver_pending("tenant-a", sender)

    assert sender_called is False
    assert len(outcomes) == 1
    assert outcomes[0].status is OutboxStatus.PENDING
    receipts = restarted.store.read_outbox_receipts(
        "tenant-a",
        outcomes[0].message_id,
    )
    assert len(receipts) == 1
    assert receipts[0].receipt_type is ReceiptType.NACK
@pytest.mark.asyncio
async def test_specific_worker_failure_code_is_preserved_in_durable_audit(
    tmp_path: Path,
) -> None:
    clock = MutableClock()
    parts = build_runtime(tmp_path, tmp_path / "state.sqlite3", clock=clock)
    ingress = parts.runtime._gateway.process_update(text_update())
    assert ingress.envelope is not None
    prepared = await parts.runtime.prepare_instruction(
        "проверить локальный проект", ingress.envelope
    )
    task = await parts.manager.get(prepared.contract.task_id)
    assert task is not None
    parsing = await parts.runtime._start_worker(prepared.contract, task)

    await parts.runtime._escalate(parsing, error_code="worker_timeout")

    snapshot = parts.store.read_task("tenant-a", prepared.contract.task_id)
    assert snapshot is not None
    assert snapshot.projection.status is TaskStatus.FAILED
    stored_task = await parts.manager.get(prepared.contract.task_id)
    assert stored_task is not None
    assert stored_task.error_message == "worker_timeout"
    attempt_id = parts.runtime._attempts[prepared.contract.task_id]
    events = parts.store.read_events("tenant-a", prepared.contract.task_id, attempt_id)
    assert events[-1].payload["error_code"] == "worker_timeout"
    assert events[-1].payload["safe_message"] == "Worker timed out."

@pytest.mark.asyncio
async def test_worker_failure_persists_failed_event_and_outbox_atomically(
    tmp_path: Path,
) -> None:
    clock = MutableClock()
    parts = build_runtime(
        tmp_path,
        tmp_path / "state.sqlite3",
        clock=clock,
        worker_failure=RuntimeError("private provider detail"),
    )

    response = await parts.runtime.handle(text_update())

    assert response.status is FakeVerticalStatus.FAILED
    assert response.task_id is not None
    snapshot = parts.store.read_task("tenant-a", response.task_id)
    assert snapshot is not None
    assert snapshot.projection.status is TaskStatus.FAILED
    attempt_id = parts.runtime._attempts[response.task_id]
    events = parts.store.read_events("tenant-a", response.task_id, attempt_id)
    assert [event.event_type.value for event in events] == ["started", "failed"]
    assert "private provider detail" not in json.dumps(
        [event.model_dump(mode="json") for event in events]
    )
    delivered = await parts.runtime.deliver_pending(
        "tenant-a",
        lambda message: _delivered(message),
    )
    assert len(delivered) == 1
    assert delivered[0].status is OutboxStatus.ACKED
