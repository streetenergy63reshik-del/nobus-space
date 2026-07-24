from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from src.application.durable_telegram_state import SQLiteTelegramState
from src.application.network_commands import NetworkCommandRunner
from src.application.network_tools import Quarantine, SafeDownloader
from src.application.owner_workspace import OwnerWorkspace
from src.application.product_effects import (
    DurableProductEffectVault,
    ProductEffectKind,
    ProductEffectService,
    approval_reference,
)


PUBLIC = [(None, None, None, None, ("93.184.216.34", 443))]


def _encode(value):
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()


def _decode(value):
    return json.loads(value)


def _vault(path: Path) -> DurableProductEffectVault:
    return DurableProductEffectVault(
        SQLiteTelegramState(path, encode=_encode, decode=_decode)
    )


def _service(tmp_path: Path, client: httpx.AsyncClient) -> ProductEffectService:
    workspace = tmp_path / "NOBUS SPACE BOT"
    quarantine = workspace / "Загрузки"
    workspace.mkdir()
    quarantine.mkdir()
    git = tmp_path / "git.exe"
    python = tmp_path / "python.exe"
    git.touch()
    python.touch()
    return ProductEffectService(
        vault=_vault(tmp_path / "effects.sqlite3"),
        workspace=OwnerWorkspace(workspace),
        downloader=SafeDownloader(
            client=client, resolver=lambda *args, **kwargs: PUBLIC
        ),
        quarantine=Quarantine(quarantine),
        network_runner=NetworkCommandRunner(
            workspace_root=workspace,
            git_executable=git,
            python_executable=python,
        ),
    )


@pytest.mark.asyncio
async def test_document_effect_survives_reopen_and_requires_exact_owner(
    tmp_path: Path,
) -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500))
    )
    service = _service(tmp_path, client)
    challenge = service.prepare_document(
        "report.html|Отчёт|Первый абзац",
        tenant_id="owner",
        user_id=7,
        chat_id=7,
    )
    reopened = ProductEffectService(
        vault=_vault(tmp_path / "effects.sqlite3"),
        workspace=service._workspace,
        downloader=service._downloader,
        quarantine=service._quarantine,
        network_runner=service._network,
    )
    with pytest.raises(ValueError, match="invalid"):
        await reopened.resolve(
            challenge.token,
            expected_kind=ProductEffectKind.ARTIFACT,
            approve=True,
            tenant_id="owner",
            user_id=8,
            chat_id=7,
            approval_ref=approval_reference(
                actor_identity="telegram:owner",
                query_id="q1",
                effect_token=challenge.token,
            ),
        )
    result = await reopened.resolve(
        challenge.token,
        expected_kind=ProductEffectKind.ARTIFACT,
        approve=True,
        tenant_id="owner",
        user_id=7,
        chat_id=7,
        approval_ref=approval_reference(
            actor_identity="telegram:owner",
            query_id="q1",
            effect_token=challenge.token,
        ),
    )
    assert result.filename == "report.html"
    assert result.content is not None and b"<!doctype html>" in result.content
    assert (service._workspace.root / "report.html").read_bytes() == result.content
    await client.aclose()


@pytest.mark.asyncio
async def test_download_is_read_only_until_l4_then_quarantined(
    tmp_path: Path,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "content-type": "application/pdf",
                "content-disposition": 'attachment; filename="report.pdf"',
            },
            content=b"%PDF-1.4\nsafe",
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = _service(tmp_path, client)
    challenge = await service.prepare_download(
        "https://example.com/report.pdf",
        tenant_id="owner",
        user_id=7,
        chat_id=7,
    )
    target = service._quarantine._root / "report.pdf"
    assert not target.exists()
    result = await service.resolve(
        challenge.token,
        expected_kind=ProductEffectKind.DOWNLOAD,
        approve=True,
        tenant_id="owner",
        user_id=7,
        chat_id=7,
        approval_ref=approval_reference(
            actor_identity="telegram:owner",
            query_id="q2",
            effect_token=challenge.token,
        ),
    )
    assert target.read_bytes() == b"%PDF-1.4\nsafe"
    assert result.filename == "report.pdf"
    await client.aclose()


def test_effect_vault_is_tenant_and_actor_bound(tmp_path: Path) -> None:
    vault = _vault(tmp_path / "effects.sqlite3")
    token = vault.issue(
        kind=ProductEffectKind.ARTIFACT,
        tenant_id="owner",
        user_id=7,
        chat_id=7,
        payload={"safe": True},
    )
    assert vault.read(
        token, tenant_id="other", user_id=7, chat_id=7
    ) is None
    assert vault.read(
        token, tenant_id="owner", user_id=8, chat_id=7
    ) is None
    assert vault.read(
        token, tenant_id="owner", user_id=7, chat_id=7
    ) is not None


@pytest.mark.asyncio
async def test_delivery_receipt_prevents_resend_before_durable_job_ack(
    tmp_path: Path,
) -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500))
    )
    service = _service(tmp_path, client)
    challenge = service.prepare_document(
        "receipt.html|Receipt|Stable delivery",
        tenant_id="owner",
        user_id=7,
        chat_id=7,
    )
    approval = approval_reference(
        actor_identity="telegram:owner",
        query_id="receipt-query",
        effect_token=challenge.token,
    )
    first = await service.resolve(
        challenge.token,
        expected_kind=ProductEffectKind.ARTIFACT,
        approve=True,
        tenant_id="owner",
        user_id=7,
        chat_id=7,
        approval_ref=approval,
    )
    assert first.delivery_required
    assert service.acknowledge_delivery(
        challenge.token,
        tenant_id="owner",
        user_id=7,
        chat_id=7,
    )

    replay = await service.resolve(
        challenge.token,
        expected_kind=ProductEffectKind.ARTIFACT,
        approve=True,
        tenant_id="owner",
        user_id=7,
        chat_id=7,
        approval_ref=approval,
    )
    assert not replay.delivery_required
    assert service.finalize_delivery(
        challenge.token,
        tenant_id="owner",
        user_id=7,
        chat_id=7,
    )
    assert (
        service._vault.read(
            challenge.token,
            tenant_id="owner",
            user_id=7,
            chat_id=7,
        )
        is None
    )
    await client.aclose()
