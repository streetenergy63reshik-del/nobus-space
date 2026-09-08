"""Voice buttons use the real gateway, durable action store and voice CAS."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import json

import pytest

from src.application.durable_confirmations import DurableTelegramActionStore
from src.application.durable_voice import DurableVoiceIntake
from src.transport.telegram import IngressStatus
from tests.test_durable_telegram_state import _store
from tests.test_durable_voice import harness, claim, rows
from tests.test_telegram_product import callback_update, text_update, voice_update


async def preview_ready(tmp_path):
    h, compiler = harness(tmp_path)
    c = h.control
    c._action_store = DurableTelegramActionStore(c._telegram_state)
    c._gateway._callback_token_store = c._action_store
    # This module isolates voice state transitions; progress editing has its own tests.
    async def feedback(message, text, *, buttons=None):
        return await c._api.send_message(message.chat_id, text, buttons=buttons or (),
                                          message_thread_id=message.message_thread_id)
    c._voice_feedback = feedback
    await c.handle(voice_update(10))
    await c._durable_voice.run(claim(c))
    assert rows(c) == [('voice', 'waiting')]
    buttons = h.api.sent[-1][2]
    assert tuple(label for label, _ in buttons) == ('Подтверждаю', 'Записать заново')
    return h, compiler, buttons, len(h.api.sent)


def route(c, token, update_id, message_id):
    update = callback_update(token, update_id)
    update['callback_query']['message']['message_id'] = message_id
    ingress = c._gateway.process_update(update)
    assert ingress.status == IngressStatus.ACCEPTED
    claimed = c._action_store.consume(ingress.payload)
    assert claimed is not None
    return ingress, claimed


async def resolve(c, token, update_id, message_id):
    ingress, claimed = route(c, token, update_id, message_id)
    original = await c._durable_voice.resolve_callback(
        ingress.payload, ingress.envelope, claimed.action, claimed.capability_token)
    assert c._action_store.commit(ingress.payload)
    return original


@pytest.mark.asyncio
async def test_confirm_survives_restart_and_conflicting_button_cannot_repeat_task(tmp_path):
    h, compiler, buttons, message_id = await preview_ready(tmp_path)
    c = h.control
    assert not compiler.inputs and c.asr_calls == 1
    c._telegram_state = _store(tmp_path)
    c._durable_voice = DurableVoiceIntake(c, c._telegram_state)
    c._action_store = DurableTelegramActionStore(c._telegram_state)
    c._gateway._callback_token_store = c._action_store
    original = await resolve(c, buttons[0][1], 11, message_id)
    assert original is not None and original.message_id == 10
    # The opposite one-shot token is distinct, but it cannot transition the accepted preview.
    assert await resolve(c, buttons[1][1], 12, message_id) is None
    await c._durable_voice.run(claim(c))
    assert rows(c) == [('draft', 'pending'), ('voice', 'finished')]
    assert compiler.inputs[0]['owner_text'] == 'Составь план проверки.'
    assert c.asr_calls == 1
    duplicate = callback_update(buttons[0][1], 13)
    duplicate['callback_query']['message']['message_id'] = message_id
    assert c._gateway.process_update(duplicate).status != IngressStatus.ACCEPTED


@pytest.mark.asyncio
async def test_replace_cancels_old_voice_without_retry_or_extra_status(tmp_path):
    h, compiler, buttons, message_id = await preview_ready(tmp_path)
    c = h.control
    assert await resolve(c, buttons[1][1], 11, message_id) is not None
    before = len(h.api.sent)
    assert await resolve(c, buttons[0][1], 12, message_id) is None
    await c._durable_voice.run(claim(c))
    assert len(h.api.sent) == before
    assert rows(c) == [('voice', 'finished')]
    assert c.asr_calls == 1 and not compiler.inputs
    await c.handle(voice_update(20))
    await c._durable_voice.run(claim(c))
    assert rows(c).count(('voice', 'waiting')) == 1 and c.asr_calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['message', 'generation', 'preview', 'expired', 'disabled',
                                    'tenant_id', 'actor_identity', 'actor_role',
                                    'auth_context_ref', 'topic'])
async def test_changed_binding_cannot_confirm(tmp_path, change):
    h, compiler, buttons, message_id = await preview_ready(tmp_path)
    c = h.control
    if change in {'tenant_id', 'actor_identity', 'actor_role', 'auth_context_ref'}:
        bindings = dict(c._gateway._actor_bindings)
        pair, binding = next(iter(bindings.items()))
        value = 'sha256:' + '9' * 64 if change == 'auth_context_ref' else 'different'
        bindings[pair] = binding.model_copy(update={'role' if change == 'actor_role' else change: value})
        c._gateway.replace_actor_bindings(bindings)
    update = callback_update(buttons[0][1], 11)
    update['callback_query']['message']['message_id'] = message_id + int(change == 'message')
    if change == 'topic':
        update['callback_query']['message']['message_thread_id'] = 42
    ingress = c._gateway.process_update(update)
    if ingress.status == IngressStatus.ACCEPTED:
        claimed = c._action_store.consume(ingress.payload)
        capability = json.loads(claimed.capability_token)
        if change == 'generation': capability['generation'] += 1
        if change == 'preview': capability['preview'] = 'sha256:' + '0' * 64
        if change == 'disabled': c._enable_semantic_admission = False
        if change == 'expired':
            c._telegram_state._clock = lambda: datetime.now(UTC) + timedelta(minutes=16)
        assert await c._durable_voice.resolve_callback(ingress.payload, ingress.envelope,
            claimed.action, json.dumps(capability)) is None
    assert rows(c) == [('voice', 'waiting')]
    assert c.asr_calls == 1 and not compiler.inputs


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['from', 'chat'])
async def test_other_user_or_chat_cannot_claim_button(tmp_path, field):
    h, compiler, buttons, message_id = await preview_ready(tmp_path)
    update = callback_update(buttons[0][1], 11)
    update['callback_query']['message']['message_id'] = message_id
    if field == 'from': update['callback_query']['from']['id'] += 1
    else: update['callback_query']['message']['chat']['id'] += 1
    assert h.control._gateway.process_update(update).status != IngressStatus.ACCEPTED
    assert rows(h.control) == [('voice', 'waiting')] and not compiler.inputs


@pytest.mark.asyncio
async def test_typed_correction_wins_over_old_buttons(tmp_path):
    h, compiler, buttons, message_id = await preview_ready(tmp_path)
    c = h.control
    await c.handle(text_update('Составь краткий отчёт.', 11, reply_to_message_id=10))
    assert await resolve(c, buttons[0][1], 12, message_id) is None
    await c._durable_voice.run(claim(c))
    assert compiler.inputs[0]['owner_text'] == 'Составь краткий отчёт.'
    assert c.asr_calls == 1 and rows(c) == [('draft', 'pending'), ('voice', 'finished')]


@pytest.mark.asyncio
async def test_gateway_envelope_mismatch_is_rejected_before_transition(tmp_path):
    h, compiler, buttons, message_id = await preview_ready(tmp_path)
    c = h.control
    ingress, claimed = route(c, buttons[0][1], 11, message_id)
    changed = ingress.payload.model_copy(update={'message_id': message_id + 1})
    with pytest.raises(ValueError, match='envelope binding mismatch'):
        await c._durable_voice.resolve_callback(changed, ingress.envelope,
                                               claimed.action, claimed.capability_token)
    assert rows(c) == [('voice', 'waiting')] and not compiler.inputs


@pytest.mark.asyncio
@pytest.mark.parametrize('capability', ['null', '[]', '{}', '{"voice":1,"generation":0,"preview":"x"}',
                                       '{"voice":"bad","generation":0,"preview":"x"}'])
async def test_malformed_capability_cannot_confirm(tmp_path, capability):
    h, compiler, buttons, message_id = await preview_ready(tmp_path)
    c = h.control
    ingress, claimed = route(c, buttons[0][1], 11, message_id)
    assert await c._durable_voice.resolve_callback(ingress.payload, ingress.envelope,
                                                  claimed.action, capability) is None
    assert rows(c) == [('voice', 'waiting')] and not compiler.inputs


@pytest.mark.asyncio
async def test_preview_with_unknown_delivery_is_never_confirmable(tmp_path):
    h, compiler = harness(tmp_path)
    async def unknown(*args, **kwargs): return 0
    h.control._voice_feedback = unknown
    await h.control.handle(voice_update(10))
    with pytest.raises(ValueError, match='preview delivery is unknown'):
        await h.control._durable_voice.run(claim(h.control))
    assert rows(h.control) == [('voice', 'leased')]
    assert h.control.asr_calls == 1 and not compiler.inputs


@pytest.mark.asyncio
async def test_actual_control_dispatch_accepts_button_without_reply(tmp_path):
    h, compiler, buttons, message_id = await preview_ready(tmp_path)
    update = callback_update(buttons[0][1], 11)
    update['callback_query']['message']['message_id'] = message_id
    assert await h.control.handle(update)
    assert h.api.callback_texts[-1] == 'Подтверждено.'
    assert (update['callback_query']['message']['chat']['id'], message_id) not in h.api.deleted
    await h.control._durable_voice.run(claim(h.control))
    assert compiler.inputs[0]['owner_text'] == 'Составь план проверки.'
    assert rows(h.control) == [('draft', 'pending'), ('voice', 'finished')]


@pytest.mark.asyncio
async def test_restart_between_voice_cas_and_action_commit_does_not_reconfirm(tmp_path):
    h, compiler, buttons, message_id = await preview_ready(tmp_path)
    c = h.control
    ingress, claimed = route(c, buttons[0][1], 11, message_id)
    async def crash(*args, **kwargs): raise asyncio.CancelledError()
    c._durable_voice._status = crash
    with pytest.raises(asyncio.CancelledError):
        await c._durable_voice.resolve_callback(ingress.payload, ingress.envelope,
                                               claimed.action, claimed.capability_token)
    c._telegram_state = _store(tmp_path)
    c._durable_voice = DurableVoiceIntake(c, c._telegram_state)
    c._action_store = DurableTelegramActionStore(c._telegram_state)
    c._gateway._callback_token_store = c._action_store
    assert await resolve(c, buttons[0][1], 12, message_id) is None
    await c._durable_voice.run(claim(c))
    assert len(compiler.inputs) == 1 and c.asr_calls == 1
    assert rows(c) == [('draft', 'pending'), ('voice', 'finished')]
