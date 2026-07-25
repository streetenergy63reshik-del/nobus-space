"""Product-facing Telegram UX for Nobus Space MVP-1."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Protocol
from uuid import UUID

from src.application.durable_runtime import PreparedTask
from src.application.fake_vertical import FakeVerticalResponse, FakeVerticalStatus
from src.application.gate5a4 import Gate5A4DraftOutcome
from src.application.nobus_memory import NobusMemory
from src.application.owner_files import (
    OwnerFileContext,
    OwnerFileContextSelection,
    OwnerFileSelection,
    OwnerFileSensitiveError,
)
from src.application.product_effects import (
    ProductEffectKind,
    ProductEffectService,
    approval_reference,
)
from src.application.business_notes import BusinessNotesService
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
from src.integrations import (
    CalendarActionKind,
    GoogleDriveActionKind,
    GoogleTaskActionKind,
)
from src.transport.telegram import CallbackQuery, IngressStatus, TextMessage, VoiceMessage
from src.voice import VoicePreviewService
from src.workers.codex_limits import WeeklyLimitSnapshot


_VOICE_LIMIT = 10 * 1024 * 1024
_EFFECT_DELIVERY_ATTEMPTS = 3
_MESSAGE_CHUNK = 3_400
_CALLBACK_ACK_TIMEOUT_SECONDS = 2.0
_CALLBACK_CLEANUP_TIMEOUT_SECONDS = 2.0
_DRAFT_QUEUE_LIMIT = 32
_EXECUTION_QUEUE_MAXSIZE = 40
_TERMINALIZE_ATTEMPTS = 3
_MOSCOW = timezone(timedelta(hours=3), "MSK")
_FILE_REQUEST_RE = re.compile(
    r"^\s*(?:\u043f\u0440\u0438\u0448\u043b\u0438|\u043e\u0442\u043f\u0440\u0430\u0432\u044c|"
    r"\u043d\u0430\u043f\u0440\u0430\u0432\u044c|\u0434\u0430\u0439)\s+"
    r"\u043c\u043d\u0435\s+(?:\u0444\u0430\u0439\u043b|\u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442)\s+"
    r"(.+?)\s*$",
    re.IGNORECASE,
)
_FILE_FOLLOWUP_RE = re.compile(
    r"\b(?:\u0438|\u0430|\u0437\u0430\u0442\u0435\u043c|\u043f\u043e\u0441\u043b\u0435)\s+"
    r"(?:\u043f\u0440\u043e\u0430\u043d\u0430\u043b\u0438\u0437\u0438\u0440\w*|\u043f\u0440\u043e\u0447\u0438\u0442\u0430\w*|"
    r"\u0438\u0437\u0443\u0447\w*|\u0438\u0437\u043c\u0435\u043d\w*|\u043f\u0440\u043e\u0432\u0435\u0440\w*)\b",
    re.IGNORECASE,
)


def _file_request_query(value: str) -> str | None:
    match = _FILE_REQUEST_RE.fullmatch(value)
    if match is None or _FILE_FOLLOWUP_RE.search(match.group(1)):
        return None
    return match.group(1)


_FILE_ANALYSIS_RE = re.compile(
    r"^\s*(?:\u043f\u0440\u043e\u0430\u043d\u0430\u043b\u0438\u0437\u0438\u0440\w*|\u043f\u0440\u043e\u0447\u0438\u0442\u0430\u0439|\u0438\u0437\u0443\u0447\u0438|\u0441\u0434\u0435\u043b\u0430\u0439\s+\u0440\u0435\u0437\u044e\u043c\w*)\s+"
    r"(?:\u0444\u0430\u0439\u043b\w*|\u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\w*)?\s*[\u00ab\"']?(.+?\.(?:csv|docx|html?|json|md|txt|xlsx))[\u00bb\"']?\s*$",
    re.IGNORECASE,
)
_CALENDAR_HINT_RE = re.compile(
    r"\b(?:календар\w*|встреч\w*|созвон\w*|событи\w*|calendar|meeting|appointment)\b",
    re.IGNORECASE,
)
_GOOGLE_TASKS_HINT_RE = re.compile(
    r"\b(?:google\s+tasks?|гугл[е]?\s+(?:задач\w*|таск\w*)|"
    r"задач\w*\s+в\s+google|список\s+google\s+tasks?)\b",
    re.IGNORECASE,
)
_GOOGLE_DRIVE_HINT_RE = re.compile(
    r"\b(?:google\s+drive|гугл[е]?\s+диск\w*|google\s+диск\w*|"
    r"(?:файл|документ)\w*\s+(?:из|на)\s+(?:google|гугл))\b",
    re.IGNORECASE,
)

_RESEARCH_HINT_RE = re.compile(
    r"\b(?:исслед\w*|проанализир\w*|собер\w*|провед\w*|найд\w*)\b"
    r"(?s:.*?)\b(?:интернет\w*|веб\w*|web|новост\w*|актуальн\w*|"
    r"последн\w*\s+(?:недел\w*|месяц\w*|дн\w*|изменен\w*)|"
    r"(?:официальн\w*|публичн\w*)\s+источник\w*|"
    r"(?:новостн\w*\s+)?(?:портал\w*|сми))\b",
    re.IGNORECASE,
)


def _message_chunks(value: str) -> tuple[str, ...]:
    if not isinstance(value, str) or not value:
        raise ValueError("Telegram message is invalid")
    chunks: list[str] = []
    current = ""
    for line in value.splitlines(keepends=True):
        while len(line) > _MESSAGE_CHUNK:
            if current:
                chunks.append(current.rstrip())
                current = ""
            chunks.append(line[:_MESSAGE_CHUNK].rstrip())
            line = line[_MESSAGE_CHUNK:]
        if len(current) + len(line) > _MESSAGE_CHUNK:
            chunks.append(current.rstrip())
            current = line
        else:
            current += line
    if current:
        chunks.append(current.rstrip())
    return tuple(chunk for chunk in chunks if chunk)
_DOCUMENT_NO_OVERWRITE_RE = re.compile(
    r"\b(?:\u043d\u0435\s+(?:\u043f\u0435\u0440\u0435\u0437\u0430\u043f\u0438\u0441\u044b\u0432\u0430\u0439\w*|"
    r"\u0438\u0437\u043c\u0435\u043d\u044f\u0439\w*|\u0437\u0430\u043c\u0435\u043d\u044f\u0439\w*)|"
    r"\u0431\u0435\u0437\s+\u043f\u0435\u0440\u0435\u0437\u0430\u043f\u0438\u0441\u0438|"
    r"\u0441\u043e\u0445\u0440\u0430\u043d\u0438\w*\s+(?:\u0438\u0441\u0445\u043e\u0434\u043d\w*|\u043e\u0440\u0438\u0433\u0438\u043d\u0430\u043b\w*)|"
    r"(?:\u0441\u043e\u0437\u0434\u0430\u0439|\u0441\u0434\u0435\u043b\u0430\u0439)\w*\s+\u043a\u043e\u043f\u0438\w*|"
    r"\u043d\u0435\s+\u0442\u0440\u043e\u0433\u0430\u0439\w*\s+(?:\u0438\u0441\u0445\u043e\u0434\u043d\w*|\u043e\u0440\u0438\u0433\u0438\u043d\u0430\u043b\w*))\b",
    re.IGNORECASE,
)
_DOCUMENT_DELIVERY_OPEN = "[deliver:document]"
_DOCUMENT_DELIVERY_CLOSE = "[/deliver:document]"
_DOCUMENT_HINT_RE = re.compile(
    r"\b(?:созда\w*|сформир\w*|подготов\w*|сдела\w*|собер\w*|представ\w*|оформ\w*|отредактир\w*|измени\w*|обнови\w*|перезапиш\w*|замени\w*)\b"
    r"(?s:.*?)\b(?:документ\w*|word|excel|pdf|html|docx|xlsx|ворд\w*|эксел\w*)\b",
    re.IGNORECASE,
)
_NOTES_PRIVATE_HINT_RE = re.compile(
    r"(?:\b(?:резюм\w*|итог\w*|задач\w*)\b(?s:.*?)\bзамет\w*\b|"
    r"\bзамет\w*\b(?s:.*?)\b(?:резюм\w*|итог\w*|задач\w*)\b)",
    re.IGNORECASE,
)
_MEMORY_SAVE_RE = re.compile(
    r"^\s*(?:сохрани|запомни)(?:\s+это)?\s+(?:в\s+)?"
    r"(?:nobus\s*memory|нобус\s*(?:memory|памят\w*)|памят\w*)"
    r"\s*[:—-]\s*(.+?)\s*$",
    re.IGNORECASE | re.DOTALL,
)
_MONTHS = (
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)



def _document_delivery(instruction: str) -> tuple[str, str] | None:
    prefix = _DOCUMENT_DELIVERY_OPEN + "\n"
    if not isinstance(instruction, str) or not instruction.startswith(prefix):
        return None
    closing = "\n" + _DOCUMENT_DELIVERY_CLOSE + "\n"
    payload, separator, _ = instruction[len(prefix):].partition(closing)
    if not separator or len(payload) > 1_024:
        raise ValueError("document delivery metadata is invalid")
    try:
        value = json.loads(payload)
    except (TypeError, ValueError):
        raise ValueError("document delivery metadata is invalid") from None
    if (
        type(value) is not dict
        or set(value) != {"path", "title"}
        or not all(
            isinstance(value[key], str)
            and value[key].strip()
            and len(value[key]) <= 256
            and "\x00" not in value[key]
            and "|" not in value[key]
            for key in ("path", "title")
        )
    ):
        raise ValueError("document delivery metadata is invalid")
    return value["path"], value["title"]

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
        message_thread_id: int | None = None,
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

    async def context(self, query: str) -> OwnerFileContextSelection: ...

@dataclass(frozen=True, slots=True)
class _QueuedDraft:
    prepared: PreparedTask
    message: TextMessage | VoiceMessage | CallbackQuery
    envelope: TrustedIngressEnvelope


@dataclass(frozen=True, slots=True)
class _QueuedPatch:
    proposal: PatchProposal
    approver_identity: str
    approval_evidence_ref: str


@dataclass(frozen=True, slots=True)
class _QueuedEffect:
    callback: TextMessage | VoiceMessage | CallbackQuery
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
    """Owner text and voice run directly; only destructive effects use buttons."""

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
        calendar_planner: Any | None = None,
        calendar_service: Any | None = None,
        google_tasks_planner: Any | None = None,
        google_tasks_service: Any | None = None,
        google_drive_planner: Any | None = None,
        google_drive_service: Any | None = None,
        business_notes: BusinessNotesService | None = None,
        nobus_memory: NobusMemory | None = None,
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
            or (
                calendar_planner is not None
                and not callable(
                    getattr(calendar_planner, "plan_calendar_action", None)
                )
            )
            or (
                calendar_service is not None
                and not all(
                    callable(getattr(calendar_service, name, None))
                    for name in ("execute", "resolve_delete", "delete_event")
                )
            )
            or (
                (calendar_planner is None) is not (calendar_service is None)
            )
            or (
                calendar_service is not None and product_effects is None
            )
            or (
                google_tasks_planner is not None
                and not callable(
                    getattr(google_tasks_planner, "plan_google_task_action", None)
                )
            )
            or (
                google_tasks_service is not None
                and not all(
                    callable(getattr(google_tasks_service, name, None))
                    for name in (
                        "execute",
                        "resolve_delete",
                        "delete_task",
                    )
                )
            )
            or (
                (google_tasks_planner is None)
                is not (google_tasks_service is None)
            )
            or (
                google_tasks_service is not None and product_effects is None
            )
            or (
                google_drive_planner is not None
                and not callable(
                    getattr(google_drive_planner, "plan_google_drive_action", None)
                )
            )
            or (
                google_drive_service is not None
                and not callable(getattr(google_drive_service, "execute", None))
            )
            or (
                (google_drive_planner is None)
                is not (google_drive_service is None)
            )
            or (
                google_drive_service is not None and product_effects is None
            )
            or (
                business_notes is not None
                and not all(
                    callable(getattr(business_notes, name, None))
                    for name in ("handle_text", "summarize_private")
                )
            )
            or (
                nobus_memory is not None
                and not all(
                    callable(getattr(nobus_memory, name, None))
                    for name in ("retrieve", "remember")
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
        self._calendar_planner = calendar_planner
        self._calendar_service = calendar_service
        self._google_tasks_planner = google_tasks_planner
        self._google_tasks_service = google_tasks_service
        self._google_drive_planner = google_drive_planner
        self._google_drive_service = google_drive_service
        self._business_notes = business_notes
        self._nobus_memory = nobus_memory
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
        message: TextMessage | VoiceMessage | CallbackQuery,
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
        payload = ingress.payload
        if payload.binding_purpose == "business_notes":
            return await self._handle_business_notes(payload)
        await self._expire_task_drafts()
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
        elif command == "/notes":
            await self._send_private_notes(
                payload,
                _argument(payload.text)
                or "Собери резюме Заметок бизнеса за сегодня",
            )
        elif command == "/file":
            await self._send_owner_file(payload.chat_id, _argument(payload.text))
        elif command in {"/help", "/start"}:
            await self._api.send_message(payload.chat_id, self._help_text())
        elif command in {"/task", "/calendar"}:
            await self._start_owner_instruction(
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
            file_query = _file_request_query(payload.text)
            if file_query is not None:
                await self._send_owner_file(payload.chat_id, file_query)
            else:
                await self._start_owner_instruction(
                    payload, ingress.envelope, payload.text
                )
        return True

    def _status_text(self) -> str:
        voice = "активен" if self._voice_service is not None else "не активирован"
        queue_status = ""
        if self._execution_queue is not None:
            queue_status = (
                f"\nВ работе: {self._active_jobs}"
                f"\nВ очереди: {self._execution_queue.qsize()}"
            )
        return (
            "Nobus Space\n"
            "Telegram: online\n"
            f"Голос: {voice}"
            f"{queue_status}"
        )

    def _help_text(self) -> str:
        return (
            "Nobus Space готов к работе.\n\n"
            "Напишите задачу обычным сообщением или продиктуйте её. Голосовое сообщение сначала "
            "распознаётся локально, а затем выполняется как команда владельца. "
            "Чтение, анализ, интернет-исследование, создание нового результата, календарь и "
            "Google Tasks выполняются без дополнительной кнопки.\n\n"
            "Отдельное подтверждение появится только для удаления, применения "
            "изменений кода и других необратимых действий.\n\n"
            "Меню:\n"
            "/status — состояние и очередь\n"
            "/limit — недельный лимит Codex\n"
            "/notes — резюме Заметок бизнеса\n"
            "/file <имя> — получить файл\n"
            "Сохранить факт: Сохрани в Nobus Memory: <текст>\n"
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


    async def _remember_owner_statement(
        self,
        message: TextMessage | VoiceMessage,
        envelope: TrustedIngressEnvelope,
        statement: str,
    ) -> None:
        if self._nobus_memory is None:
            await self._api.send_message(
                message.chat_id, "Nobus Memory пока не подключена."
            )
            return
        try:
            await asyncio.to_thread(
                self._nobus_memory.remember,
                statement,
                source_ref=f"telegram:owner:{envelope.envelope_revision}",
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._api.send_message(
                message.chat_id,
                "Не удалось безопасно сохранить запись. "
                "Не отправляйте в память пароли и токены.",
            )
            return
        await self._api.send_message(message.chat_id, "Сохранено в Nobus Memory.")


    async def _send_private_notes(
        self, message: TextMessage | VoiceMessage, request: str
    ) -> None:
        if self._business_notes is None:
            await self._api.send_message(
                message.chat_id,
                "«Заметки бизнеса» пока не подключены.",
            )
            return
        try:
            result = await asyncio.to_thread(
                self._business_notes.summarize_private,
                tenant_id=message.tenant_id,
                request=request,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            result = "Не удалось безопасно прочитать «Заметки бизнеса»."
        await self._api.send_message(message.chat_id, result)

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

    async def _start_owner_instruction(
        self,
        message: TextMessage | VoiceMessage,
        envelope: TrustedIngressEnvelope,
        instruction: str,
    ) -> None:
        normalized = self._instruction(instruction)
        if normalized is None:
            await self._api.send_message(
                message.chat_id,
                f"Задача должна содержать 1–{MAX_TASK_INSTRUCTION_LENGTH} символов.",
            )
            return
        memory_match = _MEMORY_SAVE_RE.fullmatch(normalized)
        if memory_match is not None:
            await self._remember_owner_statement(
                message, envelope, memory_match.group(1)
            )
            return
        if (
            self._business_notes is not None
            and _NOTES_PRIVATE_HINT_RE.search(normalized)
        ):
            await self._send_private_notes(message, normalized)
            return
        file_query = _file_request_query(normalized)
        if file_query is not None:
            await self._send_owner_file(message.chat_id, file_query)
            return
        file_match = _FILE_ANALYSIS_RE.fullmatch(normalized)
        if file_match is not None and self._owner_files is not None:
            await self._analyze_owner_file(
                message, envelope, normalized, file_match.group(1)
            )
            return
        if _RESEARCH_HINT_RE.search(normalized):
            research_instruction = normalized
            if (
                self._product_effects is not None
                and _DOCUMENT_HINT_RE.search(normalized)
            ):
                planner = getattr(
                    self._product_runtime, "plan_document_argument", None
                )
                if not callable(planner):
                    raise RuntimeError("document planner is unavailable")
                try:
                    argument = await planner(normalized, envelope)
                    document_path, title, _ = argument.split("|", 2)
                    delivery = json.dumps(
                        {"path": document_path, "title": title},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    research_instruction = (
                        f"{_DOCUMENT_DELIVERY_OPEN}\n{delivery}\n"
                        f"{_DOCUMENT_DELIVERY_CLOSE}\n{normalized}"
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    await self._api.send_message(
                        message.chat_id,
                        "Не удалось подготовить формат итогового документа. "
                        "Уточните тип файла.",
                    )
                    return
            await self._start_text_task(
                message,
                envelope,
                f"[profile:research.web]\n{research_instruction}",
            )
            return
        if (
            self._product_effects is not None
            and _DOCUMENT_HINT_RE.search(normalized)
        ):
            planner = getattr(
                self._product_runtime, "plan_document_argument", None
            )
            if callable(planner):
                try:
                    argument = await planner(normalized, envelope)
                    document_path = argument.split("|", 1)[0]
                    normalized_path = document_path.replace("\\", "/")
                    allow_overwrite = _owner_authorizes_document_overwrite(
                        normalized, normalized_path
                    )
                    await self._prepare_product_effect(
                        message,
                        envelope,
                        "/document",
                        argument,
                        allow_document_overwrite=allow_overwrite,
                    )
                    return
                except asyncio.CancelledError:
                    raise
                except Exception:
                    await self._api.send_message(
                        message.chat_id,
                        "Не удалось подготовить документ. Уточните формат и содержание.",
                    )
                    return
        if (
            self._google_drive_planner is not None
            and self._google_drive_service is not None
            and _GOOGLE_DRIVE_HINT_RE.search(normalized)
        ):
            try:
                action = await self._google_drive_planner.plan_google_drive_action(
                    normalized, envelope
                )
                if action.kind is not GoogleDriveActionKind.NONE:
                    if self._product_effects is None:
                        raise RuntimeError("Google Drive integration is unavailable")
                    challenge = self._product_effects.prepare_google_drive(
                        action,
                        tenant_id=message.tenant_id,
                        user_id=message.user_id,
                        chat_id=message.chat_id,
                        idempotency_key=envelope.idempotency_key,
                    )
                    if not await self._submit_effect(
                        message,
                        envelope,
                        TelegramAction.RUN_GOOGLE_DRIVE,
                        challenge.token,
                    ):
                        raise RuntimeError(
                            "Google Drive action was not durably enqueued"
                        )
                    return
            except asyncio.CancelledError:
                raise
            except Exception:
                await self._api.send_message(
                    message.chat_id,
                    "Не удалось получить файл из Google Drive. "
                    "Уточните точное имя файла.",
                )
                return
        if (
            self._google_tasks_planner is not None
            and self._google_tasks_service is not None
            and _GOOGLE_TASKS_HINT_RE.search(normalized)
        ):
            try:
                action = await self._google_tasks_planner.plan_google_task_action(
                    normalized, envelope
                )
                if action.kind is GoogleTaskActionKind.DELETE:
                    if self._product_effects is None:
                        raise RuntimeError("Google Tasks deletion is unavailable")
                    challenge = (
                        await self._product_effects.prepare_google_task_delete(
                            action,
                            tenant_id=message.tenant_id,
                            user_id=message.user_id,
                            chat_id=message.chat_id,
                            idempotency_key=envelope.idempotency_key,
                        )
                    )
                    buttons = self._action_buttons(
                        message,
                        (
                            (
                                TelegramAction.DELETE_GOOGLE_TASK,
                                challenge.token,
                                "🗑️ Удалить",
                            ),
                            (
                                TelegramAction.REJECT_GOOGLE_TASK_DELETE,
                                challenge.token,
                                "Отмена",
                            ),
                        ),
                        ttl_seconds=300,
                    )
                    await self._api.send_message(
                        message.chat_id, challenge.preview, buttons=buttons
                    )
                    return
                if action.kind is not GoogleTaskActionKind.NONE:
                    if self._product_effects is None:
                        raise RuntimeError("Google Tasks integration is unavailable")
                    challenge = self._product_effects.prepare_google_task(
                        action,
                        tenant_id=message.tenant_id,
                        user_id=message.user_id,
                        chat_id=message.chat_id,
                        idempotency_key=envelope.idempotency_key,
                    )
                    if not await self._submit_effect(
                        message,
                        envelope,
                        TelegramAction.RUN_GOOGLE_TASK,
                        challenge.token,
                    ):
                        raise RuntimeError(
                            "Google Task action was not durably enqueued"
                        )
                    return
            except asyncio.CancelledError:
                raise
            except Exception:
                await self._api.send_message(
                    message.chat_id,
                    "Не удалось выполнить команду Google Tasks. "
                    "Уточните список, задачу и срок.",
                )
                return
        if (
            self._calendar_planner is not None
            and self._calendar_service is not None
            and _CALENDAR_HINT_RE.search(normalized)
        ):
            try:
                action = await self._calendar_planner.plan_calendar_action(
                    normalized, envelope
                )
                if action.kind is CalendarActionKind.DELETE:
                    if self._product_effects is None:
                        raise RuntimeError("calendar deletion is unavailable")
                    challenge = await self._product_effects.prepare_calendar_delete(
                        action,
                        tenant_id=message.tenant_id,
                        user_id=message.user_id,
                        chat_id=message.chat_id,
                        idempotency_key=envelope.idempotency_key,
                    )
                    buttons = self._action_buttons(
                        message,
                        (
                            (TelegramAction.DELETE_CALENDAR, challenge.token, "🗑️ Удалить"),
                            (TelegramAction.REJECT_CALENDAR_DELETE, challenge.token, "Отмена"),
                        ),
                        ttl_seconds=300,
                    )
                    await self._api.send_message(
                        message.chat_id, challenge.preview, buttons=buttons
                    )
                    return
                if action.kind is not CalendarActionKind.NONE:
                    if self._product_effects is None:
                        raise RuntimeError("calendar integration is unavailable")
                    challenge = self._product_effects.prepare_calendar(
                        action,
                        tenant_id=message.tenant_id,
                        user_id=message.user_id,
                        chat_id=message.chat_id,
                        idempotency_key=envelope.idempotency_key,
                    )
                    if not await self._submit_effect(
                        message,
                        envelope,
                        TelegramAction.RUN_CALENDAR,
                        challenge.token,
                    ):
                        raise RuntimeError("calendar action was not durably enqueued")
                    return
            except asyncio.CancelledError:
                raise
            except Exception:
                await self._api.send_message(
                    message.chat_id,
                    "Не удалось выполнить команду календаря. Уточните событие и время.",
                )
                return
        await self._start_text_task(message, envelope, normalized)

    async def _analyze_owner_file(
        self,
        message: TextMessage | VoiceMessage,
        envelope: TrustedIngressEnvelope,
        instruction: str,
        query: str,
    ) -> None:
        provider = getattr(self._owner_files, "context", None)
        if not callable(provider):
            await self._api.send_message(
                message.chat_id,
                "Анализ содержимого этого файла пока недоступен.",
            )
            return
        try:
            selection = await provider(query.strip())
            if selection.context is not None:
                context = selection.context
                await self._start_text_task(
                    message,
                    envelope,
                    instruction,
                    supplied_context=context,
                )
                return
            if selection.choices:
                choices = "\n".join(f"• {item}" for item in selection.choices)
                await self._api.send_message(
                    message.chat_id,
                    f"Найдено несколько файлов:\n\n{choices}\n\n"
                    "Укажите точный относительный путь.",
                )
                return
            await self._api.send_message(message.chat_id, "Файл не найден.")
        except asyncio.CancelledError:
            raise
        except OwnerFileSensitiveError:
            await self._api.send_message(
                message.chat_id,
                "Файл содержит возможные секреты или персональные данные. "
                "Я не буду передавать его содержимое внешней модели.",
            )
        except Exception:
            await self._api.send_message(
                message.chat_id,
                "Не удалось безопасно прочитать содержимое файла.",
            )

    async def _start_text_task(
        self,
        message: TextMessage | VoiceMessage,
        envelope: TrustedIngressEnvelope,
        instruction: str,
        *,
        supplied_context: OwnerFileContext | None = None,
    ) -> None:
        instruction = self._instruction(instruction)
        if supplied_context is not None and not isinstance(
            supplied_context, OwnerFileContext
        ):
            raise ValueError("supplied file context is invalid")
        if instruction is None:
            await self._api.send_message(
                message.chat_id,
                f"Задача должна содержать 1–{MAX_TASK_INSTRUCTION_LENGTH} символов.",
            )
            return
        prepared: PreparedTask | None = None
        try:
            contextual = getattr(
                self._product_runtime, "prepare_instruction_with_context", None
            )
            if supplied_context is not None:
                if not callable(contextual):
                    raise RuntimeError("contextual worker is unavailable")
                prepared = await contextual(
                    instruction,
                    supplied_context.relative_path,
                    supplied_context.content_digest,
                    envelope,
                )
            else:
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
        try:
            audio = await self._api.download_file(
                message.file_id, size_limit=_VOICE_LIMIT
            )
            preview = await self._voice_service.preview_from_bytes(audio)
            instruction = self._instruction(preview.transcript)
            if instruction is None:
                raise ValueError("voice transcript is invalid")
            await self._start_owner_instruction(message, envelope, instruction)
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._api.send_message(
                message.chat_id,
                "⚠️ Не удалось распознать голосовое сообщение. "
                "Отправьте его ещё раз или напишите задачу текстом.",
            )

    async def _handle_business_notes(
        self, message: TextMessage | VoiceMessage | CallbackQuery
    ) -> bool:
        if self._business_notes is None or isinstance(message, CallbackQuery):
            return False
        note = message
        if isinstance(message, VoiceMessage):
            try:
                if self._voice_service is None:
                    raise RuntimeError("voice service unavailable")
                audio = await self._api.download_file(
                    message.file_id, size_limit=_VOICE_LIMIT
                )
                preview = await self._voice_service.preview_from_bytes(audio)
                instruction = self._instruction(preview.transcript)
                if instruction is None:
                    raise RuntimeError("voice transcript invalid")
                note = TextMessage(
                    **message.model_dump(
                        exclude={"file_id", "duration", "metadata"}
                    ),
                    text=instruction,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                await self._api.send_message(
                    message.chat_id,
                    "Не удалось распознать голосовую заметку. "
                    "Отправьте её ещё раз.",
                    message_thread_id=message.message_thread_id,
                )
                return True
        assert isinstance(note, TextMessage)
        result = await asyncio.to_thread(
            self._business_notes.handle_text, note
        )
        if result is not None:
            await self._api.send_message(
                note.chat_id,
                result,
                message_thread_id=note.message_thread_id,
            )
        return True

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
                                TelegramAction.DELETE_CALENDAR,
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
        message: TextMessage | VoiceMessage,
        envelope: TrustedIngressEnvelope,
        command: str,
        argument: str,
        *,
        allow_document_overwrite: bool = False,
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
                    idempotency_key=envelope.idempotency_key,
                    allow_overwrite=allow_document_overwrite,
                )
            elif command == "/download":
                challenge = await self._product_effects.prepare_download(
                    argument,
                    tenant_id=message.tenant_id,
                    user_id=message.user_id,
                    chat_id=message.chat_id,
                    idempotency_key=envelope.idempotency_key,
                )
            else:
                challenge = self._product_effects.prepare_network(
                    argument,
                    tenant_id=message.tenant_id,
                    user_id=message.user_id,
                    chat_id=message.chat_id,
                    idempotency_key=envelope.idempotency_key,
                )
            action = {
                ProductEffectKind.ARTIFACT: TelegramAction.APPLY_ARTIFACT,
                ProductEffectKind.DOWNLOAD: TelegramAction.APPLY_DOWNLOAD,
                ProductEffectKind.NETWORK: TelegramAction.RUN_NETWORK,
            }[challenge.kind]
            if not await self._submit_effect(
                message, envelope, action, challenge.token
            ):
                raise RuntimeError("product effect was not durably enqueued")
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._api.send_message(
                message.chat_id,
                "Не удалось выполнить действие. Проверьте формат и попробуйте ещё раз.",
            )


    async def _deliver_effect_result(self, chat_id: int, result: Any) -> None:
        operations = (
            (("document", result),)
            if result.filename is not None and result.content is not None
            else tuple(
                ("message", chunk)
                for chunk in _message_chunks(result.message)
            )
        )
        for operation, payload in operations:
            last_error: Exception | None = None
            for attempt in range(_EFFECT_DELIVERY_ATTEMPTS):
                try:
                    if operation == "document":
                        await self._api.send_document(
                            chat_id, payload.filename, payload.content
                        )
                    else:
                        await self._api.send_message(chat_id, payload)
                    break
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    last_error = error
                    if attempt + 1 < _EFFECT_DELIVERY_ATTEMPTS:
                        await asyncio.sleep(0)
            else:
                raise RuntimeError(
                    "product effect delivery failed"
                ) from last_error

    async def _submit_effect(
        self,
        callback: TextMessage | CallbackQuery,
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
        message: TextMessage | CallbackQuery,
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
            TelegramAction.RUN_CALENDAR: (ProductEffectKind.CALENDAR, True),
            TelegramAction.RUN_GOOGLE_TASK: (
                ProductEffectKind.GOOGLE_TASK, True
            ),
            TelegramAction.RUN_GOOGLE_DRIVE: (
                ProductEffectKind.GOOGLE_DRIVE, True
            ),
            TelegramAction.DELETE_GOOGLE_TASK: (
                ProductEffectKind.GOOGLE_TASK_DELETE, True
            ),
            TelegramAction.REJECT_GOOGLE_TASK_DELETE: (
                ProductEffectKind.GOOGLE_TASK_DELETE, False
            ),
            TelegramAction.DELETE_CALENDAR: (
                ProductEffectKind.CALENDAR_DELETE, True
            ),
            TelegramAction.REJECT_CALENDAR_DELETE: (
                ProductEffectKind.CALENDAR_DELETE, False
            ),
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
                query_id=(
                    message.query_id
                    if isinstance(message, CallbackQuery)
                    else f"message:{message.message_id}"
                ),
                effect_token=token,
            ),
        )
        if result.delivery_required:
            await self._deliver_effect_result(message.chat_id, result)
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
        message: TextMessage | VoiceMessage | CallbackQuery,
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
            delivery = _document_delivery(prepared.contract.instruction)
            if delivery is not None:
                if self._product_effects is None:
                    raise RuntimeError("document effects are unavailable")
                document_path, title = delivery
                challenge = self._product_effects.prepare_document(
                    f"{document_path}|{title}|{outcome.answer}",
                    tenant_id=message.tenant_id,
                    user_id=message.user_id,
                    chat_id=message.chat_id,
                    idempotency_key=(
                        f"{envelope.idempotency_key}:research-document"
                    ),
                )
                if not await self._submit_effect(
                    message,
                    envelope,
                    TelegramAction.APPLY_ARTIFACT,
                    challenge.token,
                ):
                    raise RuntimeError("research document was not delivered")
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
        if _patch_deletes_files(outcome.proposal):
            await self._product_runtime.reject_proposal(outcome.proposal)
            await self._api.send_message(
                message.chat_id,
                "Изменение включает удаление файла. Для каждого удаляемого "
                "объекта нужен отдельный L4-запрос с точным путём.",
            )
            await self.deliver_pending()
            return
        approval_digest = canonical_json_digest(
            {
                "actor_identity": envelope.actor_identity,
                "authorization": "exact-owner-command",
                "chat_id": message.chat_id,
                "interaction_id": (
                    message.query_id
                    if isinstance(message, CallbackQuery)
                    else str(message.message_id)
                ),
                "task_id": str(outcome.proposal.task_id),
                "update_id": message.update_id,
            }
        )
        queued = await self._submit_patch(
            outcome.proposal,
            approver_identity=envelope.actor_identity,
            approval_evidence_ref=(
                f"telegram-owner-confirmation:{approval_digest}"
            ),
        )
        if not queued:
            raise RuntimeError("owner-authorized patch was not durably enqueued")

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


def _patch_deletes_files(proposal: PatchProposal) -> bool:
    """File deletion is never inferred from a general owner edit command."""
    patch = proposal.patch.replace("\r\n", "\n")
    normalized = "\n" + patch
    return (
        "\ndeleted file mode " in normalized
        or "\n+++ /dev/null\n" in normalized
    )


def _owner_authorizes_document_overwrite(
    instruction: str, relative_path: str
) -> bool:
    """Only a closed, explicit phrase authorizes replacement of an existing file."""
    if not isinstance(instruction, str) or not isinstance(relative_path, str):
        return False
    normalized = " ".join(instruction.replace("\\", "/").split()).casefold()
    expected = (
        f"перезапиши файл {relative_path.casefold()} с заменой оригинала"
    )
    if normalized == expected:
        return True
    return normalized.startswith(expected + " | ") and bool(
        normalized.removeprefix(expected + " | ").strip()
    )


def _voice_preview(challenge: TaskConfirmationChallenge) -> str:
    return (
        "🎙 Я распознал задачу:\n\n"
        f"{challenge.instruction_preview}\n\n"
        "Проверьте текст и выберите действие. Кнопки действуют 5 минут."
    )
