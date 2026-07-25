from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.application.gate5a4 import Gate5A4Runtime
from src.application.product_effects import (
    ProductEffectChallenge,
    ProductEffectKind,
    ProductEffectResult,
)
from src.integrations import (
    GoogleDriveAction,
    GoogleDriveActionKind,
    GoogleDriveResult,
)
from src.workers.codex_cli import CodexCliResult
from tests.test_contracts import make_envelope
from tests.test_telegram_product import (
    FakeCalendarDeleteEffects,
    USER_ID,
    _product,
    text_update,
)


class _Planner:
    def __init__(self, action: GoogleDriveAction) -> None:
        self.action = action

    async def plan_google_drive_action(
        self, instruction: str, envelope: object
    ) -> GoogleDriveAction:
        return self.action


class _Drive:
    async def execute(self, action: GoogleDriveAction) -> GoogleDriveResult:
        return GoogleDriveResult(
            message="Файл получен.",
            filename="Отчёт.pdf",
            content=b"%PDF",
        )


class _Effects(FakeCalendarDeleteEffects):
    def prepare_google_drive(
        self, action: GoogleDriveAction, **kwargs: object
    ) -> ProductEffectChallenge:
        assert action.kind is GoogleDriveActionKind.DOWNLOAD
        return ProductEffectChallenge(
            "drive-token",
            ProductEffectKind.GOOGLE_DRIVE,
            "",
        )

    async def resolve(self, *args, **kwargs) -> ProductEffectResult:
        self.resolved.append((kwargs["expected_kind"], kwargs["approve"]))
        return ProductEffectResult(
            "Файл получен.",
            "Отчёт.pdf",
            b"%PDF",
        )


@pytest.mark.asyncio
async def test_drive_file_is_sent_without_confirmation(tmp_path) -> None:
    effects = _Effects()
    harness = _product(
        tmp_path,
        product_effects=effects,
        google_drive_planner=_Planner(
            GoogleDriveAction(
                kind=GoogleDriveActionKind.DOWNLOAD,
                query="Отчёт.pdf",
            )
        ),
        google_drive_service=_Drive(),
    )

    await harness.control.handle(
        text_update("Пришли файл Отчёт.pdf из Google Drive", 1)
    )

    assert effects.resolved == [(ProductEffectKind.GOOGLE_DRIVE, True)]
    assert harness.api.documents == [(USER_ID, "Отчёт.pdf", b"%PDF")]
    assert harness.runtime.drafted == []


class _Worker:
    def __init__(self, message: str) -> None:
        self.message = message
        self.contract = None

    async def execute(self, contract: object) -> CodexCliResult:
        self.contract = contract
        return CodexCliResult(message=self.message)


@pytest.mark.asyncio
async def test_drive_planner_is_tool_free(tmp_path) -> None:
    action = json.dumps(
        {"kind": "download", "query": "Отчёт.pdf"},
        ensure_ascii=False,
    )
    worker = _Worker(json.dumps({"answer": action}, ensure_ascii=False))
    runtime = object.__new__(Gate5A4Runtime)
    runtime._worker = worker
    runtime._allowed_path = str(tmp_path)
    runtime._pipeline = SimpleNamespace(root=tmp_path)

    result = await runtime.plan_google_drive_action(
        "Пришли файл из Google Drive", make_envelope()
    )

    assert result.kind is GoogleDriveActionKind.DOWNLOAD
    assert worker.contract is not None
    assert worker.contract.permissions == ("model.inference",)
    assert "Do not use tools" in worker.contract.instruction
