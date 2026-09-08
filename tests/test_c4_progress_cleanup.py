"""One owned progress message survives stage changes and is cleaned by exact ref."""

import pytest

from tests.test_durable_voice import harness
from tests.test_telegram_product import text_update
from src.application.durable_product import _miniapp_task_id


def editing_api(h):
    edits = []
    async def edit(chat_id, message_id, text, *, buttons=None):
        assert h.api.sent[message_id - 1][0] == chat_id
        edits.append((chat_id, message_id, text, buttons))
    h.api.edit_message_text = edit
    return edits


@pytest.mark.asyncio
async def test_text_receipt_and_admitted_progress_reuse_one_persisted_message(tmp_path):
    h, compiler = harness(tmp_path)
    edits = editing_api(h)
    assert await h.control.handle(text_update("Составь план проверки.", 501))
    assert len(compiler.inputs) == 1
    assert len(h.api.sent) == 1
    assert h.api.sent[0][1] == "Сообщение получено. Разбираюсь в задаче."
    assert len(edits) == 1 and edits[0][1] == 1
    assert "принята" in edits[0][2]
    with h.control._telegram_state.reconciliation_jobs() as jobs:
        job = next(iter(jobs))
    ref = h.control._telegram_state.read_progress(tenant_id=job.tenant_id, task_id=job.task_id)
    assert ref.message_id == 1
    # Cleanup retries the stored bot-owned reference, not task execution.
    h.api.delete_failure = True
    with pytest.raises(RuntimeError, match="cleanup"):
        await h.control._clear_progress_binding(job.tenant_id, job.task_id)
    assert h.control._telegram_state.read_progress(tenant_id=job.tenant_id, task_id=job.task_id) == ref
    h.api.delete_failure = False
    await h.control._clear_progress_binding(job.tenant_id, job.task_id)
    assert h.api.deleted == [(ref.chat_id, 1)]
    assert h.control._telegram_state.read_progress(tenant_id=job.tenant_id, task_id=job.task_id) is None
    assert len(compiler.inputs) == 1 and h.runtime.drafted == []


@pytest.mark.asyncio
async def test_semantic_failure_removes_only_temporary_receipt(tmp_path):
    h, compiler = harness(tmp_path)
    editing_api(h)
    async def fail(*args, **kwargs):
        raise RuntimeError("private diagnostic")
    compiler.compile_semantic = fail
    assert await h.control.handle(text_update("Составь план проверки.", 502))
    assert len(h.api.sent) == 2
    assert h.api.deleted == [(h.api.sent[0][0], 1)]
    assert "никаких действий" in h.api.sent[1][1]
    assert "private diagnostic" not in h.api.sent[1][1]
    assert h.runtime.drafted == []


@pytest.mark.asyncio
async def test_progress_destination_mismatch_cannot_edit_or_delete_foreign_message(tmp_path):
    h, _ = harness(tmp_path)
    edits = editing_api(h)
    ingress = h.control._gateway.process_update(text_update("Составь план.", 503))
    message = ingress.payload
    task_id = _miniapp_task_id(ingress.envelope.tenant_id, ingress.envelope.idempotency_key)
    h.control._telegram_state.save_progress(tenant_id=message.tenant_id, task_id=task_id,
                                            chat_id=message.chat_id + 1, message_id=987)
    with pytest.raises(RuntimeError, match="destination mismatch"):
        await h.control._show_intake_progress(message, task_id, "Получено")
    assert not h.api.sent and not edits and not h.api.deleted
