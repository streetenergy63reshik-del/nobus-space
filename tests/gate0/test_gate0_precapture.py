from __future__ import annotations

import copy
import datetime as dt
import inspect
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/gate0"))

from collect_gate0_snapshot import _read_repo_regular_bytes
from gate0_precapture import (
    CAPTURE_DEPENDENT_PATHS,
    POST_CAPTURE_CHANGED_PATHS,
    RECEIPT_PATHS,
    authoritative_external_paths,
    bind_receipts,
    prepare_precapture,
    project_snapshot,
    projection_plan,
    split_snapshot,
    verify_precapture,
)
from gate0_lifecycle import verifier_binding_verified
from generate_gate0_artifacts import (
    file_digest,
    record_review,
    seal_gate0,
    write_json,
)


UTC = dt.timezone.utc


def _database(role: str) -> dict[str, object]:
    schema_digest = "sha256:" + role.encode("utf-8").hex().ljust(64, "0")[:64]
    database: dict[str, object] = {
        "database_role": role,
        "database_ref": f"runtime-db:{role}",
        "runtime_binding_status": "verified",
        "source_schema_match": True,
        "schema_digest": schema_digest,
        "migration_inventory": {"applied": [], "pending": [], "unknown": []},
        "migration_lineage_status": (
            "genesis_baseline_verified"
            if role == "telegram_state"
            else "verified_absent"
        ),
        "snapshot": {
            "mode": "sqlite_read_transaction",
            "wal_aware": True,
            "data_version_stable": True,
            "file_markers_stable": False,
            "concurrent_file_activity_observed": True,
            "consistent": True,
        },
        "integrity": {"quick_check": "ok", "foreign_key_check": "ok"},
        "genesis_baseline": None,
    }
    if role == "telegram_state":
        database["genesis_baseline"] = {
            "genesis_id": "genesis_baseline:telegram_state_current_schema",
            "authority_ref": "owner-authority:gate0-evidence-closure-2026-07-29",
            "schema_digest": schema_digest,
            "historical_legacy_migration_proven": False,
            "durable_ledger_deferred_to_gate": 2,
            "production_database_mutated": False,
        }
    return database


def _snapshot() -> dict[str, object]:
    return {
        "runtime_snapshot": {
            "schema": "nobus.gate0.runtime_snapshot.v1",
            "capture_started_at": "2029-12-31T23:59:59Z",
            "observed_at": "2030-01-01T00:00:00Z",
            "fresh_until": "2030-01-01T00:05:00Z",
            "clock": {"trusted": True},
            "runtime_claim": {
                "status": "verified",
                "scheduled_commit": "a" * 40,
                "process_loaded_commit": "a" * 40,
            },
            "database_binding": {
                "status": "verified",
                "scheduled_commit": "a" * 40,
                "root_profile": "registered-live-root",
            },
            "processes": [
                {
                    "process_role": "telegram_runner",
                    "status": "verified",
                    "observed_count": 1,
                    "loaded_commit": "a" * 40,
                    "scheduled_commit": "a" * 40,
                    "root_profile": "registered-live-root",
                    "instances": [
                        {
                            "loaded_commit": "a" * 40,
                        }
                    ],
                }
            ],
            "scheduler": {
                "status": "verified",
                "scheduled_commit": "a" * 40,
                "root_profile": "registered-live-root",
            },
        },
        "database_snapshot": {
            "schema": "nobus.gate0.database_snapshot.v1",
            "observed_at": "2030-01-01T00:00:00Z",
            "databases": [
                _database("business_notes"),
                _database("core"),
                _database("checkpoint"),
                _database("telegram_state"),
            ],
        },
    }


def test_snapshot_split_is_idempotent_for_combined_and_separated_shapes() -> None:
    separated = _snapshot()
    runtime, databases = split_snapshot(separated)
    combined = {**runtime, "database_snapshot": databases}
    assert split_snapshot(combined) == (runtime, databases)
    assert split_snapshot(separated) == (runtime, databases)


def test_synthetic_bounded_projection_plan_is_ready_and_fast() -> None:
    started = time.monotonic()
    plan = projection_plan(
        _snapshot(),
        as_of=dt.datetime(2030, 1, 1, 0, 1, tzinfo=UTC),
    )
    elapsed = time.monotonic() - started
    assert elapsed < 120
    assert plan["ready_projection"] is True
    assert plan["blocking_reasons"] == []
    assert plan["genesis_verified"] is True
    assert set(plan["database_statuses"].values()) == {"VERIFIED"}
    assert plan["changed_paths"] == POST_CAPTURE_CHANGED_PATHS


def test_contradictory_snapshot_never_creates_genesis_or_ready() -> None:
    snapshot = _snapshot()
    telegram = snapshot["database_snapshot"]["databases"][-1]
    telegram["snapshot"]["consistent"] = False
    telegram["migration_lineage_status"] = "genesis_baseline_verified"
    plan = projection_plan(
        snapshot,
        as_of=dt.datetime(2030, 1, 1, 0, 1, tzinfo=UTC),
    )
    assert plan["ready_projection"] is False
    assert plan["genesis_verified"] is False
    assert "DATABASE_PROOF_NOT_VERIFIED" in plan["blocking_reasons"]
    assert "TELEGRAM_GENESIS_NOT_VERIFIED" in plan["blocking_reasons"]


def test_explicit_contradictory_runtime_and_missing_db_roles_never_ready() -> None:
    contradictory = _snapshot()
    contradictory["runtime_snapshot"]["status"] = "CONTRADICTORY"
    plan = projection_plan(
        contradictory,
        as_of=dt.datetime(2030, 1, 1, 0, 1, tzinfo=UTC),
    )
    assert plan["capture_lifecycle"] == "UNVERIFIABLE"
    assert plan["ready_projection"] is False
    assert plan["genesis_verified"] is False
    assert "CAPTURE_NOT_FRESH" in plan["blocking_reasons"]

    incomplete = _snapshot()
    incomplete["database_snapshot"]["databases"] = [
        incomplete["database_snapshot"]["databases"][-1]
    ]
    plan = projection_plan(
        incomplete,
        as_of=dt.datetime(2030, 1, 1, 0, 1, tzinfo=UTC),
    )
    assert plan["ready_projection"] is False
    assert plan["genesis_verified"] is False
    assert "DATABASE_ROLE_SET_INVALID" in plan["blocking_reasons"]
    assert "DATABASE_PROOF_NOT_VERIFIED" in plan["blocking_reasons"]


def test_stale_and_tenant_opaque_ref_attacks_are_blocked() -> None:
    stale = projection_plan(
        _snapshot(),
        as_of=dt.datetime(2030, 1, 1, 0, 6, tzinfo=UTC),
    )
    assert stale["capture_lifecycle"] == "STALE"
    assert stale["ready_projection"] is False
    assert stale["genesis_verified"] is False

    invalid = copy.deepcopy(_snapshot())
    invalid["database_snapshot"]["databases"][0]["database_ref"] = (
        "candidate-worktree-db:business_notes"
    )
    try:
        projection_plan(
            invalid,
            as_of=dt.datetime(2030, 1, 1, 0, 1, tzinfo=UTC),
        )
    except ValueError as error:
        assert "runtime-db:<role>" in str(error)
    else:
        raise AssertionError("unsafe database ref was accepted")


@pytest.mark.parametrize(
    ("mutation", "expected_blocker"),
    [
        (
            lambda runtime: runtime["runtime_claim"].update(
                {"status": "contradictory"}
            ),
            "RUNTIME_BINDING_NOT_VERIFIED",
        ),
        (
            lambda runtime: runtime["processes"][0].update(
                {"status": "contradictory"}
            ),
            "RUNTIME_BINDING_NOT_VERIFIED",
        ),
        (
            lambda runtime: runtime["database_binding"].update(
                {"status": "unverifiable"}
            ),
            "RUNTIME_BINDING_NOT_VERIFIED",
        ),
        (
            lambda runtime: runtime["processes"][0]["instances"][0].update(
                {"loaded_commit": "b" * 40}
            ),
            "RUNTIME_BINDING_NOT_VERIFIED",
        ),
    ],
)
def test_runtime_binding_attacks_never_project_ready(
    mutation: object,
    expected_blocker: str,
) -> None:
    snapshot = _snapshot()
    mutation(snapshot["runtime_snapshot"])
    plan = projection_plan(
        snapshot,
        as_of=dt.datetime(2030, 1, 1, 0, 1, tzinfo=UTC),
    )
    assert plan["ready_projection"] is False
    assert expected_blocker in plan["blocking_reasons"]


@pytest.mark.parametrize(
    "observed_at",
    ["2000-01-01T00:00:00Z", "2030-01-01T00:02:00Z", "not-a-time"],
)
def test_stale_future_or_malformed_database_capture_never_ready(
    observed_at: str,
) -> None:
    snapshot = _snapshot()
    snapshot["database_snapshot"]["observed_at"] = observed_at
    plan = projection_plan(
        snapshot,
        as_of=dt.datetime(2030, 1, 1, 0, 1, tzinfo=UTC),
    )
    assert plan["ready_projection"] is False
    assert "DATABASE_CAPTURE_NOT_FRESH" in plan["blocking_reasons"]


def test_post_capture_path_reuses_frozen_checks_and_has_no_collector() -> None:
    source = inspect.getsource(
        sys.modules["gate0_precapture"].project_snapshot
    )
    assert "collect_runtime" not in source
    assert "subprocess" not in source
    assert "pytest" not in source
    assert "pip_audit" not in source
    assert "gitleaks" not in source
    assert RECEIPT_PATHS.isdisjoint(CAPTURE_DEPENDENT_PATHS)
    assert all(
        path.startswith("docs/gates/gate-00-product-contract-baseline/")
        for path in POST_CAPTURE_CHANGED_PATHS
    )


def _load(path: pathlib.Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _copy_candidate(tmp_path: pathlib.Path) -> pathlib.Path:
    candidate = tmp_path / "candidate"
    subprocess.run(
        ["git", "clone", "--quiet", "--no-hardlinks", str(ROOT), str(candidate)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    for relative in (
        ".gitattributes",
        "docs/gates/gate-00-product-contract-baseline",
        "tests/gate0",
        "tests/test_fake_vertical.py",
        "tests/test_telegram_gateway.py",
        "tests/test_trusted_ingress.py",
    ):
        source = ROOT / relative
        destination = candidate / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            shutil.copyfile(source, destination)
    for source in authoritative_external_paths(
        ROOT,
        ROOT / "docs/gates/gate-00-product-contract-baseline",
    ):
        destination = candidate / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    return candidate


def _bind_synthetic_verifier(candidate: pathlib.Path) -> dict[str, object]:
    gate = candidate / "docs/gates/gate-00-product-contract-baseline"
    core = prepare_precapture(candidate)
    input_digest = str(core["input_tree_digest"])
    input_generated_at = str(core["input_generated_at"])
    run_at = max(
        dt.datetime.now(UTC),
        dt.datetime.fromisoformat(input_generated_at.replace("Z", "+00:00")),
    ).isoformat().replace("+00:00", "Z")
    dependencies = _load(gate / "evidence/dependency-inventory.json")
    verifier = dependencies["verification_toolchain"]
    expected_scan_count = len(core["input_entries"])
    gitleaks_summary = copy.deepcopy(verifier["gitleaks"])
    gitleaks_summary["scanned_file_count"] = expected_scan_count
    secret_scan = copy.deepcopy(dependencies["secret_scan"])
    secret_scan["scanned_file_count"] = expected_scan_count
    checks = {}
    for index, name in enumerate(
        ("jsonschema", "hypothesis", "import_linter"), start=1
    ):
        checks[name] = {
            "status": "passed",
            "tool_version": verifier["versions"][name],
            "scanned_input_tree_digest": input_digest,
            "started_at": run_at,
            "finished_at": run_at,
            "report_sha256": "sha256:" + str(index) * 64,
        }
    checks["pip_audit"] = {
        "status": "passed",
        "tool_version": verifier["versions"]["pip_audit"],
        "scanned_input_tree_digest": input_digest,
        "started_at": run_at,
        "finished_at": run_at,
        "report_sha256": dependencies["vulnerability_check"]["raw_report_sha256"],
    }
    checks["gitleaks"] = {
        "status": "passed",
        "tool_version": verifier["versions"]["gitleaks"],
        "scanned_input_tree_digest": input_digest,
        "started_at": run_at,
        "finished_at": run_at,
        "report_sha256": dependencies["secret_scan"]["raw_report_sha256"],
    }
    verifier_receipt = {
        "candidate_binding": {
            "status": "verified",
            "reason_code": None,
            "input_tree_digest": input_digest,
            "input_generated_at": input_generated_at,
            "lock_refs": [
                "tests/gate0/verifier-requirements.txt",
                "tests/gate0/verifier-toolchain.json",
            ],
            "authority_ref": "owner-authority:synthetic-test-only",
            "official_sources_only": True,
            "hashes_verified": True,
            "canonical_venv_mutated": False,
            "network_or_install_performed": True,
            "isolated_environment_digest": "sha256:" + "6" * 64,
            "checks": checks,
        },
        "dev_checks": {
            "jsonschema": "passed",
            "hypothesis": "passed",
            "import_linter": "passed",
        },
        "pip_audit": dependencies["verification_toolchain"]["pip_audit"],
        "gitleaks": gitleaks_summary,
    }
    tests = _load(gate / "evidence/test-inventory.json")
    for name in ("targeted_gate0", "full_pytest"):
        tests[name].update(
            {"started_at": run_at, "finished_at": run_at, "status": "pass"}
        )
    test_binding = {
        "status": "verified",
        "reason_code": None,
        "input_tree_digest": input_digest,
        "input_generated_at": input_generated_at,
        "network_or_provider_calls_performed": False,
        "canonical_venv_mutated": False,
        "environment_digest": "sha256:" + "7" * 64,
        "runs": {
            name: {
                **tests[name],
                "scanned_input_tree_digest": input_digest,
                "report_sha256": "sha256:" + str(index + 7) * 64,
            }
            for index, name in enumerate(("targeted_gate0", "full_pytest"))
        },
    }
    return bind_receipts(
        candidate,
        {
            "schema": "nobus.gate0.offline_verification_receipt.v1",
            "input_tree_digest": input_digest,
            "input_generated_at": input_generated_at,
            "verification_toolchain": verifier_receipt,
            "vulnerability_check": dependencies["vulnerability_check"],
            "secret_scan": secret_scan,
            "test_inventory": {
                "candidate_binding": test_binding,
                "targeted_gate0": tests["targeted_gate0"],
                "full_pytest": tests["full_pytest"],
                "release_checks": {"gitleaks": "passed", "pip_audit": "passed"},
                "observed_at": run_at,
            },
        },
    )


def _fresh_snapshot(candidate: pathlib.Path) -> dict[str, object]:
    gate = candidate / "docs/gates/gate-00-product-contract-baseline"
    runtime = _load(gate / "evidence/runtime-inventory.json")
    databases = _load(gate / "evidence/database-inventory.json")
    observed_at = dt.datetime.now(UTC)
    fresh_until = observed_at + dt.timedelta(minutes=5)
    observed_text = observed_at.isoformat().replace("+00:00", "Z")
    fresh_text = fresh_until.isoformat().replace("+00:00", "Z")
    runtime.update(
        {
            "capture_started_at": observed_text,
            "observed_at": observed_text,
            "fresh_until": fresh_text,
        }
    )
    runtime["clock"]["trusted"] = True
    scheduled_commit = runtime["scheduler"]["scheduled_commit"] or "a" * 40
    runtime["database_binding"]["status"] = "verified"
    runtime["runtime_claim"].update(
        {
            "status": "verified",
            "reason_code": None,
            "scheduled_commit": scheduled_commit,
            "process_loaded_commit": scheduled_commit,
        }
    )
    runtime["processes"][0].update(
        {
            "status": "verified",
            "reason_code": None,
            "observed_count": 1,
            "loaded_commit": scheduled_commit,
            "instances": [
                {
                    "pid": 4242,
                    "parent_pid": 1,
                    "started_at": observed_text,
                    "executable_digest": "sha256:" + "1" * 64,
                    "argv_profile": "sanitized_expected_runner",
                    "argv_digest": "sha256:" + "2" * 64,
                    "loaded_commit": scheduled_commit,
                    "loaded_code_digest": "sha256:" + "3" * 64,
                }
            ],
        }
    )
    runtime["scheduler"]["status"] = "verified"
    databases["observed_at"] = observed_text
    for database in databases["databases"]:
        role = database["database_role"]
        database.update(
            {
                "runtime_binding_status": "verified",
                "runtime_binding_reason": "exact_registered_runtime_root",
                "source_schema_match": True,
                "migration_inventory": {
                    "applied": [],
                    "pending": [],
                    "unknown": [],
                },
                "migration_lineage_status": (
                    "genesis_baseline_verified"
                    if role == "telegram_state"
                    else "verified_absent"
                ),
                "genesis_baseline": None,
            }
        )
        database["snapshot"].update(
            {
                "mode": "sqlite_read_transaction",
                "wal_aware": True,
                "data_version_stable": True,
                "file_markers_stable": False,
                "consistent": True,
            }
        )
        database["integrity"] = {
            "quick_check": "ok",
            "foreign_key_check": "ok",
        }
        if role == "telegram_state":
            database["genesis_baseline"] = {
                "genesis_id": "genesis_baseline:telegram_state_current_schema",
                "authority_ref": "owner-authority:gate0-evidence-closure-2026-07-29",
                "schema_digest": database["schema_digest"],
                "historical_legacy_migration_proven": False,
                "durable_ledger_deferred_to_gate": 2,
                "production_database_mutated": False,
            }
    return {
        "runtime_snapshot": runtime,
        "database_snapshot": databases,
    }


def _tree_hashes(root: pathlib.Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): file_digest(path)
        for path in root.rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    }


def test_status_only_receipt_flip_cannot_close_security_or_tests(
    tmp_path: pathlib.Path,
) -> None:
    candidate = _copy_candidate(tmp_path)
    gate = candidate / "docs/gates/gate-00-product-contract-baseline"
    core = prepare_precapture(candidate)
    dependencies_path = gate / "evidence/dependency-inventory.json"
    dependencies = _load(dependencies_path)
    dependencies["verification_toolchain"]["candidate_binding"].update(
        {"status": "verified", "reason_code": None}
    )
    write_json(dependencies_path, dependencies)
    tests_path = gate / "evidence/test-inventory.json"
    tests = _load(tests_path)
    tests["candidate_binding"].update(
        {"status": "verified", "reason_code": None}
    )
    write_json(tests_path, tests)
    refreshed = prepare_precapture(candidate)
    assert refreshed["input_tree_digest"] == core["input_tree_digest"]
    handoff = _load(gate / "fixtures/contracts/valid/gate-handoff.json")
    rows = {row["id"]: row for row in handoff["acceptance"]}
    assert rows["G0-08"]["status"] == "blocked"
    assert rows["G0-12"]["status"] == "blocked"
    assert "TEST_TREE_BINDING_NOT_VERIFIED" in handoff["release_readiness_blockers"]
    assert "VERIFIER_TREE_BINDING_NOT_VERIFIED" in handoff["release_readiness_blockers"]


@pytest.mark.parametrize(
    "target",
    [
        ("secret_scan", "triage"),
        ("verification_toolchain", "gitleaks"),
    ],
)
def test_nested_scanner_receipt_extra_field_is_rejected(
    tmp_path: pathlib.Path,
    target: tuple[str, str],
) -> None:
    candidate = _copy_candidate(tmp_path)
    gate = candidate / "docs/gates/gate-00-product-contract-baseline"
    core = _bind_synthetic_verifier(candidate)
    dependencies = _load(gate / "evidence/dependency-inventory.json")
    assert verifier_binding_verified(
        dependencies,
        core["input_tree_digest"],
        core["input_generated_at"],
        len(core["input_entries"]),
    )
    attacked = copy.deepcopy(dependencies)
    attacked[target[0]][target[1]]["raw_match"] = "forbidden-secret-shaped-extra"
    assert not verifier_binding_verified(
        attacked,
        core["input_tree_digest"],
        core["input_generated_at"],
        len(core["input_entries"]),
    )


def test_verifier_binding_rejects_inexact_gitleaks_scan_count(
    tmp_path: pathlib.Path,
) -> None:
    candidate = _copy_candidate(tmp_path)
    gate = candidate / "docs/gates/gate-00-product-contract-baseline"
    core = _bind_synthetic_verifier(candidate)
    dependencies = _load(gate / "evidence/dependency-inventory.json")
    expected_scan_count = len(core["input_entries"])
    assert dependencies["secret_scan"]["scanned_file_count"] == expected_scan_count
    assert (
        dependencies["verification_toolchain"]["gitleaks"]["scanned_file_count"]
        == expected_scan_count
    )

    attacked = copy.deepcopy(dependencies)
    attacked["secret_scan"]["scanned_file_count"] = expected_scan_count + 1
    assert not verifier_binding_verified(
        attacked,
        core["input_tree_digest"],
        core["input_generated_at"],
        expected_scan_count,
    )


def test_external_authoritative_input_tamper_invalidates_all_binding(
    tmp_path: pathlib.Path,
) -> None:
    candidate = _copy_candidate(tmp_path)
    core = prepare_precapture(candidate)
    source = (
        candidate
        / "docs/gates/gate-02-scope-document-contracts/ARCHITECTURE.md"
    )
    original = source.read_bytes()
    source.write_bytes(original + b" ")
    with pytest.raises(RuntimeError, match="frozen input tree changed"):
        verify_precapture(candidate)
    with pytest.raises(RuntimeError, match="frozen input tree changed"):
        record_review(
            candidate,
            level="l1",
            observed_at=dt.datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
    with pytest.raises(RuntimeError, match="frozen input tree changed"):
        seal_gate0(candidate)
    source.write_bytes(original)
    assert verify_precapture(candidate) == core


def test_runtime_and_test_tree_tamper_invalidates_frozen_input(
    tmp_path: pathlib.Path,
) -> None:
    candidate = _copy_candidate(tmp_path)
    core = prepare_precapture(candidate)
    frozen_paths = {entry["path"] for entry in core["input_entries"]}
    targets = (
        candidate / "scripts/run_telegram_mvp1.py",
        candidate / "src/application/windows_singleton.py",
        candidate / "tests/test_main.py",
    )

    for target in targets:
        relative = target.relative_to(candidate).as_posix()
        assert relative in frozen_paths
        original = target.read_bytes()
        target.write_bytes(original + b" ")
        with pytest.raises(RuntimeError, match="frozen input tree changed"):
            verify_precapture(candidate)
        target.write_bytes(original)
        assert verify_precapture(candidate) == core


def test_git_identity_and_status_drift_invalidates_precapture(
    tmp_path: pathlib.Path,
) -> None:
    candidate = _copy_candidate(tmp_path)
    core = prepare_precapture(candidate)
    status_drift = candidate / "gate0-untracked-status-drift.txt"
    status_drift.write_text("synthetic", encoding="utf-8")

    with pytest.raises(RuntimeError, match="frozen Git status changed"):
        verify_precapture(candidate)

    status_drift.unlink()
    assert verify_precapture(candidate) == core
    assert core["repository_head"]
    assert core["repository_branch"]
    assert core["git_status_digest"].startswith("sha256:")



@pytest.mark.parametrize(
    "relative",
    (
        "src/.env",
        "src/credentials.json",
        "tests/runtime.sqlite3",
        "tests/runtime.sqlite3-wal",
        "tests/private.key",
    ),
)
def test_sensitive_or_database_candidate_is_rejected_before_content_read(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
) -> None:
    candidate = _copy_candidate(tmp_path)
    attack = candidate / relative
    attack.parent.mkdir(parents=True, exist_ok=True)
    attack.write_text("synthetic-do-not-read", encoding="utf-8")
    core_path = (
        candidate
        / "docs/gates/gate-00-product-contract-baseline/evidence/pre-capture-core.json"
    )
    core_before = core_path.read_bytes()
    module = sys.modules["gate0_precapture"]
    original_digest = module.file_digest

    def guarded_digest(path: pathlib.Path) -> str:
        if pathlib.Path(path) == attack:
            raise AssertionError("forbidden candidate content was read")
        return original_digest(path)

    monkeypatch.setattr(module, "file_digest", guarded_digest)
    with pytest.raises(
        RuntimeError,
        match="secret or database input is not authorized",
    ):
        prepare_precapture(candidate)
    assert attack.read_text(encoding="utf-8") == "synthetic-do-not-read"
    assert core_path.read_bytes() == core_before


def test_candidate_symlink_is_rejected_without_external_content_read(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _copy_candidate(tmp_path)
    external = tmp_path / "outside-sentinel.py"
    external.write_text("external-sentinel", encoding="utf-8")
    attack = candidate / "src/linked-sentinel.py"
    try:
        attack.symlink_to(external)
    except OSError:
        pytest.skip("file symlinks are unavailable on this Windows host")
    module = sys.modules["gate0_precapture"]
    original_digest = module.file_digest

    def guarded_digest(path: pathlib.Path) -> str:
        if pathlib.Path(path) in {attack, external}:
            raise AssertionError("external linked content was read")
        return original_digest(path)

    monkeypatch.setattr(module, "file_digest", guarded_digest)
    with pytest.raises(RuntimeError, match="reparse topology is not authorized"):
        prepare_precapture(candidate)
    assert external.read_text(encoding="utf-8") == "external-sentinel"


def test_atomic_repo_read_rejects_swapped_external_handle_before_read(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    target = root / "src/input.py"
    target.parent.mkdir(parents=True)
    target.write_text("candidate", encoding="utf-8")
    external = tmp_path / "outside-sentinel.py"
    external.write_text("external-sentinel", encoding="utf-8")
    external_fd = os.open(external, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    original_open = os.open
    read_attempted = False

    def swapped_open(path: os.PathLike[str] | str, flags: int) -> int:
        if pathlib.Path(path) == target:
            return os.dup(external_fd)
        return original_open(path, flags)

    def guarded_read(fd: int, size: int) -> bytes:
        nonlocal read_attempted
        read_attempted = True
        raise AssertionError("swapped external handle content was read")

    monkeypatch.setattr(os, "open", swapped_open)
    monkeypatch.setattr(os, "read", guarded_read)
    try:
        with pytest.raises(RuntimeError, match="opened file identity changed"):
            _read_repo_regular_bytes(root, target)
    finally:
        os.close(external_fd)
    assert not read_attempted
    assert external.read_text(encoding="utf-8") == "external-sentinel"


def test_external_source_ref_is_rejected_before_target_probe(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _copy_candidate(tmp_path)
    inventory_path = (
        candidate
        / "docs/gates/gate-00-product-contract-baseline/evidence/documentation-inventory.json"
    )
    inventory = _load(inventory_path)
    inventory["current_worktree_documents"][0]["path"] = "../../outside-sentinel"
    write_json(inventory_path, inventory)
    original_is_file = pathlib.Path.is_file

    def guarded_is_file(path: pathlib.Path) -> bool:
        try:
            path.relative_to(candidate)
        except ValueError as error:
            raise AssertionError("external source_ref target was probed") from error
        return original_is_file(path)

    monkeypatch.setattr(pathlib.Path, "is_file", guarded_is_file)
    gate = candidate / "docs/gates/gate-00-product-contract-baseline"
    with pytest.raises(
        RuntimeError,
        match="repository input path escaped canonical root",
    ):
        authoritative_external_paths(candidate, gate)

def test_candidate_discovery_has_no_following_path_apis() -> None:
    source = inspect.getsource(
        sys.modules["gate0_precapture"]._candidate_paths
    )
    assert ".rglob(" not in source
    assert ".resolve(" not in source
    assert ".is_file(" not in source
    assert "os.lstat(" in source
    assert "os.scandir(" in source
    assert "follow_symlinks=False" in source


def test_freeze_hashes_use_atomic_validated_handles() -> None:
    module = sys.modules["gate0_precapture"]
    entry_source = inspect.getsource(module._entry)
    status_source = inspect.getsource(sys.modules["collect_gate0_snapshot"]._status_entries)
    assert "_read_repo_regular_bytes(" in entry_source
    assert "file_digest(" not in entry_source
    assert ".read_bytes(" not in status_source


def test_precapture_cli_drift_failure_is_closed_and_path_free(
    tmp_path: pathlib.Path,
) -> None:
    candidate = _copy_candidate(tmp_path)
    prepare_precapture(candidate)
    source = (
        candidate
        / "docs/gates/gate-02-scope-document-contracts/ARCHITECTURE.md"
    )
    source.write_bytes(source.read_bytes() + b" ")

    completed = subprocess.run(
        [
            sys.executable,
            str(candidate / "tests/gate0/gate0_precapture.py"),
            "readback",
            "--root",
            str(candidate),
        ],
        cwd=candidate,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert json.loads(completed.stderr) == {
        "schema": "nobus.gate0.precapture.v1",
        "result": "blocked",
        "error_stage": "readback",
    }
    combined = completed.stdout + completed.stderr
    assert "Traceback" not in combined
    assert str(candidate) not in combined
    assert str(source) not in combined


def test_precapture_cli_invalid_mode_is_closed_and_argument_free(
    tmp_path: pathlib.Path,
) -> None:
    script = ROOT / "tests/gate0/gate0_precapture.py"
    secret_mode = "token=must-not-escape"
    secret_root = tmp_path / "root-must-not-escape"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            secret_mode,
            "--root",
            str(secret_root),
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
        "schema": "nobus.gate0.precapture.v1",
        "result": "blocked",
        "error_stage": "entry",
    }
    combined = completed.stdout + completed.stderr
    assert secret_mode not in combined
    assert str(secret_root) not in combined
    assert str(script) not in combined
    assert "Traceback" not in combined
    assert "usage:" not in combined
    assert "invalid choice" not in combined


def test_precapture_cli_rejects_noncanonical_roots_before_io(
    tmp_path: pathlib.Path,
) -> None:
    script = ROOT / "tests/gate0/gate0_precapture.py"
    absent_root = tmp_path / "must-not-be-created"
    live_root = ROOT.parent / "worktrees/telegram-live"

    for mode, rejected_root in (
        ("prepare", absent_root),
        ("readback", live_root),
    ):
        completed = subprocess.run(
            [
                sys.executable,
                str(script),
                mode,
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
            "schema": "nobus.gate0.precapture.v1",
            "result": "blocked",
            "error_stage": "canonical_repo_authority",
        }
        combined = completed.stdout + completed.stderr
        assert str(rejected_root) not in combined
        assert str(script) not in combined
        assert "Traceback" not in combined
        assert "usage:" not in combined

    assert not absent_root.exists()


def test_precapture_cli_keyboard_interrupt_is_closed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = sys.modules["gate0_precapture"]
    script = ROOT / "tests/gate0/gate0_precapture.py"

    def interrupted() -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(module, "main", interrupted)
    monkeypatch.setattr(
        sys,
        "argv",
        [str(script), "readback", "--root", "must-not-escape"],
    )

    assert module.cli() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "schema": "nobus.gate0.precapture.v1",
        "result": "blocked",
        "error_stage": "readback",
    }
    assert "Traceback" not in captured.err
    assert str(script) not in captured.err
    assert "must-not-escape" not in captured.err


def test_full_bounded_projection_review_seal_and_tamper_rejection(
    tmp_path: pathlib.Path,
) -> None:
    candidate = _copy_candidate(tmp_path)
    gate = candidate / "docs/gates/gate-00-product-contract-baseline"
    frozen = _bind_synthetic_verifier(candidate)
    snapshot = _fresh_snapshot(candidate)
    before = _tree_hashes(candidate)
    started = time.monotonic()
    first_plan = project_snapshot(candidate, snapshot)
    after_first = _tree_hashes(candidate)
    changed = {
        path
        for path in before.keys() | after_first.keys()
        if before.get(path) != after_first.get(path)
    }
    assert changed
    assert changed <= set(POST_CAPTURE_CHANGED_PATHS)
    assert first_plan["ready_projection"] is True
    assert first_plan["elapsed_seconds"] < 120
    assert verify_precapture(candidate) == frozen

    second_plan = project_snapshot(candidate, snapshot)
    assert _tree_hashes(candidate) == after_first
    assert second_plan["capture_digest"] == first_plan["capture_digest"]

    product_path = gate / "product/product-contract.json"
    product_bytes = product_path.read_bytes()
    product_path.write_bytes(product_bytes + b" ")
    with pytest.raises(RuntimeError, match="frozen input tree changed"):
        record_review(
            candidate,
            level="l1",
            observed_at=dt.datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
    product_path.write_bytes(product_bytes)
    verify_precapture(candidate)

    for level in ("l1", "l2", "l3"):
        record_review(
            candidate,
            level=level,
            observed_at=dt.datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
        receipt = _load(gate / "verification" / f"{level}.json")
        assert receipt["stage"] == "post_capture"
        assert receipt["frozen_tree_digest"] == frozen["frozen_tree_digest"]
        assert receipt["capture_digest"] == first_plan["capture_digest"]
        assert receipt["review_tree_digest"].startswith("sha256:")

    for relative in (
        "evidence/baseline-evidence.json",
        "fixtures/contracts/valid/gate-handoff.json",
    ):
        path = gate / relative
        original = path.read_bytes()
        path.write_bytes(original + b" ")
        with pytest.raises(
            RuntimeError,
            match=(
                "canonical core digest index"
                if relative.startswith("evidence/baseline")
                else "Gate 0 seal preconditions"
            ),
        ):
            seal_gate0(candidate)
        path.write_bytes(original)
    seal_gate0(candidate)
    assert _load(gate / "fixtures/contracts/valid/gate-handoff.json")["status"] == "ready"
    manifest = _load(gate / "evidence/evidence-manifest.json")
    for entry in manifest["entries"]:
        path = candidate / pathlib.PurePosixPath(entry["path"])
        assert path.stat().st_size == entry["bytes"]
        assert file_digest(path) == entry["sha256"]
    assert time.monotonic() - started < 120
