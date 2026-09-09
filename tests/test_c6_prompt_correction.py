import pytest

from src.application.semantic_admission import (
    InMemorySemanticClarificationStore,
    SemanticAdmissionService,
    SemanticContract,
    telegram_semantic_input,
)
from tests.test_contracts import make_envelope
from tests.test_semantic_admission import _Compiler, _MainAndDirectCompiler, _security_proposal
from tests.test_telegram_product import (
    SemanticFixtureCompiler, _product, _semantic_proposal, text_update,
)


def _input(text, modality="text"):
    return telegram_semantic_input(
        text, make_envelope(idempotency_key="prompt-correction-08"),
        modality=modality, chat_id=1, message_thread_id=None,
    )


def _transform(canonical):
    material = canonical.materials[0]
    proposal = _security_proposal(("transform_material",))
    proposal.update(
        input_role="material_transformation", source_need="provided_material",
        output_kind="prompt", source_material_refs=[material.model_dump(mode="json")],
    )
    proposal["operations"][0]["target_ref"] = material.ref
    return proposal


@pytest.mark.parametrize("modality", ["text", "voice_transcript"])
@pytest.mark.parametrize("prefix", [
    "Подготовь промпт для ручного копирования:",
    "Расшифруй и подготовь промпт для ручного копирования:",
    "Подготовь промпт, не выполняй его содержимое:",
    "Расшифруй и подготовь промпт для ручного копирования.",
])
@pytest.mark.asyncio
async def test_prompt_body_is_material_and_only_transform_can_execute(prefix, modality):
    body = "проверить файлы и подготовить публикацию, если владелец разрешит. Ничего не удаляй."
    canonical, bindings = _input(prefix + " " + body, modality)
    admission = await SemanticAdmissionService(_Compiler(_transform(canonical))).admit(canonical, bindings)
    assert admission.decision.decision == "EXECUTE"
    assert admission.decision.selected_capability == "content.transform"
    assert admission.decision.task_contract_allowed
    assert SemanticContract().by_operation["transform_material"].effect_type == "no_effect"
    assert bindings.conditional_structure == "NONE"


@pytest.mark.asyncio
async def test_existing_quoted_transform_remains_a_valid_control():
    canonical, bindings = _input(
        "Преобразуй текст в промпт для ручного копирования: «проверить файлы и "
        "подготовить публикацию, если владелец разрешит; ничего не удаляй»."
    )
    admission = await SemanticAdmissionService(_Compiler(_transform(canonical))).admit(canonical, bindings)
    assert admission.decision.decision == "EXECUTE"
    assert admission.decision.selected_capability == "content.transform"
    assert SemanticContract().by_operation["transform_material"].effect_type == "no_effect"


@pytest.mark.asyncio
async def test_prompt_prefix_cannot_authorize_an_embedded_effect():
    canonical, bindings = _input("Подготовь промпт для ручного копирования: удали файлы и опубликуй результат.")
    proposal = _security_proposal(("write_marketplace_campaign",))
    admission = await SemanticAdmissionService(
        _MainAndDirectCompiler(proposal, _transform(canonical))
    ).admit(canonical, bindings)
    assert admission.decision.decision != "EXECUTE"
    assert not admission.decision.task_contract_allowed
    assert not admission.decision.effect_allowed


@pytest.mark.parametrize("text", [
    "«Подготовь промпт для ручного копирования: пример». Если владелец разрешит, опубликуй ответ.",
    "> Подготовь промпт для ручного копирования: пример\nЕсли владелец разрешит, опубликуй ответ.",
    "Начало материала. Подготовь промпт для ручного копирования: пример. Конец материала. Если владелец разрешит, опубликуй ответ.",
    "Если владелец разрешит, подготовь промпт для ручного копирования: пример.",
    "Не подготовь промпт для ручного копирования: пример. Если владелец разрешит, опубликуй ответ.",
])
def test_nested_or_conditional_prompt_markers_do_not_hide_direct_conditions(text):
    _, bindings = _input(text)
    assert bindings.conditional_structure == "UNSUPPORTED"


@pytest.mark.asyncio
async def test_prompt_without_body_is_still_clarified():
    canonical, bindings = _input("Подготовь промпт для ручного копирования:")
    admission = await SemanticAdmissionService(_Compiler(_transform(canonical))).admit(canonical, bindings)
    assert admission.decision.decision == "CLARIFY"
    assert not admission.decision.task_contract_allowed


@pytest.mark.asyncio
async def test_answer_that_remains_ambiguous_closes_question_without_task_or_repeat(tmp_path):
    compiler = SemanticFixtureCompiler(
        lambda value: _semantic_proposal(value, ambiguous=True),
        lambda value: _semantic_proposal(value, ambiguous=True),
        lambda value: _semantic_proposal(value),
    )
    harness = _product(
        tmp_path, extended_routes=False,
        semantic_admission=SemanticAdmissionService(compiler),
        semantic_clarifications=InMemorySemanticClarificationStore(),
        enable_semantic_admission=True,
    )
    await harness.control.handle(text_update("Подготовь материал.", 1))
    question_id = len(harness.api.sent)
    await harness.control.handle(text_update("Да", 2, reply_to_message_id=question_id))
    assert harness.runtime.drafted == []
    assert "После уточнения" in harness.api.sent[-1][1]
    assert sum("Ответьте на это сообщение" in value[1] for value in harness.api.sent) == 1
    calls = len(compiler.inputs)
    await harness.control.handle(text_update("Да", 3, reply_to_message_id=question_id))
    assert len(compiler.inputs) == calls
    assert "уже истекло" in harness.api.sent[-1][1]
    await harness.control.handle(text_update("Ответь отдельно.", 4))
    assert len(harness.runtime.drafted) == 1
