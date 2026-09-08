"""Feedback precedes slow semantic intake without admitting a task early."""

import asyncio

import pytest

from tests.test_durable_voice import harness, rows
from tests.test_telegram_product import _semantic_proposal, text_update


RECEIVED = "Сообщение получено. Разбираюсь в задаче."


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["execute", "clarify", "unavailable", "failure"])
async def test_received_feedback_precedes_semantic_result_and_admission(tmp_path, outcome):
    h, compiler = harness(tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()

    async def compile_semantic(model_input, output_schema, *, timeout_seconds):
        compiler.inputs.append(model_input)
        entered.set()
        await release.wait()
        if outcome == "failure":
            raise RuntimeError("private provider failure")
        return _semantic_proposal(
            model_input,
            ambiguous=outcome == "clarify",
            operation_kind="create_file" if outcome == "unavailable" else "respond",
        )

    compiler.compile_semantic = compile_semantic
    update = text_update("Составь план проверки.", 80)
    running = asyncio.create_task(h.control.handle(update))
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        assert [value[1] for value in h.api.sent] == [RECEIVED]
        assert rows(h.control) == []
        assert not h.runtime.drafted and not h.runtime.applied
        assert not running.done()
    finally:
        release.set()
        await running

    if outcome == "execute":
        assert rows(h.control) == [("draft", "pending")]
        # An outer polling replay may repeat feedback, but cannot create a second job.
        assert await h.control.handle(update)
        assert rows(h.control) == [("draft", "pending")]
    else:
        assert rows(h.control) == []
        assert h.api.sent[-1][1] != RECEIVED
    assert not h.runtime.drafted and not h.runtime.applied and not h.api.documents
    assert all("private provider failure" not in value[1] for value in h.api.sent)


@pytest.mark.asyncio
async def test_unbound_clarification_returns_rejection_without_understanding_feedback(tmp_path):
    h, compiler = harness(tmp_path)
    assert await h.control.handle(text_update("Используй этот текст.", 81, reply_to_message_id=999))
    assert len(h.api.sent) == 1 and "уже истекло" in h.api.sent[0][1]
    assert compiler.inputs == [] and rows(h.control) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_failed_received_delivery_stops_before_semantic_admission(tmp_path, cancelled):
    h, compiler = harness(tmp_path)
    send = h.api.send_message
    attempted = []

    async def fail_received(chat_id, text, **kwargs):
        attempted.append(text)
        if text == RECEIVED:
            if cancelled:
                raise asyncio.CancelledError()
            raise TimeoutError("delivery outcome unknown")
        return await send(chat_id, text, **kwargs)

    h.api.send_message = fail_received
    update = text_update("Составь план проверки.", 82)
    if cancelled:
        with pytest.raises(asyncio.CancelledError):
            await h.control.handle(update)
    else:
        assert await h.control.handle(update)
    assert attempted.count(RECEIVED) == 1
    assert compiler.inputs == [] and rows(h.control) == []
    assert not h.runtime.drafted and not h.runtime.applied
    h.api.send_message = send
    assert await h.control.handle(update)
    assert rows(h.control) == [("draft", "pending")]
