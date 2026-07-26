from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.application.gate5a4 import (
    Gate5A4Runtime,
    _simple_google_drive_link_action,
)
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


@pytest.mark.asyncio
async def test_drive_link_request_is_parsed_without_worker(tmp_path) -> None:
    worker = _Worker("unused")
    runtime = object.__new__(Gate5A4Runtime)
    runtime._worker = worker
    runtime._allowed_path = str(tmp_path)
    runtime._pipeline = SimpleNamespace(root=tmp_path)

    result = await runtime.plan_google_drive_action(
        "Пришли ссылку на гугл таблицу с гугл диска - "
        "Юнит экономика Ozon по бренду HomeEdit "
        "в папке Пространство-Клиенты",
        make_envelope(),
    )

    assert result == GoogleDriveAction(
        kind=GoogleDriveActionKind.LINK,
        query="Юнит экономика Ozon по бренду HomeEdit",
        folder="Пространство-Клиенты",
    )
    assert worker.contract is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "instruction",
    (
        "Пришли ссылку с Google Drive на файл Юнит экономика HomeEdit",
        "Пришли ссылку на гугл таблицу Юнит экономика HomeEdit",
    ),
)
async def test_drive_link_request_without_dash_extracts_only_title(
    tmp_path, instruction: str
) -> None:
    worker = _Worker("unused")
    runtime = object.__new__(Gate5A4Runtime)
    runtime._worker = worker
    runtime._allowed_path = str(tmp_path)
    runtime._pipeline = SimpleNamespace(root=tmp_path)

    result = await runtime.plan_google_drive_action(instruction, make_envelope())

    assert result == GoogleDriveAction(
        kind=GoogleDriveActionKind.LINK,
        query="Юнит экономика HomeEdit",
    )
    assert worker.contract is None


@pytest.mark.asyncio
async def test_hyphenated_google_sheet_request_routes_to_drive(tmp_path) -> None:
    effects = _Effects()
    harness = _product(
        tmp_path,
        product_effects=effects,
        google_drive_planner=_Planner(
            GoogleDriveAction(
                kind=GoogleDriveActionKind.DOWNLOAD,
                query="Юнит экономика Ozon",
            )
        ),
        google_drive_service=_Drive(),
    )

    await harness.control.handle(
        text_update(
            "Пришли ссылку на гугл-таблицу с юнит-экономикой Ozon "
            "из папки PROстранство — Клиенты",
            1,
        )
    )

    assert effects.resolved == [(ProductEffectKind.GOOGLE_DRIVE, True)]
    assert harness.runtime.drafted == []


@pytest.mark.parametrize(
    "instruction",
    (
        "Find link to Google Drive API documentation",
        "Send link from Google Drive to file Annual Report",
        "Пришли ссылку на документацию Google Drive API",
        "Пришли ссылку на статью о безопасности Google Drive",
    ),
)
def test_drive_fast_path_ignores_non_owner_english_docs_prompts(
    instruction: str,
) -> None:
    assert _simple_google_drive_link_action(instruction) is None