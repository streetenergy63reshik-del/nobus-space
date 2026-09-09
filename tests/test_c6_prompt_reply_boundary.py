from dataclasses import replace
import json

import pytest

from src.application.durable_product import DurableProductTelegramControlPlane
from src.application.semantic_admission import (
    InMemorySemanticClarificationStore, SemanticAdmissionError,
    SemanticAdmissionService, SemanticClarificationRejected,
    SemanticClarificationRequired, telegram_semantic_input,
)
from src.contracts.models import TrustedIngressEnvelope, canonical_json_digest
from tests.test_contracts import make_envelope
from tests.test_semantic_admission import _Compiler, _security_proposal
from tests.test_telegram_product import SemanticFixtureCompiler, _product, _semantic_proposal, text_update


ORIGINAL = "Подготовь промпт для ручного копирования: синтетический материал"
CONDITIONAL_REPLY = "Если владелец разрешит, подготовь промпт для ручного копирования"
SEPARATOR = "\n\nИсходная задача владельца указана выше.\nУточнение владельца:\n"


def _envelope(text, number):
    data = make_envelope(idempotency_key=f"reply-boundary-{number}").model_dump(
        mode="json", exclude={"envelope_revision"}
    )
    data["content_ref"] = canonical_json_digest({"text": text, "number": number})
    data["envelope_revision"] = canonical_json_digest(data)
    return TrustedIngressEnvelope.model_validate_json(json.dumps(data))


def _compiler():
    return SemanticFixtureCompiler(
        lambda value: _semantic_proposal(value, operation_kind="transform_material",
                                        input_role="material_transformation", output_kind="prompt", ambiguous=True),
        lambda value: _semantic_proposal(value, operation_kind="transform_material",
                                        input_role="material_transformation", output_kind="prompt"),
    )


@pytest.mark.asyncio
async def test_actual_telegram_pending_reply_keeps_its_condition_direct(tmp_path):
    compiler = _compiler()
    harness = _product(
        tmp_path, extended_routes=False,
        semantic_admission=SemanticAdmissionService(compiler),
        semantic_clarifications=InMemorySemanticClarificationStore(),
        enable_semantic_admission=True,
    )
    await harness.control.handle(text_update(ORIGINAL, 1))
    question_id = len(harness.api.sent)
    await harness.control.handle(text_update(CONDITIONAL_REPLY, 2, reply_to_message_id=question_id))
    assert harness.runtime.drafted == []
    assert "После уточнения" in harness.api.sent[-1][1]
    assert sum("Ответьте на это сообщение" in entry[1] for entry in harness.api.sent) == 1
    calls = len(compiler.inputs)
    await harness.control.handle(text_update("Да", 3, reply_to_message_id=question_id))
    assert len(compiler.inputs) == calls
    assert harness.runtime.drafted == []


@pytest.mark.asyncio
async def test_actual_miniapp_pending_reply_closes_without_a_second_token_or_task():
    compiler = _compiler()
    control = object.__new__(DurableProductTelegramControlPlane)
    control._admission_readiness = None
    control._closing = False
    control._enable_semantic_admission = True
    control._semantic_admission = SemanticAdmissionService(compiler)
    control._semantic_clarifications = InMemorySemanticClarificationStore()
    # Any accidental acceptance must fail the test before task construction.
    control._product_runtime = None
    with pytest.raises(SemanticClarificationRequired) as question:
        await control.submit_miniapp_task(ORIGINAL, _envelope(ORIGINAL, 1))
    token = question.value.token
    with pytest.raises(SemanticClarificationRejected, match="remained ambiguous"):
        await control.submit_miniapp_task(CONDITIONAL_REPLY, _envelope(CONDITIONAL_REPLY, 2), clarification_token=token)
    calls = len(compiler.inputs)
    with pytest.raises(SemanticClarificationRejected, match="binding is invalid"):
        await control.submit_miniapp_task("Да", _envelope("Да", 3), clarification_token=token)
    assert len(compiler.inputs) == calls


@pytest.mark.parametrize("modality", ["text", "voice_transcript", "miniapp_text"])
@pytest.mark.parametrize("original", [
    ORIGINAL,
    "Подготовь промпт для ручного копирования: «незакрытая цитата",
    "Подготовь промпт для ручного копирования: материал\nУточнение владельца:\nэто всё ещё материал",
])
def test_structural_boundaries_are_server_owned_and_voice_text_miniapp_equal(modality, original):
    merged = original + SEPARATOR + CONDITIONAL_REPLY
    canonical, bindings = telegram_semantic_input(
        merged, _envelope(merged, 4), modality=modality, chat_id=1,
        message_thread_id=None, owner_message_break=len(original),
    )
    assert bindings.conditional_structure == "UNSUPPORTED"
    reply_start = merged.index(CONDITIONAL_REPLY)
    span = next(value for value in bindings.text_span_bindings if value.start <= reply_start < value.end)
    assert span.trusted_origin == "DIRECT_OWNER_COMMAND"
    assert "owner_message_break" not in canonical.model_input()


@pytest.mark.parametrize("boundary", [0, -1, 100000, True, 1.5])
def test_invalid_message_boundary_fails_closed(boundary):
    with pytest.raises(ValueError, match="boundary is invalid"):
        telegram_semantic_input(ORIGINAL, _envelope(ORIGINAL, 5), modality="text",
                                chat_id=1, message_thread_id=None, owner_message_break=boundary)


@pytest.mark.asyncio
async def test_changed_message_boundary_cannot_reuse_the_trusted_span_ledger():
    merged = ORIGINAL + SEPARATOR + "Ответь кратко."
    canonical, bindings = telegram_semantic_input(
        merged, _envelope(merged, 6), modality="text", chat_id=1,
        message_thread_id=None, owner_message_break=len(ORIGINAL),
    )
    forged = replace(bindings, owner_message_break=len(ORIGINAL) + 1)
    with pytest.raises(SemanticAdmissionError, match="SEMANTIC_CONTEXT_INVALID"):
        await SemanticAdmissionService(_Compiler(_security_proposal(("respond",)))).admit(canonical, forged)
