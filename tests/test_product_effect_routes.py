from __future__ import annotations

import json

import httpx
import pytest

from src.application.durable_telegram_state import SQLiteTelegramState
from src.application.network_commands import NetworkCommandRunner
from src.application.network_tools import Quarantine, SafeDownloader
from src.application.owner_workspace import OwnerWorkspace
from src.application.product_effects import (
    DurableProductEffectVault,
    ProductEffectService,
)
from tests.test_telegram_product import _product, callback_update, text_update


PUBLIC = [(None, None, None, None, ("93.184.216.34", 443))]


@pytest.mark.asyncio
async def test_document_route_requires_button_then_sends_created_file(
    tmp_path,
) -> None:
    harness = _product(tmp_path)
    root = tmp_path / "NOBUS SPACE BOT"
    quarantine = root / "Загрузки"
    root.mkdir()
    quarantine.mkdir()
    git = tmp_path / "git.exe"
    python = tmp_path / "python.exe"
    git.touch()
    python.touch()
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500))
    )
    state = SQLiteTelegramState(
        tmp_path / "effects.sqlite3",
        encode=lambda value: json.dumps(value, sort_keys=True).encode(),
        decode=lambda value: json.loads(value),
    )
    harness.control._product_effects = ProductEffectService(
        vault=DurableProductEffectVault(state),
        workspace=OwnerWorkspace(root),
        downloader=SafeDownloader(
            client=client, resolver=lambda *args, **kwargs: PUBLIC
        ),
        quarantine=Quarantine(quarantine),
        network_runner=NetworkCommandRunner(
            workspace_root=root,
            git_executable=git,
            python_executable=python,
        ),
    )

    await harness.control.handle(
        text_update("/document report.html|Отчёт|Готово", 1)
    )
    assert not (root / "report.html").exists()
    buttons = harness.api.sent[-1][2]
    assert [label for label, _ in buttons] == [
        "✅ Подтверждаю",
        "❌ Отмена",
    ]

    await harness.control.handle(callback_update(buttons[0][1], 2))

    assert (root / "report.html").is_file()
    assert harness.api.documents[-1][1] == "report.html"
    assert harness.api.deleted[-1] == (harness.api.sent[0][0], 102)
    await client.aclose()


@pytest.mark.asyncio
async def test_cancelled_document_route_writes_nothing(tmp_path) -> None:
    harness = _product(tmp_path)

    class Effects:
        def prepare_document(self, *args, **kwargs):
            from src.application.product_effects import (
                ProductEffectChallenge,
                ProductEffectKind,
            )

            return ProductEffectChallenge(
                "effect-token", ProductEffectKind.ARTIFACT, "Создать?"
            )

        async def prepare_download(self, *args, **kwargs):
            raise AssertionError

        def prepare_network(self, *args, **kwargs):
            raise AssertionError

        async def resolve(self, *args, **kwargs):
            from src.application.product_effects import ProductEffectResult

            assert not kwargs["approve"]
            return ProductEffectResult("Действие отменено.")

        def acknowledge_delivery(self, *args, **kwargs):
            return True

        def finalize_delivery(self, *args, **kwargs):
            return True

    harness.control._product_effects = Effects()
    await harness.control.handle(
        text_update("/document report.html|Отчёт|Готово", 1)
    )
    cancel = harness.api.sent[-1][2][1][1]
    await harness.control.handle(callback_update(cancel, 2))

    assert harness.api.sent[-1][1] == "Действие отменено."
    assert harness.api.documents == []
