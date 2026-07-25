from __future__ import annotations

import base64
import hashlib
import json
from types import SimpleNamespace

import pytest

from src.application.gate5a4 import Gate5A4Runtime, _needs_project_context
from src.application.owner_files import OwnerFileService
from src.workers.codex_cli import CodexCliError, CodexCliResult
from tests.test_contracts import make_contract, make_envelope


class _Worker:
    def __init__(self, answer: dict[str, object]) -> None:
        self.message = json.dumps(
            {"answer": json.dumps(answer, ensure_ascii=False)},
            ensure_ascii=False,
        )
        self.contract = None

    async def execute(self, contract: object) -> CodexCliResult:
        self.contract = contract
        return CodexCliResult(message=self.message)


def _runtime(tmp_path, answer: dict[str, object]) -> tuple[Gate5A4Runtime, _Worker]:
    worker = _Worker(answer)
    runtime = object.__new__(Gate5A4Runtime)
    runtime._worker = worker
    runtime._allowed_path = str(tmp_path)
    runtime._pipeline = SimpleNamespace(root=tmp_path)
    return runtime, worker


@pytest.mark.asyncio
async def test_natural_document_planner_is_tool_free_and_bounded(tmp_path) -> None:
    runtime, worker = _runtime(
        tmp_path,
        {
            "path": "Документы/2026-07-25-отчёт.docx",
            "title": "Итоговый отчёт",
            "body": "Краткий результат.",
        },
    )

    argument = await runtime.plan_document_argument(
        "Подготовь документ Word с кратким итогом.",
        make_envelope(),
    )

    assert argument == (
        "Документы/2026-07-25-отчёт.docx|"
        "Итоговый отчёт|Краткий результат."
    )
    assert worker.contract is not None
    assert worker.contract.permissions == ("model.inference",)
    assert worker.contract.timeout_seconds == 120
    assert "Do not use tools" in worker.contract.instruction


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    (
        "../outside.docx",
        r"C:\outside.docx",
        "Документы/report.exe",
        "Другая папка/report.docx",
    ),
)
async def test_natural_document_planner_rejects_unsafe_paths(
    tmp_path, path: str
) -> None:
    runtime, _ = _runtime(
        tmp_path,
        {"path": path, "title": "Отчёт", "body": "Текст"},
    )

    with pytest.raises(CodexCliError, match="invalid output"):
        await runtime.plan_document_argument("Создай документ.", make_envelope())


def test_compact_context_is_selected_only_for_project_questions() -> None:
    assert _needs_project_context("Что ты знаешь о Nobus Space?")
    assert _needs_project_context("Опиши контекст компании PROстранство")
    assert not _needs_project_context("Объясни idempotency key одним предложением")



from src.application.business_notes import BusinessNotesService
from src.application.product_effects import (
    ProductEffectChallenge,
    ProductEffectKind,
    ProductEffectResult,
)
from tests.test_business_notes import _message, _store
from tests.test_telegram_product import _product, text_update
from src.application.telegram_product import _document_delivery


@pytest.mark.asyncio
async def test_natural_research_routes_to_closed_web_profile(tmp_path) -> None:
    harness = _product(tmp_path)

    await harness.control.handle(
        text_update(
            "Проведи исследование в интернете о новостях маркетплейсов.",
            1,
        )
    )

    assert len(harness.runtime.drafted) == 1
    assert harness.runtime.drafted[0].contract.instruction.startswith(
        "[profile:research.web]\n"
    )


class _NaturalDocumentEffects:
    def __init__(self) -> None:
        self.arguments: list[str] = []
        self.overwrites: list[bool] = []
        self.resolved: list[tuple[ProductEffectKind, bool]] = []

    def prepare_document(self, argument: str, **kwargs: object):
        self.arguments.append(argument)
        self.overwrites.append(bool(kwargs.get("allow_overwrite", False)))
        return ProductEffectChallenge(
            "artifact-token",
            ProductEffectKind.ARTIFACT,
            "",
        )

    async def prepare_download(self, *args: object, **kwargs: object):
        raise AssertionError

    def prepare_network(self, *args: object, **kwargs: object):
        raise AssertionError

    async def resolve(self, *args: object, **kwargs: object):
        self.resolved.append((kwargs["expected_kind"], kwargs["approve"]))
        return ProductEffectResult(
            "Документ создан.",
            "отчёт.docx",
            b"document",
        )

    def acknowledge_delivery(self, *args: object, **kwargs: object) -> bool:
        return True

    def finalize_delivery(self, *args: object, **kwargs: object) -> bool:
        return True


@pytest.mark.asyncio
async def test_natural_document_command_creates_and_sends_artifact(
    tmp_path,
) -> None:
    effects = _NaturalDocumentEffects()
    harness = _product(tmp_path, product_effects=effects)

    async def plan(instruction: str, envelope: object) -> str:
        assert "документ Word" in instruction
        return "Документы/отчёт.docx|Отчёт|Готовый текст"

    harness.runtime.plan_document_argument = plan
    await harness.control.handle(
        text_update("Подготовь документ Word с итогом встречи.", 1)
    )

    assert effects.arguments == [
        "Документы/отчёт.docx|Отчёт|Готовый текст"
    ]
    assert effects.resolved == [(ProductEffectKind.ARTIFACT, True)]
    assert harness.api.documents == [(42, "отчёт.docx", b"document")]
    assert harness.runtime.drafted == []


def test_private_notes_summary_is_tenant_isolated(tmp_path) -> None:
    store = _store(tmp_path)
    store.append(_message("Идея новой услуги.", message_id=1, thread_id=10))
    store.append(
        _message(
            "Нужно позвонить поставщику завтра.",
            message_id=2,
            thread_id=20,
        )
    )
    store.append(
        _message(
            "Чужая задача.",
            message_id=3,
            thread_id=10,
            tenant_id="tenant-b",
        )
    )
    service = BusinessNotesService(store)

    summary = service.summarize_private(
        tenant_id="owner",
        request="Собери резюме Заметок бизнеса.",
    )
    tasks = service.summarize_private(
        tenant_id="owner",
        request="Собери задачи из Заметок бизнеса.",
    )

    assert "Идея новой услуги" in summary
    assert "Нужно позвонить поставщику" in summary
    assert "Чужая задача" not in summary
    assert "Нужно позвонить поставщику" in tasks
    assert "Идея новой услуги" not in tasks


@pytest.mark.asyncio
async def test_natural_file_analysis_supplies_bounded_untrusted_context(
    tmp_path,
) -> None:
    (tmp_path / "brief.md").write_text(
        "Вывод: очередь восстанавливается после перезапуска.",
        encoding="utf-8",
    )
    harness = _product(tmp_path, owner_files=OwnerFileService(tmp_path))

    await harness.control.handle(
        text_update("Проанализируй файл brief.md", 1)
    )

    assert len(harness.runtime.drafted) == 1
    instruction = harness.runtime.drafted[0].contract.instruction
    assert instruction.startswith("Проанализируй файл brief.md")
    assert "[owner_file_context_ref]" in instruction
    assert "[untrusted_owner_file]" not in instruction
    assert "очередь восстанавливается после перезапуска" not in instruction


@pytest.mark.asyncio
async def test_owner_file_context_is_reloaded_after_restart_without_plaintext(
    tmp_path,
) -> None:
    content = "Вывод: очередь восстанавливается после перезапуска."
    raw = content.encode("utf-8")
    (tmp_path / "brief.md").write_bytes(raw)
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    encoded = base64.urlsafe_b64encode(b"brief.md").decode("ascii").rstrip("=")
    contract = make_contract(
        instruction=(
            "Проанализируй файл brief.md\n\n"
            f"[owner_file_context_ref]{digest}:{encoded}"
            "[/owner_file_context_ref]"
        )
    )
    runtime, _ = _runtime(tmp_path, {"answer": "ok"})
    runtime._owner_files = OwnerFileService(tmp_path)

    worker_contract = await runtime._worker_contract(contract)

    assert content not in contract.instruction
    assert content in worker_contract.instruction
    assert "[untrusted_owner_file]" in worker_contract.instruction

    (tmp_path / "brief.md").write_text("changed", encoding="utf-8")
    with pytest.raises(CodexCliError) as captured:
        await runtime._worker_contract(contract)
    assert captured.value.code == "worker_context_unavailable"


@pytest.mark.asyncio
async def test_natural_research_document_keeps_web_profile_and_delivery_metadata(
    tmp_path,
) -> None:
    effects = _NaturalDocumentEffects()
    harness = _product(tmp_path, product_effects=effects)

    async def plan(instruction: str, envelope: object) -> str:
        return (
            "Документы/2026-07-25-обзор.docx|Обзор рынка|"
            "Body is replaced by verified research output"
        )

    harness.runtime.plan_document_argument = plan
    await harness.control.handle(
        text_update(
            "Проведи исследование в интернете о рынке и представь результат "
            "в документе Word.",
            1,
        )
    )

    assert len(harness.runtime.drafted) == 1
    instruction = harness.runtime.drafted[0].contract.instruction
    assert instruction.startswith("[profile:research.web]\n")
    assert "[deliver:document]" in instruction
    assert '"path":"Документы/2026-07-25-обзор.docx"' in instruction
    assert effects.arguments == []


def test_document_delivery_metadata_is_strict() -> None:
    assert _document_delivery(
        '[deliver:document]\n{"path":"Документы/report.docx","title":"Отчёт"}\n'
        '[/deliver:document]\nЗапрос'
    ) == ("Документы/report.docx", "Отчёт")

    with pytest.raises(ValueError, match="document delivery metadata is invalid"):
        _document_delivery(
            '[deliver:document]\n{"path":"../report.docx","title":"Отчёт","x":1}\n'
            '[/deliver:document]\nЗапрос'
        )


@pytest.mark.asyncio
async def test_natural_document_overwrite_requires_exact_path_and_edit_verb(
    tmp_path,
) -> None:
    effects = _NaturalDocumentEffects()
    harness = _product(tmp_path, product_effects=effects)

    async def plan(instruction: str, envelope: object) -> str:
        return "Документы/отчёт.docx|Отчёт|Обновлённый текст"

    harness.runtime.plan_document_argument = plan
    await harness.control.handle(
        text_update(
            "Перезапиши файл Документы/отчёт.docx с заменой оригинала | обнови текст.",
            1,
        )
    )
    await harness.control.handle(
        text_update("Подготовь документ Word с итогами.", 2)
    )

    await harness.control.handle(
        text_update(
            "Измени документ Документы/отчёт.docx, но не перезаписывай его.",
            3,
        )
    )

    assert effects.overwrites == [True, False, False]


@pytest.mark.asyncio
async def test_sensitive_owner_file_is_not_drafted_or_echoed(tmp_path) -> None:
    (tmp_path / "brief.md").write_text(
        "client_secret: must-not-leave-boundary",
        encoding="utf-8",
    )
    harness = _product(tmp_path, owner_files=OwnerFileService(tmp_path))

    await harness.control.handle(
        text_update("Проанализируй файл brief.md", 1)
    )

    assert harness.runtime.drafted == []
    assert "не буду передавать" in harness.api.sent[-1][1]
    assert "must-not-leave-boundary" not in harness.api.sent[-1][1]


@pytest.mark.asyncio
async def test_document_overwrite_rejects_preserve_original_and_copy_language(
    tmp_path,
):
    effects = _NaturalDocumentEffects()
    harness = _product(tmp_path, product_effects=effects)

    async def plan(instruction: str, envelope: object) -> str:
        return "Документы/отчёт.docx|Отчёт|Обновлённый текст"

    harness.runtime.plan_document_argument = plan
    await harness.control.handle(
        text_update(
            "Обнови документ Документы/отчёт.docx, "
            "но сохрани исходный и создай копию",
            4,
        )
    )

    assert effects.overwrites == [False]


@pytest.mark.asyncio
async def test_owner_file_output_guard_rejects_durable_verbatim_copy(
    tmp_path,
) -> None:
    content = " ".join(f"owner-word-{index}" for index in range(80))
    raw = content.encode("utf-8")
    (tmp_path / "brief.md").write_bytes(raw)
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    encoded = base64.urlsafe_b64encode(b"brief.md").decode("ascii").rstrip("=")
    contract = make_contract(
        instruction=(
            "Проанализируй файл brief.md\n\n"
            f"[owner_file_context_ref]{digest}:{encoded}"
            "[/owner_file_context_ref]"
        )
    )
    runtime, _ = _runtime(tmp_path, {"answer": "ok"})
    runtime._owner_files = OwnerFileService(tmp_path)

    await runtime._require_safe_owner_file_answer(
        contract, "Документ содержит тестовый последовательный перечень."
    )
    with pytest.raises(CodexCliError) as captured:
        await runtime._require_safe_owner_file_answer(
            contract, f"Дословно: {content}"
        )
    assert captured.value.code == "worker_protocol_error"


@pytest.mark.asyncio
async def test_document_overwrite_rejects_leave_original_unchanged(tmp_path):
    effects = _NaturalDocumentEffects()
    harness = _product(tmp_path, product_effects=effects)

    async def plan(instruction: str, envelope: object) -> str:
        return "Документы/отчёт.docx|Отчёт|Обновлённый текст"

    harness.runtime.plan_document_argument = plan
    await harness.control.handle(
        text_update(
            "Обнови документ Документы/отчёт.docx, "
            "оставив оригинал без изменений.",
            5,
        )
    )
    assert effects.overwrites == [False]
