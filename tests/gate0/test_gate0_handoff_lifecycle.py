from __future__ import annotations

import copy
import datetime as dt
import json
import pathlib
import sys

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
GATE = ROOT / "docs/gates/gate-00-product-contract-baseline"
sys.path.insert(0, str(ROOT / "tests/gate0"))

from generate_gate0_artifacts import handoff_markdown
import normalize_gate0_contracts as normalization


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


def test_blocked_handoff_never_accepts_fresh_genesis() -> None:
    baseline = _load("evidence/baseline-evidence.json")
    raw_runtime = copy.deepcopy(_load("evidence/runtime-inventory.json"))
    raw_databases = copy.deepcopy(_load("evidence/database-inventory.json"))
    dependencies = _load("evidence/dependency-inventory.json")
    handoff = _load("fixtures/contracts/valid/gate-handoff.json")
    now = dt.datetime.now(dt.timezone.utc)

    def timestamp(value: dt.datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")

    raw_runtime["capture_started_at"] = timestamp(
        now - dt.timedelta(seconds=2)
    )
    raw_databases["observed_at"] = timestamp(
        now - dt.timedelta(seconds=1)
    )
    raw_runtime["observed_at"] = timestamp(now)
    raw_runtime["fresh_until"] = timestamp(now + dt.timedelta(minutes=5))

    rendered = handoff_markdown(
        baseline,
        raw_runtime,
        raw_databases,
        dependencies,
        handoff,
        handoff["generated_at"],
        ready=False,
    )

    assert "**Status:** `GATE 0 BLOCKED`" in rendered
    assert "genesis baseline: `NOT_ACCEPTED`" in rendered
    assert "genesis baseline: `VERIFIED`" not in rendered


def test_machine_handoff_materializes_genesis_only_at_ready_seal() -> None:
    projector = getattr(normalization, "genesis_handoff_projection", None)
    assert callable(projector)

    pending = projector("VERIFIED", accepted=False)
    assert pending == {
        "database_migration_status": "GENESIS_PROOF_VERIFIED_ACCEPTANCE_PENDING",
        "target_remaining": [
            "Complete the Gate 0 independent review and READY seal before accepting the verified genesis proof",
            "Gate 2 may start the durable ledger only from a subsequently accepted genesis baseline",
        ],
        "risk": (
            "Current Telegram schema proof is verified; genesis acceptance remains "
            "pending until the Gate 0 READY seal"
        ),
    }
    accepted = projector("VERIFIED", accepted=True)
    assert accepted == {
        "database_migration_status": "GENESIS_BASELINE_VERIFIED",
        "target_remaining": [
            "Gate 2 must start its durable migration ledger at the accepted genesis before any post-genesis migration",
        ],
        "risk": (
            "Historical Telegram legacy migration execution is not proven; only "
            "the accepted current schema is the genesis baseline"
        ),
    }
    with pytest.raises(ValueError, match="verified proof"):
        projector("STALE", accepted=True)


def test_current_raw_database_refs_are_runtime_opaque() -> None:
    inventory = _load("evidence/database-inventory.json")
    assert inventory["databases"]
    assert all(
        item["database_ref"] == f"runtime-db:{item['database_role']}"
        for item in inventory["databases"]
    )
