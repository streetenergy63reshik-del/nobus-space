from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.application.gate5a4 import (
    Gate5A4Runtime,
    _await_worker_before_deadline,
    _has_evidenced_public_source_url,
    _has_usable_public_source_url,
    _retain_evidenced_public_source_urls,
)
from src.application.telegram_product import _message_chunks
from src.contracts import IngressKind, IngressSource, TrustedIngressEnvelope
from src.contracts.models import canonical_json_digest
from src.core.policy import InMemoryPolicyStore, trusted_conversation_ref
from src.integrations.google_tasks import (
    GoogleTaskAction,
    GoogleTaskActionKind,
    GoogleTasksClient,
)
from src.workers.codex_cli import CodexCliResult
from tests.test_contracts import make_envelope
from tests.test_telegram_product import _product, text_update


def _telegram_envelope(
    external_message_id: str = "update:42:user:7:chat:-100123:thread:77:message:42",
) -> TrustedIngressEnvelope:
    values = {
        "ingress_id": __import__("uuid").uuid4(),
        "tenant_id": "owner",
        "source": IngressSource.TELEGRAM,
        "actor_identity": "telegram:user:opaque",
        "external_message_id": external_message_id,
        "idempotency_key": "owner:telegram:42",
        "received_at": datetime(2026, 7, 26, 9, 15, tzinfo=UTC),
        "kind": IngressKind.TEXT,
        "content_ref": "sha256:" + "2" * 64,
        "auth_context_ref": "sha256:" + "3" * 64,
    }
    revision = canonical_json_digest(
        TrustedIngressEnvelope.model_construct(
            **values,
            envelope_revision="sha256:" + "0" * 64,
        ).model_dump(mode="json", exclude={"envelope_revision"})
    )
    return TrustedIngressEnvelope(**values, envelope_revision=revision)


class _Request:
    def __init__(self, value: object) -> None:
        self._value = value

    def execute(self) -> object:
        return deepcopy(self._value)


class _TaskLists:
    def list(self, *, pageToken: str | None = None, **_: object) -> _Request:
        if pageToken is None:
            return _Request(
                {
                    "items": [{"id": "personal", "title": "Личные"}],
                    "nextPageToken": "lists-2",
                }
            )
        return _Request(
            {"items": [{"id": "space", "title": "PROстранство"}]}
        )


class _Tasks:
    def list(
        self,
        *,
        tasklist: str,
        pageToken: str | None = None,
        **_: object,
    ) -> _Request:
        if tasklist == "personal":
            if pageToken is None:
                return _Request(
                    {
                        "items": [
                            {
                                "id": "p1",
                                "title": "Получить справку",
                                "status": "needsAction",
                                "due": "2026-07-24T00:00:00.000Z",
                            },
                            {
                                "id": "old",
                                "title": "Старая задача",
                                "status": "needsAction",
                                "due": "2026-07-19T00:00:00.000Z",
                            },
                        ],
                        "nextPageToken": "personal-2",
                    }
                )
            return _Request(
                {
                    "items": [
                        {
                            "id": "done",
                            "title": "Уже выполнена",
                            "status": "completed",
                            "due": "2026-07-25T00:00:00.000Z",
                        }
                    ]
                }
            )
        return _Request(
            {
                "items": [
                    {
                        "id": "s1",
                        "title": "Вопросы по Uzum",
                        "status": "needsAction",
                        "due": "2026-07-26T00:00:00.000Z",
                    },
                    {
                        "id": "undated",
                        "title": "Без даты",
                        "status": "needsAction",
                    },
                ]
            }
        )


class _Service:
    def tasklists(self) -> _TaskLists:
        return _TaskLists()

    def tasks(self) -> _Tasks:
        return _Tasks()


class _Worker:
    def __init__(self, answer: dict[str, object]) -> None:
        self._message = json.dumps(
            {"answer": json.dumps(answer, ensure_ascii=False)},
            ensure_ascii=False,
        )
        self.contract = None

    async def execute(self, contract: object) -> CodexCliResult:
        self.contract = contract
        return CodexCliResult(message=self._message)


@pytest.mark.asyncio
async def test_list_all_tasklists_is_paged_grouped_and_period_filtered() -> None:
    client = GoogleTasksClient(
        Path("C:/unused/google-token.json"),
        service_factory=_Service,
    )
    result = await client.execute(
        GoogleTaskAction(
            kind=GoogleTaskActionKind.LIST,
            due_from=date(2026, 7, 20),
            due_to=date(2026, 7, 26),
        ),
        idempotency_key="sha256:" + "a" * 64,
    )

    assert "Личные\n• Получить справку — до 24.07.2026" in result.message
    assert "PROстранство\n• Вопросы по Uzum — до 26.07.2026" in result.message
    assert all(
        value not in result.message
        for value in ("Старая задача", "Уже выполнена", "Без даты")
    )


@pytest.mark.asyncio
async def test_google_tasks_planner_contract_supports_week_across_all_lists(
    tmp_path: Path,
) -> None:
    worker = _Worker(
        {
            "kind": "list",
            "title": None,
            "target": None,
            "list_name": None,
            "notes": None,
            "due": None,
            "due_from": None,
            "due_to": None,
        }
    )
    runtime = object.__new__(Gate5A4Runtime)
    runtime._worker = worker
    runtime._allowed_path = str(tmp_path)
    runtime._pipeline = SimpleNamespace(root=tmp_path)
    runtime._clock = lambda: datetime(
        2026, 7, 25, 12, 0, tzinfo=UTC
    )

    action = await runtime.plan_google_task_action(
        "Покажи все незавершённые задачи Google Tasks за текущую неделю "
        "по всем спискам",
        make_envelope(),
    )

    assert action.due_from == date(2026, 7, 20)
    assert action.due_to == date(2026, 7, 26)
    assert action.list_name is None
    assert worker.contract is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "instruction",
    [
        "Проведи углублённое исследование последних изменений правил Ozon "
        "и Wildberries со ссылками на источники.",
        "Проведи исследование по официальным источникам, новостным порталам "
        "и СМИ бизнес-сообщества РФ.",
        "Обратись в интернет, в бизнес сообщества РФ, всё что связано с "
        "маркетплейсами и собери актуальный новостной фон на сегодня",
        "Проведи анализ в интернете на актуальные даты предстоящих изменений "
        "комиссий озон и вб",
    ],
)
async def test_owner_research_phrases_use_web_profile(
    tmp_path: Path, instruction: str
) -> None:
    harness = _product(tmp_path)
    await harness.control.handle(text_update(instruction, 1))
    assert harness.runtime.drafted[0].contract.instruction.startswith(
        "[profile:research.web]\n"
    )


def test_telegram_contract_keeps_trust_source_and_separate_conversation() -> None:
    runtime = object.__new__(Gate5A4Runtime)
    runtime._allowed_path = "C:/owner"
    runtime._owner_read_root = None
    runtime._nobus_memory = None
    runtime._project_context = None
    envelope = _telegram_envelope()

    contract = runtime._contract("Подготовь краткий ответ", envelope)

    assert contract.source == "telegram"
    assert contract.conversation_ref == trusted_conversation_ref(envelope)
    assert contract.conversation_ref is not None
    InMemoryPolicyStore().register_contract(contract, envelope)


def test_malformed_telegram_conversation_is_rejected_fail_closed() -> None:
    runtime = object.__new__(Gate5A4Runtime)
    runtime._allowed_path = "C:/owner"
    runtime._owner_read_root = None
    runtime._nobus_memory = None
    runtime._project_context = None
    envelope = _telegram_envelope("update:42:message:42")

    with pytest.raises(Exception, match="conversation binding unavailable"):
        runtime._contract("Подготовь краткий ответ", envelope)


def test_policy_rejects_forged_conversation_ref() -> None:
    runtime = object.__new__(Gate5A4Runtime)
    runtime._allowed_path = "C:/owner"
    runtime._owner_read_root = None
    runtime._nobus_memory = None
    runtime._project_context = None
    envelope = _telegram_envelope()
    contract = runtime._contract("Подготовь краткий ответ", envelope)
    forged = contract.model_copy(
        update={"conversation_ref": "telegram:" + "f" * 40}
    )

    with pytest.raises(Exception, match="contract/ingress binding mismatch"):
        InMemoryPolicyStore().register_contract(forged, envelope)


def test_policy_rejects_conversation_ref_for_api_ingress() -> None:
    envelope = make_envelope()
    runtime = object.__new__(Gate5A4Runtime)
    runtime._allowed_path = "C:/owner"
    runtime._owner_read_root = None
    runtime._nobus_memory = None
    runtime._project_context = None
    contract = runtime._contract("Подготовь краткий ответ", envelope)
    forged = contract.model_copy(
        update={"conversation_ref": "telegram:" + "f" * 40}
    )

    with pytest.raises(Exception, match="contract/ingress binding mismatch"):
        InMemoryPolicyStore().register_contract(forged, envelope)


def test_long_effect_result_is_split_within_telegram_limit() -> None:
    value = "Задачи\n" + "\n".join(
        f"• Задача {index}: " + "x" * 90 for index in range(100)
    )
    chunks = _message_chunks(value)
    assert len(chunks) > 1
    assert all(0 < len(chunk) <= 3_400 for chunk in chunks)
    assert chunks[0].startswith("Задачи")


def test_research_source_url_rejects_reserved_and_local_hosts() -> None:
    assert _has_usable_public_source_url("Источник: https://openai.com/news")
    assert not _has_usable_public_source_url("https://x")
    assert not _has_usable_public_source_url("https://example.invalid/report")
    assert not _has_usable_public_source_url("https://127.0.0.1/report")
    assert not _has_usable_public_source_url("https://example.com/report")
    assert not _has_usable_public_source_url("https://foo.local/report")
    assert not _has_usable_public_source_url("https://openai.com:bad/report")
    assert not _has_usable_public_source_url("https://localhost./report")
    assert not _has_usable_public_source_url("https://home.arpa/report")
    assert not _has_usable_public_source_url("https://100.64.0.1/report")
    assert not _has_usable_public_source_url("https://224.0.0.1/report")
    assert not _has_usable_public_source_url("https://%65xample.com/report")
    assert not _has_usable_public_source_url("https://bad..host/report")
    assert not _has_usable_public_source_url("https://-bad.example.edu/report")


def test_research_source_must_be_observed_by_worker() -> None:
    assert _has_evidenced_public_source_url(
        "Source: https://openai.com/news",
        ("https://openai.com/news",),
    )
    assert not _has_evidenced_public_source_url(
        "Source: https://invented-public.example.edu/news",
        ("https://openai.com/news",),
    )
    assert not _has_evidenced_public_source_url(
        "Sources: https://openai.com/news and https://invented.edu/report",
        ("https://openai.com/news",),
    )
    assert not _has_evidenced_public_source_url(
        "Sources: https://openai.com/news and https://127.0.0.1/private",
        ("https://openai.com/news",),
    )


def test_research_answer_drops_only_unevidenced_url_tokens() -> None:
    sanitized = _retain_evidenced_public_source_urls(
        (
            "Verified: https://openai.com/news\n"
            "Invented: https://invented.edu/report\n"
            "Local: https://127.0.0.1/private"
        ),
        ("https://openai.com/news",),
    )
    assert sanitized
    assert "https://openai.com/news" in sanitized
    assert "invented.edu" not in sanitized
    assert "127.0.0.1" not in sanitized
    assert _has_evidenced_public_source_url(
        sanitized,
        ("https://openai.com/news",),
    )


def test_research_answer_removes_non_https_and_protocol_relative_uris() -> None:
    sanitized = _retain_evidenced_public_source_urls(
        (
            "Verified: https://openai.com/news\n"
            "Local: http://localhost:8080/private\n"
            "File: file:///C:/secret\n"
            "Fake: http://example.invalid/report\n"
            "Relative: //localhost/private\n"
            "Nested file: file://https://openai.com/news\n"
            "Nested http: http://https://openai.com/news\n"
            "Nested custom: evil+https://openai.com/news\n"
            "Mail: mailto:owner@example.invalid\n"
            "Data: data:text/plain,secret\n"
            "Script: javascript:alert(1)"
        ),
        ("https://openai.com/news",),
    )
    assert sanitized
    assert "https://openai.com/news" in sanitized
    assert "http://" not in sanitized
    assert "file://" not in sanitized
    assert "//localhost" not in sanitized
    assert "file://" not in sanitized
    assert "http://https://" not in sanitized
    assert "evil+https://" not in sanitized
    assert "mailto:" not in sanitized
    assert "data:" not in sanitized
    assert "javascript:" not in sanitized
    assert _has_evidenced_public_source_url(
        sanitized,
        ("https://openai.com/news",),
    )
    assert not _has_evidenced_public_source_url(
        "Verified: https://openai.com/news and file:///C:/secret",
        ("https://openai.com/news",),
    )


def test_research_answer_appends_opened_evidence_after_filtering() -> None:
    sanitized = _retain_evidenced_public_source_urls(
        (
            "Substantive verified research result with enough useful text. "
            "Unsupported: https://invented.edu/report"
        ),
        ("https://openai.com/news",),
    )
    assert sanitized
    assert "invented.edu" not in sanitized
    assert "https://openai.com/news" in sanitized
    assert _has_evidenced_public_source_url(
        sanitized,
        ("https://openai.com/news",),
    )


def test_research_answer_without_evidenced_url_is_rejected() -> None:
    assert (
        _retain_evidenced_public_source_urls(
            "Invented: https://invented.edu/report",
            ("https://openai.com/news",),
        )
        == ""
    )


@pytest.mark.asyncio
async def test_research_repair_shares_one_absolute_deadline() -> None:
    async def first():
        await asyncio.sleep(0.15)
        return CodexCliResult(message="first")

    async def repair():
        await asyncio.sleep(0.60)
        return CodexCliResult(message="repair")

    loop = asyncio.get_running_loop()
    deadline = loop.time() + 0.50
    assert (await _await_worker_before_deadline(first, deadline)).message == "first"
    started = loop.time()
    with pytest.raises(Exception, match="timed out"):
        await _await_worker_before_deadline(repair, deadline)
    assert loop.time() - started < 0.45
