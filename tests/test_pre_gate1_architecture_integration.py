"""Regression contract for the forward-only ADR 0022 architecture overlay."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
GATE0 = ROOT / "docs/gates/gate-00-product-contract-baseline"
ACCEPTANCE = GATE0 / "GATE-0-ACCEPTANCE.json"
CATALOG = GATE0 / "product/normative-catalog.json"
ADR = (
    ROOT
    / "docs/adr/0022-thin-miniapp-orchestrator-mvp1-and-delivery-workflow.md"
)
EXPECTED_RESULT_COMMIT = "f5086b2a71a9ae22be3c858ff69453287f6925da"
EXPECTED_RESULT_TREE = "2e3248eb295b1627d36f196c26dfc21c6ebd90fd"
ADR_FILENAME = "0022-thin-miniapp-orchestrator-mvp1-and-delivery-workflow.md"


def _text(path: Path) -> str:
    assert path.is_file(), (
        f"required ADR 0022 projection is missing: {path.relative_to(ROOT)}"
    )
    return path.read_text(encoding="utf-8")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _marked_block(text: str, name: str) -> str:
    match = re.search(
        rf"<!-- {re.escape(name)}:start -->(.*?)<!-- {re.escape(name)}:end -->",
        text,
        re.DOTALL,
    )
    assert match is not None, f"ADR 0022 has no machine-checkable {name} block"
    return match.group(1)


def _assert_ordered(text: str, tokens: tuple[str, ...]) -> None:
    positions = [text.index(token) for token in tokens]
    assert positions == sorted(positions), f"tokens are not ordered: {tokens}"


def test_adr0022_is_accepted_forward_only_and_preserves_gate0_binding() -> None:
    text = _text(ADR)
    acceptance = _json(ACCEPTANCE)

    assert "**Статус ADR:** ACCEPTED" in text
    assert "forward-only" in text
    assert "GATE-0-ACCEPTANCE.json" in text
    assert "normative-catalog.json" in text
    assert EXPECTED_RESULT_COMMIT in text
    assert EXPECTED_RESULT_TREE in text
    assert acceptance["status"] == "accepted"
    assert acceptance["result_commit"] == EXPECTED_RESULT_COMMIT
    assert acceptance["result_tree"] == EXPECTED_RESULT_TREE
    assert "20 `required_sources`" in text
    assert "byte-identical" in text


def test_mvp1_vertical_path_is_complete_and_ordered() -> None:
    block = _marked_block(_text(ADR), "mvp1-vertical-path")
    _assert_ordered(
        block,
        (
            "Telegram Mini App",
            "owner authentication / Telegram initData",
            "existing Nobus Core",
            "local Codex/runtime",
            "authoritative state",
            "Telegram/Mini App status/result/artifact",
        ),
    )


def test_thin_topology_keeps_one_authority_and_freezes_full_gate2a() -> None:
    text = _text(ADR)

    assert (
        "Telegram Mini App и Telegram-оркестратор — **REQUIRED in MVP-1**"
        in text
    )
    assert (
        "one Core / one queue / one authoritative state / one effect authority"
        in text
    )
    assert "Mini App Web Boundary" in text
    assert (
        "не имеет собственной БД, очереди, policy engine, effect engine" in text
    )
    assert (
        "Полный распределённый Gate 2A имеет статус "
        "**FROZEN / NOT CURRENT**" in text
    )
    assert "owner-bound" in text
    assert "initDataUnsafe" in text
    assert "не выполняет задачу отдельно" in text
    assert "Только Core проверяет signature" in text
    assert "Только Core выпускает и валидирует" in text
    assert "Boundary не кэширует raw `initData`" in text
    assert "Boundary не является очередью и не делает blind retry" in text
    assert "readback/reconciliation по тому же request id" in text


def test_supersession_is_partial_and_runtime_invariants_remain_authoritative() -> None:
    text = _text(ADR)

    for source in (
        "06-Регламент-качества-L1-L4.md",
        "07-Правила-внешней-записи.md",
        "docs 12/13",
        "ADR 0017",
        "ADR 0018",
        "ADR 0019",
        "ADR 0020",
        "ADR 0021",
        "full Gate 2A",
    ):
        assert source in text
    assert "product/runtime approval semantics" in text
    assert (
        "Security, tenant isolation, effect authority, idempotency, "
        "evidence binding" in text
    )
    assert "forward verification mapping" in text
    assert "superseded" in text


def test_delivery_workflow_and_runtime_policy_are_separate() -> None:
    text = _text(ADR)
    block = _marked_block(text, "delivery-workflow")

    _assert_ordered(
        block,
        (
            "TASK",
            "WIP_ITERATION",
            "CHECKPOINT",
            "GATE_CANDIDATE",
            "MERGE",
            "RELEASE_PRODUCTION",
        ),
    )
    assert (
        "Эти роли — роли процесса Codex, а не новые runtime `AgentRole` "
        "Nobus Core" in text
    )
    assert (
        "Локальные docs/code/tests/commit не требуют formal quality-L4" in text
    )
    assert "ApprovalRequest/ApprovalDecision" in text
    assert "один независимый L2" in text
    assert "один adversarial L3" in text


def test_active_projections_and_authority_point_to_adr0022() -> None:
    projections = (
        ROOT / "README.md",
        ROOT / "docs/README.md",
        ROOT / "docs/01-Единый-документ-проекта.md",
        ROOT / "docs/03-Архитектурный-обзор.md",
        ROOT / "docs/14-Действия-владельца-после-Gate-0-SSH-VPS-и-Gate-1-2.md",
        ROOT / "docs/gates/README.md",
        ROOT / "docs/handoffs/CURRENT-STATUS.md",
    )
    for path in projections:
        text = _text(path)
        assert ADR_FILENAME in text, path
        assert "Telegram Mini App" in text, path
        assert "MVP-1" in text, path
        assert "FROZEN / NOT CURRENT" in text, path

    journal = _text(ROOT / "docs/04-Журнал-ADR.md")
    assert re.search(r"\| \[0022\].*\| ACCEPTED \|", journal)
    assert "## Scoped supersession by ADR 0022" in journal
    for source in (
        "docs 12/13",
        "ADR 0017",
        "ADR 0018",
        "ADR 0019",
        "ADR 0020",
        "ADR 0021",
        "full Gate 2A",
    ):
        assert source in journal
    assert "**FROZEN / NOT CURRENT** topology" in journal

    runbook = _text(ROOT / "docs/08-Runbook-эксплуатации.md")
    assert "L4 на конкретный production deployment" not in runbook
    assert (
        "Получить action-bound L4 с TTL на конкретную среду"
        not in runbook
    )
    assert "Это не formal quality-L4 самого" in runbook

    authority_docs = (
        _text(ADR),
        _text(ROOT / "docs/README.md"),
        _text(ROOT / "docs/handoffs/CURRENT-STATUS.md"),
    )
    for text in authority_docs:
        assert "Git-репозиторий" in text
        assert "GitHub `main`" in text
        assert "Nobus Memory" in text


def test_gate0_catalog_required_sources_remain_byte_identical() -> None:
    catalog = _json(CATALOG)
    required_sources = catalog["required_sources"]

    assert isinstance(required_sources, list)
    assert len(required_sources) == 20
    mismatches: list[str] = []
    for entry in required_sources:
        assert isinstance(entry, dict)
        relative = entry["path"]
        expected = entry["sha256"]
        assert isinstance(relative, str)
        assert isinstance(expected, str) and expected.startswith("sha256:")
        source = ROOT / Path(relative)
        actual = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
        if actual != expected:
            mismatches.append(f"{relative}: expected {expected}, got {actual}")

    assert not mismatches, "Gate 0 required source drift:\n" + "\n".join(mismatches)
