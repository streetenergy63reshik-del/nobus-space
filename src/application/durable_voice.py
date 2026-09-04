"""Voice stages in the existing encrypted Telegram queue, before semantic admission."""
from __future__ import annotations

import asyncio
import base64
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
from typing import Any
from uuid import UUID

from src.application.durable_runtime import PreparedTask
from src.application.durable_telegram_state import DurableJob, SQLiteTelegramState
from src.contracts import TaskContract, TrustedIngressEnvelope
from src.contracts.models import canonical_json_digest
from src.transport.telegram import IngressStatus, TextMessage, TrustedIngressResult, VoiceMessage
from src.voice import VoicePreview

VOICE_BYTES = 10 * 1024 * 1024
VOICE_SECONDS = 300
VOICE_TEXT = 2000
SEMANTIC_BINDING = 'sha256:f09457922593bb82bc200cddaa6c6602295df3462627a5b101f0cab5e9115e87'
_ACTIVE: ContextVar[VoiceExecution | None] = ContextVar('voice_execution', default=None)


def voice_id(message: VoiceMessage | TextMessage, *, original_id: int | None = None) -> UUID:
    binding = canonical_json_digest(dict(tenant=message.tenant_id, actor=message.actor_identity,
        user=message.user_id, chat=message.chat_id, topic=message.message_thread_id,
        message=original_id if original_id is not None else message.message_id))
    return UUID(hex=binding[7:39], version=4)


def validate_job(job: DurableJob) -> tuple[VoiceMessage, TrustedIngressEnvelope]:
    payload = job.payload
    message = VoiceMessage.model_validate(payload['message'])
    envelope = TrustedIngressEnvelope.model_validate(payload['envelope'])
    TrustedIngressResult(status=IngressStatus.ACCEPTED, update_id=message.update_id,
                         payload=message, envelope=envelope)
    if (job.kind != 'voice' or voice_id(message) != job.task_id or job.tenant_id != message.tenant_id
        or canonical_json_digest(message.model_dump(mode='json')) != job.binding_digest
        or payload['semantic_contract'] != SEMANTIC_BINDING):
        raise ValueError('voice binding mismatch')
    return message, envelope


@dataclass
class VoiceExecution:
    control: Any
    job: DurableJob

    def save(self, *, status: str = 'leased', **changes: Any) -> None:
        self.require_live()
        self.job = self.control._telegram_state.checkpoint_voice(
            self.job, lease_owner=self.control._lease_owner,
            payload={**self.job.payload, **changes}, status=status)

    def require_live(self) -> None:
        if self.control._telegram_state.voice_remaining(self.job) <= 0:
            raise ValueError('voice content expired')


class DurableVoiceIntake:
    """One bounded voice flow; ASR output never selects a capability."""

    def __init__(self, control: Any, state: SQLiteTelegramState) -> None:
        self.control, self.state = control, state

    async def admit(self, message: VoiceMessage, envelope: TrustedIngressEnvelope) -> None:
        TrustedIngressResult(status=IngressStatus.ACCEPTED, update_id=message.update_id,
                             payload=message, envelope=envelope)
        if (not 0 < message.duration <= VOICE_SECONDS
            or not message.metadata.file_unique_id
            or message.metadata.file_size is None
            or not 0 < message.metadata.file_size <= VOICE_BYTES
            or message.metadata.mime_type not in {None, 'audio/ogg', 'audio/opus', 'audio/wav'}):
            await self.control._api.send_message(message.chat_id,
                'Нужна голосовая запись до 5 минут и 10 МБ в формате Ogg/Opus или WAV. Можно отправить задачу текстом.')
            return
        self.state.sweep_voice()
        self.state.enqueue(kind='voice', tenant_id=message.tenant_id, task_id=voice_id(message),
            binding_digest=canonical_json_digest(message.model_dump(mode='json')),
            payload=dict(stage='received', message=message.model_dump(mode='json'),
                envelope=envelope.model_dump(mode='json'), semantic_contract=SEMANTIC_BINDING,
                expires_at=(self.state._now()+timedelta(hours=1)).isoformat()))
        await self.control.start()
        self.control._wake()

    async def reply(self, message: TextMessage, envelope: TrustedIngressEnvelope) -> bool:
        if message.reply_to_message_id is None:
            return False
        job = self.state.read_voice(tenant_id=message.tenant_id,
            task_id=voice_id(message, original_id=message.reply_to_message_id))
        if job is None:
            return False
        if not job.payload:
            await self.control._api.send_message(message.chat_id, 'Эта голосовая запись больше не ожидает подтверждения. Отправьте новую задачу отдельным сообщением.')
            return True
        original, _ = validate_job(job)
        if original.auth_context_ref != message.auth_context_ref or self.state.voice_remaining(job) <= 0:
            await self.control._api.send_message(message.chat_id, 'Подтверждение истекло. Отправьте новую задачу.')
            return True
        text = message.text.strip()
        stage = job.payload['stage']
        if not self.control._enable_semantic_admission:
            if self.state.confirm_voice(job, reply_update_id=message.update_id,
                                        payload={**job.payload, 'stage':'cancelled'}):
                self.control._wake()
            await self.control._api.send_message(message.chat_id,
                'Обработка голосовой задачи остановлена: режим сейчас не активен. Никаких новых действий не выполнялось.')
            return True
        if stage not in {'waiting', 'interrupted'}:
            self.state.confirm_voice(job, reply_update_id=message.update_id, payload=None)
            await self.control._api.send_message(message.chat_id, 'Голосовая задача уже обрабатывается.')
            return True
        if text.casefold() == 'нет':
            updates = dict(stage='cancelled', audio=None, preview=None)
        elif stage == 'interrupted' and text.casefold() == 'повторить':
            updates = dict(stage='received', generation=job.payload.get('generation', 0)+1)
        else:
            instruction = (job.payload['preview']['transcript'] if text.casefold() == 'да' and stage == 'waiting' else text)
            if stage == 'interrupted' and text.casefold() == 'да':
                self.state.confirm_voice(job, reply_update_id=message.update_id, payload=None)
                await self.control._api.send_message(message.chat_id, 'Распознанного текста нет. Напишите задачу или ответьте «повторить».')
                return True
            if not 0 < len(instruction) <= VOICE_TEXT:
                self.state.confirm_voice(job, reply_update_id=message.update_id, payload=None)
                await self.control._api.send_message(message.chat_id, 'Текст задачи должен содержать от 1 до 2000 символов.')
                return True
            updates = dict(stage='confirmed', accepted_text=instruction,
                confirmation_revision=envelope.envelope_revision, audio=None)
        if self.state.confirm_voice(job, reply_update_id=message.update_id,
                                    payload={**job.payload, **updates}):
            self.control._wake()
        return True

    async def run(self, durable: DurableJob) -> None:
        execution = VoiceExecution(self.control, durable)
        marker = _ACTIVE.set(execution)
        try:
            seconds = self.state.voice_remaining(durable)
            if seconds <= 0:
                return
            async with asyncio.timeout(seconds):
                await self._run(execution)
        finally:
            _ACTIVE.reset(marker)

    async def _run(self, execution: VoiceExecution) -> None:
        message, envelope = validate_job(execution.job)
        if not self.control._enable_semantic_admission:
            self._finish(execution)
            await self._status(message,
                'Обработка голосовой задачи остановлена: режим сейчас не активен. Никаких новых действий не выполнялось.')
            return
        execution.require_live()
        stage = execution.job.payload['stage']
        if stage == 'recognizing':
            # Inference may have completed before the process died. No silent second ASR.
            execution.save(stage='interrupted', audio=None)
            stage = 'interrupted'
        if stage in {'received', 'downloading'}:
            execution.save(stage='downloading')
            await self._status(message, 'Получаю голосовую запись…')
            async with asyncio.timeout(60):
                audio = await self.control._api.download_file(message.file_id, size_limit=VOICE_BYTES)
            if (not isinstance(audio, bytes) or len(audio) != message.metadata.file_size
                or not 0 < len(audio) <= VOICE_BYTES):
                raise ValueError('voice size mismatch')
            execution.save(stage='downloaded', audio=base64.b64encode(audio).decode('ascii'),
                           audio_sha256=hashlib.sha256(audio).hexdigest())
            stage = 'downloaded'
        if stage == 'downloaded':
            audio = base64.b64decode(execution.job.payload['audio'], validate=True)
            if (len(audio) > VOICE_BYTES or hashlib.sha256(audio).hexdigest() != execution.job.payload['audio_sha256']):
                raise ValueError('voice content mismatch')
            execution.save(stage='recognizing')
            await self._status(message, 'Распознаю запись на русском языке…')
            async with asyncio.timeout(180):
                preview = await self.control._voice_service.preview_from_bytes(audio)
            preview = VoicePreview.model_validate(preview.model_dump())
            if preview.sha256 != execution.job.payload['audio_sha256'] or preview.size != len(audio):
                raise ValueError('voice result binding mismatch')
            execution.save(stage='transcribed', audio=None, preview=preview.model_dump(mode='json'))
            stage = 'transcribed'
        if stage in {'transcribed', 'interrupted'}:
            execution.require_live()
            if stage == 'transcribed':
                preview = VoicePreview.model_validate(execution.job.payload['preview'])
                text = ('Проверьте распознанный текст:\n\n' + preview.transcript +
                    '\n\nВ течение часа ответьте на исходное голосовое сообщение: «да», «нет» или исправленным текстом. До подтверждения задача не запускается.')
                next_stage = 'waiting'
            else:
                text = ('Распознавание было прервано. Ответьте на исходное голосовое сообщение «повторить» или напишите задачу текстом. Никаких действий не выполнялось.')
                next_stage = 'interrupted'
            await self.control._api.send_message(message.chat_id, text, message_thread_id=message.message_thread_id)
            execution.save(stage=next_stage, status='waiting')
            return
        if stage == 'confirmed':
            execution.require_live()
            prepared_data = execution.job.payload.get('prepared')
            if prepared_data is not None:
                prepared = PreparedTask(contract=TaskContract.model_validate(prepared_data['contract']),
                                        envelope_revision=prepared_data['envelope_revision'])
                if not await self.control._submit_draft(prepared, message, envelope):
                    raise RuntimeError('voice draft enqueue failed')
            else:
                await self.control._start_owner_instruction(message, envelope, execution.job.payload['accepted_text'])
            self._finish(execution)
            return
        if stage == 'cancelled':
            self._finish(execution)
            await self._status(message, 'Голосовая задача отменена.')
            return
        raise ValueError('voice stage is invalid')

    def _finish(self, execution: VoiceExecution) -> None:
        self.state.checkpoint_voice(execution.job, lease_owner=self.control._lease_owner,
                                    payload={}, status='finished')

    async def _status(self, message: VoiceMessage, text: str) -> None:
        try:
            await self.control._api.send_message(message.chat_id, text, message_thread_id=message.message_thread_id)
        except Exception:
            pass  # Stage authority is in SQLite, not the Telegram acknowledgement.

    async def prepare(self, instruction: str, envelope: TrustedIngressEnvelope) -> PreparedTask:
        execution = _ACTIVE.get()
        if execution is None:
            raise RuntimeError('voice execution context is missing')
        prepared = await self.control._product_runtime.build_instruction(instruction, envelope)
        execution.require_live()
        prepared = PreparedTask(contract=prepared.contract.model_copy(update={'task_id':execution.job.task_id}),
                                envelope_revision=prepared.envelope_revision)
        execution.save(prepared=dict(contract=prepared.contract.model_dump(mode='json'),
                                     envelope_revision=prepared.envelope_revision))
        return prepared


def active_voice() -> bool:
    return _ACTIVE.get() is not None
