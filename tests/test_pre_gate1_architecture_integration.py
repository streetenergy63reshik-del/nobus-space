"""Regression contract for the post-Gate-0 PRE-G1 architecture overlay."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
GATE0 = ROOT / "docs/gates/gate-00-product-contract-baseline"
ACCEPTANCE = GATE0 / "GATE-0-ACCEPTANCE.json"
CATALOG = GATE0 / "product/normative-catalog.json"
ADR = ROOT / "docs/adr/0021-post-gate0-agent-roles-and-downstream-integration.md"
EXPECTED_ROLES = {
    "general_orchestrator_worker",
    "google_workspace_specialist",
    "research_analytics_specialist",
    "content_studio_specialist",
    "development_specialist",
    "verification_specialist",
}
EXPECTED_RESULT_COMMIT = "f5086b2a71a9ae22be3c858ff69453287f6925da"
EXPECTED_RESULT_TREE = "2e3248eb295b1627d36f196c26dfc21c6ebd90fd"


def _text(path: Path) -> str:
    assert path.is_file(), f"required PRE-G1 document is missing: {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_overlay_is_accepted_and_binds_the_exact_sealed_snapshot() -> None:
    text = _text(ADR)
    acceptance = _json(ACCEPTANCE)

    assert "**Статус ADR:** ACCEPTED" in text
    assert "post-seal overlay" in text
    assert "GATE-0-ACCEPTANCE.json" in text
    assert "normative-catalog.json" in text
    assert EXPECTED_RESULT_COMMIT in text
    assert EXPECTED_RESULT_TREE in text
    assert acceptance["status"] == "accepted"
    assert acceptance["result_commit"] == EXPECTED_RESULT_COMMIT
    assert acceptance["result_tree"] == EXPECTED_RESULT_TREE
    assert "уточняет только" in text
    assert "остаются byte-identical" in text
    assert "приоритет" in text


def test_closed_role_vocabulary_is_exact_and_overlayed() -> None:
    catalog = _json(CATALOG)
    text = _text(ADR)
    catalog_roles = catalog["agent_roles"]

    assert isinstance(catalog_roles, list)
    assert len(catalog_roles) == len(EXPECTED_ROLES)
    assert set(catalog_roles) == EXPECTED_ROLES

    role_block = re.search(
        r"<!-- closed-agent-roles:start -->(.*?)<!-- closed-agent-roles:end -->",
        text,
        re.DOTALL,
    )
    assert role_block is not None, "ADR 0021 has no machine-checkable role block"
    adr_roles = set(re.findall(r"`([a-z_]+)`", role_block.group(1)))
    assert adr_roles == EXPECTED_ROLES


def test_core_worker_and_effect_authority_stays_closed() -> None:
    text = _text(ADR)

    assert "один Nobus Core" in text
    assert "единственным orchestrator" in text
    assert "один generic effect plane" in text
    assert "второй effect engine запрещён" in text
    assert "provider credentials не передаются specialist" in text
    assert "specialist не выполняет external effects" in text
    assert "peer-to-peer authority запрещена" in text
    assert "verification_specialist" in text
    assert "не может проверять или одобрять собственную работу" in text


def test_windows_and_downstream_gate_boundaries_are_explicit() -> None:
    text = _text(ADR)

    assert "`development_jobs.v1`" in text
    assert "`document_jobs.v1`" in text
    assert "разные Windows service identities" in text
    assert "разные queue namespaces" in text
    assert "разные capability sets" in text
    assert "Document Bridge не исполняет development jobs" in text
    assert "Development Worker не получает document authority" in text
    assert "closed `AnalysisResult`" in text
    assert "unknown fields отклоняются" in text
    assert "verified analytical source" in text
    assert "Gate 7 не перечитывает источники и не пересчитывает факты" in text
    assert "финальная интеграция" in text
    assert "Core/Mini App, Development Worker и Document Bridge" in text
    assert "не является первым server deployment" in text


def test_gate_order_and_current_status_are_unambiguous() -> None:
    gates = _text(ROOT / "docs/gates/README.md")
    current = _text(ROOT / "docs/handoffs/CURRENT-STATUS.md")
    precondition = _text(
        ROOT / "docs/handoffs/PRE-GATE-1-ARCHITECTURE-INTEGRATION.md"
    )
    roadmap = _text(
        ROOT / "docs/14-Действия-владельца-после-Gate-0-SSH-VPS-и-Gate-1-2.md"
    )

    for text in (gates, current):
        assert "PRE-G1" in text and "`ACCEPTED`" in text
        assert "Gate 1" in text and "`READY TO START`" in text
        assert "Gate 2" in text and "`BLOCKED` до accepted Gate 1" in text
        assert "Gate 2A" in text and "`BLOCKED` до accepted Gate 2" in text
    assert "**Статус:** ACCEPTED" in precondition
    assert "ADR 0021" in precondition
    assert "Gate 2A выполняется после accepted Gate 2 и до Gate 3" in ADR.read_text(
        encoding="utf-8"
    )
    assert "PRE-G1 accepted" in roadmap
    assert "Gate 1 READY TO START" in roadmap


def test_navigation_and_journal_point_to_the_overlay() -> None:
    references = (
        ROOT / "README.md",
        ROOT / "docs/README.md",
        ROOT / "docs/04-Журнал-ADR.md",
        ROOT / "docs/gates/README.md",
        ROOT / "docs/handoffs/CURRENT-STATUS.md",
    )
    for path in references:
        text = _text(path)
        assert "0021-post-gate0-agent-roles-and-downstream-integration.md" in text
    journal = _text(ROOT / "docs/04-Журнал-ADR.md")
    assert re.search(r"\| \[0021\].*\| ACCEPTED \| TARGET \|", journal)


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
