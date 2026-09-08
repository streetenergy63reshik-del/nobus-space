"""Closed product projection and Telegram journey checks; no provider/ASR calls."""
from datetime import UTC, datetime, timedelta

import pytest

from src.application.durable_product import DurableProductTelegramControlPlane
from src.application.product_status import (
    ProductAction, ProductAdmissionStopped, ProductReason,
    product_event_label, product_progress_state, product_reason_state, product_task_state,
)
from src.application.semantic_admission import (
    SemanticAdmissionService, SemanticClarificationRequired,
)
from src.models.task import TaskStatus
from src.contracts.models import canonical_json_digest
from src.storage.outbox import artifact_for_message, delivery_parts
from src.transport.telegram.bot_api import TelegramStatusSender, _status_text
from tests.test_durable_voice import harness, rows
from tests.test_telegram_bot_api import DESTINATION_REF, api_for, outbox_message, response
from tests.test_telegram_product import SemanticFixtureCompiler, _semantic_proposal, text_update


def test_closed_catalog_covers_states_without_authorizing_effects():
    for status in TaskStatus:
        state = product_task_state(status)
        assert state.reason in ProductReason and state.action in ProductAction
        assert state.reason_label and state.label
        if state.status.value == "ready":
            assert status in {TaskStatus.ANSWERED, TaskStatus.COMPLETED}
    for reason in ProductReason:
        state = product_reason_state(reason)
        assert state.reason == reason
        assert "проверенный" not in state.reason_label.casefold()
    with pytest.raises(ValueError):
        product_task_state("ANSWERED")
    with pytest.raises(ValueError):
        product_reason_state("result_ready")
    with pytest.raises(ValueError):
        product_event_label("<script>unsafe</script>")


@pytest.mark.parametrize("seconds,duration", [(-1, "меньше минуты"), (0, "меньше минуты"),
    (59.9, "меньше минуты"), (60, "1 мин."), (119.9, "1 мин."), (120, "2 мин.")])
def test_progress_duration_is_measured_and_stage_is_allowlisted(seconds, duration):
    rendered = DurableProductTelegramControlPlane._progress_text("C:/private/worker-secret", seconds)
    assert rendered.endswith(duration)
    assert "private" not in rendered and "secret" not in rendered
    assert rendered.startswith(product_reason_state(ProductReason.WORKING).reason_label)
    assert product_progress_state("Проверяю результат").reason == ProductReason.CHECKING_RESULT


def test_recovery_and_delivery_never_instruct_new_task():
    for reason in (ProductReason.RECOVERY_REQUIRED, ProductReason.TEMPORARILY_UNAVAILABLE):
        state = product_reason_state(reason)
        assert state.action is ProductAction.CHECK_STATUS
        assert "не отправляйте" in state.reason_label
    delivery = product_reason_state(ProductReason.DELIVERY_PENDING)
    assert "не подтверждена" in delivery.reason_label
    assert delivery.action is ProductAction.OPEN_RESULT
    assert "Попробуйте ещё раз" not in _status_text(outbox_message(TaskStatus.ESCALATE), technical_details=False)


def test_telegram_result_copy_does_not_change_artifact_bytes():
    message = outbox_message(TaskStatus.ANSWERED)
    artifact = artifact_for_message(message)
    assert artifact is not None
    assert artifact.content_bytes() == message.user_message.encode("utf-8")
    rendered = _status_text(message, technical_details=False)
    assert rendered == message.user_message
    assert str(message.task_id) not in rendered


@pytest.mark.asyncio
async def test_visible_file_alias_preserves_c3_artifact_and_delivery_binding():
    message = outbox_message(TaskStatus.ANSWERED)
    artifact = artifact_for_message(message)
    api = api_for(lambda request: response({"message_id": 1, "chat": {"id": 42}}))
    sender = TelegramStatusSender(api, {"tenant-a": (DESTINATION_REF, 42)}, technical_details=False)
    try:
        parts = sender._parts(message)
        assert parts[-1] == ("document", artifact.content_bytes(), "nobus-result.txt")
        assert artifact.filename == f"nobus-result-{message.task_id}.txt"
        expected = delivery_parts(message, (("text", message.user_message.encode("utf-8")),
            ("document", artifact.content_bytes())))
        assert sender.delivery_manifest(message) == expected
        assert artifact_for_message(message) == artifact
    finally:
        await api.aclose()


@pytest.mark.asyncio
async def test_help_describes_confirmation_only_when_c2_semantic_path_enabled(tmp_path):
    h, _ = harness(tmp_path)
    assert "подтвердите" in h.control._help_text()
    assert "без отдельного предпросмотра" not in h.control._help_text()
    assert "текстовый результат" in h.control._help_text()
    h.control._enable_semantic_admission = False
    assert "подтвердите" not in h.control._help_text()


@pytest.mark.asyncio
async def test_miniapp_semantic_stop_is_typed_and_creates_no_task(tmp_path):
    h, _ = harness(tmp_path)
    compiler = SemanticFixtureCompiler(lambda value: _semantic_proposal(value, operation_kind="create_file"))
    h.control._semantic_admission = SemanticAdmissionService(compiler)
    envelope = h.control._gateway.process_update(text_update("Создай файл.", 70)).envelope
    with pytest.raises(ProductAdmissionStopped) as stopped:
        await h.control.submit_miniapp_task("Создай файл.", envelope)
    assert stopped.value.state.reason is ProductReason.CAPABILITY_UNAVAILABLE
    assert rows(h.control) == []
    assert not h.runtime.drafted and not h.runtime.applied


@pytest.mark.asyncio
async def test_clarification_read_is_bound_current_and_does_not_consume(tmp_path):
    h, _ = harness(tmp_path)
    compiler = SemanticFixtureCompiler(lambda value: _semantic_proposal(value, ambiguous=True))
    h.control._semantic_admission = SemanticAdmissionService(compiler)
    envelope = h.control._gateway.process_update(text_update("Подготовь материал.", 71)).envelope
    with pytest.raises(SemanticClarificationRequired) as issued:
        await h.control.submit_miniapp_task("Подготовь материал.", envelope)
    token = issued.value.token
    count = len(compiler.inputs)
    assert h.control.miniapp_clarification_current(envelope, token)
    assert h.control.miniapp_clarification_current(envelope, token)
    assert not h.control.miniapp_clarification_current(envelope, "a" * 43)
    values = envelope.model_dump(mode="json", exclude={"envelope_revision"})
    values["tenant_id"] = "foreign"
    foreign = type(envelope).model_validate({**values, "envelope_revision": canonical_json_digest(values)})
    assert not h.control.miniapp_clarification_current(foreign, token)
    assert len(compiler.inputs) == count and rows(h.control) == []
    h.control._semantic_clarifications._clock = lambda: datetime.now(UTC) + timedelta(hours=1)
    assert not h.control.miniapp_clarification_current(envelope, token)
