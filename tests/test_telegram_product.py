"""Product UX regressions for the live Telegram control plane."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from src.application.durable_runtime import PreparedTask
from src.application.fake_vertical import FakeVerticalResponse, FakeVerticalStatus
from src.application.gate5a4 import Gate5A4DraftOutcome
from src.application.owner_files import OwnerDocument, OwnerFileSelection
from src.application.patch_confirmation import (
    InMemoryPatchConfirmationStore,
    PatchProposal,
    patch_proposal_digest,
)
from src.application.task_confirmation import InMemoryTaskConfirmationStore
from src.application.telegram_actions import InMemoryTelegramActionStore
from src.application.telegram_product import ProductTelegramControlPlane
from src.contracts.models import canonical_json_digest
from src.core.policy import task_contract_digest
from src.transport.telegram import ActorBinding, PollingCheckpointUpdateIdStore, TelegramGateway
from src.voice import VoicePreview
from tests.test_telegram_task_control import (
    AUTH_REF,
    DESTINATION_REF,
    TENANT_ID,
    USER_ID,
    FakeStatusSender,
    MutableClock,
    build_harness,
)


class FakeProductApi:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str, tuple[tuple[str, str], ...]]] = []
        self.answered: list[str] = []
        self.callback_texts: list[str | None] = []
        self.callback_failure = False
        self.callback_gate: asyncio.Event | None = None
        self.deleted: list[tuple[int, int]] = []
        self.delete_failure = False
        self.documents: list[tuple[int, str, bytes]] = []

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        buttons: tuple[tuple[str, str], ...] = (),
    ) -> int:
        self.sent.append((chat_id, text, buttons))
        return len(self.sent)

    async def answer_callback_query(
        self, query_id: str, *, text: str | None = None
    ) -> None:
        if self.callback_gate is not None:
            await self.callback_gate.wait()
        if self.callback_failure:
            raise RuntimeError("transient callback failure")
        self.answered.append(query_id)
        self.callback_texts.append(text)

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        if self.delete_failure:
            raise RuntimeError("transient delete failure")
        self.deleted.append((chat_id, message_id))

    async def download_file(self, file_id: str, *, size_limit: int) -> bytes:
        assert file_id == "voice-file" and size_limit > 0
        return b"voice"

    async def send_document(
        self, chat_id: int, filename: str, content: bytes
    ) -> int:
        self.documents.append((chat_id, filename, content))
        return len(self.documents)


class FakeVoiceService:
    async def preview_from_bytes(self, audio: bytes) -> VoicePreview:
        assert audio == b"voice"
        return VoicePreview(
            transcript="Проверь голосовую задачу",
            language="ru",
            confidence=0.99,
            sha256="0" * 64,
            size=len(audio),
        )


@dataclass
class FakeProductRuntime:
    base: object
    drafted: list[PreparedTask]
    applied: list[tuple[PatchProposal, str, str]]
    rejected: list[PatchProposal]
    reject_failures: int = 0
    deliveries: int = 0

    async def deliver_pending(self, tenant_id: str, sender: object) -> tuple[object, ...]:
        self.deliveries += 1
        return await self.base.deliver_pending(tenant_id, sender)

    async def prepare_instruction(self, instruction: str, envelope: object) -> PreparedTask:
        return await self.base.prepare_instruction(instruction, envelope)

    async def cancel_prepared(self, prepared: PreparedTask) -> FakeVerticalResponse:
        return await self.base.cancel_prepared(prepared)

    async def is_task_terminal(
        self, tenant_id: str, task_id: object, contract_digest: str
    ) -> bool:
        return await self.base.is_task_terminal(tenant_id, task_id, contract_digest)

    async def draft_prepared(self, prepared: PreparedTask) -> Gate5A4DraftOutcome:
        self.drafted.append(prepared)
        patch = (
            "diff --git a/safe.txt b/safe.txt\n"
            "--- a/safe.txt\n"
            "+++ b/safe.txt\n"
            "@@ -1 +1 @@\n"
            "-before\n"
            "+after\n"
        )
        values: dict[str, object] = {
            "tenant_id": prepared.contract.tenant_id,
            "task_id": prepared.contract.task_id,
            "contract_digest": task_contract_digest(prepared.contract),
            "result_revision": 1,
            "result_digest": canonical_json_digest({"result": "draft"}),
            "output_digest": canonical_json_digest({"output": "draft"}),
            "summary": "Обновить safe.txt",
            "patch": patch,
            "paths": ("safe.txt",),
        }
        proposal = PatchProposal(
            **values,
            patch_digest=patch_proposal_digest(
                {**values, "task_id": str(prepared.contract.task_id)}
            ),
        )
        return Gate5A4DraftOutcome(
            status=FakeVerticalStatus.COMPLETED,
            task_id=prepared.contract.task_id,
            proposal=proposal,
            message="ready",
        )

    async def apply_proposal(
        self,
        proposal: PatchProposal,
        *,
        approver_identity: str,
        approval_evidence_ref: str,
    ) -> FakeVerticalResponse:
        self.applied.append((proposal, approver_identity, approval_evidence_ref))
        return FakeVerticalResponse(
            status=FakeVerticalStatus.COMPLETED,
            task_id=proposal.task_id,
            result_digest=proposal.result_digest,
            message="applied",
        )

    async def reject_proposal(self, proposal: PatchProposal) -> FakeVerticalResponse:
        if self.reject_failures:
            self.reject_failures -= 1
            return FakeVerticalResponse(
                status=FakeVerticalStatus.FAILED,
                task_id=proposal.task_id,
                message="transient failure",
            )
        prepared = next(
            (
                candidate
                for candidate in self.drafted
                if candidate.contract.task_id == proposal.task_id
            ),
            None,
        )
        if prepared is None:
            return FakeVerticalResponse(
                status=FakeVerticalStatus.FAILED,
                task_id=proposal.task_id,
                message="prepared binding unavailable",
            )
        durable = await self.base.cancel_prepared(prepared)
        if durable.status is not FakeVerticalStatus.REJECTED:
            return durable
        self.rejected.append(proposal)
        return FakeVerticalResponse(
            status=FakeVerticalStatus.REJECTED,
            task_id=proposal.task_id,
            message="rejected",
        )


@dataclass
class ProductHarness:
    control: ProductTelegramControlPlane
    api: FakeProductApi
    runtime: FakeProductRuntime
    clock: MutableClock
    patches: InMemoryPatchConfirmationStore


class FakeOwnerFiles:
    def __init__(self, selection: OwnerFileSelection) -> None:
        self.selection = selection
        self.queries: list[str] = []

    async def select(self, query: str) -> OwnerFileSelection:
        self.queries.append(query)
        return self.selection


def _product(
    tmp_path: Path,
    *,
    voice: bool = False,
    execution_concurrency: int = 0,
    owner_files: object | None = None,
) -> ProductHarness:
    base = build_harness(tmp_path)
    clock = MutableClock()
    actions = InMemoryTelegramActionStore()
    gateway = TelegramGateway(
        actor_bindings={
            (USER_ID, USER_ID): ActorBinding(
                tenant_id=TENANT_ID,
                actor_identity="telegram:owner",
                role="owner",
                auth_context_ref=AUTH_REF,
            )
        },
        update_id_store=PollingCheckpointUpdateIdStore(),
        callback_token_store=actions,
        clock=clock,
    )
    runtime = FakeProductRuntime(base.runtime, [], [], [])
    patches = InMemoryPatchConfirmationStore(clock=clock)
    api = FakeProductApi()
    control = ProductTelegramControlPlane(
        gateway,
        api,
        task_runtime=runtime,
        task_confirmations=InMemoryTaskConfirmationStore(clock=clock),
        patch_confirmations=patches,
        action_store=actions,
        voice_service=FakeVoiceService() if voice else None,
        owner_files=owner_files,
        execution_concurrency=execution_concurrency,
        task_tenants=(TENANT_ID,),
        task_status_sender=FakeStatusSender(),
    )
    return ProductHarness(control, api, runtime, clock, patches)


def text_update(text: str, update_id: int) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": {"id": USER_ID},
            "chat": {"id": USER_ID},
            "text": text,
        },
    }


def voice_update(update_id: int) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": {"id": USER_ID},
            "chat": {"id": USER_ID},
            "voice": {
                "file_id": "voice-file",
                "file_unique_id": "voice-unique",
                "duration": 3,
                "file_size": 5,
            },
        },
    }


def callback_update(token: str, update_id: int) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"query-{update_id}",
            "from": {"id": USER_ID},
            "message": {"message_id": 100 + update_id, "chat": {"id": USER_ID}},
            "data": token,
        },
    }


@pytest.mark.asyncio
async def test_plain_text_immediately_creates_read_only_draft_then_button_applies(
    tmp_path: Path,
) -> None:
    harness = _product(tmp_path)

    assert await harness.control.handle(text_update("Исправь безопасный файл", 1))
    assert all("Задача принята" not in text for _, text, _ in harness.api.sent)
    assert len(harness.runtime.drafted) == 1
    assert harness.runtime.applied == []
    labels = [label for label, _ in harness.api.sent[-1][2]]
    assert labels == ["✅ Применить", "❌ Отклонить"]

    apply_token = harness.api.sent[-1][2][0][1]
    assert await harness.control.handle(callback_update(apply_token, 2))
    assert len(harness.runtime.applied) == 1
    assert harness.runtime.applied[0][1] == "telegram:owner"
    assert harness.runtime.applied[0][2].startswith("telegram-owner-confirmation:sha256:")
    assert harness.api.answered == ["query-2"]
    assert "Точный diff подтверждён" in harness.api.sent[-1][1]
    assert harness.api.deleted == [(USER_ID, 102)]
    assert "Task:" not in harness.api.sent[-1][1]
    assert "Event:" not in harness.api.sent[-1][1]


@pytest.mark.asyncio
async def test_voice_requires_button_before_read_only_draft(tmp_path: Path) -> None:
    harness = _product(tmp_path, voice=True)

    assert await harness.control.handle(voice_update(1))
    assert harness.runtime.drafted == []
    assert len(harness.api.sent) == 1
    assert "Распознаю" not in harness.api.sent[0][1]
    assert "Я распознал задачу" in harness.api.sent[-1][1]
    confirm_token = harness.api.sent[-1][2][0][1]

    assert await harness.control.handle(callback_update(confirm_token, 2))
    assert len(harness.runtime.drafted) == 1
    assert all("Текст подтверждён" not in text for _, text, _ in harness.api.sent)
    assert harness.api.callback_texts == ["Обрабатываю…"]
    assert harness.api.sent[-1][2][0][0] == "✅ Применить"


@pytest.mark.asyncio
async def test_cancelled_voice_never_reaches_codex(tmp_path: Path) -> None:
    harness = _product(tmp_path, voice=True)
    await harness.control.handle(voice_update(1))
    cancel_token = harness.api.sent[-1][2][1][1]
    sent_before_cancel = len(harness.api.sent)

    await harness.control.handle(callback_update(cancel_token, 2))

    assert harness.runtime.drafted == []
    assert harness.runtime.applied == []
    assert harness.api.answered == ["query-2"]
    assert len(harness.api.sent) == sent_before_cancel


@pytest.mark.asyncio
async def test_menu_commands_are_separate_from_default_task_text(tmp_path: Path) -> None:
    harness = _product(tmp_path)
    await harness.control.handle(text_update("/status", 1))
    await harness.control.handle(text_update("/help", 2))
    await harness.control.handle(text_update("/unknown", 3))

    assert "Голос:" in harness.api.sent[0][1]
    assert "Напишите задачу обычным сообщением" in harness.api.sent[1][1]
    assert "Неизвестная команда" in harness.api.sent[2][1]
    assert harness.runtime.drafted == []

@pytest.mark.asyncio
async def test_callback_answer_failure_does_not_lose_owner_apply(tmp_path: Path) -> None:
    harness = _product(tmp_path)
    await harness.control.handle(text_update("??????? ?????????? ????", 1))
    apply_token = harness.api.sent[-1][2][0][1]
    harness.api.callback_failure = True

    assert await harness.control.handle(callback_update(apply_token, 2))

    assert len(harness.runtime.applied) == 1


@pytest.mark.asyncio
async def test_callback_delete_failure_does_not_lose_owner_apply(tmp_path: Path) -> None:
    harness = _product(tmp_path)
    await harness.control.handle(text_update("safe change", 1))
    apply_token = harness.api.sent[-1][2][0][1]
    harness.api.delete_failure = True

    assert await harness.control.handle(callback_update(apply_token, 2))

    assert len(harness.runtime.applied) == 1


@pytest.mark.asyncio
async def test_slow_callback_ack_does_not_delay_voice_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _product(tmp_path, voice=True)
    await harness.control.handle(voice_update(1))
    confirm_token = harness.api.sent[-1][2][0][1]
    harness.api.callback_gate = asyncio.Event()
    monkeypatch.setattr(
        "src.application.telegram_product._CALLBACK_ACK_TIMEOUT_SECONDS",
        0.01,
    )

    await harness.control.handle(callback_update(confirm_token, 2))

    assert len(harness.runtime.drafted) == 1
    assert harness.api.answered == []
    assert harness.api.deleted == [(USER_ID, 102)]


@pytest.mark.asyncio
async def test_cancellation_after_callback_claim_cannot_lose_owner_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _product(tmp_path)
    await harness.control.handle(text_update("safe change", 1))
    apply_token = harness.api.sent[-1][2][0][1]
    started = asyncio.Event()
    release = asyncio.Event()
    completed: list[str] = []

    async def delayed_resolution(*args: object, **kwargs: object) -> None:
        started.set()
        await release.wait()
        completed.append("applied")

    monkeypatch.setattr(harness.control, "_resolve_patch", delayed_resolution)
    handler = asyncio.create_task(
        harness.control.handle(callback_update(apply_token, 2))
    )
    await started.wait()
    handler.cancel()
    await asyncio.sleep(0)
    handler.cancel()
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await handler

    assert completed == ["applied"]
    assert harness.api.deleted == [(USER_ID, 102)]
    sent_before_replay = len(harness.api.sent)
    replay = callback_update(apply_token, 3)
    replay["callback_query"]["message"]["message_id"] = 102
    assert await harness.control.handle(replay)
    assert len(harness.api.sent) == sent_before_replay


@pytest.mark.asyncio
async def test_ordinary_pre_durable_failure_releases_callback_for_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _product(tmp_path)
    await harness.control.handle(text_update("safe change", 1))
    apply_token = harness.api.sent[-1][2][0][1]
    attempts = 0

    async def flaky_resolution(*args: object, **kwargs: object) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("pre-durable failure")

    monkeypatch.setattr(harness.control, "_resolve_patch", flaky_resolution)

    with pytest.raises(RuntimeError, match="pre-durable failure"):
        await harness.control.handle(callback_update(apply_token, 2))
    assert harness.api.deleted == []

    retry = callback_update(apply_token, 3)
    retry["callback_query"]["message"]["message_id"] = 102
    assert await harness.control.handle(retry)

    assert attempts == 2
    assert harness.api.deleted == [(USER_ID, 102)]


@pytest.mark.asyncio
async def test_child_cancellation_releases_callback_for_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _product(tmp_path)
    await harness.control.handle(text_update("safe change", 1))
    apply_token = harness.api.sent[-1][2][0][1]
    attempts = 0

    async def cancelled_then_succeeds(*args: object, **kwargs: object) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise asyncio.CancelledError

    monkeypatch.setattr(
        harness.control, "_resolve_patch", cancelled_then_succeeds
    )

    with pytest.raises(asyncio.CancelledError):
        await harness.control.handle(callback_update(apply_token, 2))
    assert harness.api.deleted == []

    retry = callback_update(apply_token, 3)
    retry["callback_query"]["message"]["message_id"] = 102
    assert await harness.control.handle(retry)

    assert attempts == 2
    assert harness.api.deleted == [(USER_ID, 102)]


@pytest.mark.asyncio
async def test_expired_patch_is_rejected_and_discarded(tmp_path: Path) -> None:
    harness = _product(tmp_path)
    await harness.control.handle(text_update("??????? ?????????? ????", 1))
    assert harness.runtime.rejected == []

    harness.clock.advance(601)
    await harness.control.handle(text_update("/status", 2))

    assert len(harness.runtime.rejected) == 1
    assert harness.runtime.applied == []

@pytest.mark.asyncio
async def test_expiry_cleanup_retries_after_transient_reject_failure(tmp_path: Path) -> None:
    harness = _product(tmp_path)
    await harness.control.handle(text_update("??????? ?????????? ????", 1))
    harness.runtime.reject_failures = 1
    harness.clock.advance(601)
    await harness.control.handle(text_update("/status", 2))
    assert harness.runtime.rejected == []
    assert len(harness.patches.sweep_expired()) == 1
    await harness.control.handle(text_update("/status", 3))
    assert len(harness.runtime.rejected) == 1
    assert harness.patches.sweep_expired() == ()


@pytest.mark.asyncio
async def test_verified_informational_answer_is_sent_without_technical_metadata(
    tmp_path: Path,
) -> None:
    harness = _product(tmp_path)

    async def answer(prepared: PreparedTask) -> Gate5A4DraftOutcome:
        return Gate5A4DraftOutcome(
            status=FakeVerticalStatus.COMPLETED,
            task_id=prepared.contract.task_id,
            answer="Готовность подтверждена. Работаю в безопасном read-only режиме.",
            message="ready",
        )

    harness.runtime.draft_prepared = answer  # type: ignore[method-assign]
    await harness.control.handle(text_update("Представь свой текущий статус", 1))

    visible = "\n".join(text for _, text, _ in harness.api.sent)
    assert harness.runtime.deliveries == 1
    assert "Готовность подтверждена" not in visible
    for marker in ("Task:", "Event:", "Revision:", "Digest:", "/confirm ", "/cancel "):
        assert marker not in visible


@pytest.mark.asyncio
async def test_patch_and_voice_product_messages_hide_ids_and_backup_codes(
    tmp_path: Path,
) -> None:
    text_harness = _product(tmp_path)
    await text_harness.control.handle(text_update("Исправь безопасный файл", 1))
    text_visible = "\n".join(text for _, text, _ in text_harness.api.sent)

    voice_harness = _product(tmp_path, voice=True)
    await voice_harness.control.handle(voice_update(1))
    voice_visible = "\n".join(text for _, text, _ in voice_harness.api.sent)

    for visible in (text_visible, voice_visible):
        for marker in ("Task:", "Event:", "Revision:", "Digest:", "/confirm ", "/cancel "):
            assert marker not in visible
    assert "agent/telegram-live" not in text_harness.control._status_text()
    assert [label for label, _ in voice_harness.api.sent[-1][2]] == [
        "✅ Подтверждаю",
        "❌ Отмена",
    ]

@pytest.mark.asyncio
async def test_informational_answer_uses_only_durable_delivery_boundary(
    tmp_path: Path,
) -> None:
    harness = _product(tmp_path)

    async def answer(prepared: PreparedTask) -> Gate5A4DraftOutcome:
        return Gate5A4DraftOutcome(
            status=FakeVerticalStatus.COMPLETED,
            task_id=prepared.contract.task_id,
            answer="Проверенный ответ.",
            message="ready",
        )

    harness.runtime.draft_prepared = answer  # type: ignore[method-assign]
    await harness.control.handle(text_update("Дай статус", 1))

    assert harness.runtime.deliveries == 1
    assert all(text != "Проверенный ответ." for _, text, _ in harness.api.sent)

@pytest.mark.asyncio
async def test_durable_failure_is_not_duplicated_by_product_fallback(
    tmp_path: Path,
) -> None:
    harness = _product(tmp_path)

    async def failed(prepared: PreparedTask) -> Gate5A4DraftOutcome:
        return Gate5A4DraftOutcome(
            status=FakeVerticalStatus.FAILED,
            task_id=prepared.contract.task_id,
            message="failed",
        )

    async def deliver() -> int:
        await harness.api.send_message(
            USER_ID,
            "⚠️ Не удалось выполнить задачу. Попробуйте ещё раз.",
        )
        return 1

    harness.runtime.draft_prepared = failed  # type: ignore[method-assign]
    harness.control.deliver_pending = deliver  # type: ignore[method-assign]
    await harness.control.handle(text_update("Дай статус", 1))

    failures = [
        text
        for _, text, _ in harness.api.sent
        if text.startswith("⚠️ Не удалось выполнить")
    ]
    assert failures == [
        "⚠️ Не удалось выполнить задачу. Попробуйте ещё раз."
    ]

@pytest.mark.asyncio
async def test_background_queue_accepts_five_tasks_while_two_workers_are_busy(
    tmp_path: Path,
) -> None:
    harness = _product(tmp_path, execution_concurrency=2)
    release = asyncio.Event()
    two_started = asyncio.Event()
    started: list[PreparedTask] = []
    original_draft = harness.runtime.draft_prepared

    async def blocked_draft(prepared: PreparedTask) -> Gate5A4DraftOutcome:
        started.append(prepared)
        if len(started) == 2:
            two_started.set()
        await release.wait()
        return await original_draft(prepared)

    harness.runtime.draft_prepared = blocked_draft  # type: ignore[method-assign]
    try:
        await asyncio.wait_for(
            asyncio.gather(
                *(
                    harness.control.handle(text_update(f"Task {index}", index))
                    for index in range(1, 6)
                )
            ),
            timeout=1,
        )
        await asyncio.wait_for(two_started.wait(), timeout=1)

        assert harness.control._active_jobs == 2
        assert harness.control._execution_queue is not None
        assert harness.control._execution_queue.qsize() == 3
        status = harness.control._status_text()
        assert "\u0412 \u0440\u0430\u0431\u043e\u0442\u0435: 2" in status
        assert "\u0412 \u043e\u0447\u0435\u0440\u0435\u0434\u0438: 3" in status

        release.set()
        await asyncio.wait_for(harness.control.wait_idle(), timeout=2)
        assert len(harness.runtime.drafted) == 5
    finally:
        release.set()
        await harness.control.close()

@pytest.mark.asyncio
async def test_voice_confirmation_is_queued_while_previous_task_runs(
    tmp_path: Path,
) -> None:
    harness = _product(tmp_path, voice=True, execution_concurrency=1)
    release = asyncio.Event()
    started = asyncio.Event()
    original_draft = harness.runtime.draft_prepared

    async def blocked_draft(prepared: PreparedTask) -> Gate5A4DraftOutcome:
        started.set()
        await release.wait()
        return await original_draft(prepared)

    harness.runtime.draft_prepared = blocked_draft  # type: ignore[method-assign]
    try:
        await harness.control.handle(text_update("First task", 1))
        await asyncio.wait_for(started.wait(), timeout=1)
        await harness.control.handle(voice_update(2))
        confirm_token = harness.api.sent[-1][2][0][1]

        await asyncio.wait_for(
            harness.control.handle(callback_update(confirm_token, 3)), timeout=1
        )

        assert harness.api.answered == ["query-3"]
        assert harness.control._execution_queue is not None
        assert harness.control._execution_queue.qsize() == 1

        release.set()
        await asyncio.wait_for(harness.control.wait_idle(), timeout=2)
        assert len(harness.runtime.drafted) == 2
    finally:
        release.set()
        await harness.control.close()

@pytest.mark.asyncio
async def test_bounded_queue_rejects_overflow_and_close_drains_pending_jobs(
    tmp_path: Path,
) -> None:
    harness = _product(tmp_path, execution_concurrency=1)
    release = asyncio.Event()
    started = asyncio.Event()
    cancelled: list[PreparedTask] = []
    original_draft = harness.runtime.draft_prepared
    original_cancel = harness.runtime.cancel_prepared

    async def blocked_draft(prepared: PreparedTask) -> Gate5A4DraftOutcome:
        started.set()
        await release.wait()
        return await original_draft(prepared)

    async def track_cancel(prepared: PreparedTask) -> FakeVerticalResponse:
        cancelled.append(prepared)
        return await original_cancel(prepared)

    harness.runtime.draft_prepared = blocked_draft  # type: ignore[method-assign]
    harness.runtime.cancel_prepared = track_cancel  # type: ignore[method-assign]
    await harness.control.handle(text_update("Active task", 1))
    await asyncio.wait_for(started.wait(), timeout=1)
    for index in range(2, 34):
        await harness.control.handle(text_update(f"Queued task {index}", index))

    assert harness.control._execution_queue is not None
    assert harness.control._execution_queue.qsize() == 32
    assert cancelled == []

    await harness.control.handle(text_update("Overflow task", 34))

    assert harness.control._execution_queue.qsize() == 32
    assert len(cancelled) == 1

    await harness.control.close()

    assert len(cancelled) == 34
    assert harness.control._execution_queue.empty()


@pytest.mark.asyncio
async def test_unexpected_job_failure_does_not_stop_queue_worker(
    tmp_path: Path,
) -> None:
    harness = _product(tmp_path, execution_concurrency=1)
    cancelled: list[PreparedTask] = []
    calls = 0
    original_draft = harness.runtime.draft_prepared
    original_cancel = harness.runtime.cancel_prepared

    async def fail_once(prepared: PreparedTask) -> Gate5A4DraftOutcome:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("synthetic worker failure")
        return await original_draft(prepared)

    async def track_cancel(prepared: PreparedTask) -> FakeVerticalResponse:
        cancelled.append(prepared)
        return await original_cancel(prepared)

    harness.runtime.draft_prepared = fail_once  # type: ignore[method-assign]
    harness.runtime.cancel_prepared = track_cancel  # type: ignore[method-assign]
    try:
        await harness.control.handle(text_update("Fail once", 1))
        await harness.control.handle(text_update("Continue", 2))
        await asyncio.wait_for(harness.control.wait_idle(), timeout=2)

        assert calls == 2
        assert len(cancelled) == 1
        assert len(harness.runtime.drafted) == 1
        assert all(not worker.done() for worker in harness.control._execution_workers)
    finally:
        await harness.control.close()


@pytest.mark.asyncio
async def test_active_job_terminalization_retries_exception_and_failed_response(
    tmp_path: Path,
) -> None:
    harness = _product(tmp_path, execution_concurrency=1)
    started = asyncio.Event()
    original_cancel = harness.runtime.cancel_prepared
    attempts = 0
    active: PreparedTask | None = None

    async def blocked_draft(prepared: PreparedTask) -> Gate5A4DraftOutcome:
        nonlocal active
        active = prepared
        started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def flaky_cancel(prepared: PreparedTask) -> FakeVerticalResponse:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient persistence failure")
        if attempts == 2:
            return FakeVerticalResponse(
                status=FakeVerticalStatus.FAILED,
                task_id=prepared.contract.task_id,
                message="transient failure",
            )
        return await original_cancel(prepared)

    harness.runtime.draft_prepared = blocked_draft  # type: ignore[method-assign]
    harness.runtime.cancel_prepared = flaky_cancel  # type: ignore[method-assign]
    await harness.control.handle(text_update("Active retry", 1))
    await asyncio.wait_for(started.wait(), timeout=1)

    await harness.control.close()

    assert attempts == 3
    assert harness.control._closed is True
    assert active is not None
    assert await harness.runtime.is_task_terminal(
        TENANT_ID,
        active.contract.task_id,
        task_contract_digest(active.contract),
    ) is True


@pytest.mark.asyncio
async def test_persistent_terminalization_failure_is_not_silently_closed(
    tmp_path: Path,
) -> None:
    harness = _product(tmp_path, execution_concurrency=1)
    started = asyncio.Event()
    attempts = 0

    async def blocked_draft(prepared: PreparedTask) -> Gate5A4DraftOutcome:
        started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def always_failed(prepared: PreparedTask) -> FakeVerticalResponse:
        nonlocal attempts
        attempts += 1
        return FakeVerticalResponse(
            status=FakeVerticalStatus.FAILED,
            task_id=prepared.contract.task_id,
            message="persistent failure",
        )

    harness.runtime.draft_prepared = blocked_draft  # type: ignore[method-assign]
    harness.runtime.cancel_prepared = always_failed  # type: ignore[method-assign]
    await harness.control.handle(text_update("Cannot close silently", 1))
    await asyncio.wait_for(started.wait(), timeout=1)

    with pytest.raises(RuntimeError, match="did not close safely"):
        await harness.control.close()
    with pytest.raises(RuntimeError, match="did not close safely"):
        await harness.control.close()
    await harness.control.start()

    assert attempts == 3
    assert harness.control._execution_workers == ()


@pytest.mark.asyncio
async def test_parallel_close_waits_for_first_close_and_start_cannot_resurrect(
    tmp_path: Path,
) -> None:
    harness = _product(tmp_path, execution_concurrency=1)
    draft_started = asyncio.Event()
    cancel_started = asyncio.Event()
    release_cancel = asyncio.Event()
    original_cancel = harness.runtime.cancel_prepared

    async def blocked_draft(prepared: PreparedTask) -> Gate5A4DraftOutcome:
        draft_started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def blocked_cancel(prepared: PreparedTask) -> FakeVerticalResponse:
        cancel_started.set()
        await release_cancel.wait()
        return await original_cancel(prepared)

    harness.runtime.draft_prepared = blocked_draft  # type: ignore[method-assign]
    harness.runtime.cancel_prepared = blocked_cancel  # type: ignore[method-assign]
    await harness.control.handle(text_update("Concurrent close", 1))
    await asyncio.wait_for(draft_started.wait(), timeout=1)
    first = asyncio.create_task(harness.control.close())
    await asyncio.wait_for(cancel_started.wait(), timeout=1)
    second = asyncio.create_task(harness.control.close())
    await asyncio.sleep(0)

    assert not second.done()
    release_cancel.set()
    await asyncio.gather(first, second)
    await harness.control.start()

    assert harness.control._execution_workers == ()


@pytest.mark.asyncio
async def test_confirmed_patch_rejection_retries_before_queue_ack(
    tmp_path: Path,
) -> None:
    harness = _product(tmp_path, execution_concurrency=1)
    ingress = harness.runtime.base._gateway.process_update(text_update("Patch task", 1))
    assert ingress.envelope is not None
    prepared = await harness.runtime.prepare_instruction("Patch task", ingress.envelope)
    proposal = (await harness.runtime.draft_prepared(prepared)).proposal
    assert proposal is not None
    harness.runtime.reject_failures = 2
    harness.control._closing = True

    await harness.control._submit_patch(
        proposal,
        approver_identity="telegram:owner",
        approval_evidence_ref="telegram-owner-confirmation:" + "a" * 64,
    )

    assert harness.runtime.reject_failures == 0
    assert harness.runtime.rejected == [proposal]
    await harness.control.close()


@pytest.mark.asyncio
async def test_rejected_response_without_durable_write_does_not_close_safely(
    tmp_path: Path,
) -> None:
    harness = _product(tmp_path, execution_concurrency=1)
    started = asyncio.Event()
    active: PreparedTask | None = None
    attempts = 0
    original_cancel = harness.runtime.cancel_prepared

    async def blocked_draft(prepared: PreparedTask) -> Gate5A4DraftOutcome:
        nonlocal active
        active = prepared
        started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def false_rejected(prepared: PreparedTask) -> FakeVerticalResponse:
        nonlocal attempts
        attempts += 1
        return FakeVerticalResponse(
            status=FakeVerticalStatus.REJECTED,
            task_id=prepared.contract.task_id,
            message="claimed without persistence",
        )

    harness.runtime.draft_prepared = blocked_draft  # type: ignore[method-assign]
    harness.runtime.cancel_prepared = false_rejected  # type: ignore[method-assign]
    await harness.control.handle(text_update("False terminal", 1))
    await asyncio.wait_for(started.wait(), timeout=1)

    with pytest.raises(RuntimeError, match="did not close safely"):
        await harness.control.close()

    assert active is not None
    assert attempts == 3
    assert not await harness.runtime.is_task_terminal(
        TENANT_ID,
        active.contract.task_id,
        task_contract_digest(active.contract),
    )
    await original_cancel(active)


@pytest.mark.asyncio
async def test_public_text_overflow_does_not_ack_without_durable_terminal_proof(
    tmp_path: Path,
) -> None:
    harness = _product(tmp_path, execution_concurrency=1)
    started = asyncio.Event()
    attempts = 0
    overflow: PreparedTask | None = None
    original_cancel = harness.runtime.cancel_prepared

    async def blocked_draft(prepared: PreparedTask) -> Gate5A4DraftOutcome:
        started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def persistence_failed(prepared: PreparedTask) -> FakeVerticalResponse:
        nonlocal attempts, overflow
        attempts += 1
        overflow = prepared
        return FakeVerticalResponse(
            status=FakeVerticalStatus.FAILED,
            task_id=prepared.contract.task_id,
            message="persistent failure",
        )

    harness.runtime.draft_prepared = blocked_draft  # type: ignore[method-assign]
    await harness.control.handle(text_update("Active", 1))
    await asyncio.wait_for(started.wait(), timeout=1)
    for update_id in range(2, 34):
        await harness.control.handle(text_update(f"Queued {update_id}", update_id))
    harness.runtime.cancel_prepared = persistence_failed  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="could not be terminalized"):
        await harness.control.handle(text_update("Overflow", 34))

    assert attempts == 6
    assert overflow is not None
    assert not await harness.runtime.is_task_terminal(
        TENANT_ID,
        overflow.contract.task_id,
        task_contract_digest(overflow.contract),
    )
    harness.runtime.cancel_prepared = original_cancel  # type: ignore[method-assign]
    await original_cancel(overflow)
    await harness.control.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "query"),
    [
        ("/file roadmap.html", "roadmap.html"),
        ("\u041f\u0440\u0438\u0448\u043b\u0438 \u043c\u043d\u0435 \u0444\u0430\u0439\u043b roadmap.html", "roadmap.html"),
    ],
)
async def test_owner_file_request_sends_only_selected_document(
    tmp_path: Path, text: str, query: str
) -> None:
    provider = FakeOwnerFiles(
        OwnerFileSelection(
            document=OwnerDocument(
                "docs/roadmap.html", "roadmap.html", b"safe"
            )
        )
    )
    harness = _product(tmp_path, owner_files=provider)

    await harness.control.handle(text_update(text, 90))

    assert provider.queries == [query]
    assert harness.api.documents == [(USER_ID, "roadmap.html", b"safe")]
    assert harness.api.sent == []


@pytest.mark.asyncio
async def test_owner_file_request_lists_only_relative_choices(
    tmp_path: Path,
) -> None:
    provider = FakeOwnerFiles(
        OwnerFileSelection(choices=("docs/a.pdf", "reports/a.pdf"))
    )
    harness = _product(tmp_path, owner_files=provider)

    await harness.control.handle(text_update("/file a.pdf", 91))

    assert harness.api.documents == []
    assert "docs/a.pdf" in harness.api.sent[-1][1]
    assert "reports/a.pdf" in harness.api.sent[-1][1]
    assert "C:\\" not in harness.api.sent[-1][1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "\u041e\u0442\u043f\u0440\u0430\u0432\u044c \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442 \u043a\u043b\u0438\u0435\u043d\u0442\u0443 \u043f\u043e\u0441\u043b\u0435 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438",
        "\u041f\u0440\u0438\u0448\u043b\u0438 \u0444\u0430\u0439\u043b \u043e\u0442\u0447\u0451\u0442 \u0438 \u0437\u0430\u0442\u0435\u043c \u043f\u0440\u043e\u0430\u043d\u0430\u043b\u0438\u0437\u0438\u0440\u0443\u0439 \u0435\u0433\u043e",
        "\u041e\u0442\u043f\u0440\u0430\u0432\u044c \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442 roadmap.html \u043a\u043b\u0438\u0435\u043d\u0442\u0443",
        "\u041f\u0440\u0438\u0448\u043b\u0438 \u043c\u043d\u0435 \u0444\u0430\u0439\u043b roadmap.html \u0438 \u043f\u0440\u043e\u0430\u043d\u0430\u043b\u0438\u0437\u0438\u0440\u0443\u0439",
    ],
)
async def test_ambiguous_file_language_remains_a_regular_task(
    tmp_path: Path, text: str
) -> None:
    provider = FakeOwnerFiles(OwnerFileSelection())
    harness = _product(tmp_path, owner_files=provider)

    await harness.control.handle(text_update(text, 92))

    assert provider.queries == []
    assert len(harness.runtime.drafted) == 1
