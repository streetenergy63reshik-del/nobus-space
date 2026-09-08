from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import hashlib
import io
import json
from pathlib import Path
import sqlite3
from uuid import uuid4
import wave

import pytest

from src.application.durable_product import DurableProductTelegramControlPlane
from src.application.durable_voice import DurableVoiceIntake, voice_id
from src.application.durable_telegram_state import SQLiteTelegramState, DurableTelegramStateError
from src.application.semantic_admission import SemanticAdmissionService, InMemorySemanticClarificationStore
from src.voice import VoicePreview, VoicePreviewService, FasterWhisperTranscriber, TranscriptResult, VoiceTranscriptionError
from tests.test_telegram_product import _product, voice_update, text_update, _semantic_proposal
from tests.test_durable_telegram_state import _store


class Compiler:
    def __init__(self):
        self.inputs = []

    async def compile_semantic(self, model_input, output_schema, *, timeout_seconds):
        self.inputs.append(model_input)
        return _semantic_proposal(model_input)


def harness(tmp_path):
    compiler = Compiler()
    h = _product(tmp_path, voice=True, enable_semantic_admission=True,
                 semantic_admission=SemanticAdmissionService(compiler),
                 semantic_clarifications=InMemorySemanticClarificationStore(), extended_routes=False)
    h.control.__class__ = DurableProductTelegramControlPlane
    h.control._admission_readiness = None
    c = h.control
    c._telegram_state = _store(tmp_path)
    c._lease_owner = uuid4()
    c._durable_voice = DurableVoiceIntake(c, c._telegram_state)
    c._execution_queue = asyncio.Queue(40)
    c._cleanup_pending = set()
    # Exercise the real no-effect contract normalization, not the generic test runtime prefix.
    from src.application.gate5a4 import Gate5A4Runtime
    contract_runtime = object.__new__(Gate5A4Runtime)
    contract_runtime.__dict__.update(h.runtime.base.__dict__)
    h.runtime.base._contract = contract_runtime._contract
    c._product_runtime.build_instruction = h.runtime.base.build_instruction
    c._product_runtime.admit_prepared = h.runtime.base.admit_prepared
    c._worker_error_count = 0
    c._worker_error = None
    c._execution_concurrency = 0
    c.asr_calls = 0
    async def preview(audio):
        c.asr_calls += 1
        return VoicePreview(transcript='Составь план проверки.', language='ru', language_confidence=0.99,
                            sha256=hashlib.sha256(audio).hexdigest(), size=len(audio))
    c._voice_service.preview_from_bytes = preview
    return h, compiler


def claim(c):
    job = c._telegram_state.claim(lease_owner=c._lease_owner, lease_seconds=60)
    assert job is not None
    return job


def rows(c):
    with sqlite3.connect(c._telegram_state.path) as db:
        return db.execute('SELECT kind,status FROM telegram_jobs ORDER BY kind').fetchall()


@pytest.mark.asyncio
async def test_full_queue_transfers_reserved_voice_capacity_to_draft(tmp_path):
    h, _ = harness(tmp_path); c = h.control
    for identifier in range(10, 50):
        await c.handle(voice_update(identifier))
        await c._durable_voice.run(claim(c))
    assert rows(c) == [('voice', 'waiting')] * 40
    await c.handle(text_update('да', 60, reply_to_message_id=10))
    await c._durable_voice.run(claim(c))
    assert rows(c).count(('draft', 'pending')) == 1
    assert rows(c).count(('voice', 'finished')) == 1
    with pytest.raises(DurableTelegramStateError, match='queue_full'):
        await c.handle(voice_update(61))
    draft = claim(c)
    assert await c._restore(draft) is not None
    c._telegram_state.ack(draft, lease_owner=c._lease_owner)
    await c.handle(voice_update(61))
    assert rows(c).count(('voice', 'pending')) == 1


@pytest.mark.asyncio
async def test_intake_ack_is_durable_before_download_and_confirmation_uses_c1(tmp_path):
    h, compiler = harness(tmp_path); c = h.control
    assert await c.handle(voice_update(10))
    assert rows(c) == [('voice','pending')]
    assert c.asr_calls == 0 and compiler.inputs == []
    await c._durable_voice.run(claim(c))
    assert rows(c) == [('voice','waiting')]
    assert c.asr_calls == 1 and compiler.inputs == []
    assert await c.handle(text_update('да',11,reply_to_message_id=10))
    await c._durable_voice.run(claim(c))
    assert rows(c) == [('draft','pending'),('voice','finished')]
    assert c.asr_calls == 1 and compiler.inputs
    assert compiler.inputs[0]['owner_text'] == 'Составь план проверки.'
    job = claim(c)
    restored = await c._restore(job)
    assert restored is not None
    assert restored.prepared.contract.instruction.endswith('Составь план проверки.')


@pytest.mark.asyncio
async def test_duplicate_does_not_repeat_asr_and_file_rebinding_fails(tmp_path):
    h,_=harness(tmp_path); c=h.control
    await c.handle(voice_update(10)); await c.handle(voice_update(10))
    assert rows(c)==[('voice','pending')]
    await c._durable_voice.run(claim(c))
    await c.handle(voice_update(10))
    assert rows(c)==[('voice','waiting')] and c.asr_calls==1
    other=voice_update(10); other['message']['voice']['file_id']='changed'
    with pytest.raises(DurableTelegramStateError,match='conflict'):
        await c.handle(other)


@pytest.mark.asyncio
@pytest.mark.parametrize('stage',['received','downloading','downloaded','recognizing','transcribed','confirmed'])
async def test_reopen_every_voice_boundary(tmp_path,stage):
    h,_=harness(tmp_path); c=h.control
    await c.handle(voice_update(10)); first=claim(c)
    payload=dict(first.payload,stage=stage)
    audio=b'voice'
    if stage in {'downloaded','recognizing'}:
        payload.update(audio=__import__('base64').b64encode(audio).decode(),audio_sha256=hashlib.sha256(audio).hexdigest())
    if stage=='transcribed':
        payload['preview']=VoicePreview(transcript='Составь план проверки.',sha256=hashlib.sha256(audio).hexdigest(),size=5).model_dump()
    if stage=='confirmed': payload['accepted_text']='Составь план проверки.'
    c._telegram_state.checkpoint_voice(first,lease_owner=c._lease_owner,payload=payload)
    c._telegram_state.release(first,lease_owner=c._lease_owner)
    c._telegram_state=_store(tmp_path)
    c._durable_voice=DurableVoiceIntake(c,c._telegram_state)
    await c._durable_voice.run(claim(c))
    if stage=='confirmed': assert rows(c)==[('draft','pending'),('voice','finished')]
    else: assert rows(c)==[('voice','waiting')]
    assert c.asr_calls == (1 if stage in {'received','downloading','downloaded'} else 0)


@pytest.mark.asyncio
async def test_interrupted_requires_explicit_retry_and_cancellation_has_no_task(tmp_path):
    h,compiler=harness(tmp_path); c=h.control
    await c.handle(voice_update(10)); job=claim(c)
    c._telegram_state.checkpoint_voice(job,lease_owner=c._lease_owner,payload=dict(job.payload,stage='recognizing'))
    c._telegram_state.release(job,lease_owner=c._lease_owner)
    await c._durable_voice.run(claim(c))
    await c.handle(text_update('повторить',11,reply_to_message_id=10))
    await c._durable_voice.run(claim(c))
    assert c.asr_calls==1 and not compiler.inputs
    await c.handle(text_update('нет',12,reply_to_message_id=10))
    await c._durable_voice.run(claim(c))
    assert rows(c)==[('voice','finished')]
    await c.handle(voice_update(10))
    assert rows(c)==[('voice','finished')]


@pytest.mark.asyncio
@pytest.mark.parametrize('cut',['prepared','enqueued'])
async def test_no_orphan_or_duplicate_at_draft_handoff(tmp_path,cut):
    h,compiler=harness(tmp_path); c=h.control
    await c.handle(voice_update(10)); await c._durable_voice.run(claim(c))
    await c.handle(text_update('да',11,reply_to_message_id=10))
    real=c._submit_draft
    async def crash(*args,**kwargs):
        if cut=='enqueued': assert await real(*args,**kwargs)
        raise asyncio.CancelledError()
    c._submit_draft=crash
    job=claim(c)
    with pytest.raises(asyncio.CancelledError): await c._durable_voice.run(job)
    c._telegram_state.release(job,lease_owner=c._lease_owner)
    c._submit_draft=real
    before=len(compiler.inputs)
    await c._durable_voice.run(claim(c))
    assert len(compiler.inputs)==before and c.asr_calls==1
    assert rows(c)==[('draft','pending'),('voice','finished')]
    assert await c._restore(claim(c)) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['download','asr','size','malformed'])
async def test_failures_never_reach_semantic_or_expose_content(tmp_path,fault):
    h,compiler=harness(tmp_path); c=h.control
    async def fail(*a,**k): raise RuntimeError('PRIVATE_PROVIDER_PATH')
    if fault=='download': c._api.download_file=fail
    elif fault=='asr': c._voice_service.preview_from_bytes=fail
    elif fault=='size':
        async def wrong(*a,**k): return b'different'
        c._api.download_file=wrong
    else:
        async def malformed(*a,**k): return {'text':'PRIVATE_TRANSCRIPT'}
        c._voice_service.preview_from_bytes=malformed
    await c.handle(voice_update(10))
    await c._execute_voice_with_lease(claim(c))
    assert not compiler.inputs
    assert 'PRIVATE_' not in str(h.api.sent)


@pytest.mark.asyncio
async def test_foreign_reply_never_confirms_and_expiry_scrubs(tmp_path):
    h,compiler=harness(tmp_path); c=h.control
    await c.handle(voice_update(10)); await c._durable_voice.run(claim(c))
    foreign=text_update('да',11,reply_to_message_id=10); foreign['message']['from']['id']+=1
    await c.handle(foreign)
    assert rows(c)==[('voice','waiting')] and not compiler.inputs
    c._telegram_state._clock=lambda:datetime.now(UTC)+timedelta(hours=2)
    c._telegram_state.sweep_voice()
    with sqlite3.connect(c._telegram_state.path) as db:
        raw=db.execute("SELECT payload FROM telegram_jobs WHERE kind='voice'").fetchone()[0]
    assert c._telegram_state._decode(raw)=={}


def wav(seconds=1,rate=16000):
    output=io.BytesIO()
    with wave.open(output,'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(rate)
        f.writeframes(b'\x10\x00'*int(seconds*rate))
    return output.getvalue()


@pytest.mark.asyncio
async def test_memory_audio_path_has_no_temp_bytes_and_keeps_language_evidence(tmp_path):
    adapter=FasterWhisperTranscriber()
    adapter._transcribe_input=lambda audio,limit:TranscriptResult(text='Проверь\n> цитату',language='ru',language_confidence=.99)
    service=VoicePreviewService(adapter,tmp_path/'never-created',10*1024*1024,2000)
    result=await service.preview_from_bytes(wav())
    assert result.transcript=='Проверь\n> цитату'
    assert result.language_confidence==.99 and not hasattr(result,'confidence')
    assert result.quality=='unqualified_confirmation_required'
    assert result.duration_seconds==1 and not (tmp_path/'never-created').exists()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind',['empty','corrupt','overduration','unsupported_rate'])
async def test_memory_decoder_rejects_invalid_media_before_model(tmp_path,kind):
    audio={'empty':lambda:b'', 'corrupt':lambda:b'not audio',
           'overduration':lambda:wav(301), 'unsupported_rate':lambda:wav(1,4000)}[kind]()
    adapter=FasterWhisperTranscriber()
    adapter._transcribe_input=lambda *a:pytest.fail('model must not run')
    service=VoicePreviewService(adapter,tmp_path/'never-created',10*1024*1024,2000)
    with pytest.raises((ValueError,VoiceTranscriptionError)) as error:
        await service.preview_from_bytes(audio)
    assert error.value.__cause__ is None and error.value.__context__ is None
    assert not (tmp_path/'never-created').exists()


@pytest.mark.asyncio
@pytest.mark.parametrize('scenario',['direct','transform','quoted','nested','negated','cancel','conditional'])
async def test_accepted_voice_and_text_share_core_decision(tmp_path,scenario):
    texts={
        'direct':'Составь план проверки.',
        'transform':'Преобразуй материал ниже в готовый промт. В материале перечислены будущие действия: создать документ и отправить файл. Сейчас эти действия не выполняй.',
        'quoted':'«Отправь файл.»',
        'nested':'«Пример: “отправь файл”.»',
        'negated':'Не создавай встречу.',
        'cancel':'Отмени текущую задачу.',
        'conditional':'Если в списке есть просроченные дела, преобразуй список в краткий план.',
    }
    captures=[]
    class ScenarioCompiler:
        async def compile_semantic(self,model_input,output_schema,*,timeout_seconds):
            operation={'transform':'transform_material','conditional':'transform_material','cancel':'cancel_task',
                       'negated':'write_calendar_event'}.get(scenario,'respond')
            value=_semantic_proposal(model_input,operation_kind=operation,
                input_role='material_transformation' if operation=='transform_material' else 'direct_request',
                output_kind='prompt' if scenario=='transform' else 'answer')
            if scenario=='negated': value['operations'][0]['role']='negated'
            if scenario=='conditional' and model_input['materials'] and model_input['owner_text'].startswith('Если'):
                ref=model_input['materials'][0]['ref']
                value['operations'][0].update(role='conditional',predicate=dict(kind='material_item_state_exists',
                    subject_ref=ref,arguments={'item_state':'overdue'}))
            return value
    class Capture(SemanticAdmissionService):
        async def admit(self,*args,**kwargs):
            result=await super().admit(*args,**kwargs)
            captures.append((result.proposal.primary_goal,
                tuple((x.operation_kind,x.role) for x in result.proposal.operations),
                result.decision.decision,result.decision.selected_capability,
                result.decision.task_contract_allowed,result.decision.effect_allowed))
            return result
    for modality in ('text','voice'):
        h,_=harness(tmp_path/modality); c=h.control
        c._semantic_admission=Capture(ScenarioCompiler())
        if modality=='text':
            await c.handle(text_update(texts[scenario],10))
        else:
            async def preview(audio):
                return VoicePreview(transcript=texts[scenario],sha256=hashlib.sha256(audio).hexdigest(),size=len(audio))
            c._voice_service.preview_from_bytes=preview
            await c.handle(voice_update(10)); await c._durable_voice.run(claim(c))
            await c.handle(text_update('да',11,reply_to_message_id=10)); await c._durable_voice.run(claim(c))
        assert h.runtime.applied==[] and h.api.documents==[]
    assert len(captures)==2 and captures[0]==captures[1]
    if scenario in {'direct','transform'}: assert captures[0][2]=='EXECUTE'
    if scenario in {'quoted','nested','negated','conditional','cancel'}: assert captures[0][4] is False


@pytest.mark.asyncio
async def test_concurrent_voices_and_repeated_confirmation_have_one_draft_each(tmp_path):
    h,_=harness(tmp_path); c=h.control
    await asyncio.gather(c.handle(voice_update(10)),c.handle(voice_update(20)))
    first,second=claim(c),claim(c)
    await asyncio.gather(c._durable_voice.run(first),c._durable_voice.run(second))
    await asyncio.gather(c.handle(text_update('да',11,reply_to_message_id=10)),
                         c.handle(text_update('да',21,reply_to_message_id=20)))
    first,second=claim(c),claim(c)
    await asyncio.gather(c._durable_voice.run(first),c._durable_voice.run(second))
    assert rows(c)==[('draft','pending'),('draft','pending'),('voice','finished'),('voice','finished')]
    await c.handle(text_update('да',11,reply_to_message_id=10))
    assert c.asr_calls==2 and len(rows(c))==4


def test_dpapi_voice_payload_is_ciphertext_and_waiting_row_validates(tmp_path):
    from src.application.runtime_maintenance import validate_runtime_database
    from src.contracts.models import canonical_json_digest
    state=SQLiteTelegramState(tmp_path/'telegram-state.sqlite3')
    payload={'stage':'transcribed','synthetic_marker':'synthetic-voice-privacy-marker'}
    state.enqueue(kind='voice',tenant_id='owner',task_id=uuid4(),binding_digest=canonical_json_digest({'binding':1}),payload=payload)
    owner=uuid4(); job=state.claim(lease_owner=owner)
    state.checkpoint_voice(job,lease_owner=owner,payload=payload,status='waiting')
    validate_runtime_database(state.path)
    with sqlite3.connect(state.path) as db:
        encrypted=db.execute('SELECT payload FROM telegram_jobs').fetchone()[0]
    assert b'synthetic-voice-privacy-marker' not in encrypted
    assert state._decode(encrypted)==payload


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value',[('file_size',10*1024*1024+1),('duration',301),
    ('duration',0),('mime_type','video/mp4'),('file_unique_id','')])
async def test_voice_metadata_rejected_before_download(tmp_path,field,value):
    h,compiler=harness(tmp_path); c=h.control
    update=voice_update(10); update['message']['voice'][field]=value
    await c.handle(update)
    assert rows(c)==[] and c.asr_calls==0 and not compiler.inputs
    assert any('запис' in str(item).lower() for item in h.api.sent)


@pytest.mark.asyncio
@pytest.mark.parametrize('cut',['received','downloaded','transcribed','finished'])
async def test_disk_pressure_preserves_previous_durable_boundary(tmp_path,cut):
    h,compiler=harness(tmp_path); c=h.control
    real_encode=c._telegram_state._encode
    def fail_write(payload):
        if payload.get('stage')==cut or (cut=='finished' and payload=={}):
            raise OSError('SYNTHETIC_DISK_FULL')
        return real_encode(payload)
    if cut=='received':
        c._telegram_state._encode=fail_write
        with pytest.raises(OSError): await c.handle(voice_update(10))
        assert not rows(c) and c.asr_calls==0
        return
    await c.handle(voice_update(10))
    if cut=='finished':
        await c._durable_voice.run(claim(c))
        await c.handle(text_update('да',11,reply_to_message_id=10))
    c._telegram_state._encode=fail_write
    await c._execute_voice_with_lease(claim(c))
    assert 'SYNTHETIC_DISK_FULL' not in str(h.api.sent)
    assert c._worker_error=='voice_processing_failed'
    c._telegram_state._encode=real_encode
    if cut=='finished':
        # Recovery reuses the already prepared/enqueued draft.
        before=len(compiler.inputs)
        await c._durable_voice.run(claim(c))
        assert len(compiler.inputs)==before
        assert rows(c)==[('draft','pending'),('voice','finished')]
    else:
        await c._durable_voice.run(claim(c))
        assert rows(c)==[('voice','waiting')]
        assert c.asr_calls==1 and not compiler.inputs
    assert not list(tmp_path.rglob('*.tmp'))


@pytest.mark.asyncio
async def test_cancelled_native_worker_cannot_queue_more_inference_or_deliver_late_result(tmp_path):
    import threading
    started,release,stopped=threading.Event(),threading.Event(),threading.Event()
    adapter=FasterWhisperTranscriber()
    calls=[]
    def blocking_model(*a):
        calls.append(1); started.set()
        assert release.wait(5)
        stopped.set()
        return TranscriptResult(text='late synthetic result')
    adapter._transcribe_input=blocking_model
    task=asyncio.create_task(adapter.transcribe_audio(wav(),max_chars=2000))
    try:
        assert await asyncio.to_thread(started.wait,3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        with pytest.raises(VoiceTranscriptionError):
            await adapter.transcribe_audio(wav(),max_chars=2000)
        assert calls==[1]
    finally:
        release.set()
        assert await asyncio.to_thread(stopped.wait,3)
    # The native call itself cannot be forcibly interrupted by a Python thread;
    # this check proves bounded concurrency and late-result rejection, not a hard timeout.


@pytest.mark.asyncio
async def test_retry_reply_replay_cannot_confirm_a_different_generation(tmp_path):
    h,compiler=harness(tmp_path); c=h.control
    await c.handle(voice_update(10)); job=claim(c)
    c._telegram_state.checkpoint_voice(job,lease_owner=c._lease_owner,
                                       payload={**job.payload,'stage':'recognizing'})
    c._telegram_state.release(job,lease_owner=c._lease_owner)
    await c._durable_voice.run(claim(c))
    retry=text_update('повторить',11,reply_to_message_id=10)
    await c.handle(retry); await c._durable_voice.run(claim(c))
    c._telegram_state=_store(tmp_path); c._durable_voice=DurableVoiceIntake(c,c._telegram_state)
    await c.handle(retry)
    assert rows(c)==[('voice','waiting')] and compiler.inputs==[]
    await c.handle(text_update('да',12,reply_to_message_id=10))
    await c._durable_voice.run(claim(c))
    assert rows(c)==[('draft','pending'),('voice','finished')]


@pytest.mark.asyncio
@pytest.mark.parametrize('stage',['recognizing','interrupted'])
async def test_early_reply_is_consumed_and_survives_late_worker_checkpoint(tmp_path,stage):
    h,compiler=harness(tmp_path); c=h.control
    await c.handle(voice_update(10)); job=claim(c)
    job=c._telegram_state.checkpoint_voice(job,lease_owner=c._lease_owner,
        payload={**job.payload,'stage':stage},status='waiting' if stage=='interrupted' else 'leased')
    early=text_update('да',11,reply_to_message_id=10)
    await c.handle(early)
    if stage=='interrupted':
        await c.handle(text_update('повторить',12,reply_to_message_id=10))
        await c._durable_voice.run(claim(c))
    else:
        audio=b'voice'
        # Old worker's object predates reply11. Its checkpoint must merge the receipt.
        c._telegram_state.checkpoint_voice(job,lease_owner=c._lease_owner,payload={**job.payload,
            'stage':'waiting','preview':VoicePreview(transcript='Составь план.',
                sha256=hashlib.sha256(audio).hexdigest(),size=len(audio)).model_dump()},status='waiting')
    await c.handle(early)
    assert rows(c)==[('voice','waiting')] and not compiler.inputs


@pytest.mark.asyncio
@pytest.mark.parametrize('stage',['waiting','confirmed'])
async def test_disabled_c1_never_sends_recovered_voice_to_legacy_route(tmp_path,stage):
    h,compiler=harness(tmp_path); c=h.control
    await c.handle(voice_update(10)); await c._durable_voice.run(claim(c))
    if stage=='confirmed': await c.handle(text_update('да',11,reply_to_message_id=10))
    c._enable_semantic_admission=False; c._enable_extended_routes=True
    async def forbidden(*a,**kw): pytest.fail('disabled voice must not reach any instruction route')
    c._start_owner_instruction=forbidden
    if stage=='waiting': await c.handle(text_update('да',11,reply_to_message_id=10))
    await c._durable_voice.run(claim(c))
    assert rows(c)==[('voice','finished')] and not compiler.inputs
    await c.handle(text_update('да',11,reply_to_message_id=10))
    assert rows(c)==[('voice','finished')]


@pytest.mark.asyncio
async def test_two_healthy_voice_jobs_serialize_native_inference_without_manual_retry(tmp_path):
    import threading
    h,_=harness(tmp_path); c=h.control
    started,release=threading.Event(),threading.Event()
    adapter=FasterWhisperTranscriber(); calls=[]
    def model(*a):
        calls.append(1); started.set()
        assert release.wait(5)
        return TranscriptResult(text='Составь план.')
    adapter._transcribe_input=model
    audio=wav()
    async def download(*a,**kw): return audio
    c._api.download_file=download
    c._voice_service=VoicePreviewService(adapter,tmp_path/'no-temp',10*1024**2,2000)
    for identifier in (10,20):
        update=voice_update(identifier); update['message']['voice']['file_size']=len(audio)
        await c.handle(update)
    first,second=claim(c),claim(c)
    tasks=[asyncio.create_task(c._durable_voice.run(job)) for job in (first,second)]
    try:
        assert await asyncio.to_thread(started.wait,3)
        await asyncio.sleep(.02)
    finally:
        release.set()
        await asyncio.gather(*tasks)
    assert calls==[1,1] and rows(c)==[('voice','waiting'),('voice','waiting')]


@pytest.mark.asyncio
async def test_rejection_notice_is_only_sent_to_allowlisted_owner(tmp_path):
    h,_=harness(tmp_path); c=h.control
    update=voice_update(10); update['message']['voice']['duration']=301
    update['message']['from']['id']+=1
    await c.handle(update)
    assert rows(c)==[] and h.api.sent==[]
