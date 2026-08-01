from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import pathlib
import shutil
import sys

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
GATE = ROOT / "docs/gates/gate-00-product-contract-baseline"
sys.path.insert(0, str(ROOT / "tests/gate0"))

import gate0_normative_catalog as normative_catalog  # noqa: E402
from gate0_precapture import project_snapshot  # noqa: E402
from gate0_normative_catalog import load_normative_catalog  # noqa: E402
from gate0_review_origin import review_receipts_origin_verified  # noqa: E402
from gate0_product_v2 import reconcile_product_v2  # noqa: E402
from gate0_review_submission import (  # noqa: E402
    REVIEW_CHECKS, REVIEWER_TYPES,
    _decode_review_submission,
)
from generate_gate0_artifacts import (  # noqa: E402
    product_contract,
    record_review,
    source_document_inventory,
)
from test_gate0_precapture import (  # noqa: E402
    UTC,
    _bind_synthetic_verifier,
    _copy_candidate,
    _fresh_snapshot,
)


BINDING_KEYS = (
    "stage",
    "candidate_core_digest",
    "frozen_tree_digest",
    "capture_digest",
    "review_tree_digest",
)


def _submission(
    candidate: pathlib.Path,
    *,
    level: str,
    observed_at: str,
) -> dict[str, object]:
    template = json.loads(
        (
            candidate
            / f"docs/gates/gate-00-product-contract-baseline/verification/{level}.json"
        ).read_text(encoding="utf-8")
    )
    evidence_refs = ["tests/gate0/test_independent_audit_closure.py"]
    return {
        "schema": "nobus.gate0.independent_review_submission.v1",
        "level": level,
        "stage": "post_capture",
        "verdict": "pass" if level == "l1" else "accept",
        "observed_at": observed_at,
        **{key: template[key] for key in BINDING_KEYS if key != "stage"},
        "reviewer": {
            "reviewer_id": f"synthetic-{level}-reviewer",
            "reviewer_type": REVIEWER_TYPES[level],
            "method": "independent synthetic reproduction for contract tests",
            "independence_attested": True,
            "executor_separation_attested": True,
            "evidence_refs": evidence_refs,
        },
        "checks": [
            {"id": check, "status": "pass", "evidence_refs": evidence_refs}
            for check in REVIEW_CHECKS[level]
        ],
        "findings": [],
        "blocking_criteria": [],
        "release_blockers": [],
        "hidden_reasoning_persisted": False,
    }


def _write_submission(
    candidate: pathlib.Path,
    value: dict[str, object],
) -> pathlib.Path:
    path = candidate / "tmp/review-submission.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def test_product_contract_binds_catalog_sources_gate2a_and_roles() -> None:
    contract = product_contract(ROOT)
    assert contract["contract_version"] == "2.0.0"
    assert contract["normative_input"]["catalog_ref"] == (
        "docs/gates/gate-00-product-contract-baseline/product/normative-catalog.json"
    )
    assert contract["normative_input"]["catalog_sha256"].startswith("sha256:")
    assert contract["normative_input"]["source_count"] == 20
    assert contract["normative_input"]["source_set_sha256"].startswith("sha256:")
    assert "development_specialist" in contract["vocabularies"]["agent_roles"]
    gate2a = next(
        family
        for family in contract["contract_families"]
        if family["family"] == "miniapp_development_control"
    )
    assert gate2a["owner_gate"] == "2a"


def test_normative_catalog_and_every_source_use_atomic_repo_safe_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[pathlib.Path] = []
    original = normative_catalog._read_repo_regular_bytes

    def observed(root: pathlib.Path, path: pathlib.Path) -> bytes:
        calls.append(path.relative_to(root))
        return original(root, path)

    monkeypatch.setattr(
        normative_catalog,
        "_read_repo_regular_bytes",
        observed,
    )
    catalog = normative_catalog.load_normative_catalog(ROOT)
    normative_catalog.source_document_inventory(ROOT)
    assert len(calls) == 2 + len(catalog["required_sources"])


def test_normative_source_digest_mutation_fails_closed(
    tmp_path: pathlib.Path,
) -> None:
    candidate = _copy_candidate(tmp_path)
    source = candidate / "docs/adr/0020-early-miniapp-and-specialist-workers.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        ROOT / "docs/adr/0020-early-miniapp-and-specialist-workers.md",
        source,
    )
    source.write_bytes(source.read_bytes() + b" ")
    with pytest.raises(RuntimeError, match="source digest mismatch"):
        source_document_inventory(candidate)


def test_external_review_submission_is_preserved_not_awarded(
    tmp_path: pathlib.Path,
) -> None:
    candidate = _copy_candidate(tmp_path)
    _bind_synthetic_verifier(candidate)
    project_snapshot(candidate, _fresh_snapshot(candidate))
    observed_at = dt.datetime.now(UTC).isoformat().replace("+00:00", "Z")
    submission = _submission(candidate, level="l2", observed_at=observed_at)
    path = _write_submission(candidate, submission)
    expected_digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    record_review(
        candidate,
        level="l2",
        observed_at=observed_at,
        submission_path=path,
    )

    receipt = json.loads(
        (
            candidate
            / "docs/gates/gate-00-product-contract-baseline/verification/l2.json"
        ).read_text(encoding="utf-8")
    )
    assert receipt["level"] == "l2"
    assert receipt["verdict"] == submission["verdict"]
    assert receipt["reviewer"] == submission["reviewer"]
    assert receipt["checks"] == submission["checks"]
    assert receipt["submission_sha256"] == expected_digest
    expected_ref = (
        "docs/gates/gate-00-product-contract-baseline/verification/"
        "submissions/l2.json"
    )
    assert receipt["submission_ref"] == expected_ref
    assert (candidate / expected_ref).read_bytes() == path.read_bytes()


def test_external_review_identity_mismatch_fails_closed(
    tmp_path: pathlib.Path,
) -> None:
    candidate = _copy_candidate(tmp_path)
    _bind_synthetic_verifier(candidate)
    project_snapshot(candidate, _fresh_snapshot(candidate))
    observed_at = dt.datetime.now(UTC).isoformat().replace("+00:00", "Z")
    submission = _submission(candidate, level="l3", observed_at=observed_at)
    attacked = copy.deepcopy(submission)
    attacked["reviewer"]["reviewer_type"] = "executor"
    path = _write_submission(candidate, attacked)

    with pytest.raises(RuntimeError, match="review identity is not acceptable"):
        record_review(
            candidate,
            level="l3",
            observed_at=observed_at,
            submission_path=path,
        )


def test_verification_profiles_separate_pure_tests_from_live_maintenance() -> None:
    profile = json.loads(
        (ROOT / "tests/gate0/verification-profiles.json").read_text(encoding="utf-8")
    )
    assert profile["schema"] == "nobus.gate0.verification_profiles.v1"
    assert profile["pure"]["runtime_or_scheduler_mutation"] is False
    assert profile["pure"]["argv"] == [
        ".venv/Scripts/python.exe",
        "-m",
        "pytest",
        "tests/gate0/test_gate0_normative.py",
        "tests/gate0/test_gate0_handoff_lifecycle.py",
        "tests/gate0/test_gate0_precapture.py",
        "tests/gate0/test_gate0_acceptance.py",
        "tests/gate0/test_independent_audit_regressions.py",
        "tests/gate0/test_independent_audit_closure.py",
        "-q",
    ]
    assert profile["full_read_only"]["argv"] == [
        ".venv/Scripts/python.exe",
        "-m",
        "pytest",
        "-p",
        "tests.gate0.pytest_mutex_namespace",
        "-q",
    ]
    assert profile["full_read_only"]["production_mutex_contended"] is False
    assert profile["full_read_only"]["runtime_or_scheduler_mutation"] is False
    assert profile["live_maintenance"]["requires_action_bound_l4"] is True
    assert profile["live_maintenance"]["helper"] == (
        "tests/gate0/manage_runtime_maintenance.ps1"
    )
    assert profile["live_maintenance"]["helper"] not in profile["pure"]["argv"]
    assert "tests/gate0" not in profile["pure"]["argv"]
    assert not any(
        "runtime_maintenance" in argument
        for argument in profile["pure"]["argv"]
    )

def test_runtime_collector_uses_exact_profile_not_runner_path_substring() -> None:
    source = (
        ROOT / "tests/gate0/collect_runtime_snapshot.ps1"
    ).read_text(encoding="utf-8")

    assert "New-RunnerCandidateProfile" in source
    assert "[bool] $profile.exact_runner_script_match" in source
    assert "[bool] $profile.secret_shape_absent" in source
    assert "if ([bool] $profile.verified)" in source
    assert "Runner candidate identity changed" in source
    assert "$rawCommandLine.IndexOf(" not in source


def test_external_review_json_is_strict() -> None:
    with pytest.raises(RuntimeError, match="duplicate key"):
        _decode_review_submission(b'{"schema":"first","schema":"second"}')
    with pytest.raises(RuntimeError, match="non-finite"):
        _decode_review_submission(b'{"value":NaN}')


def test_normative_catalog_rejects_duplicate_keys(
    tmp_path: pathlib.Path,
) -> None:
    candidate = _copy_candidate(tmp_path)
    path = (
        candidate
        / "docs/gates/gate-00-product-contract-baseline/product/normative-catalog.json"
    )
    raw = path.read_text(encoding="utf-8")
    path.write_text(
        raw.replace("{", '{"schema":"duplicate",', 1),
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(ValueError, match="duplicate key"):
        load_normative_catalog(candidate)



def test_normative_catalog_semantic_sets_are_exact_and_closed(
    tmp_path: pathlib.Path,
) -> None:
    expected = {
        "domains": [
            "notes", "calendar", "tasks", "documents", "research",
            "development", "general",
        ],
        "gate_ids": ["0", "1", "2", "2a", "3", "4", "5", "6", "7", "8"],
        "agent_roles": [
            "general_orchestrator_worker",
            "google_workspace_specialist",
            "research_analytics_specialist",
            "content_studio_specialist",
            "development_specialist",
            "verification_specialist",
        ],
    }
    assert {
        key: load_normative_catalog(ROOT)[key] for key in expected
    } == expected

    candidate = _copy_candidate(tmp_path)
    path = (
        candidate
        / "docs/gates/gate-00-product-contract-baseline/product/normative-catalog.json"
    )
    original = json.loads(path.read_text(encoding="utf-8"))
    for field in expected:
        attacked = copy.deepcopy(original)
        attacked[field] = [*attacked[field], "unapproved_value"]
        path.write_text(
            json.dumps(attacked, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        with pytest.raises(ValueError, match="semantic set"):
            load_normative_catalog(candidate)


def test_v2_reconciliation_removes_unapproved_legacy_vocabulary() -> None:
    product = product_contract(ROOT)
    catalog = load_normative_catalog(ROOT)
    assert product["vocabularies"]["domains"] == catalog["domains"]
    assert product["vocabularies"]["agent_roles"] == catalog["agent_roles"]
    for field in ("actions", "source_kinds", "effect_kinds"):
        attacked = copy.deepcopy(product)
        attacked["vocabularies"][field].append("arbitrary_authority_expansion")
        reconciled = reconcile_product_v2(ROOT, attacked)
        assert "arbitrary_authority_expansion" not in reconciled["vocabularies"][field]


def test_gate2a_contract_family_catalog_and_goldens_are_complete() -> None:
    product = json.loads(
        (GATE / "product/product-contract.json").read_text(encoding="utf-8")
    )
    family = next(
        item for item in product["contract_families"]
        if item["family"] == "miniapp_development_control"
    )
    expected_family = {
        "AgentProfile", "AgentDispatch", "WorkerResultEnvelope",
        "ControlTaskView", "ControlEventView", "ApprovalChallenge",
        "CodeTaskContract", "CodePlan", "PatchCandidate",
        "CandidateCommitReceipt",
    }
    assert set(family["contracts"]) == expected_family
    formal = {
        "AgentProfile", "AgentDispatch", "ApprovalChallenge",
        "CodeTaskContract", "CodePlan", "PatchCandidate",
        "CandidateCommitReceipt",
    }
    catalog_names = {item["contract_name"] for item in product["contract_catalog"]}
    assert formal <= catalog_names
    bundle = json.loads(
        (
            GATE / "fixtures/golden/target-contract-schema-projections.json"
        ).read_text(encoding="utf-8")
    )
    assert formal <= set(bundle["schemas"])
    assert (
        "docs/gates/gate-02a-miniapp-development-control/ARCHITECTURE.md"
        in bundle["authoritative_sources"]
    )


def test_target_intent_schema_uses_exact_product_vocabulary() -> None:
    product = json.loads(
        (GATE / "product/product-contract.json").read_text(encoding="utf-8")
    )
    vocabularies = product["vocabularies"]
    bundle = json.loads(
        (
            GATE / "fixtures/golden/target-contract-schema-projections.json"
        ).read_text(encoding="utf-8")
    )
    properties = bundle["schemas"]["IntentEnvelope"]["properties"]
    assert properties["domain"]["enum"] == vocabularies["domains"]
    assert properties["action"]["enum"] == vocabularies["actions"]
    effect = properties["proposed_effects"]["items"]["properties"]
    assert effect["source"]["enum"] == vocabularies["source_kinds"]
    assert effect["kind"]["enum"] == vocabularies["effect_kinds"]
    source = properties["source_scope"]["items"]["properties"]["source"]
    assert source["enum"] == vocabularies["source_kinds"]


def test_gate2a_decision_and_catalog_are_in_core_manifests() -> None:
    decisions = json.loads(
        (GATE / "decisions/decision-register.json").read_text(encoding="utf-8")
    )["decisions"]
    gate2a = next(item for item in decisions if item["id"] == "G0-D014")
    assert gate2a["status"] == "accepted"
    assert gate2a["source_ref"] == "docs/adr/0020-early-miniapp-and-specialist-workers.md"
    assert "self-deploy" in gate2a["decision"]

    catalog_path = (
        "docs/gates/gate-00-product-contract-baseline/product/normative-catalog.json"
    )
    core = json.loads(
        (GATE / "fixtures/golden/core-digests.json").read_text(encoding="utf-8")
    )
    component = json.loads(
        (GATE / "evidence/component-manifest.json").read_text(encoding="utf-8")
    )
    assert catalog_path in {item["path"] for item in core["entries"]}
    assert catalog_path in {item["path"] for item in component["entries"]}


def test_seal_requires_preserved_submissions_and_unique_reviewer_identities(
    tmp_path: pathlib.Path,
) -> None:
    candidate = _copy_candidate(tmp_path)
    _bind_synthetic_verifier(candidate)
    project_snapshot(candidate, _fresh_snapshot(candidate))
    observed_at = dt.datetime.now(UTC).isoformat().replace("+00:00", "Z")
    for level in ("l1", "l2", "l3"):
        path = _write_submission(
            candidate,
            _submission(
                candidate,
                level=level,
                observed_at=observed_at,
            ),
)
        record_review(
            candidate,
            level=level,
            observed_at=observed_at,
            submission_path=path,
        )
    verification = candidate / (
        "docs/gates/gate-00-product-contract-baseline/verification"
    )
    receipts = {
        level: json.loads((verification / f"{level}.json").read_text(encoding="utf-8"))
        for level in ("l1", "l2", "l3")
    }
    assert review_receipts_origin_verified(candidate, receipts) is True

    duplicate = _submission(candidate, level="l3", observed_at=observed_at)
    duplicate["reviewer"]["reviewer_id"] = "synthetic-l2-reviewer"
    path = _write_submission(candidate, duplicate)
    record_review(
        candidate,
        level="l3",
        observed_at=observed_at,
        submission_path=path,
    )
    receipts["l3"] = json.loads(
        (verification / "l3.json").read_text(encoding="utf-8")
    )
    assert review_receipts_origin_verified(candidate, receipts) is False

    (verification / "submissions/l1.json").unlink()
    assert review_receipts_origin_verified(candidate, receipts) is False
