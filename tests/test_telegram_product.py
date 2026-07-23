"""Product UX regressions for the live Telegram control plane."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from src.application.durable_runtime import PreparedTask
from src.application.fake_vertical import FakeVerticalResponse, FakeVerticalStatus
from src.application.gate5a4 import Gate5A4DraftOutcome
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
        self.callback_failure = False

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        buttons: tuple[tuple[str, str], ...] = (),
    ) -> int:
        self.sent.append((chat_id, text, buttons))
        return len(self.sent)

    async def answer_callback_query(self, query_id: str) -> None:
        if self.callback_failure:
            raise RuntimeError("transient callback failure")
        self.answered.append(query_id)

    async def download_file(self, file_id: str, *, size_limit: int) -> bytes:
        assert file_id == "voice-file" and size_limit > 0
        return b"voice"


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


def _product(tmp_path: Path, *, voice: bool = False) -> ProductHarness:
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
