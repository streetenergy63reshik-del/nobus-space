"""Durable admission extension for the product Telegram control plane."""

from __future__ import annotations

import asyncio
import hashlib
import re
import secrets
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Callable
from uuid import UUID, uuid4

from src.application.durable_runtime import PreparedTask
from src.application.durable_telegram_state import (
    DurableJob,
    DurableTelegramStateError,
    SQLiteTelegramState,
)
from src.application.patch_confirmation import PatchProposal
from src.application.semantic_admission import (
    PendingClarification,
    SemanticClarificationRejected,
    SemanticClarificationRequired,
    TrustedReferenceBinding,
    pending_clarification,
    semantic_clarification_question,
    telegram_semantic_input,
)
from src.application.telegram_product import (
    ProductTelegramControlPlane,
    _QueuedDraft,
    _QueuedEffect,
    _QueuedJob,
    _QueuedPatch,
    _SEMANTIC_NO_EFFECT_PROFILE,
    _TERMINALIZE_ATTEMPTS,
)
from src.contracts import TaskContract, TrustedIngressEnvelope
from src.contracts.models import canonical_json_digest
from src.core.policy import DuplicateIdempotencyKeyError, task_contract_digest
from src.transport.telegram import (
    CallbackQuery,
    IngressStatus,
    TextMessage,
    TrustedIngressResult,
    VoiceMessage,
)


_LEASE_SECONDS = 60
_QUEUE_MAXSIZE = 40
_MAX_JOB_ATTEMPTS = 3
_PROGRESS_INTERVAL_SECONDS = 30
_CLARIFICATION_TOKEN = re.compile(r"[A-Za-z0-9_-]{32,128}")


@dataclass(frozen=True)
class _QueuedMiniAppDraft:
    prepared: PreparedTask
    envelope: TrustedIngressEnvelope


def _effect_task_id(tenant_id: str, token: str) -> UUID:
    return UUID(
        bytes=hashlib.sha256(f"{tenant_id}:{token}".encode()).digest()[:16],
        version=4,
    )


def _miniapp_task_id(tenant_id: str, idempotency_key: str) -> UUID:
    binding = canonical_json_digest(
        {
            "kind": "miniapp_task_create",
            "tenant_id": tenant_id,
            "idempotency_key": idempotency_key,
        }
    )
    return UUID(hex=binding[7:39], version=4)


class DurableProductTelegramControlPlane(ProductTelegramControlPlane):
    """Persist accepted work before returning control to Telegram polling."""

    def __init__(
        self,
        *values: object,
        telegram_state: SQLiteTelegramState,
        execution_concurrency: int,
        **named: object,
    ) -> None:
        if (
            not isinstance(telegram_state, SQLiteTelegramState)
            or type(execution_concurrency) is not int
            or not 1 <= execution_concurrency <= 8
        ):
            raise ValueError("durable product configuration is invalid")
        super().__init__(
            *values,
            execution_concurrency=0,
            **named,
        )
        self._telegram_state = telegram_state
        self._execution_concurrency = execution_concurrency
        self._execution_queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        self._lease_owner = uuid4()
        self._worker_error: str | None = None
        self._worker_error_count = 0

    async def start(self) -> None:
        if self._execution_workers or self._closing or self._closed:
            return
        self._execution_workers = tuple(
            asyncio.create_task(
                self._execution_worker(), name=f"telegram-durable-executor-{index + 1}"
            )
            for index in range(self._execution_concurrency)
        )

    def assert_healthy(self) -> None:
        for worker in self._execution_workers:
            if worker.done():
                if worker.cancelled():
                    raise RuntimeError("durable Telegram worker stopped")
                error = worker.exception()
                if error is not None:
                    raise RuntimeError(
                        "durable Telegram worker stopped"
                    ) from error

    async def submit_miniapp_task(
        self,
        instruction: str,
        envelope: TrustedIngressEnvelope,
        *,
        clarification_token: str | None = None,
    ) -> UUID:
        """Admit one Mini App task through the existing Core and durable queue."""
        if self._closing:
            raise RuntimeError("runtime queue is closing")
        trusted = TrustedIngressEnvelope.model_validate(
            envelope.model_dump(mode="json")
        )
        if getattr(self, "_enable_semantic_admission", False):
            service = getattr(self, "_semantic_admission", None)
            clarifications = getattr(self, "_semantic_clarifications", None)
            if service is None or clarifications is None:
                raise RuntimeError("semantic admission is unavailable")
            if clarification_token is not None and (
                not isinstance(clarification_token, str)
                or _CLARIFICATION_TOKEN.fullmatch(clarification_token) is None
            ):
                raise SemanticClarificationRejected(
                    "semantic clarification binding is invalid"
                )
            conversation_id = int(trusted.auth_context_ref[7:22], 16) or 1
            canonical, bindings = telegram_semantic_input(
                instruction,
                trusted,
                modality="miniapp_text",
                chat_id=conversation_id,
                message_thread_id=None,
            )
            pending: PendingClarification | None = None
            if clarification_token is not None:
                answer_binding = canonical_json_digest(
                    {
                        "clarification_token": clarification_token,
                        "source": "miniapp",
                    }
                )
                pending = clarifications.read(
                    owner_binding=bindings.owner_binding,
                    tenant_binding=bindings.tenant_binding,
                    conversation_binding=bindings.conversation_binding,
                    answer_binding=answer_binding,
                    reply_envelope_revision=trusted.envelope_revision,
                )
                if pending is None:
                    raise SemanticClarificationRejected(
                        "semantic clarification binding is invalid"
                    )
                merged_text = (
                    f"{pending.canonical_input.owner_text}\n\n"
                    "Исходная задача владельца указана выше.\n"
                    "Уточнение владельца:\n"
                    f"{instruction}"
                )
                canonical, bindings = telegram_semantic_input(
                    merged_text,
                    trusted,
                    modality="miniapp_text",
                    chat_id=conversation_id,
                    message_thread_id=None,
                )
                materials = tuple(
                    dict.fromkeys(
                        pending.canonical_input.materials + canonical.materials
                    )
                )
                canonical = canonical.model_copy(update={"materials": materials})
                bindings = replace(
                    bindings,
                    materials=materials,
                    reference_bindings=tuple(
                        TrustedReferenceBinding(
                            ref=value.ref,
                            trusted_boundary=value.boundary,
                            issued_by_server=True,
                            current_intake_member=True,
                            owner_binding=bindings.owner_binding,
                            tenant_binding=bindings.tenant_binding,
                            conversation_binding=bindings.conversation_binding,
                            intake_ref=bindings.intake_ref,
                            intake_revision=bindings.intake_revision,
                        )
                        for value in materials
                    ),
                )
            admission = await service.admit(canonical, bindings)
            if admission.decision.decision == "CLARIFY":
                token = secrets.token_urlsafe(32)
                answer_binding = canonical_json_digest(
                    {"clarification_token": token, "source": "miniapp"}
                )
                ttl = getattr(clarifications, "ttl", None)
                if not isinstance(ttl, timedelta):
                    raise RuntimeError("semantic clarification TTL is invalid")
                clarifications.put(
                    pending_clarification(
                        admission,
                        trusted,
                        now=datetime.now(UTC),
                        ttl=ttl,
                        answer_binding=answer_binding,
                    )
                )
                raise SemanticClarificationRequired(
                    semantic_clarification_question(admission),
                    token,
                )
            if (
                admission.decision.decision != "EXECUTE"
                or not admission.decision.task_contract_allowed
                or admission.decision.selected_capability
                not in {"task.answer.general", "content.transform"}
            ):
                raise RuntimeError("semantic admission did not allow a task")
            if pending is not None and not clarifications.delete(pending):
                raise SemanticClarificationRejected(
                    "semantic clarification binding changed"
                )
            instruction = _SEMANTIC_NO_EFFECT_PROFILE + canonical.owner_text
        prepared = await self._product_runtime.build_instruction(
            instruction, trusted
        )
        contract_values = prepared.contract.model_dump(mode="python")
        contract_values["task_id"] = _miniapp_task_id(
            trusted.tenant_id, trusted.idempotency_key
        )
        prepared = PreparedTask(
            contract=TaskContract.model_validate(contract_values),
            envelope_revision=prepared.envelope_revision,
        )
        if self._closing:
            raise RuntimeError("runtime queue is closing")
        payload = {
            "prepared": {
                "contract": prepared.contract.model_dump(mode="json"),
                "envelope_revision": prepared.envelope_revision,
            },
            "envelope": trusted.model_dump(mode="json"),
        }
        try:
            self._telegram_state.enqueue(
                kind="miniapp_draft",
                tenant_id=prepared.contract.tenant_id,
                task_id=prepared.contract.task_id,
                binding_digest=task_contract_digest(prepared.contract),
                payload=payload,
            )
        except DurableTelegramStateError as error:
            if str(error) == "runtime_job_conflict":
                raise DuplicateIdempotencyKeyError(
                    "durable request conflict"
                ) from None
            raise
        await self._product_runtime.admit_prepared(prepared, trusted)
        await self.start()
        self._wake()
        return prepared.contract.task_id

    def miniapp_task_submitted(
        self, tenant_id: str, task_id: UUID, contract_digest: str
    ) -> bool:
        return self._telegram_state.has_runnable_job(
            kind="miniapp_draft",
            tenant_id=tenant_id,
            task_id=task_id,
            binding_digest=contract_digest,
        )

    async def close(self) -> None:
        async with self._close_lock:
            if self._closed:
                if self._close_failed:
                    raise RuntimeError("Telegram execution queue did not close safely")
                return
            self._closing = True
            workers, self._execution_workers = self._execution_workers, ()
            for worker in workers:
                worker.cancel()
            results = (
                await asyncio.gather(*workers, return_exceptions=True)
                if workers
                else ()
            )
            failures = [
                result
                for result in results
                if isinstance(result, BaseException)
                and not isinstance(result, asyncio.CancelledError)
            ]
            while True:
                try:
                    self._execution_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                else:
                    self._execution_queue.task_done()
            with suppress(Exception):
                await self.deliver_pending()
            effects_close = getattr(self._product_effects, "close", None)
            if callable(effects_close):
                with suppress(Exception):
                    await effects_close()
            self._closed = True
            self._close_failed = bool(failures)
            if failures:
                raise RuntimeError(
                    "Telegram execution queue did not close safely"
                ) from failures[0]

    async def _execution_worker(self) -> None:
        while True:
            marker = False
            try:
                await asyncio.wait_for(self._execution_queue.get(), timeout=1)
                marker = True
            except TimeoutError:
                pass
            try:
                durable = self._telegram_state.claim(
                    lease_owner=self._lease_owner,
                    lease_seconds=_LEASE_SECONDS,
                )
            except asyncio.CancelledError:
                if marker:
                    self._execution_queue.task_done()
                raise
            except Exception:
                self._worker_error = "runtime_store_unavailable"
                self._worker_error_count += 1
                if marker:
                    self._execution_queue.task_done()
                if self._worker_error_count >= 3:
                    raise RuntimeError("durable Telegram worker is unhealthy")
                await asyncio.sleep(1)
                continue
            if durable is None:
                self._worker_error = None
                self._worker_error_count = 0
                if marker:
                    self._execution_queue.task_done()
                continue
            try:
                job = await self._restore(durable)
            except asyncio.CancelledError:
                with suppress(Exception):
                    self._telegram_state.release(
                        durable, lease_owner=self._lease_owner
                    )
                if marker:
                    self._execution_queue.task_done()
                raise
            except Exception:
                self._worker_error = "runtime_job_recovery_failed"
                if durable.attempt_count < _MAX_JOB_ATTEMPTS:
                    self._telegram_state.release(
                        durable, lease_owner=self._lease_owner
                    )
                else:
                    self._telegram_state.fail(
                        durable,
                        lease_owner=self._lease_owner,
                        failure_code=self._worker_error,
                    )
                    await self._finalize_recovery_failure(durable)
                if marker:
                    self._execution_queue.task_done()
                continue
            if job is None:
                await self._clear_durable_progress(durable)
                self._telegram_state.ack(
                    durable, lease_owner=self._lease_owner
                )
                with suppress(Exception):
                    await self.deliver_pending()
                self._worker_error = None
                self._worker_error_count = 0
                if marker:
                    self._execution_queue.task_done()
                continue
            await self._set_progress(job, "⏳ Выполняю задачу…")
            self._active_jobs += 1
            try:
                await self._execute_with_lease(durable, job)
                await self._clear_progress(job)
                if isinstance(job, _QueuedEffect):
                    self._telegram_state.ack_effect_delivery(
                        durable,
                        lease_owner=self._lease_owner,
                        capability_token=job.capability_token,
                        tenant_id=job.callback.tenant_id,
                        user_id=job.callback.user_id,
                        chat_id=job.callback.chat_id,
                    )
                else:
                    self._telegram_state.ack(
                        durable, lease_owner=self._lease_owner
                    )
                self._worker_error = None
                self._worker_error_count = 0
            except asyncio.CancelledError:
                with suppress(Exception):
                    self._telegram_state.release(
                        durable, lease_owner=self._lease_owner
                    )
                raise
            except Exception:
                self._worker_error = (
                    "runtime_effect_failed"
                    if isinstance(job, _QueuedEffect)
                    else "runtime_job_failed"
                )
                delivery_pending = (
                    isinstance(job, _QueuedEffect)
                    and self._product_effects is not None
                    and self._product_effects.delivery_pending(
                        job.capability_token,
                        tenant_id=job.callback.tenant_id,
                        user_id=job.callback.user_id,
                        chat_id=job.callback.chat_id,
                    )
                )
                if delivery_pending:
                    try:
                        self._telegram_state.retry_effect_delivery(
                            durable,
                            lease_owner=self._lease_owner,
                            delay_seconds=30,
                        )
                    except Exception:
                        pass
                    await asyncio.sleep(1)
                elif durable.attempt_count < _MAX_JOB_ATTEMPTS:
                    try:
                        self._telegram_state.release(
                            durable, lease_owner=self._lease_owner
                        )
                    except Exception:
                        pass
                else:
                    if isinstance(job, _QueuedEffect):
                        recorded = (
                            self._product_effects is not None
                            and self._product_effects.record_terminal_failure(
                                job.capability_token,
                                tenant_id=job.callback.tenant_id,
                                user_id=job.callback.user_id,
                                chat_id=job.callback.chat_id,
                            )
                        )
                        if recorded:
                            try:
                                await self._resolve_product_effect(
                                    job.callback,
                                    job.envelope,
                                    job.action,
                                    job.capability_token,
                                )
                                self._telegram_state.ack_effect_delivery(
                                    durable,
                                    lease_owner=self._lease_owner,
                                    capability_token=job.capability_token,
                                    tenant_id=job.callback.tenant_id,
                                    user_id=job.callback.user_id,
                                    chat_id=job.callback.chat_id,
                                )
                                await self._clear_progress(job)
                                continue
                            except Exception:
                                try:
                                    self._telegram_state.retry_effect_delivery(
                                        durable,
                                        lease_owner=self._lease_owner,
                                        delay_seconds=30,
                                    )
                                except Exception:
                                    pass
                                await self._clear_progress(job)
                                continue
                    else:
                        await self._terminalize_job(job)
                    try:
                        self._telegram_state.fail(
                            durable,
                            lease_owner=self._lease_owner,
                            failure_code=self._worker_error,
                        )
                    except Exception:
                        pass
                    await self._clear_progress(job)
                    try:
                        await self.deliver_pending()
                    except Exception:
                        pass
            finally:
                self._active_jobs -= 1
                if marker:
                    self._execution_queue.task_done()

    async def _execute_with_lease(
        self, durable: DurableJob, job: _QueuedJob | _QueuedMiniAppDraft
    ) -> None:
        started_at = asyncio.get_running_loop().time()
        stage = "Проверяю контекст и границы доступа"

        async def report(value: str) -> None:
            nonlocal stage
            stage = value
            elapsed = asyncio.get_running_loop().time() - started_at
            await self._set_progress(job, self._progress_text(stage, elapsed))

        async def operation() -> None:
            if isinstance(job, _QueuedMiniAppDraft):
                outcome = await self._product_runtime.draft_prepared(
                    job.prepared
                )
                if outcome.task_id != job.prepared.contract.task_id:
                    raise RuntimeError("Mini App task execution binding mismatch")
                await self.deliver_pending()
            elif isinstance(job, _QueuedDraft):
                await report(stage)
                await self._draft_and_present(
                    job.prepared,
                    job.message,
                    job.envelope,
                    progress=report,
                )
            elif isinstance(job, _QueuedPatch):
                await self._product_runtime.apply_proposal(
                    job.proposal,
                    approver_identity=job.approver_identity,
                    approval_evidence_ref=job.approval_evidence_ref,
                )
                await self.deliver_pending()
            else:
                await self._resolve_product_effect(
                    job.callback,
                    job.envelope,
                    job.action,
                    job.capability_token,
                )

        execution = asyncio.create_task(operation())
        lease_heartbeat = asyncio.create_task(self._renew(durable))
        progress_heartbeat = asyncio.create_task(
            self._refresh_progress(job, lambda: stage, started_at)
        )
        try:
            done, _ = await asyncio.wait(
                {execution, lease_heartbeat},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if lease_heartbeat in done:
                lease_heartbeat.result()
                raise RuntimeError("runtime lease heartbeat stopped")
            await execution
        finally:
            for task in (execution, lease_heartbeat, progress_heartbeat):
                if not task.done():
                    task.cancel()
            await asyncio.gather(
                execution,
                lease_heartbeat,
                progress_heartbeat,
                return_exceptions=True,
            )

    async def _renew(self, job: DurableJob) -> None:
        while True:
            await asyncio.sleep(_LEASE_SECONDS / 3)
            self._telegram_state.renew(
                job,
                lease_owner=self._lease_owner,
                lease_seconds=_LEASE_SECONDS,
            )

    async def _refresh_progress(
        self,
        job: _QueuedJob | _QueuedMiniAppDraft,
        stage: Callable[[], str],
        started_at: float,
    ) -> None:
        while True:
            await asyncio.sleep(_PROGRESS_INTERVAL_SECONDS)
            elapsed = asyncio.get_running_loop().time() - started_at
            await self._set_progress(
                job, self._progress_text(stage(), elapsed)
            )

    @staticmethod
    def _progress_text(stage: str, elapsed: float) -> str:
        minutes = max(1, int(max(0.0, elapsed) // 60))
        return f"⏳ {stage}…\n\nВ работе: {minutes} мин."

    async def _submit_draft(
        self,
        prepared: PreparedTask,
        message: TextMessage | VoiceMessage | CallbackQuery,
        envelope: TrustedIngressEnvelope,
        *,
        recovery_envelope: TrustedIngressEnvelope | None = None,
    ) -> bool:
        if self._closing:
            return False
        prepared = PreparedTask.validate(prepared)
        recovery_envelope = TrustedIngressEnvelope.model_validate(
            (recovery_envelope or envelope).model_dump(mode="json")
        )
        try:
            TrustedIngressResult(
                status=IngressStatus.ACCEPTED,
                update_id=message.update_id,
                payload=message,
                envelope=envelope,
            )
        except Exception:
            return False
        if (
            recovery_envelope.tenant_id != prepared.contract.tenant_id
            or recovery_envelope.idempotency_key
            != prepared.contract.idempotency_key
            or recovery_envelope.envelope_revision
            != prepared.envelope_revision
        ):
            return False
        payload = {
            "prepared": {
                "contract": prepared.contract.model_dump(mode="json"),
                "envelope_revision": prepared.envelope_revision,
            },
            "message_type": (
                "text"
                if isinstance(message, TextMessage)
                else "voice"
                if isinstance(message, VoiceMessage)
                else "callback"
            ),
            "message": message.model_dump(mode="json"),
            "envelope": envelope.model_dump(mode="json"),
            "recovery_envelope": recovery_envelope.model_dump(mode="json"),
        }
        try:
            self._telegram_state.enqueue(
                kind="draft",
                tenant_id=prepared.contract.tenant_id,
                task_id=prepared.contract.task_id,
                binding_digest=task_contract_digest(prepared.contract),
                payload=payload,
            )
        except Exception:
            return False
        progress_id: int | None = None
        try:
            progress_id = await self._api.send_message(
                message.chat_id, "⏳ Задача в очереди…"
            )
            self._telegram_state.save_progress(
                tenant_id=prepared.contract.tenant_id,
                task_id=prepared.contract.task_id,
                chat_id=message.chat_id,
                message_id=progress_id,
            )
        except Exception:
            if progress_id is not None:
                with suppress(Exception):
                    await self._api.delete_message(
                        message.chat_id, progress_id
                    )
        await self.start()
        self._wake()
        return True

    async def _submit_patch(
        self,
        proposal: PatchProposal,
        *,
        approver_identity: str,
        approval_evidence_ref: str,
    ) -> bool:
        if self._closing:
            return False
        payload = {
            "proposal": proposal.model_dump(mode="json"),
            "approver_identity": approver_identity,
            "approval_evidence_ref": approval_evidence_ref,
        }
        try:
            self._telegram_state.enqueue(
                kind="patch",
                tenant_id=proposal.tenant_id,
                task_id=proposal.task_id,
                binding_digest=proposal.patch_digest,
                payload=payload,
            )
        except Exception:
            return False
        await self.start()
        self._wake()
        return True

    async def _submit_effect(
        self,
        callback: TextMessage | VoiceMessage | CallbackQuery,
        envelope: TrustedIngressEnvelope,
        action: object,
        token: str,
    ) -> bool:
        if self._closing:
            return False
        payload = {
            "callback": callback.model_dump(mode="json"),
            "message_type": (
                "text"
                if isinstance(callback, TextMessage)
                else "voice"
                if isinstance(callback, VoiceMessage)
                else "callback"
            ),
            "envelope": envelope.model_dump(mode="json"),
            "action": getattr(action, "value", None),
            "capability_token": token,
        }
        task_id = _effect_task_id(callback.tenant_id, token)
        try:
            self._telegram_state.enqueue(
                kind="effect",
                tenant_id=callback.tenant_id,
                task_id=task_id,
                binding_digest=canonical_json_digest(payload),
                payload=payload,
            )
        except Exception:
            return False
        await self.start()
        self._wake()
        return True

    def _wake(self) -> None:
        if not self._execution_queue.full():
            self._execution_queue.put_nowait(None)  # type: ignore[arg-type]

    async def _restore(
        self, durable: DurableJob
    ) -> _QueuedJob | _QueuedMiniAppDraft | None:
        payload = durable.payload
        if durable.kind == "miniapp_draft":
            job = self._miniapp_draft_binding(durable)
            admit = getattr(self._product_runtime, "admit_prepared", None)
            if callable(admit):
                await admit(job.prepared, job.envelope)
            recover = getattr(self._product_runtime, "recover_prepared", None)
            if callable(recover) and not await recover(
                job.prepared, job.envelope
            ):
                return None
            return job
        if durable.kind == "effect":
            from src.application.telegram_actions import TelegramAction

            if canonical_json_digest(payload) != durable.binding_digest:
                raise RuntimeError("durable effect binding mismatch")
            message_type = payload.get("message_type", "callback")
            if message_type not in {"text", "voice", "callback"}:
                raise RuntimeError("durable effect message type is invalid")
            callback = (
                TextMessage.model_validate(payload["callback"])
                if message_type == "text"
                else VoiceMessage.model_validate(payload["callback"])
                if message_type == "voice"
                else CallbackQuery.model_validate(payload["callback"])
            )
            envelope = TrustedIngressEnvelope.model_validate(payload["envelope"])
            action = TelegramAction(payload["action"])
            token = payload["capability_token"]
            if not isinstance(token, str) or not token:
                raise RuntimeError("durable effect capability is invalid")
            try:
                TrustedIngressResult(
                    status=IngressStatus.ACCEPTED,
                    update_id=callback.update_id,
                    payload=callback,
                    envelope=envelope,
                )
            except Exception:
                raise RuntimeError("durable effect ingress mismatch") from None
            if (
                callback.tenant_id != durable.tenant_id
                or envelope.tenant_id != durable.tenant_id
                or _effect_task_id(durable.tenant_id, token) != durable.task_id
            ):
                raise RuntimeError("durable effect binding mismatch")
            return _QueuedEffect(callback, envelope, action, token)
        if durable.kind == "patch":
            proposal = PatchProposal.model_validate(payload["proposal"])
            if proposal.task_id != durable.task_id or proposal.patch_digest != durable.binding_digest:
                raise RuntimeError("durable patch binding mismatch")
            recover = getattr(self._product_runtime, "recover_proposal", None)
            if callable(recover) and not await recover(proposal):
                return None
            return _QueuedPatch(
                proposal,
                str(payload["approver_identity"]),
                str(payload["approval_evidence_ref"]),
            )
        job, recovery_envelope = self._draft_binding(durable)
        recover = getattr(self._product_runtime, "recover_prepared", None)
        if callable(recover) and not await recover(
            job.prepared, recovery_envelope
        ):
            return None
        return job

    @staticmethod
    def _miniapp_draft_binding(durable: DurableJob) -> _QueuedMiniAppDraft:
        payload = durable.payload
        if set(payload) != {"prepared", "envelope"}:
            raise RuntimeError("Mini App draft payload mismatch")
        prepared_data = payload["prepared"]
        prepared = PreparedTask.validate(
            PreparedTask(
                contract=TaskContract.model_validate(prepared_data["contract"]),
                envelope_revision=str(prepared_data["envelope_revision"]),
            )
        )
        envelope = TrustedIngressEnvelope.model_validate(payload["envelope"])
        if (
            durable.kind != "miniapp_draft"
            or durable.tenant_id != prepared.contract.tenant_id
            or durable.task_id != prepared.contract.task_id
            or durable.binding_digest != task_contract_digest(prepared.contract)
            or envelope.tenant_id != durable.tenant_id
            or envelope.idempotency_key != prepared.contract.idempotency_key
            or envelope.envelope_revision != prepared.envelope_revision
        ):
            raise RuntimeError("Mini App draft binding mismatch")
        return _QueuedMiniAppDraft(prepared, envelope)

    @staticmethod
    def _draft_binding(
        durable: DurableJob,
    ) -> tuple[_QueuedDraft, TrustedIngressEnvelope]:
        payload = durable.payload
        prepared_data = payload["prepared"]
        prepared = PreparedTask.validate(
            PreparedTask(
                contract=TaskContract.model_validate(prepared_data["contract"]),
                envelope_revision=str(prepared_data["envelope_revision"]),
            )
        )
        message_type = payload["message_type"]
        if message_type not in {"text", "voice", "callback"}:
            raise RuntimeError("durable draft message type is invalid")
        message = (
            TextMessage.model_validate(payload["message"])
            if message_type == "text"
            else VoiceMessage.model_validate(payload["message"])
            if message_type == "voice"
            else CallbackQuery.model_validate(payload["message"])
        )
        envelope = TrustedIngressEnvelope.model_validate(payload["envelope"])
        recovery_envelope = TrustedIngressEnvelope.model_validate(
            payload.get("recovery_envelope", payload["envelope"])
        )
        try:
            TrustedIngressResult(
                status=IngressStatus.ACCEPTED,
                update_id=message.update_id,
                payload=message,
                envelope=envelope,
            )
        except Exception:
            raise RuntimeError("durable draft ingress mismatch") from None
        if (
            prepared.contract.task_id != durable.task_id
            or task_contract_digest(prepared.contract) != durable.binding_digest
            or prepared.contract.tenant_id != durable.tenant_id
            or message.tenant_id != durable.tenant_id
            or envelope.tenant_id != durable.tenant_id
            or recovery_envelope.tenant_id != durable.tenant_id
            or recovery_envelope.idempotency_key
            != prepared.contract.idempotency_key
            or recovery_envelope.envelope_revision
            != prepared.envelope_revision
        ):
            raise RuntimeError("durable draft binding mismatch")
        return _QueuedDraft(prepared, message, envelope), recovery_envelope

    async def _finalize_recovery_failure(self, durable: DurableJob) -> None:
        if durable.kind not in {"draft", "miniapp_draft"}:
            await self._clear_durable_progress(durable)
            return
        try:
            job = (
                self._miniapp_draft_binding(durable)
                if durable.kind == "miniapp_draft"
                else self._draft_binding(durable)[0]
            )
            await self._terminalize_job(job)
            await self.deliver_pending()
        except Exception:
            await self._finish_progress_with_error(durable)
            return
        with suppress(Exception):
            await self._clear_progress(job)

    async def _terminalize_job(
        self, job: _QueuedJob | _QueuedMiniAppDraft
    ) -> None:
        if not isinstance(job, _QueuedMiniAppDraft):
            await super()._terminalize_job(job)
            return
        last_error: Exception | None = None
        contract = job.prepared.contract
        digest = task_contract_digest(contract)
        for _ in range(_TERMINALIZE_ATTEMPTS):
            try:
                await self._product_runtime.cancel_prepared(job.prepared)
                if await self._product_runtime.is_task_terminal(
                    contract.tenant_id, contract.task_id, digest
                ):
                    return
            except asyncio.CancelledError:
                raise
            except Exception as error:
                last_error = error
            await asyncio.sleep(0)
        raise RuntimeError("queued task could not be terminalized") from last_error

    async def _finish_progress_with_error(self, durable: DurableJob) -> None:
        ref = self._telegram_state.read_progress(
            tenant_id=durable.tenant_id,
            task_id=durable.task_id,
        )
        if ref is None:
            return
        text = "⚠️ Задачу не удалось восстановить. Отправьте её повторно."
        edit = getattr(self._api, "edit_message_text", None)
        try:
            if callable(edit):
                await edit(ref.chat_id, ref.message_id, text)
            else:
                await self._api.send_message(ref.chat_id, text)
            if not self._telegram_state.delete_progress(ref):
                raise RuntimeError("progress message commit failed")
        except Exception:
            pass

    async def _set_progress(
        self, job: _QueuedJob | _QueuedMiniAppDraft, text: str
    ) -> None:
        if not isinstance(job, _QueuedDraft):
            return
        ref = self._telegram_state.read_progress(
            tenant_id=job.prepared.contract.tenant_id,
            task_id=job.prepared.contract.task_id,
        )
        edit = getattr(self._api, "edit_message_text", None)
        if ref is not None and callable(edit):
            with suppress(Exception):
                await edit(ref.chat_id, ref.message_id, text)

    async def _clear_progress(
        self, job: _QueuedJob | _QueuedMiniAppDraft
    ) -> None:
        if not isinstance(job, _QueuedDraft):
            return
        await self._clear_progress_binding(
            job.prepared.contract.tenant_id,
            job.prepared.contract.task_id,
        )

    async def _clear_durable_progress(self, job: DurableJob) -> None:
        if job.kind == "draft":
            await self._clear_progress_binding(job.tenant_id, job.task_id)

    async def _clear_progress_binding(
        self, tenant_id: str, task_id: UUID
    ) -> None:
        ref = self._telegram_state.read_progress(
            tenant_id=tenant_id,
            task_id=task_id,
        )
        if ref is not None:
            try:
                await self._api.delete_message(ref.chat_id, ref.message_id)
            except Exception:
                raise RuntimeError("progress message cleanup failed") from None
            if not self._telegram_state.delete_progress(ref):
                raise RuntimeError("progress message commit failed")

    def _status_text(self) -> str:
        voice = (
            "активен" if self._voice_service is not None else "не активирован"
        )
        active, pending = self._telegram_state.queue_counts()
        failed = self._telegram_state.dead_letter_count()
        health = (
            "\nСостояние очереди: требует проверки"
            if self._worker_error is not None or failed
            else ""
        )
        return (
            "Nobus Space\n"
            "Telegram: online\n"
            f"Голос: {voice}\n"
            f"В работе: {active}\n"
            f"В очереди: {pending}\n"
            f"Сбойных задач: {failed}"
            f"{health}"
        )
