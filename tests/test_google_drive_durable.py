from __future__ import annotations

import httpx
import pytest

from src.application.product_effects import (
    ProductEffectKind,
    ProductEffectService,
    approval_reference,
)
from src.integrations import (
    GoogleDriveAction,
    GoogleDriveActionKind,
    GoogleDriveResult,
)
from tests.test_product_effects import _service, _vault


class _Drive:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, action: GoogleDriveAction) -> GoogleDriveResult:
        self.calls += 1
        return GoogleDriveResult(
            message="Файл получен.",
            filename="Отчёт.pdf",
            content=b"%PDF-durable",
        )


@pytest.mark.asyncio
async def test_drive_content_survives_delivery_crash_and_reopen(tmp_path) -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500))
    )
    service = _service(tmp_path, client)
    drive = _Drive()
    service._google_drive = drive
    challenge = service.prepare_google_drive(
        GoogleDriveAction(
            kind=GoogleDriveActionKind.DOWNLOAD,
            query="Отчёт.pdf",
        ),
        tenant_id="owner",
        user_id=7,
        chat_id=7,
        idempotency_key="sha256:" + "d" * 64,
    )
    approval = approval_reference(
        actor_identity="telegram:owner",
        query_id="message:1",
        effect_token=challenge.token,
    )

    first = await service.resolve(
        challenge.token,
        expected_kind=ProductEffectKind.GOOGLE_DRIVE,
        approve=True,
        tenant_id="owner",
        user_id=7,
        chat_id=7,
        approval_ref=approval,
    )
    reopened = ProductEffectService(
        vault=_vault(tmp_path / "effects.sqlite3"),
        workspace=service._workspace,
        downloader=service._downloader,
        quarantine=service._quarantine,
        network_runner=service._network,
    )
    replay = await reopened.resolve(
        challenge.token,
        expected_kind=ProductEffectKind.GOOGLE_DRIVE,
        approve=True,
        tenant_id="owner",
        user_id=7,
        chat_id=7,
        approval_ref=approval,
    )

    assert drive.calls == 1
    assert first == replay
    assert replay.filename == "Отчёт.pdf"
    assert replay.content == b"%PDF-durable"
    await client.aclose()
