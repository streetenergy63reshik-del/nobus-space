from __future__ import annotations

import json
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
GATE = ROOT / "docs/gates/gate-00-product-contract-baseline"
sys.path.insert(0, str(ROOT / "tests/gate0"))

from generate_gate0_artifacts import handoff_markdown


def _load(relative: str) -> dict[str, object]:
    return json.loads((GATE / relative).read_text(encoding="utf-8"))


def test_current_handoff_never_overstates_saved_evidence() -> None:
    baseline = _load("evidence/baseline-evidence.json")
    raw_runtime = _load("evidence/runtime-inventory.json")
    raw_databases = _load("evidence/database-inventory.json")
    dependencies = _load("evidence/dependency-inventory.json")
    handoff = _load("fixtures/contracts/valid/gate-handoff.json")

    rendered = handoff_markdown(
        baseline,
        raw_runtime,
        raw_databases,
        dependencies,
        handoff,
        handoff["generated_at"],
        ready=False,
    )
    assert "All four authoritative SQLite schemas" not in rendered
    assert "genesis baseline: `NOT_ACCEPTED`" in rendered
    binding_status = dependencies["verification_toolchain"]["candidate_binding"][
        "status"
    ]
    if binding_status == "verified":
        assert "Exact-tree verifier/release evidence: `VERIFIED`" in rendered
        assert "Exact-tree verifier/release evidence: `RERUN_REQUIRED`" not in rendered
    else:
        assert binding_status in {"rerun_required", "stale"}
        assert (
            "Exact-tree verifier/release evidence: `RERUN_REQUIRED`" in rendered
        )
        assert "Exact-tree verifier/release evidence: `VERIFIED`" not in rendered
    assert "candidate-worktree-db:" not in rendered
    old_collector_roles = [
        database["database_role"]
        for database in raw_databases["databases"]
        if database["snapshot"].get("consistent") is False
        and database["snapshot"].get("data_version_stable") is True
        and database["snapshot"].get("file_markers_stable") is False
    ]
    if old_collector_roles:
        assert "Preserved old-collector inconsistency roles" in rendered
        assert "does not retroactively verify the stale capture" in rendered
    else:
        assert "Preserved old-collector inconsistency roles" not in rendered
        assert "does not retroactively verify the stale capture" not in rendered


def test_current_raw_database_refs_are_runtime_opaque() -> None:
    inventory = _load("evidence/database-inventory.json")
    assert inventory["databases"]
    assert all(
        item["database_ref"] == f"runtime-db:{item['database_role']}"
        for item in inventory["databases"]
    )
