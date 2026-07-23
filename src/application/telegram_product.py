"""Product-facing Telegram UX for Nobus Space MVP-1."""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any, Protocol
from uuid import UUID

from src.application.durable_runtime import PreparedTask
from src.application.fake_vertical import FakeVerticalResponse, FakeVerticalStatus
from src.application.gate5a4 import Gate5A4DraftOutcome
from src.application.patch_confirmation import (
    InMemoryPatchConfirmationStore,
    PatchConfirmationChallenge,
    PatchConfirmationStatus,
    PatchProposal,
)
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
from src.transport.telegram import CallbackQuery, IngressStatus, TextMessage, VoiceMessage
from src.voice import VoicePreviewService


_VOICE_LIMIT = 10 * 1024 * 1024
_MESSAGE_CHUNK = 3_400


class ProductTelegramApi(Protocol):
    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        buttons: tuple[tuple[str, str], ...] = (),
    ) -> int: ...

    async def answer_callback_query(self, query_id: str) -> None: ...

    async def download_file(self, file_id: str, *, size_limit: int) -> bytes: ...


class ProductTaskRuntime(Protocol):
    async def prepare_instruction(
        self, instruction: str, envelope: TrustedIngressEnvelope
    ) -> PreparedTask: ...

    async def cancel_prepared(self, prepared: PreparedTask) -> FakeVerticalResponse: ...

    async def draft_prepared(self, prepared: PreparedTask) -> Gate5A4DraftOutcome: ...

    async def apply_proposal(
        self,
        proposal: PatchProposal,
        *,
        approver_identity: str,
        approval_evidence_ref: str,
    ) -> FakeVerticalResponse: ...

    async def reject_proposal(self, proposal: PatchProposal) -> FakeVerticalResponse: ...


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
        **values: object,
    ) -> None:
        required = (
            "prepare_instruction",
            "cancel_prepared",
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
        if command == "/status":
            await self._api.send_message(payload.chat_id, self._status_text())
        elif command in {"/help", "/start"}:
            await self._api.send_message(payload.chat_id, self._help_text())
        elif command == "/task":
            await self._start_text_task(
                payload, ingress.envelope, _argument(payload.text)
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
            await self._start_text_task(payload, ingress.envelope, payload.text)
        return True

    def _status_text(self) -> str:
        voice = "активен" if self._voice_service is not None else "не активирован"
        return (
            "Nobus Space · MVP-1\n"
            "Telegram: online\n"
            "Владелец: подтверждён\n"
            "Текст: сразу в read-only работу\n"
            "Изменение кода: только после кнопки «Применить»\n"
            f"Голос: {voice}"
        )

    def _help_text(self) -> str:
        return (
            "Отправьте обычное текстовое сообщение — оно сразу станет задачей.\n"
            "Голосовое сообщение сначала будет расшифровано и показано вам "
            "с кнопками «Подтверждаю» и «Отмена».\n\n"
            "Если задача создаёт изменение, бот покажет полный diff. Только "
            "кнопка «Применить» разрешает проверку и локальный commit.\n\n"
            "Меню:\n"
            "/status — состояние системы\n"
            "/help — эта справка\n\n"
            "Не отправляйте пароли, токены и клиентские персональные данные."
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
        await self._api.send_message(
            message.chat_id,
            "✅ Задача принята. Готовлю решение; файлы пока не меняются.",
        )
        prepared: PreparedTask | None = None
        try:
            prepared = await self._product_runtime.prepare_instruction(
                instruction, envelope
            )
            await self._draft_and_present(prepared, message, envelope)
        except asyncio.CancelledError:
            raise
        except Exception:
            if prepared is not None:
                await self._product_runtime.cancel_prepared(prepared)
            await self._api.send_message(
                message.chat_id,
                "⚠️ Не удалось безопасно подготовить задачу. Изменения не применены.",
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
        await self._api.send_message(message.chat_id, "🎙 Распознаю голосовое сообщение…")
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
                "⚠️ Не удалось безопасно распознать голосовое сообщение.",
            )

    async def _handle_callback(
        self, callback: CallbackQuery, envelope: TrustedIngressEnvelope
    ) -> None:
        claimed = self._action_store.consume(callback)
        try:
            await self._api.answer_callback_query(callback.query_id)
        except Exception:
            pass
        if claimed is None:
            await self._api.send_message(
                callback.chat_id, "Кнопка недействительна, уже использована или истекла."
            )
            return
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
        else:
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
        if result.prepared is None:
            await self._api.send_message(
                message.chat_id, "Подтверждение задачи недействительно или уже использовано."
            )
            return
        if action is TaskConfirmationStatus.CANCELLED:
            await self._product_runtime.cancel_prepared(result.prepared)
            await self.deliver_pending()
            return
        await self._api.send_message(
            message.chat_id,
            "✅ Текст подтверждён. Готовлю решение.",
        )
        await self._draft_and_present(result.prepared, message, envelope)

    async def _draft_and_present(
        self,
        prepared: PreparedTask,
        message: TextMessage | CallbackQuery,
        envelope: TrustedIngressEnvelope,
    ) -> None:
        outcome = await self._product_runtime.draft_prepared(prepared)
        if outcome.answer is not None:
            await self.deliver_pending()
            return
        if outcome.proposal is None:
            await self._api.send_message(
                message.chat_id,
                "⚠️ Не удалось безопасно подготовить результат. Изменения не применены.",
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
            await self._product_runtime.apply_proposal(
                result.proposal,
                approver_identity=envelope.actor_identity,
                approval_evidence_ref=f"telegram-owner-confirmation:{approval_digest}",
            )
        await self.deliver_pending()

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
