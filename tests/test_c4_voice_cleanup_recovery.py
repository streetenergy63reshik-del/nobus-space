"""Finished voice cleanup remains recoverable without additional execution claims."""
from types import SimpleNamespace
import pytest
from src.application.durable_confirmations import DurableTelegramActionStore
from tests.test_durable_voice import harness
from tests.test_telegram_product import callback_update, voice_update
from tests.test_durable_voice import claim, rows
from src.storage import SQLiteStore
from src.models.task import TaskStatus
import sqlite3


async def ready(tmp_path):
    h, compiler = harness(tmp_path)
    c = h.control
    c._action_store = DurableTelegramActionStore(c._telegram_state)
    c._gateway._callback_token_store = c._action_store
    observed = []
    async def edit(chat, message, text, *, buttons=None):
        observed.append((chat, message, text, buttons))
    h.api.edit_message_text = edit
    await c.handle(voice_update(10))
    await c._durable_voice.run(claim(c))
    assert len(h.api.sent) == 1
    assert len(observed) == 2
    tokens = observed[-1][3]
    assert len(tokens) == 2
    return h, compiler, observed, tokens

def callback(token, update_id, message_id=1):
    update = callback_update(token, update_id)
    update['callback_query']['message']['message_id'] = message_id
    return update

def core(c,tmp_path):
    c._task_tenants=('owner',)
    c._task_runtime=None
    c._task_status_sender=None
    c._product_runtime._destination_refs={'owner':'sha256:'+'f'*64}
    store=SQLiteStore(tmp_path/'core.sqlite3')
    c._product_runtime._store=store
    return store

async def finished_cancel(tmp_path):
    h, compiler, observed, tokens=await ready(tmp_path)
    c=h.control
    h.api.delete_failure=True
    await c.handle(callback(tokens[1][1],11))
    # The selected fix uses terminal voice metadata; no further inference/retry is required.
    await c._durable_voice.run(claim(c))
    assert rows(c)==[('voice','finished')]
    core(c,tmp_path)
    ref=c._telegram_state.list_progress()[0]
    return h,compiler,ref

@pytest.mark.asyncio
async def test_reconcile_retries_delete_after_several_outages_without_voice_claims(tmp_path):
    h, compiler, ref=await finished_cancel(tmp_path)
    c=h.control
    for _ in range(4):
        await c.deliver_pending()
        assert c._telegram_state.list_progress()==(ref,)
    h.api.delete_failure=False
    await c.deliver_pending()
    assert not c._telegram_state.list_progress()
    assert h.api.deleted==[(42,1)] and not compiler.inputs and c.asr_calls==1
    assert rows(c)==[('voice','finished')] and c._worker_error is None

@pytest.mark.asyncio
async def test_waiting_preview_cannot_be_removed_by_empty_core_inventory(tmp_path):
    h,compiler,observed,tokens=await ready(tmp_path)
    c=h.control
    core(c,tmp_path)
    ref=c._telegram_state.list_progress()[0]
    await c._settle_task_progress(ref.tenant_id,ref.task_id)
    assert c._telegram_state.list_progress()==(ref,)
    assert not h.api.deleted and not compiler.inputs

@pytest.mark.asyncio
@pytest.mark.parametrize('draft_state', ['pending', 'failed', 'corrupt'])
async def test_finished_voice_with_pending_draft_keeps_progress_before_core_admission(tmp_path,draft_state):
    h,compiler,observed,tokens=await ready(tmp_path)
    c=h.control
    await c.handle(callback(tokens[0][1],11))
    await c._durable_voice.run(claim(c))
    assert rows(c)==[('draft','pending'),('voice','finished')]
    with sqlite3.connect(c._telegram_state.path) as db:
        if draft_state == 'failed':
            db.execute("UPDATE telegram_jobs SET status='failed' WHERE kind='draft'")
        elif draft_state == 'corrupt':
            db.execute("UPDATE telegram_jobs SET payload=? WHERE kind='draft'",(b'broken',))
    core(c,tmp_path)
    ref=c._telegram_state.list_progress()[0]
    await c._settle_task_progress(ref.tenant_id,ref.task_id)
    assert c._telegram_state.list_progress()==(ref,)
    assert not h.api.deleted and len(compiler.inputs)==1 and c.asr_calls==1

@pytest.mark.asyncio
async def test_stale_initial_core_absence_cannot_delete_later_task_status(tmp_path):
    h,compiler,ref=await finished_cancel(tmp_path)
    c=h.control
    h.api.delete_failure=False
    store=c._product_runtime._store
    observed=[]
    def stale_then_current(tenant,task_id):
        observed.append((tenant,task_id))
        return None if len(observed)==1 else SimpleNamespace(projection=SimpleNamespace(status=TaskStatus.PARSING))
    store.read_task=stale_then_current
    await c._settle_task_progress(ref.tenant_id,ref.task_id)
    assert len(observed)==2
    assert c._telegram_state.list_progress()==(ref,) and not h.api.deleted
