"""Product-facing Telegram UX for Nobus Space MVP-1."""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Protocol
from uuid import UUID

from src.application.durable_runtime import PreparedTask
from src.application.fake_vertical import FakeVerticalResponse, FakeVerticalStatus
from src.application.gate5a4 import Gate5A4DraftOutcome
from src.application.owner_files import OwnerFileSelection
from src.application.product_effects import (
    ProductEffectKind,
    ProductEffectService,
    approval_reference,
)
from src.application.patch_confirmation import (
    InMemoryPatchConfirmationStore,
    PatchConfirmationChallenge,
    PatchConfirmationStatus,
    PatchProposal,
)
from src.application.task_profiles import PROFILE_POLICIES, TaskProfile, profile_for_command
from src.application.task_confirmation import (
    MAX_TASK_INSTRUCTION_LENGTH,
    InMemoryTaskConfirmationStore,
    TaskConfirmationChallenge,
    TaskConfirmationStatus,
)
from src.application.telegram_actions import (
    InMemoryTelegramActionStore,
    TelegramAction,
)
from src.application.telegram_control import TelegramControlPlane, _argument, _command
from src.contracts import TrustedIngressEnvelope
from src.contracts.models import canonical_json_digest
from src.core.policy import task_contract_digest
from src.transport.telegram import CallbackQuery, IngressStatus, TextMessage, VoiceMessage
from src.voice import VoicePreviewService
from src.workers.codex_limits import WeeklyLimitSnapshot


_VOICE_LIMIT = 10 * 1024 * 1024
_MESSAGE_CHUNK = 3_400
_CALLBACK_ACK_TIMEOUT_SECONDS = 2.0
_CALLBACK_CLEANUP_TIMEOUT_SECONDS = 2.0
_DRAFT_QUEUE_LIMIT = 32
_EXECUTION_QUEUE_MAXSIZE = 40
_TERMINALIZE_ATTEMPTS = 3
_MOSCOW = timezone(timedelta(hours=3), "MSK")
_FILE_REQUEST_RE = re.compile(
    r"^\s*(?:\u043f\u0440\u0438\u0448\u043b\u0438|\u043e\u0442\u043f\u0440\u0430\u0432\u044c)\s+"
    r"\u043c\u043d\u0435\s+(?:\u0444\u0430\u0439\u043b|\u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442)\s+"
    r"(.+\.(?:docx|html?|pdf|xlsx))\s*$",
    re.IGNORECASE,
)
_MONTHS = (
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def _weekly_limit_text(snapshot: WeeklyLimitSnapshot) -> str:
    reset = "не сообщён OpenAI"
    if snapshot.resets_at is not None:
        moment = datetime.fromtimestamp(snapshot.resets_at, UTC).astimezone(_MOSCOW)
        reset = f"{moment.day} {_MONTHS[moment.month]} в {moment:%H:%M} по Москве"
    return (
        "Лимит Codex на неделю\n\n"
        f"Осталось: {100 - snapshot.used_percent}%\n"
        f"Использовано: {snapshot.used_percent}%\n"
        f"Сброс: {reset}\n\n"
        "OpenAI сообщает квоту в процентах, без абсолютного числа токенов."
    )


class ProductTelegramApi(Protocol):
    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        buttons: tuple[tuple[str, str], ...] = (),
    ) -> int: ...

    async def answer_callback_query(
        self, query_id: str, *, text: str | None = None
    ) -> None: ...

    async def edit_message_text(
        self, chat_id: int, message_id: int, text: str
    ) -> None: ...


    async def delete_message(self, chat_id: int, message_id: int) -> None: ...

    async def download_file(self, file_id: str, *, size_limit: int) -> bytes: ...

    async def send_document(
        self, chat_id: int, filename: str, content: bytes
    ) -> int: ...


class ProductTaskRuntime(Protocol):
    async def prepare_instruction(
        self, instruction: str, envelope: TrustedIngressEnvelope
    ) -> PreparedTask: ...

    async def cancel_prepared(self, prepared: PreparedTask) -> FakeVerticalResponse: ...

    async def is_task_terminal(
        self, tenant_id: str, task_id: UUID, contract_digest: str
    ) -> bool: ...

    async def draft_prepared(self, prepared: PreparedTask) -> Gate5A4DraftOutcome: ...

    async def apply_proposal(
        self,
        proposal: PatchProposal,
        *,
        approver_identity: str,
        approval_evidence_ref: str,
    ) -> FakeVerticalResponse: ...

    async def reject_proposal(self, proposal: PatchProposal) -> FakeVerticalResponse: ...


class WeeklyLimitProvider(Protocol):
    async def fetch_weekly(self) -> WeeklyLimitSnapshot: ...


class OwnerFileProvider(Protocol):
    async def select(self, query: str) -> OwnerFileSelection: ...

@dataclass(frozen=True, slots=True)
class _QueuedDraft:
    prepared: PreparedTask
    message: TextMessage | CallbackQuery
    envelope: TrustedIngressEnvelope


@dataclass(frozen=True, slots=True)
class _QueuedPatch:
    proposal: PatchProposal
    approver_identity: str
    approval_evidence_ref: str


@dataclass(frozen=True, slots=True)
class _QueuedEffect:
    callback: CallbackQuery
    envelope: TrustedIngressEnvelope
    action: TelegramAction
    capability_token: str


_QueuedJob = _QueuedDraft | _QueuedPatch | _QueuedEffect


async def _optional_callback_call(
    operation: Awaitable[object], timeout_seconds: float
) -> None:
    try:
        await asyncio.wait_for(operation, timeout=timeout_seconds)
    except asyncio.CancelledError:
        raise
    except Exception:
        pass


async def _complete_claimed_action(operation: Awaitable[object]) -> bool:
    """Finish a consumed one-shot action before propagating outer cancellation."""
    task = asyncio.create_task(operation)
    was_cancelled = False
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        if task.done():
            task.result()
        was_cancelled = True
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
    task.result()
    return was_cancelled


class ProductTelegramControlPlane(TelegramControlPlane):
    """Text starts immediately; voice and exact code effects use owner buttons."""

    def __init__(
        self,
        gateway: object,
        api: ProductTelegramApi,
        *,
        task_runtime: ProductTaskRuntime,
        task_confirmations: InMemoryTaskConfirmationStore,
        patch_confirmations: InMemoryPatchConfirmationStore,
        action_store: InMemoryTelegramActionStore,
        voice_service: VoicePreviewService | None = None,
        limit_provider: WeeklyLimitProvider | None = None,
        owner_files: OwnerFileProvider | None = None,
        product_effects: ProductEffectService | None = None,
        execution_concurrency: int = 0,
        **values: object,
    ) -> None:
        required = (
            "prepare_instruction",
            "cancel_prepared",
            "is_task_terminal",
            "draft_prepared",
            "apply_proposal",
            "reject_proposal",
        )
        if (
            not all(callable(getattr(task_runtime, name, None)) for name in required)
            or not isinstance(task_confirmations, InMemoryTaskConfirmationStore)
            or not isinstance(patch_confirmations, InMemoryPatchConfirmationStore)
            or not isinstance(action_store, InMemoryTelegramActionStore)
            or (
                voice_service is not None
                and not callable(getattr(voice_service, "preview_from_bytes", None))
            )
            or (
                limit_provider is not None
                and not callable(getattr(limit_provider, "fetch_weekly", None))
            )
            or (
                owner_files is not None
                and not callable(getattr(owner_files, "select", None))
            )
            or (
                product_effects is not None
                and not all(
                    callable(getattr(product_effects, name, None))
                    for name in (
                        "prepare_document",
                        "prepare_download",
                        "prepare_network",
                        "resolve",
                    )
                )
            )
            or not isinstance(execution_concurrency, int)
            or isinstance(execution_concurrency, bool)
            or not 0 <= execution_concurrency <= 8
        ):
            raise ValueError("product Telegram configuration is invalid")
        super().__init__(
            gateway,  # type: ignore[arg-type]
            api,
            task_runtime=task_runtime,  # type: ignore[arg-type]
            task_confirmations=task_confirmations,
            **values,
        )
        self._product_runtime = task_runtime
        self._patch_confirmations = patch_confirmations
        self._action_store = action_store
        self._voice_service = voice_service
        self._limit_provider = limit_provider
        self._owner_files = owner_files
        self._product_effects = product_effects
        self._execution_concurrency = execution_concurrency
        self._execution_queue: asyncio.Queue[_QueuedJob] | None = (
            asyncio.Queue(maxsize=_EXECUTION_QUEUE_MAXSIZE)
            if execution_concurrency
            else None
        )
        self._execution_workers: tuple[asyncio.Task[None], ...] = ()
        self._active_jobs = 0
        self._closing = False
        self._closed = False
        self._close_failed = False
        self._close_lock = asyncio.Lock()

    async def start(self) -> None:
        """Start background executors without coupling them to Telegram polling."""
        if (
            self._execution_queue is None
            or self._execution_workers
            or self._closing
            or self._closed
        ):
            return
        self._execution_workers = tuple(
            asyncio.create_task(
                self._execution_worker(), name=f"telegram-executor-{index + 1}"
            )
            for index in range(self._execution_concurrency)
        )

    async def close(self) -> None:
        """Stop intake and prove every accepted job terminal before returning."""
        async with self._close_lock:
            if self._closed:
                if self._close_failed:
                    raise RuntimeError("Telegram execution queue did not close safely")
                return
            self._closing = True
            failures: list[BaseException] = []
            workers, self._execution_workers = self._execution_workers, ()
            for worker in workers:
                worker.cancel()
            if workers:
                results = await asyncio.gather(*workers, return_exceptions=True)
                failures.extend(
                    result
                    for result in results
                    if isinstance(result, BaseException)
                    and not isinstance(result, asyncio.CancelledError)
                )
            queue = self._execution_queue
            if queue is not None:
                while True:
                    try:
                        job = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    try:
                        await self._terminalize_job(job)
                    except Exception as error:
                        failures.append(error)
                    finally:
                        queue.task_done()
            try:
                await self.deliver_pending()
            except Exception:
                pass
            self._closed = True
            self._close_failed = bool(failures)
            if failures:
                raise RuntimeError(
                    "Telegram execution queue did not close safely"
                ) from failures[0]

    async def wait_idle(self) -> None:
        """Wait until all currently queued work completes."""
        if self._execution_queue is not None:
            await self._execution_queue.join()

    async def _execution_worker(self) -> None:
        queue = self._execution_queue
        if queue is None:
            return
        while True:
            job = await queue.get()
            self._active_jobs += 1
            try:
                if isinstance(job, _QueuedDraft):
                    await self._draft_and_present(
                        job.prepared, job.message, job.envelope
                    )
                else:
                    await self._product_runtime.apply_proposal(
                        job.proposal,
                        approver_identity=job.approver_identity,
                        approval_evidence_ref=job.approval_evidence_ref,
                    )
                    await self.deliver_pending()
            except asyncio.CancelledError:
                await asyncio.shield(self._terminalize_job(job))
                raise
            except Exception:
                await self._terminalize_job(job)
                try:
                    await self.deliver_pending()
                except Exception:
                    pass
            finally:
                self._active_jobs -= 1
                queue.task_done()

    async def _reject_job(self, job: _QueuedJob) -> None:
        try:
            await self._terminalize_job(job)
        finally:
            await self.deliver_pending()

    async def _terminalize_job(self, job: _QueuedJob) -> None:
        prepared = job.prepared if isinstance(job, _QueuedDraft) else None
        proposal = job.proposal if isinstance(job, _QueuedPatch) else None
        if isinstance(job, _QueuedEffect):
            raise RuntimeError("product effect cannot be terminalized as a task")
        binding = prepared.contract if prepared is not None else proposal
        if binding is None:
            raise RuntimeError("queued task binding is unavailable")
        last_error: Exception | None = None
        for _ in range(_TERMINALIZE_ATTEMPTS):
            try:
                outcome = (
                    await self._product_runtime.cancel_prepared(prepared)
                    if prepared is not None
                    else await self._product_runtime.reject_proposal(proposal)
                )
                digest = (
                    task_contract_digest(prepared.contract)
                    if prepared is not None
                    else proposal.contract_digest
                )
                response_matches = (
                    outcome.status is FakeVerticalStatus.REJECTED
                    and outcome.task_id == binding.task_id
                )
                if await self._product_runtime.is_task_terminal(
                    binding.tenant_id, binding.task_id, digest
                ):
                    return
                if response_matches:
                    last_error = RuntimeError(
                        "terminal response has no durable task proof"
                    )
            except asyncio.CancelledError:
                raise
            except Exception as error:
                last_error = error
            await asyncio.sleep(0)
        raise RuntimeError("queued task could not be terminalized") from last_error

    async def _submit_draft(
        self,
        prepared: PreparedTask,
        message: TextMessage | CallbackQuery,
        envelope: TrustedIngressEnvelope,
        *,
        recovery_envelope: TrustedIngressEnvelope | None = None,
    ) -> bool:
        queue = self._execution_queue
        if queue is None:
            await self._draft_and_present(prepared, message, envelope)
            return True
        job = _QueuedDraft(prepared, message, envelope)
        if self._closing or queue.qsize() >= _DRAFT_QUEUE_LIMIT:
            await self._reject_job(job)
            return False
        await self.start()
        try:
            queue.put_nowait(job)
        except asyncio.QueueFull:
            await self._reject_job(job)
            return False
        return True

    async def _submit_patch(
        self,
        proposal: PatchProposal,
        *,
        approver_identity: str,
        approval_evidence_ref: str,
    ) -> bool:
        queue = self._execution_queue
        if queue is None:
            await self._product_runtime.apply_proposal(
                proposal,
                approver_identity=approver_identity,
                approval_evidence_ref=approval_evidence_ref,
            )
            await self.deliver_pending()
            return True
        job = _QueuedPatch(proposal, approver_identity, approval_evidence_ref)
        if self._closing or queue.full():
            await self._reject_job(job)
            return False
        await self.start()
        try:
            queue.put_nowait(job)
        except asyncio.QueueFull:
            await self._reject_job(job)
            return False
        return True

    async def _expire_task_drafts(self) -> None:
        await super()._expire_task_drafts()
        for proposal in self._patch_confirmations.sweep_expired():
            outcome = await self._product_runtime.reject_proposal(proposal)
            if outcome.status is FakeVerticalStatus.REJECTED:
                self._patch_confirmations.acknowledge_expired(proposal)

    async def handle(self, update: dict[str, Any]) -> bool:
        ingress = self._gateway.process_update(update)
        if (
            ingress.status is not IngressStatus.ACCEPTED
            or ingress.payload is None
            or ingress.envelope is None
        ):
            return True
        await self._expire_task_drafts()
        payload = ingress.payload
        if isinstance(payload, CallbackQuery):
            await self._handle_callback(payload, ingress.envelope)
            return True
        if isinstance(payload, VoiceMessage):
            await self._create_voice_preview(payload, ingress.envelope)
            return True
        if not isinstance(payload, TextMessage):
            return True

        command = _command(payload.text)
        profile = profile_for_command(command)
        if command == "/status":
            await self._api.send_message(payload.chat_id, self._status_text())
        elif command == "/limit":
            await self._send_limit(payload.chat_id)
        elif command == "/file":
            await self._send_owner_file(payload.chat_id, _argument(payload.text))
        elif command in {"/help", "/start"}:
            await self._api.send_message(payload.chat_id, self._help_text())
        elif command == "/task":
            await self._start_text_task(
                payload, ingress.envelope, _argument(payload.text)
            )
        elif profile is TaskProfile.RESEARCH_WEB:
            query = _argument(payload.text)
            await self._start_text_task(
                payload,
                ingress.envelope,
                f"[profile:research.web]\n{query}" if query else "",
            )
        elif profile in {
            TaskProfile.ARTIFACT_CREATE,
            TaskProfile.DOWNLOAD_QUARANTINE,
            TaskProfile.NETWORK_COMMAND,
        }:
            if not PROFILE_POLICIES[profile].requires_l4:
                raise RuntimeError("product effect profile must require L4")
            await self._prepare_product_effect(
                payload,
                ingress.envelope,
                command,
                _argument(payload.text),
            )
        elif command == "/confirm":
            await self._confirm_voice(
                payload,
                ingress.envelope,
                _argument(payload.text),
                TaskConfirmationStatus.CONFIRMED,
            )
        elif command == "/cancel":
            await self._confirm_voice(
                payload,
                ingress.envelope,
                _argument(payload.text),
                TaskConfirmationStatus.CANCELLED,
            )
        elif command in {"/apply", "/reject"}:
            await self._resolve_patch(
                payload,
                ingress.envelope,
                _argument(payload.text),
                (
                    PatchConfirmationStatus.CONFIRMED
                    if command == "/apply"
                    else PatchConfirmationStatus.CANCELLED
                ),
            )
        elif payload.text.startswith("/"):
            await self._api.send_message(
                payload.chat_id,
                "Неизвестная команда. Откройте меню или используйте /help.",
            )
        else:
            match = _FILE_REQUEST_RE.fullmatch(payload.text)
            if match is not None:
                await self._send_owner_file(payload.chat_id, match.group(1))
            else:
                await self._start_text_task(payload, ingress.envelope, payload.text)
        return True

    def _status_text(self) -> str:
        voice = "активен" if self._voice_service is not None else "не активирован"
        queue_status = ""
        if self._execution_queue is not None:
            queue_status = (
                f"\n\u0412 \u0440\u0430\u0431\u043e\u0442\u0435: {self._active_jobs}"
                f"\n\u0412 \u043e\u0447\u0435\u0440\u0435\u0434\u0438: {self._execution_queue.qsize()}"
            )
        return (
            "Nobus Space\n"
            "Telegram: online\n"
            f"Голос: {voice}"
            f"{queue_status}"
        )

    def _help_text(self) -> str:
        return (
            "Напишите задачу обычным сообщением — готовый результат придёт ответом.\n"
            "Голосовое сообщение сначала будет расшифровано и показано вам "
            "с кнопками «Подтверждаю» и «Отмена».\n\n"
            "Меню:\n"
            "/status — состояние системы\n"
            "/limit — недельный лимит Codex\n"
            "/file <\u0438\u043c\u044f> \u2014 \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442 \u0441 \u043a\u043e\u043c\u043f\u044c\u044e\u0442\u0435\u0440\u0430\n"
            "/research <запрос> — исследование интернета со ссылками\n"
            "/document <путь>|<заголовок>|<текст> — создать документ\n"
            "/download <https-url> — скачать и отправить файл\n"
            "/network <тип>|... — подтверждаемая сетевая команда\n"
            "/help — эта справка\n\n"
            "Не отправляйте пароли, токены и клиентские персональные данные."
        )

    async def _send_limit(self, chat_id: int) -> None:
        if self._limit_provider is None:
            text = "Лимит Codex сейчас недоступен. Попробуйте позже."
        else:
            try:
                snapshot = await self._limit_provider.fetch_weekly()
                text = _weekly_limit_text(snapshot)
            except asyncio.CancelledError:
                raise
            except Exception:
                text = "Лимит Codex сейчас недоступен. Попробуйте позже."
        await self._api.send_message(chat_id, text)

    async def _send_owner_file(self, chat_id: int, query: str) -> None:
        if self._owner_files is None:
            await self._api.send_message(
                chat_id,
                "\u041f\u043e\u043b\u0443\u0447\u0435\u043d\u0438\u0435 \u0444\u0430\u0439\u043b\u043e\u0432 \u0441\u0435\u0439\u0447\u0430\u0441 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u043e.",
            )
            return
        if not isinstance(query, str) or not query.strip():
            await self._api.send_message(
                chat_id,
                "\u0423\u043a\u0430\u0436\u0438\u0442\u0435 \u0438\u043c\u044f: /file <\u0438\u043c\u044f \u0444\u0430\u0439\u043b\u0430>.",
            )
            return
        try:
            selection = await self._owner_files.select(query)
            if selection.document is not None:
                document = selection.document
                await self._api.send_document(
                    chat_id, document.filename, document.content
                )
                return
            if selection.choices:
                choices = "\n".join(
                    f"\u2022 {path}" for path in selection.choices
                )
                await self._api.send_message(
                    chat_id,
                    "\u041d\u0430\u0439\u0434\u0435\u043d\u043e \u043d\u0435\u0441\u043a\u043e\u043b\u044c\u043a\u043e \u0444\u0430\u0439\u043b\u043e\u0432:\n\n"
                    f"{choices}\n\n"
                    "\u0423\u0442\u043e\u0447\u043d\u0438\u0442\u0435: /file <\u0442\u043e\u0447\u043d\u043e\u0435 \u0438\u043c\u044f \u0438\u043b\u0438 \u043f\u0443\u0442\u044c>.",
                )
                return
            await self._api.send_message(
                chat_id, "\u0424\u0430\u0439\u043b \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d."
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._api.send_message(
                chat_id,
                "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e \u043e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c \u0444\u0430\u0439\u043b.",
            )

    async def _start_text_task(
        self,
        message: TextMessage,
        envelope: TrustedIngressEnvelope,
        instruction: str,
    ) -> None:
        instruction = self._instruction(instruction)
        if instruction is None:
            await self._api.send_message(
                message.chat_id,
                f"Задача должна содержать 1–{MAX_TASK_INSTRUCTION_LENGTH} символов.",
            )
            return
        prepared: PreparedTask | None = None
        try:
            prepared = await self._product_runtime.prepare_instruction(
                instruction, envelope
            )
            await self._submit_draft(prepared, message, envelope)
        except asyncio.CancelledError:
            raise
        except Exception:
            if prepared is not None:
                await self._terminalize_job(_QueuedDraft(prepared, message, envelope))
            await self._api.send_message(
                message.chat_id,
                "⚠️ Не удалось обработать задачу. Попробуйте ещё раз.",
            )

    async def _create_voice_preview(
        self, message: VoiceMessage, envelope: TrustedIngressEnvelope
    ) -> None:
        if self._voice_service is None:
            await self._api.send_message(
                message.chat_id,
                "Голосовой ввод пока не активирован. Отправьте задачу текстом.",
            )
            return
        prepared: PreparedTask | None = None
        try:
            audio = await self._api.download_file(
                message.file_id, size_limit=_VOICE_LIMIT
            )
            preview = await self._voice_service.preview_from_bytes(audio)
            instruction = self._instruction(preview.transcript)
            if instruction is None:
                raise ValueError("voice transcript is invalid")
            prepared = await self._product_runtime.prepare_instruction(
                instruction, envelope
            )
            challenge = self._task_confirmations.issue(
                message=message,
                envelope=envelope,
                prepared=prepared,
            )
            token = challenge.confirmation_token.get_secret_value()
            buttons = self._action_buttons(
                message,
                (
                    (TelegramAction.CONFIRM_VOICE, token, "✅ Подтверждаю"),
                    (TelegramAction.CANCEL_VOICE, token, "❌ Отмена"),
                ),
                ttl_seconds=300,
            )
            await self._api.send_message(
                message.chat_id,
                _voice_preview(challenge),
                buttons=buttons,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            if prepared is not None:
                await self._product_runtime.cancel_prepared(prepared)
            await self._api.send_message(
                message.chat_id,
                "⚠️ Не удалось распознать голосовое сообщение. "
                "Отправьте его ещё раз или напишите задачу текстом.",
            )

    async def _handle_callback(
        self, callback: CallbackQuery, envelope: TrustedIngressEnvelope
    ) -> None:
        claimed = self._action_store.consume(callback)
        if claimed is None:
            await _optional_callback_call(
                self._api.answer_callback_query(callback.query_id),
                _CALLBACK_ACK_TIMEOUT_SECONDS,
            )
            await self._api.send_message(
                callback.chat_id, "Кнопка недействительна, уже использована или истекла."
            )
            return

        async def execute_claimed_action() -> None:
            if claimed.action in {
                TelegramAction.CONFIRM_VOICE,
                TelegramAction.CANCEL_VOICE,
            }:
                await self._confirm_voice(
                    callback,
                    envelope,
                    claimed.capability_token,
                    (
                        TaskConfirmationStatus.CONFIRMED
                        if claimed.action is TelegramAction.CONFIRM_VOICE
                        else TaskConfirmationStatus.CANCELLED
                    ),
                )
            elif claimed.action in {
                TelegramAction.APPLY_PATCH,
                TelegramAction.REJECT_PATCH,
            }:
                await self._resolve_patch(
                    callback,
                    envelope,
                    claimed.capability_token,
                    (
                        PatchConfirmationStatus.CONFIRMED
                        if claimed.action is TelegramAction.APPLY_PATCH
                        else PatchConfirmationStatus.CANCELLED
                    ),
                )
            else:
                await _optional_callback_call(
                    self._api.answer_callback_query(
                        callback.query_id,
                        text=(
                            "Выполняю…"
                            if claimed.action
                            in {
                                TelegramAction.APPLY_ARTIFACT,
                                TelegramAction.APPLY_DOWNLOAD,
                                TelegramAction.RUN_NETWORK,
                            }
                            else None
                        ),
                    ),
                    _CALLBACK_ACK_TIMEOUT_SECONDS,
                )
                queued = await self._submit_effect(
                    callback,
                    envelope,
                    claimed.action,
                    claimed.capability_token,
                )
                if not queued:
                    raise RuntimeError(
                        "confirmed effect was not durably enqueued"
                    )

        try:
            was_cancelled = await _complete_claimed_action(execute_claimed_action())
        except (asyncio.CancelledError, Exception):
            self._action_store.release(callback)
            raise
        if not self._action_store.commit(callback):
            raise RuntimeError("Telegram action commit failed")
        await asyncio.gather(
            _optional_callback_call(
                self._api.answer_callback_query(
                    callback.query_id,
                    text=(
                        "Обрабатываю…"
                        if claimed.action is TelegramAction.CONFIRM_VOICE
                        else None
                    ),
                ),
                _CALLBACK_ACK_TIMEOUT_SECONDS,
            ),
            _optional_callback_call(
                self._api.delete_message(callback.chat_id, callback.message_id),
                _CALLBACK_CLEANUP_TIMEOUT_SECONDS,
            ),
        )
        if was_cancelled:
            raise asyncio.CancelledError

    async def _prepare_product_effect(
        self,
        message: TextMessage,
        envelope: TrustedIngressEnvelope,
        command: str,
        argument: str,
    ) -> None:
        if self._product_effects is None:
            await self._api.send_message(
                message.chat_id, "Эта функция пока не активирована."
            )
            return
        try:
            if command == "/document":
                challenge = self._product_effects.prepare_document(
                    argument,
                    tenant_id=message.tenant_id,
                    user_id=message.user_id,
                    chat_id=message.chat_id,
                )
                actions = (
                    TelegramAction.APPLY_ARTIFACT,
                    TelegramAction.REJECT_ARTIFACT,
                )
            elif command == "/download":
                challenge = await self._product_effects.prepare_download(
                    argument,
                    tenant_id=message.tenant_id,
                    user_id=message.user_id,
                    chat_id=message.chat_id,
                )
                actions = (
                    TelegramAction.APPLY_DOWNLOAD,
                    TelegramAction.REJECT_DOWNLOAD,
                )
            else:
                challenge = self._product_effects.prepare_network(
                    argument,
                    tenant_id=message.tenant_id,
                    user_id=message.user_id,
                    chat_id=message.chat_id,
                )
                actions = (
                    TelegramAction.RUN_NETWORK,
                    TelegramAction.REJECT_NETWORK,
                )
            buttons = self._action_buttons(
                message,
                (
                    (actions[0], challenge.token, "✅ Подтверждаю"),
                    (actions[1], challenge.token, "❌ Отмена"),
                ),
                ttl_seconds=600,
            )
            await self._api.send_message(
                message.chat_id, challenge.preview, buttons=buttons
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._api.send_message(
                message.chat_id,
                "Не удалось безопасно подготовить действие. Проверьте формат.",
            )

    async def _submit_effect(
        self,
        callback: CallbackQuery,
        envelope: TrustedIngressEnvelope,
        action: TelegramAction,
        token: str,
    ) -> bool:
        await self._resolve_product_effect(
            callback, envelope, action, token
        )
        if self._product_effects is None or not self._product_effects.finalize_delivery(
            token,
            tenant_id=callback.tenant_id,
            user_id=callback.user_id,
            chat_id=callback.chat_id,
        ):
            raise RuntimeError("product effect delivery finalize failed")
        return True

    async def _resolve_product_effect(
        self,
        message: CallbackQuery,
        envelope: TrustedIngressEnvelope,
        action: TelegramAction,
        token: str,
    ) -> None:
        if self._product_effects is None:
            raise RuntimeError("product effects are unavailable")
        mapping = {
            TelegramAction.APPLY_ARTIFACT: (ProductEffectKind.ARTIFACT, True),
            TelegramAction.REJECT_ARTIFACT: (ProductEffectKind.ARTIFACT, False),
            TelegramAction.APPLY_DOWNLOAD: (ProductEffectKind.DOWNLOAD, True),
            TelegramAction.REJECT_DOWNLOAD: (ProductEffectKind.DOWNLOAD, False),
            TelegramAction.RUN_NETWORK: (ProductEffectKind.NETWORK, True),
            TelegramAction.REJECT_NETWORK: (ProductEffectKind.NETWORK, False),
        }
        selected = mapping.get(action)
        if selected is None:
            raise ValueError("product effect action is invalid")
        kind, approve = selected
        result = await self._product_effects.resolve(
            token,
            expected_kind=kind,
            approve=approve,
            tenant_id=message.tenant_id,
            user_id=message.user_id,
            chat_id=message.chat_id,
            approval_ref=approval_reference(
                actor_identity=envelope.actor_identity,
                query_id=message.query_id,
                effect_token=token,
            ),
        )
        if result.delivery_required:
            if result.filename is not None and result.content is not None:
                await self._api.send_document(
                    message.chat_id, result.filename, result.content
                )
            else:
                await self._api.send_message(message.chat_id, result.message)
        if not self._product_effects.acknowledge_delivery(
            token,
            tenant_id=message.tenant_id,
            user_id=message.user_id,
            chat_id=message.chat_id,
        ):
            raise RuntimeError("product effect delivery commit failed")

    async def _confirm_voice(
        self,
        message: TextMessage | CallbackQuery,
        envelope: TrustedIngressEnvelope,
        token: str,
        action: TaskConfirmationStatus,
    ) -> None:
        result = self._task_confirmations.consume(
            token=token,
            action=action,
            message=message,
            envelope=envelope,
        )
        if result.status is not action or result.prepared is None:
            if (
                result.status is TaskConfirmationStatus.EXPIRED
                and result.prepared is not None
            ):
                try:
                    await self._terminalize_job(
                        _QueuedDraft(result.prepared, message, envelope)
                    )
                    await self.deliver_pending()
                    self._ack_confirmation(
                        self._task_confirmations, token, message.tenant_id
                    )
                except Exception:
                    self._release_confirmation(
                        self._task_confirmations, token, message.tenant_id
                    )
                    raise
                return
            await self._api.send_message(
                message.chat_id, "Подтверждение задачи недействительно или уже использовано."
            )
            return
        if action is TaskConfirmationStatus.CANCELLED:
            try:
                await self._terminalize_job(
                    _QueuedDraft(result.prepared, message, envelope)
                )
                await self.deliver_pending()
                self._ack_confirmation(
                    self._task_confirmations, token, message.tenant_id
                )
            except Exception:
                self._release_confirmation(
                    self._task_confirmations, token, message.tenant_id
                )
                raise
            return
        if result.envelope is None:
            raise RuntimeError("confirmed task envelope is unavailable")
        queued = await self._submit_draft(
            result.prepared,
            message,
            envelope,
            recovery_envelope=result.envelope,
        )
        if not queued:
            self._release_confirmation(
                self._task_confirmations, token, message.tenant_id
            )
            raise RuntimeError("confirmed task was not durably enqueued")
        self._ack_confirmation(
            self._task_confirmations, token, message.tenant_id
        )

    async def _draft_and_present(
        self,
        prepared: PreparedTask,
        message: TextMessage | CallbackQuery,
        envelope: TrustedIngressEnvelope,
        *,
        progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        draft_with_progress = getattr(
            self._product_runtime, "draft_prepared_with_progress", None
        )
        outcome = (
            await draft_with_progress(prepared, progress)
            if progress is not None and callable(draft_with_progress)
            else await self._product_runtime.draft_prepared(prepared)
        )
        if outcome.answer is not None:
            await self.deliver_pending()
            return
        if outcome.proposal is None:
            if outcome.task_id is None:
                await self._api.send_message(
                    message.chat_id,
                    "⚠️ Не удалось подготовить результат. Попробуйте ещё раз.",
                )
            await self.deliver_pending()
            return
        challenge = self._patch_confirmations.issue(
            message=message,
            envelope=envelope,
            proposal=outcome.proposal,
        )
        await self._send_patch_challenge(message, challenge)

    async def _resolve_patch(
        self,
        message: TextMessage | CallbackQuery,
        envelope: TrustedIngressEnvelope,
        token: str,
        action: PatchConfirmationStatus,
    ) -> None:
        result = self._patch_confirmations.consume(
            token=token,
            action=action,
            message=message,
            envelope=envelope,
        )
        if result.proposal is None:
            await self._api.send_message(
                message.chat_id, "Подтверждение diff недействительно или уже использовано."
            )
            return
        if action is PatchConfirmationStatus.CANCELLED:
            await self._product_runtime.reject_proposal(result.proposal)
        else:
            await self._api.send_message(
                message.chat_id,
                "✅ Точный diff подтверждён. Запускаю L2/L3 и локальный commit…",
            )
            approval_digest = canonical_json_digest(
                {
                    "actor_identity": envelope.actor_identity,
                    "chat_id": message.chat_id,
                    "interaction_id": (
                        message.query_id
                        if isinstance(message, CallbackQuery)
                        else str(message.message_id)
                    ),
                    "update_id": message.update_id,
                    "task_id": str(result.proposal.task_id),
                }
            )
            queued = await self._submit_patch(
                result.proposal,
                approver_identity=envelope.actor_identity,
                approval_evidence_ref=f"telegram-owner-confirmation:{approval_digest}",
            )
            if not queued:
                self._release_confirmation(
                    self._patch_confirmations, token, message.tenant_id
                )
                raise RuntimeError("confirmed patch was not durably enqueued")
        self._ack_confirmation(
            self._patch_confirmations, token, message.tenant_id
        )
        await self.deliver_pending()

    @staticmethod
    def _ack_confirmation(store: object, token: str, tenant_id: str) -> None:
        operation = getattr(store, "acknowledge", None)
        if callable(operation) and not operation(token, tenant_id):
            raise RuntimeError("durable confirmation commit failed")

    @staticmethod
    def _release_confirmation(store: object, token: str, tenant_id: str) -> None:
        operation = getattr(store, "release", None)
        if callable(operation):
            operation(token, tenant_id)

    async def _send_patch_challenge(
        self,
        message: TextMessage | CallbackQuery,
        challenge: PatchConfirmationChallenge,
    ) -> None:
        proposal = challenge.proposal
        await self._api.send_message(
            message.chat_id,
            "📄 Подготовлено изменение — файлы ещё не изменены.\n"
            f"Кратко: {proposal.summary}\n"
            f"Файлы: {', '.join(proposal.paths)}",
        )
        chunks = [
            proposal.patch[index : index + _MESSAGE_CHUNK]
            for index in range(0, len(proposal.patch), _MESSAGE_CHUNK)
        ]
        for index, chunk in enumerate(chunks, 1):
            await self._api.send_message(
                message.chat_id, f"Diff {index}/{len(chunks)}:\n{chunk}"
            )
        token = challenge.confirmation_token.get_secret_value()
        buttons = self._action_buttons(
            message,
            (
                (TelegramAction.APPLY_PATCH, token, "✅ Применить"),
                (TelegramAction.REJECT_PATCH, token, "❌ Отклонить"),
            ),
            ttl_seconds=600,
        )
        await self._api.send_message(
            message.chat_id,
            "Проверьте весь diff выше. Применение запустит тесты и локальный commit; "
            "merge и push отключены. Кнопки действуют 10 минут.",
            buttons=buttons,
        )

    def _action_buttons(
        self,
        message: TextMessage | VoiceMessage | CallbackQuery,
        actions: tuple[tuple[TelegramAction, str, str], ...],
        *,
        ttl_seconds: int,
    ) -> tuple[tuple[str, str], ...]:
        return tuple(
            (
                label,
                self._action_store.issue(
                    action=action,
                    capability_token=capability,
                    user_id=message.user_id,
                    chat_id=message.chat_id,
                    ttl_seconds=ttl_seconds,
                ),
            )
            for action, capability, label in actions
        )

    @staticmethod
    def _instruction(value: str) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        if (
            not normalized
            or len(normalized) > MAX_TASK_INSTRUCTION_LENGTH
            or "\x00" in normalized
        ):
            return None
        return normalized


def _voice_preview(challenge: TaskConfirmationChallenge) -> str:
    return (
        "🎙 Я распознал задачу:\n\n"
        f"{challenge.instruction_preview}\n\n"
        "Проверьте текст и выберите действие. Кнопки действуют 5 минут."
    )
