"""Durable local fake runtime wiring accepted Nobus boundaries without I/O."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from src.application.fake_vertical import (
    FakeVertical,
    FakeVerticalResponse,
    FakeVerticalStatus,
)
from src.contracts import (
    TaskContract,
    TrustedIngressEnvelope,
    WorkerEvent,
    WorkerEventType,
)
from src.contracts.models import canonical_json_digest
from src.core.policy import DuplicateIdempotencyKeyError, task_contract_digest
from src.models.task import Task, TaskStatus
from src.storage import (
    DeliveryReceipt,
    OutboxMessage,
    ReceiptType,
    SQLiteStore,
    StoredTaskSnapshot,
)
from src.transport.telegram import CallbackQuery, IngressStatus, TextMessage, VoiceMessage
from src.voice import (
    InMemoryVoiceConfirmationStore,
    VoiceConfirmationStatus,
    VoicePreviewService,
)


_WORKER_FAILURE_MESSAGES = {
    "worker_configuration_invalid": "Worker configuration is invalid.",
    "worker_forbidden": "Worker request is not allowed.",
    "worker_start_failed": "Worker could not be started.",
    "worker_timeout": "Worker timed out.",
    "worker_failed": "Worker execution failed.",
    "worker_protocol_error": "Worker returned invalid output.",
    "worker_output_too_large": "Worker output is too large.",
    "worker_context_unavailable": "Selected owner file changed or is unavailable.",
}


class StatusDeliveryBoundary(Protocol):
    """Injected fake sender; a live network adapter is outside Gate 4F."""

    async def __call__(self, message: OutboxMessage) -> bool: ...


@dataclass(frozen=True, repr=False)
class PreparedTask:
    """In-memory instruction binding for a durable content-free PENDING task."""

    contract: TaskContract
    envelope_revision: str

    @classmethod
    def validate(cls, value: "PreparedTask") -> "PreparedTask":
        if not isinstance(value, cls):
            raise ValueError("prepared task is invalid")
        contract = TaskContract.model_validate(value.contract.model_dump(mode="json"))
        revision = value.envelope_revision
        if (
            not isinstance(revision, str)
            or not revision.startswith("sha256:")
            or len(revision) != 71
            or any(character not in "0123456789abcdef" for character in revision[7:])
            or contract.ingress_digest != revision
        ):
            raise ValueError("prepared task binding is invalid")
        return cls(contract=contract, envelope_revision=revision)


class DurableFakeRuntime(FakeVertical):
    """Wire local Core, SQLite, voice confirmation, fake worker and outbox."""

    _OUTBOX_STATUSES = frozenset(
        {
            TaskStatus.COMPLETED,
            TaskStatus.ANSWERED,
            TaskStatus.REJECTED,
            TaskStatus.FAILED,
            TaskStatus.ESCALATE,
        }
    )

    def __init__(
        self,
        *,
        store: SQLiteStore,
        destination_refs: Mapping[str, str],
        voice_service: VoicePreviewService | None = None,
        voice_confirmation: InMemoryVoiceConfirmationStore | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        **vertical: Any,
    ) -> None:
        super().__init__(**vertical)
        normalized_destinations: dict[str, str] = {}
        for tenant_id, destination_ref in destination_refs.items():
            tenant = tenant_id.strip() if isinstance(tenant_id, str) else ""
            if not (
                tenant
                and isinstance(destination_ref, str)
                and destination_ref.startswith("sha256:")
                and len(destination_ref) == 71
                and all(
                    character in "0123456789abcdef"
                    for character in destination_ref[7:]
                )
            ):
                raise ValueError("destination_refs are invalid")
            normalized_destinations[tenant] = destination_ref
        if not normalized_destinations:
            raise ValueError("at least one destination_ref is required")
        if (voice_service is None) != (voice_confirmation is None):
            raise ValueError("voice service and confirmation store must be supplied together")
        self._store = store
        self._destination_refs = normalized_destinations
        self._voice_service = voice_service
        self._voice_confirmation = voice_confirmation
        self._clock = clock
        self._revisions: dict[UUID, int] = {}
        self._attempts: dict[UUID, UUID] = {}

    async def handle(
        self,
        update: dict[str, Any],
        *,
        voice_bytes: bytes | None = None,
    ) -> FakeVerticalResponse:
        """Process text or supplied voice bytes through the durable local runtime."""
        ingress = self._gateway.process_update(update)
        if ingress.status != IngressStatus.ACCEPTED:
            if ingress.reason == "duplicate update_id":
                return self._response(
                    FakeVerticalStatus.DUPLICATE,
                    "Update was already processed.",
                )
            return self._response(FakeVerticalStatus.REJECTED, "Update was rejected.")

        payload = ingress.payload
        envelope = ingress.envelope
        if payload is None or envelope is None:
            return self._response(FakeVerticalStatus.FAILED, "Trusted ingress failed.")
        if voice_bytes is not None and not isinstance(payload, VoiceMessage):
            return self._response(
                FakeVerticalStatus.REJECTED,
                "Audio bytes do not match this update.",
            )
        if isinstance(payload, TextMessage):
            return await self._run_durable_instruction(payload.text, envelope)
        if isinstance(payload, VoiceMessage):
            try:
                existing = self._store.read_ingress_claim(envelope)
            except Exception:
                return self._response(
                    FakeVerticalStatus.FAILED,
                    "Durable recovery failed.",
                )
            if existing is not None:
                return self._recovery_response(existing)
            return await self._preview_voice(payload, envelope, voice_bytes)
        if isinstance(payload, CallbackQuery):
            return await self._confirm_voice(payload, envelope)
        return self._response(FakeVerticalStatus.UNSUPPORTED, "Update is unsupported.")

    async def _preview_voice(
        self,
        message: VoiceMessage,
        envelope: TrustedIngressEnvelope,
        audio: bytes | None,
    ) -> FakeVerticalResponse:
        if self._voice_service is None or self._voice_confirmation is None:
            return self._response(
                FakeVerticalStatus.UNSUPPORTED,
                "Voice processing is not configured.",
            )
        if audio is None:
            return self._response(
                FakeVerticalStatus.NEEDS_VOICE_PREVIEW,
                "Authorized audio bytes are required.",
            )
        try:
            preview = await self._voice_service.preview_from_bytes(audio)
            challenge = self._voice_confirmation.issue(
                message=message,
                envelope=envelope,
                preview=preview,
            )
            return FakeVerticalResponse(
                status=FakeVerticalStatus.NEEDS_VOICE_CONFIRMATION,
                voice_preview=preview.transcript,
                confirmation_challenge=challenge,
                message="Confirm the voice preview before execution.",
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            return self._response(
                FakeVerticalStatus.FAILED,
                "Voice preview could not be prepared.",
            )

    async def _confirm_voice(
        self,
        callback: CallbackQuery,
        envelope: TrustedIngressEnvelope,
    ) -> FakeVerticalResponse:
        if self._voice_confirmation is None:
            return self._response(
                FakeVerticalStatus.UNSUPPORTED,
                "Voice confirmation is not configured.",
            )
        result = self._voice_confirmation.confirm(
            callback=callback,
            envelope=envelope,
        )
        if (
            result.status is not VoiceConfirmationStatus.CONFIRMED
            or result.confirmation is None
        ):
            return self._response(
                FakeVerticalStatus.REJECTED,
                "Voice confirmation was rejected.",
            )
        return await self._run_durable_instruction(
            result.confirmation.transcript,
            result.confirmation.voice_envelope,
        )

    async def _run_durable_instruction(
        self,
        instruction: str,
        envelope: TrustedIngressEnvelope,
    ) -> FakeVerticalResponse:
        if envelope.tenant_id not in self._destination_refs:
            return self._response(
                FakeVerticalStatus.FAILED,
                "Tenant delivery is not configured.",
            )
        try:
            existing = self._store.read_ingress_claim(envelope)
        except Exception:
            return self._response(
                FakeVerticalStatus.FAILED,
                "Durable recovery failed.",
            )
        if existing is not None:
            return self._recovery_response(existing)
        try:
            prepared = await self.prepare_instruction(instruction, envelope)
        except DuplicateIdempotencyKeyError:
            return self._response(
                FakeVerticalStatus.DUPLICATE, "Update was already processed."
            )
        except Exception:
            return self._response(FakeVerticalStatus.FAILED, "Task could not be created.")
        return await self.execute_prepared(prepared)

    async def prepare_instruction(
        self, instruction: str, envelope: TrustedIngressEnvelope
    ) -> PreparedTask:
        """Persist a content-free PENDING task without starting the worker."""
        prepared = await self.build_instruction(instruction, envelope)
        await self.admit_prepared(prepared, envelope)
        return prepared

    async def build_instruction(
        self, instruction: str, envelope: TrustedIngressEnvelope
    ) -> PreparedTask:
        """Build an exact contract without mutating task or outbox state."""
        trusted = TrustedIngressEnvelope.model_validate(
            envelope.model_dump(mode="json")
        )
        if trusted.tenant_id not in self._destination_refs:
            raise ValueError("tenant delivery is not configured")
        if self._store.read_ingress_claim(trusted) is not None:
            raise DuplicateIdempotencyKeyError("durable ingress already claimed")
        contract = self._contract(instruction, trusted)
        return PreparedTask(
            contract=contract,
            envelope_revision=trusted.envelope_revision,
        )

    async def admit_prepared(
        self, prepared: PreparedTask, envelope: TrustedIngressEnvelope
    ) -> bool:
        """Persist one exact prepared contract after its durable job exists."""
        prepared = PreparedTask.validate(prepared)
        trusted = TrustedIngressEnvelope.model_validate(
            envelope.model_dump(mode="json")
        )
        contract = prepared.contract
        if (
            trusted.tenant_id not in self._destination_refs
            or prepared.envelope_revision != trusted.envelope_revision
            or contract.tenant_id != trusted.tenant_id
            or contract.idempotency_key != trusted.idempotency_key
            or contract.ingress_digest != trusted.envelope_revision
        ):
            raise ValueError("prepared admission binding mismatch")
        existing = self._store.read_ingress_claim(trusted)
        if existing is not None:
            if (
                existing.projection.task_id != contract.task_id
                or existing.projection.contract_digest
                != task_contract_digest(contract)
            ):
                raise DuplicateIdempotencyKeyError(
                    "durable ingress already claimed"
                )
            return False
        task = await self._begin_task(contract, trusted)
        if task.status is not TaskStatus.PENDING:
            raise RuntimeError("prepared task is not pending")
        return True

    async def execute_prepared(self, prepared: PreparedTask) -> FakeVerticalResponse:
        """Execute only the exact in-memory contract bound to the durable draft."""
        try:
            prepared = PreparedTask.validate(prepared)
            contract = prepared.contract
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
        except Exception:
            return self._response(FakeVerticalStatus.FAILED, "Prepared task is unavailable.")
        return await self._execute_task(contract, task)

    async def cancel_prepared(self, prepared: PreparedTask) -> FakeVerticalResponse:
        """Reject one exact PENDING draft and enqueue its content-free status."""
        try:
            prepared = PreparedTask.validate(prepared)
            contract = prepared.contract
            task = await self._state.get(contract.task_id)
            if (
                task is None
                or task.status is not TaskStatus.PENDING
                or task.contract_digest != task_contract_digest(contract)
            ):
                raise ValueError("prepared task binding mismatch")
            task = await self._required_update(
                task.id,
                status=TaskStatus.REJECTED,
                error_message="cancelled_before_execution",
            )
        except Exception:
            return self._response(FakeVerticalStatus.FAILED, "Prepared task is unavailable.")
        return self._response(
            FakeVerticalStatus.REJECTED,
            "Task was cancelled before execution.",
            task_id=task.id,
        )

    async def is_task_terminal(
        self, tenant_id: str, task_id: UUID, contract_digest: str
    ) -> bool:
        """Verify one exact durable task binding reached an outbox terminal state."""
        if (
            not isinstance(tenant_id, str)
            or not tenant_id.strip()
            or not isinstance(task_id, UUID)
            or not isinstance(contract_digest, str)
        ):
            return False
        tenant_id = tenant_id.strip()
        task = await self._state.get(task_id)
        snapshot = self._store.read_task(tenant_id, task_id)
        return bool(
            task is not None
            and snapshot is not None
            and task.tenant_id == tenant_id
            and task.contract_digest == contract_digest
            and snapshot.projection.contract_digest == contract_digest
            and task.status in self._OUTBOX_STATUSES
            and snapshot.projection.status is task.status
            and self._revisions.get(task.id) == snapshot.revision
        )

    async def _begin_task(
        self,
        contract: TaskContract,
        envelope: TrustedIngressEnvelope,
    ) -> Task:
        self._policy_store.register_contract(contract, envelope)
        captured: list[StoredTaskSnapshot] = []

        def persist(candidate: Task) -> None:
            created, snapshot = self._store.claim_ingress_with_task(
                envelope,
                contract,
                candidate,
            )
            if not created:
                raise DuplicateIdempotencyKeyError("durable ingress already claimed")
            captured.append(snapshot)

        task = await self._state.create_from_contract(
            contract,
            before_commit=persist,
        )
        if len(captured) != 1:
            raise RuntimeError("durable ingress was not committed")
        self._revisions[task.id] = captured[0].revision
        return task

    async def _required_update(
        self, task_id: UUID, *, user_message: str | None = None, **values: Any
    ) -> Task:
        revision = self._revisions.get(task_id)
        if revision is None:
            raise RuntimeError("durable task revision is unavailable")
        captured: list[int] = []

        def persist(candidate: Task) -> None:
            if candidate.status in self._OUTBOX_STATUSES:
                result = self._store.save_task_and_enqueue_status(
                    candidate,
                    expected_revision=revision,
                    destination_ref=self._destination_refs[candidate.tenant_id],
                    user_message=user_message,
                    now=self._now(),
                )
                captured.append(result.task_revision)
            else:
                if user_message is not None:
                    raise RuntimeError("only terminal outbox updates may carry a message")
                snapshot = self._store.save_task(
                    candidate,
                    expected_revision=revision,
                )
                captured.append(snapshot.revision)

        task = await self._state.update(
            task_id,
            before_commit=persist,
            **values,
        )
        if task is None or len(captured) != 1:
            raise RuntimeError("durable task update failed")
        self._revisions[task_id] = captured[0]
        return task

    async def _complete(self, task: Task) -> Task:
        return await self._required_update(task.id, status=TaskStatus.COMPLETED)

    async def _start_worker(self, contract: TaskContract, task: Task) -> Task:
        revision = self._revisions.get(task.id)
        if revision is None:
            raise RuntimeError("durable task revision is unavailable")
        attempt_id = uuid4()
        self._policy_store.bind_worker(
            task.id,
            task.tenant_id,
            attempt_id,
            task.contract_digest,
            self._EXECUTOR_IDENTITY,
        )
        event = WorkerEvent(
            event_id=uuid4(),
            tenant_id=task.tenant_id,
            task_id=task.id,
            attempt_id=attempt_id,
            contract_digest=task.contract_digest,
            worker_identity=self._EXECUTOR_IDENTITY,
            sequence=1,
            event_type=WorkerEventType.STARTED,
            emitted_at=self._now(),
            payload={
                "lease_ref": canonical_json_digest(
                    {"attempt_id": str(attempt_id), "task_id": str(task.id)}
                )
            },
        )
        self._policy_store.accept_event(event)
        captured: list[StoredTaskSnapshot] = []

        def persist(candidate: Task) -> None:
            captured.append(
                self._store.save_task_and_append_event(
                    candidate,
                    event,
                    expected_revision=revision,
                )
            )

        started = await self._state.update(
            task.id,
            status=TaskStatus.PARSING,
            before_commit=persist,
        )
        if started is None or len(captured) != 1:
            raise RuntimeError("durable worker start failed")
        self._revisions[task.id] = captured[0].revision
        self._attempts[task.id] = attempt_id
        return started

    async def _record_worker_result(
        self,
        contract: TaskContract,
        task: Task,
        message: str,
        *,
        result_kind: str | None = None,
    ) -> Task:
        if result_kind not in {None, "answer", "patch"}:
            raise RuntimeError("durable worker result kind is invalid")
        revision = self._revisions.get(task.id)
        attempt_id = self._attempts.get(task.id)
        if revision is None or attempt_id is None:
            raise RuntimeError("durable worker attempt binding is unavailable")
        captured: list[StoredTaskSnapshot] = []

        def persist(candidate: Task) -> None:
            if candidate.result_digest is None or candidate.result is None:
                raise RuntimeError("durable worker result binding is unavailable")
            output_digest = candidate.result.get("output_digest")
            if not isinstance(output_digest, str):
                raise RuntimeError("durable worker output binding is unavailable")
            event = WorkerEvent(
                event_id=uuid4(),
                tenant_id=candidate.tenant_id,
                task_id=candidate.id,
                attempt_id=attempt_id,
                contract_digest=candidate.contract_digest,
                worker_identity=self._EXECUTOR_IDENTITY,
                sequence=2,
                event_type=WorkerEventType.RESULT_READY,
                emitted_at=self._now(),
                payload={
                    "result_ref": output_digest,
                    "result_revision": candidate.result_revision,
                    "result_digest": candidate.result_digest,
                },
            )
            self._policy_store.accept_event(event)
            captured.append(
                self._store.save_task_and_append_event(
                    candidate,
                    event,
                    expected_revision=revision,
                )
            )

        recorded = await self._state.update(
            task.id,
            status=TaskStatus.DRAFT,
            agent_id=self._EXECUTOR_IDENTITY,
            result={
                "output_digest": canonical_json_digest({"message": message}),
                "summary": "Worker completed.",
                **({"result_kind": result_kind} if result_kind is not None else {}),
            },
            before_commit=persist,
        )
        if recorded is None or len(captured) != 1:
            raise RuntimeError("durable worker result failed")
        self._revisions[task.id] = captured[0].revision
        return recorded

    async def _escalate(
        self, task: Task, *, error_code: str = "worker_failed"
    ) -> None:
        if task.status is not TaskStatus.PARSING:
            await super()._escalate(task)
            return
        try:
            await self._record_worker_failure(task, error_code=error_code)
        except Exception:
            return

    async def _record_worker_failure(
        self, task: Task, *, error_code: str = "worker_failed"
    ) -> None:
        safe_message = _WORKER_FAILURE_MESSAGES.get(error_code)
        if safe_message is None:
            raise ValueError("worker failure code is invalid")
        revision = self._revisions.get(task.id)
        attempt_id = self._attempts.get(task.id)
        if revision is None or attempt_id is None:
            raise RuntimeError("durable worker attempt binding is unavailable")
        event = WorkerEvent(
            event_id=uuid4(),
            tenant_id=task.tenant_id,
            task_id=task.id,
            attempt_id=attempt_id,
            contract_digest=task.contract_digest,
            worker_identity=self._EXECUTOR_IDENTITY,
            sequence=2,
            event_type=WorkerEventType.FAILED,
            emitted_at=self._now(),
            payload={
                "error_code": error_code,
                "safe_message": safe_message,
                "retryable": False,
            },
        )
        self._policy_store.accept_event(event)
        captured: list[int] = []

        def persist(candidate: Task) -> None:
            result = self._store.save_task_and_enqueue_status(
                candidate,
                expected_revision=revision,
                destination_ref=self._destination_refs[candidate.tenant_id],
                event=event,
                now=self._now(),
            )
            captured.append(result.task_revision)

        failed = await self._state.update(
            task.id,
            status=TaskStatus.FAILED,
            error_message=error_code,
            before_commit=persist,
        )
        if failed is None or len(captured) != 1:
            raise RuntimeError("durable worker failure was not committed")
        self._revisions[task.id] = captured[0]

    async def deliver_pending(
        self,
        tenant_id: str,
        sender: StatusDeliveryBoundary,
        *,
        limit: int = 100,
        lease_seconds: int = 60,
    ) -> tuple[OutboxMessage, ...]:
        """Deliver content-free status records through one injected fake boundary."""
        if tenant_id not in self._destination_refs:
            raise ValueError("tenant delivery is not configured")
        owner = uuid4()
        claimed = self._store.claim_outbox_messages(
            tenant_id,
            lease_owner=owner,
            lease_duration_seconds=lease_seconds,
            limit=limit,
            now=self._now(),
        )
        outcomes: list[OutboxMessage] = []
        expected_destination = self._destination_refs[tenant_id]
        for message in claimed:
            if message.destination_ref != expected_destination:
                delivered = False
            else:
                try:
                    delivered = await sender(message)
                    if type(delivered) is not bool:
                        raise TypeError("delivery boundary must return bool")
                except asyncio.CancelledError:
                    raise
                except Exception:
                    delivered = False
            if message.lease_id is None:
                raise RuntimeError("claimed outbox message has no lease")
            receipt = DeliveryReceipt(
                receipt_id=uuid4(),
                tenant_id=message.tenant_id,
                message_id=message.message_id,
                lease_id=message.lease_id,
                attempt_count=message.attempt_count,
                receipt_type=ReceiptType.ACK if delivered else ReceiptType.NACK,
                received_at=self._now(),
            )
            outcomes.append(
                self._store.record_outbox_receipt(
                    receipt,
                    lease_owner=owner,
                    now=self._now(),
                )
            )
        return tuple(outcomes)

    @staticmethod
    def _recovery_response(snapshot: StoredTaskSnapshot) -> FakeVerticalResponse:
        projection = snapshot.projection
        if projection.status in {TaskStatus.COMPLETED, TaskStatus.ANSWERED}:
            return FakeVerticalResponse(
                status=FakeVerticalStatus.RECOVERED,
                task_id=projection.task_id,
                result_digest=projection.result_digest,
                message="Task was already completed.",
            )
        if projection.status in {TaskStatus.FAILED, TaskStatus.ESCALATE}:
            return FakeVerticalResponse(
                status=FakeVerticalStatus.FAILED,
                task_id=projection.task_id,
                result_digest=projection.result_digest,
                message="Task previously ended without completion.",
            )
        return FakeVerticalResponse(
            status=FakeVerticalStatus.RECOVERY_REQUIRED,
            task_id=projection.task_id,
            result_digest=projection.result_digest,
            message="Task requires explicit recovery; worker was not restarted.",
        )

    def _now(self) -> datetime:
        try:
            value = self._clock()
        except Exception:
            raise RuntimeError("runtime clock is unavailable") from None
        if (
            type(value) is not datetime
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise RuntimeError("runtime clock is unavailable")
        return value.astimezone(UTC)
