from __future__ import annotations

from uuid import uuid4

import pytest

from src.application.durable_product import (
    DurableProductTelegramControlPlane,
)
from src.application.durable_runtime import PreparedTask
from src.application.durable_telegram_state import DurableJob
from src.application.telegram_actions import TelegramAction
from src.application.telegram_product import _QueuedDraft, _QueuedEffect
from src.core.policy import task_contract_digest
from src.transport.telegram import VoiceMessage
from tests.test_telegram_product import _product, voice_update


@pytest.mark.asyncio
async def test_voice_origin_effect_roundtrips_through_durable_restore(
    tmp_path,
) -> None:
    source = _product(tmp_path)
    ingress = source.control._gateway.process_update(voice_update(1))
    assert isinstance(ingress.payload, VoiceMessage)
    assert ingress.envelope is not None
    queued: list[dict[str, object]] = []

    class State:
        def enqueue(self, **values: object) -> None:
            queued.append(values)

    control = object.__new__(DurableProductTelegramControlPlane)
    control._closing = False
    control._telegram_state = State()
    control._execution_workers = ()

    async def start() -> None:
        return None

    control.start = start
    control._wake = lambda: None

    assert await control._submit_effect(
        ingress.payload,
        ingress.envelope,
        TelegramAction.RUN_GOOGLE_TASK,
        "voice-effect-token",
    )
    values = queued[0]
    durable = DurableJob(
        uuid4(),
        str(values["kind"]),
        str(values["tenant_id"]),
        values["task_id"],  # type: ignore[arg-type]
        str(values["binding_digest"]),
        values["payload"],  # type: ignore[arg-type]
        1,
    )

    restored = await control._restore(durable)

    assert isinstance(restored, _QueuedEffect)
    assert isinstance(restored.callback, VoiceMessage)
    assert restored.callback.metadata.file_unique_id == "voice-unique"
@pytest.mark.asyncio
async def test_voice_origin_draft_roundtrips_through_durable_restore(
    tmp_path,
) -> None:
    source = _product(tmp_path)
    ingress = source.control._gateway.process_update(voice_update(1))
    assert isinstance(ingress.payload, VoiceMessage)
    assert ingress.envelope is not None
    prepared = await source.runtime.prepare_instruction(
        "voice task", ingress.envelope
    )
    queued: list[dict[str, object]] = []

    class State:
        def enqueue(self, **values: object) -> None:
            queued.append(values)

        def save_progress(self, **values: object) -> None:
            return None

    control = object.__new__(DurableProductTelegramControlPlane)
    control._closing = False
    control._telegram_state = State()
    control._execution_workers = ()
    control._api = source.api

    async def start() -> None:
        return None

    control.start = start
    control._wake = lambda: None

    assert await control._submit_draft(
        prepared, ingress.payload, ingress.envelope
    )
    values = queued[0]
    assert values["kind"] == "draft"
    assert values["payload"]["message_type"] == "voice"
    durable = DurableJob(
        uuid4(),
        "draft",
        str(values["tenant_id"]),
        prepared.contract.task_id,
        task_contract_digest(prepared.contract),
        values["payload"],
        1,
    )
    control._product_runtime = source.runtime

    restored = await control._restore(durable)

    assert isinstance(restored, _QueuedDraft)
    assert isinstance(restored.message, VoiceMessage)
    assert PreparedTask.validate(restored.prepared) == prepared
