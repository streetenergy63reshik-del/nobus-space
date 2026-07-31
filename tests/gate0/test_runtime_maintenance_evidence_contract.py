from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
GATE = ROOT / "docs/gates/gate-00-product-contract-baseline"
sys.path.insert(0, str(ROOT / "tests/gate0"))

from collect_gate0_snapshot import collect_repo
from generate_gate0_artifacts import decision_register, handoff_markdown


def load(relative: str) -> dict[str, object]:
    return json.loads((GATE / relative).read_text(encoding="utf-8"))


def test_handoff_records_legacy_scheduler_supervision_limit() -> None:
    rendered = handoff_markdown(
        load("evidence/baseline-evidence.json"),
        load("evidence/runtime-inventory.json"),
        load("evidence/database-inventory.json"),
        load("evidence/dependency-inventory.json"),
        load("fixtures/contracts/valid/gate-handoff.json"),
        "2026-07-30T00:00:00Z",
        ready=False,
    )

    assert "Legacy Scheduler stop semantics can leave detached runner processes" in rendered
    assert "WinSW" in rendered
    assert "current launcher remains unchanged" in rendered
    assert "owner-authorized exact-runner maintenance" in rendered
    assert "canonical candidate worktree" in rendered
    assert "telegram-live isolation remains TARGET" in rendered
    assert "reject-before-read" in rendered
    assert "reparse" in rendered
    assert "exact whole launcher" in rendered
    assert "single in-process start-verified" in rendered
    assert "all eight expected digests" in rendered
    assert "core/live/core/core/live/start" in rendered
    assert "final live read" in rendered
    assert "atomic validated file handles" in rendered
    assert "no runtime mutation" not in rendered


def test_decision_register_routes_supervision_fix_to_runtime_gate() -> None:
    decisions = decision_register()["decisions"]
    matching = [item for item in decisions if item["id"] == "G0-D009"]
    assert len(matching) == 1
    assert "WinSW" in matching[0]["decision"]
    assert "current launcher remains unchanged" in matching[0]["decision"]
    assert "canonical candidate worktree" in matching[0]["decision"]
    assert "telegram-live isolation remains TARGET" in matching[0]["decision"]


def test_materialized_decision_register_matches_generator() -> None:
    assert load("decisions/decision-register.json") == decision_register()


def test_decision_register_freezes_safe_topology_and_exact_start_authority() -> None:
    decisions = {
        item["id"]: item["decision"]
        for item in decision_register()["decisions"]
    }
    assert "G0-D010" in decisions
    assert "reject-before-read" in decisions["G0-D010"]
    assert "reparse" in decisions["G0-D010"]
    assert "credential" in decisions["G0-D010"]
    assert "database" in decisions["G0-D010"]
    assert "atomic validated file handles" in decisions["G0-D010"]
    assert "G0-D011" in decisions
    assert "exact whole launcher" in decisions["G0-D011"]
    assert "exact Scheduler definition" in decisions["G0-D011"]
    assert "all eight expected digests" in decisions["G0-D011"]
    assert "core/live/core/core/live/start" in decisions["G0-D011"]
    assert "final live read" in decisions["G0-D011"]
    assert "single in-process start-verified" in decisions["G0-D011"]
    assert "opaque digests" in decisions["G0-D011"]
    assert "same resolved Windows SID" in decisions["G0-D011"]
    assert "closed eight-token action contract" in decisions["G0-D011"]
    assert "single-command AST" in decisions["G0-D011"]
    assert "single matching outer quote pair" in decisions["G0-D011"]
    assert "20-field action bitmap" in decisions["G0-D011"]
    assert "raw Scheduler values are never persisted" in decisions["G0-D011"]
    assert "G0-D012" in decisions
    assert "two stable repair observations" in decisions["G0-D012"]
    assert "only Action.Arguments" in decisions["G0-D012"]
    assert "one Set-ScheduledTask" in decisions["G0-D012"]
    assert "non-argument definition digest" in decisions["G0-D012"]
    assert "without retry" in decisions["G0-D012"]
    assert "canonical shifted -File target" in decisions["G0-D012"]
    assert "installer-equivalent empty Action.Id" in decisions["G0-D012"]
    assert "third final coherent freshness observation" in decisions["G0-D012"]
    assert "exclusive sanctioned-writer mutex" in decisions["G0-D012"]
    assert "no OS-level compare-and-swap" in decisions["G0-D012"]
    assert "G0-D013" in decisions
    assert "exact immutable input_entries" in decisions["G0-D013"]
    assert "scanned_file_count" in decisions["G0-D013"]
    assert "self-referential receipt files" in decisions["G0-D013"]
    assert "receipt_entries" in decisions["G0-D013"]
    assert "frozen_tree_digest" in decisions["G0-D013"]
    assert "post-bind targeted and full" in decisions["G0-D013"]


def test_repo_snapshot_records_canonical_as_current_runtime_release() -> None:
    live = ROOT.parent / "worktrees/telegram-live"
    snapshot = collect_repo(ROOT, live)

    assert snapshot["runtime_release"]["head_commit"] == (
        snapshot["repository"]["head_commit"]
    )
    assert snapshot["runtime_release"]["branch"] == snapshot["repository"]["branch"]
    assert snapshot["runtime_release"]["dirty_entries"] == (
        snapshot["repository"]["dirty_entries"]
    )
    assert snapshot["runtime_release"]["repo_is_descendant_of_runtime_release"]
    assert snapshot["runtime_release"]["repo_runtime_merge_base"] == (
        snapshot["repository"]["head_commit"]
    )


def test_runtime_collector_accepts_only_canonical_current_root() -> None:
    source = (
        ROOT / "tests/gate0/collect_runtime_snapshot.ps1"
    ).read_text(encoding="utf-8")

    assert (
        '$scriptRepoRootFull = [System.IO.Path]::GetFullPath('
        in source
    )
    assert 'Join-Path $PSScriptRoot "..\\.."' in source
    assert '$repoRootFull.Equals(' in source
    assert '$expectedLiveRootFull.Equals(' in source
    assert '"error_stage":"canonical_repo_authority"' in source
    assert '$rootProfile -eq "canonical-repo"' in source
    assert (
        '$rootProfile -in @("canonical-repo", "telegram-live-worktree")'
        not in source
    )


def test_normalizer_labels_canonical_current_and_target_isolation() -> None:
    source = (
        ROOT / "tests/gate0/normalize_gate0_contracts.py"
    ).read_text(encoding="utf-8")

    assert '"runtime-worktree:canonical-repo"' in source
    assert '"worktree:canonical-current"' in source
    assert '"runtime-worktree:telegram-live"' not in source
    assert '"worktree:telegram-live"' not in source


def test_generator_does_not_claim_distinct_current_release_worktree() -> None:
    source = (
        ROOT / "tests/gate0/generate_gate0_artifacts.py"
    ).read_text(encoding="utf-8")

    assert "Release worktree is clean and distinct" not in source
    assert "CURRENT runtime release shares the canonical candidate worktree" in source


def test_generator_cli_rejects_noncanonical_root_before_io(
    tmp_path: pathlib.Path,
) -> None:
    script = ROOT / "tests/gate0/generate_gate0_artifacts.py"
    rejected_root = tmp_path / "must-not-be-created"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "refresh",
            "--root",
            str(rejected_root),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert json.loads(completed.stderr) == {
        "schema": "nobus.gate0.generator.v1",
        "result": "blocked",
        "error_stage": "canonical_repo_authority",
    }
    assert str(rejected_root) not in completed.stderr
    assert str(script) not in completed.stderr
    assert "Traceback" not in completed.stderr
    assert "usage:" not in completed.stderr
    assert not rejected_root.exists()
