from __future__ import annotations

import collections
import datetime as dt
import json
import pathlib
import shutil
import sys

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
GATE = ROOT / "docs/gates/gate-00-product-contract-baseline"
CATALOG = GATE / "product/normative-catalog.json"
sys.path.insert(0, str(ROOT / "tests/gate0"))

from generate_gate0_artifacts import (  # noqa: E402
    build_corpus,
    record_review,
    source_document_inventory,
)
from gate0_precapture import (  # noqa: E402
    prepare_precapture,
    project_snapshot,
    verify_precapture,
)
from test_gate0_precapture import (  # noqa: E402
    UTC,
    _bind_synthetic_verifier,
    _copy_candidate,
    _fresh_snapshot,
)


def test_normative_catalog_is_the_required_gate0_input() -> None:
    assert CATALOG.is_file(), "Gate 0 has no single normative input catalog"
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    assert catalog["schema"] == "nobus.gate0.normative_catalog.v1"
    assert "development" in catalog["domains"]
    assert "2a" in catalog["gate_ids"]
    assert {
        "general_orchestrator_worker",
        "google_workspace_specialist",
        "research_analytics_specialist",
        "content_studio_specialist",
        "development_specialist",
    } <= set(catalog["agent_roles"])


def test_accepted_target_sources_and_gate2a_are_inventory_bound() -> None:
    records = {entry["path"]: entry for entry in source_document_inventory(ROOT)}
    assert {
        "docs/adr/0020-early-miniapp-and-specialist-workers.md",
        "docs/gates/gate-02a-miniapp-development-control/ARCHITECTURE.md",
    } <= set(records)


def test_removing_accepted_adr0020_blocks_source_inventory(
    tmp_path: pathlib.Path,
) -> None:
    candidate = _copy_candidate(tmp_path)
    source = candidate / "docs/adr/0020-early-miniapp-and-specialist-workers.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        ROOT / "docs/adr/0020-early-miniapp-and-specialist-workers.md",
        source,
    )
    source.unlink()
    with pytest.raises(FileNotFoundError, match="required Gate 0 source"):
        source_document_inventory(candidate)


def test_precapture_freezes_every_normative_catalog_source(
    tmp_path: pathlib.Path,
) -> None:
    candidate = _copy_candidate(tmp_path)
    core = prepare_precapture(candidate)
    frozen = {entry["path"] for entry in core["input_entries"]}
    required = {
        "docs/adr/0020-early-miniapp-and-specialist-workers.md",
        "docs/gates/gate-02a-miniapp-development-control/ARCHITECTURE.md",
    }
    assert required <= frozen

    inventory = json.loads(
        (
            candidate
            / "docs/gates/gate-00-product-contract-baseline/evidence/documentation-inventory.json"
        ).read_text(encoding="utf-8")
    )
    assert required <= {
        entry["path"] for entry in inventory["current_worktree_documents"]
    }

    accepted_adr = candidate / "docs/adr/0020-early-miniapp-and-specialist-workers.md"
    accepted_adr.write_bytes(accepted_adr.read_bytes() + b"\n")
    with pytest.raises(RuntimeError, match="frozen input tree changed"):
        verify_precapture(candidate)


def test_development_corpus_covers_authority_l4_and_no_self_deploy() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    requirements = catalog["development_requirements"]
    cases = [
        case
        for case in build_corpus()
        if case["expected"]["intent"]["domain"] == "development"
    ]
    assert len(cases) >= requirements["minimum_cases"]
    codes = collections.Counter(
        error
        for case in cases
        for error in case["expected"]["errors"]
    )
    assert set(requirements["required_error_codes"]) <= set(codes)
    assert {case["input"]["modality"] for case in cases} == set(
        requirements["required_modalities"]
    )


def test_review_cannot_be_self_stamped_without_external_submission(
    tmp_path: pathlib.Path,
) -> None:
    candidate = _copy_candidate(tmp_path)
    _bind_synthetic_verifier(candidate)
    project_snapshot(candidate, _fresh_snapshot(candidate))
    observed_at = dt.datetime.now(UTC).isoformat().replace("+00:00", "Z")

    with pytest.raises(
        RuntimeError,
        match="independent review submission is required",
    ):
        record_review(
            candidate,
            level="l2",
            observed_at=observed_at,
        )
import subprocess
import generate_gate0_artifacts as gate0_generator  # noqa: E402


def test_git_whitespace_check_includes_untracked_files(
    tmp_path: pathlib.Path,
) -> None:
    subprocess.run(
        ["git", "init", "--quiet"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "new-file.txt").write_text(
        "content with trailing spaces  \n",
        encoding="utf-8",
        newline="\n",
    )

    check = getattr(gate0_generator, "git_whitespace_check", None)
    assert callable(check), "Gate 0 has no untracked-aware whitespace check"
    result = check(tmp_path)

    assert result.returncode != 0
    assert result.output
