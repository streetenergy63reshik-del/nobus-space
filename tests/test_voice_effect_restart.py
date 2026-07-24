from __future__ import annotations

from uuid import uuid4

import pytest

from src.application.durable_product import (
    DurableProductTelegramControlPlane,
)
from src.application.durable_telegram_state import DurableJob
from src.application.telegram_actions import TelegramAction
from src.application.telegram_product import _QueuedEffect
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
