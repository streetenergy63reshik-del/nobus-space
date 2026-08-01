"""Freeze and project Gate 0 evidence without collecting live state."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import os
import pathlib
import stat
import sys
import time
from typing import Any

from collect_gate0_snapshot import (
    _read_repo_regular_bytes,
    _safe_repo_regular_file,
    _status_entries,
    _unsafe_artifact_reason,
    canonical_bytes,
    digest_bytes,
    git,
)
from gate0_core_paths import core_artifact_paths
from gate0_normative_catalog import load_normative_catalog
from gate0_lifecycle import (
    REQUIRED_VERIFIER_CHECKS,
    authoritative_database_set,
    capture_lifecycle,
    database_capture_lifecycle,
    database_claim,
    runtime_binding_verified,
    test_binding_verified,
    verifier_binding_verified,
)
from generate_gate0_artifacts import (
    build_manifest,
    decision_register,
    file_digest,
    handoff_markdown,
    normalized_dirty,
    write_acceptance_score,
    write_json,
    write_text,
)
from normalize_gate0_contracts import (
    digest,
    fix_baseline,
    fix_capture_enclosure,
    fix_handoff,
    normalize,
    normalized_baseline,
)


UTC = dt.timezone.utc
GATE_REL = "docs/gates/gate-00-product-contract-baseline"
PRECATURE_REL = f"{GATE_REL}/evidence/pre-capture-core.json"
RECEIPT_PATHS = {
    f"{GATE_REL}/evidence/dependency-inventory.json",
    f"{GATE_REL}/evidence/dirty-manifest.json",
    f"{GATE_REL}/evidence/test-inventory.json",
}
CAPTURE_DEPENDENT_PATHS = {
    f"{GATE_REL}/HANDOFF.md",
    f"{GATE_REL}/evidence/baseline-evidence.json",
    f"{GATE_REL}/evidence/component-manifest.json",
    f"{GATE_REL}/evidence/current-corpus-baseline.json",
    f"{GATE_REL}/evidence/database-inventory.json",
    f"{GATE_REL}/evidence/evidence-manifest.json",
    f"{GATE_REL}/evidence/runtime-inventory.json",
    f"{GATE_REL}/fixtures/contracts/valid/baseline-evidence.json",
    f"{GATE_REL}/fixtures/contracts/valid/gate-handoff.json",
    f"{GATE_REL}/fixtures/contracts/invalid/baseline-bool-as-int.json",
    f"{GATE_REL}/fixtures/contracts/invalid/baseline-naive-timestamp.json",
    f"{GATE_REL}/fixtures/contracts/invalid/baseline-non-utc-timestamp.json",
    f"{GATE_REL}/fixtures/contracts/invalid/capability-naive-timestamp.json",
    f"{GATE_REL}/fixtures/contracts/invalid/capability-non-utc-timestamp.json",
    f"{GATE_REL}/fixtures/contracts/invalid/gate-handoff-naive-timestamp.json",
    f"{GATE_REL}/fixtures/contracts/invalid/gate-handoff-non-utc-timestamp.json",
    f"{GATE_REL}/fixtures/golden/core-digests.json",
    f"{GATE_REL}/fixtures/golden/gate-acceptance-score.json",
    f"{GATE_REL}/verification/l1.json",
    f"{GATE_REL}/verification/l2.json",
    f"{GATE_REL}/verification/l3.json",
}
POST_CAPTURE_CHANGED_PATHS = sorted(CAPTURE_DEPENDENT_PATHS)
REVIEW_SUBMISSION_PATHS = {
    f"{GATE_REL}/verification/submissions/{level}.json"
    for level in ("l1", "l2", "l3")
}
REVIEW_MUTABLE_PATHS = {
    f"{GATE_REL}/evidence/evidence-manifest.json",
    f"{GATE_REL}/verification/l1.json",
    f"{GATE_REL}/verification/l2.json",
    f"{GATE_REL}/verification/l3.json",
    *REVIEW_SUBMISSION_PATHS,
}

RUNTIME_TEST_ROOTS = ("ops", "scripts", "src", "tests")
TRACKED_INPUT_EXCLUDED_PREFIXES = (".nobus-quality/",)
STATUS_VOLATILE_PATHS = {
    *CAPTURE_DEPENDENT_PATHS,
    *RECEIPT_PATHS,
    *REVIEW_SUBMISSION_PATHS,
    PRECATURE_REL,
}


SCRIPT_CANONICAL_ROOT = pathlib.Path(
    os.path.abspath(pathlib.Path(__file__).parents[2])
)


class ClosedArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError("invalid command line")


class CanonicalRepoAuthorityError(ValueError):
    pass


def _validated_cli_root(value: pathlib.Path) -> pathlib.Path:
    supplied = pathlib.Path(os.path.abspath(value))
    if os.path.normcase(str(supplied)) != os.path.normcase(
        str(SCRIPT_CANONICAL_ROOT)
    ):
        raise CanonicalRepoAuthorityError("canonical repository authority failed")
    return SCRIPT_CANONICAL_ROOT


def _load(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validated_repo_input(root: pathlib.Path, relative: str) -> pathlib.Path:
    normalized = pathlib.PurePosixPath(relative)
    if (
        normalized.is_absolute()
        or ".." in normalized.parts
        or "\\" in relative
        or (normalized.parts and ":" in normalized.parts[0])
    ):
        raise RuntimeError("repository input path escaped canonical root")
    if _unsafe_artifact_reason(normalized.as_posix()) is not None:
        raise RuntimeError("secret or database input is not authorized")
    candidate = pathlib.Path(os.path.abspath(root / normalized))
    if not _safe_repo_regular_file(root, candidate):
        raise RuntimeError("repository input topology is not a regular file")
    return candidate


def _entry(root: pathlib.Path, path: pathlib.Path) -> dict[str, Any]:
    relative = path.relative_to(root).as_posix()
    safe_path = _validated_repo_input(root, relative)
    content = _read_repo_regular_bytes(root, safe_path)
    return {
        "path": relative,
        "sha256": digest_bytes(content),
        "bytes": len(content),
    }


def _candidate_paths(root: pathlib.Path, gate: pathlib.Path) -> list[pathlib.Path]:
    paths: list[pathlib.Path] = []
    skipped_directories = {"__pycache__", ".hypothesis", ".pytest_cache"}
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

    def safe_walk(base: pathlib.Path) -> None:
        base_metadata = os.lstat(base)
        if (
            not stat.S_ISDIR(base_metadata.st_mode)
            or stat.S_ISLNK(base_metadata.st_mode)
            or getattr(base_metadata, "st_file_attributes", 0) & reparse_flag
        ):
            raise RuntimeError("candidate directory topology is not authorized")
        with os.scandir(base) as entries:
            for entry in entries:
                if entry.name in skipped_directories:
                    continue
                relative = pathlib.Path(entry.path).relative_to(root).as_posix()
                if _unsafe_artifact_reason(relative) is not None:
                    raise RuntimeError("secret or database input is not authorized")
                metadata = entry.stat(follow_symlinks=False)
                if (
                    stat.S_ISLNK(metadata.st_mode)
                    or getattr(metadata, "st_file_attributes", 0) & reparse_flag
                ):
                    raise RuntimeError("candidate reparse topology is not authorized")
                if stat.S_ISDIR(metadata.st_mode):
                    safe_walk(pathlib.Path(entry.path))
                elif stat.S_ISREG(metadata.st_mode):
                    if pathlib.Path(entry.name).suffix not in {".pyc", ".pyo"}:
                        paths.append(pathlib.Path(os.path.abspath(entry.path)))

    for base in (gate, *(root / name for name in RUNTIME_TEST_ROOTS)):
        safe_walk(base)
    paths.append(_validated_repo_input(root, ".gitattributes"))
    return sorted(set(paths))


def _tracked_paths(root: pathlib.Path) -> list[pathlib.Path]:
    """Return the exact repository-tracked closure without local ignored data."""

    raw = git(root, "ls-files", "-z", strip=False)
    paths: list[pathlib.Path] = []
    for value in raw.split("\0"):
        if not value or value.startswith(TRACKED_INPUT_EXCLUDED_PREFIXES):
            continue
        paths.append(_validated_repo_input(root, value))
    return sorted(set(paths))


def _normalized_status_projection(
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    projection = copy.deepcopy(entries)
    for entry in projection:
        if entry.get("owner") == "gate0":
            entry["safe_content_sha256"] = None
            entry["content_omitted_reason"] = "covered_by_evidence_manifest"
    return [
        entry
        for entry in projection
        if entry.get("path") not in STATUS_VOLATILE_PATHS
    ]


def authoritative_external_paths(
    root: pathlib.Path,
    gate: pathlib.Path,
) -> list[pathlib.Path]:
    """Resolve the exact non-artifact bytes from which Gate 0 is derived."""

    relatives: set[str] = set()

    def add_ref(value: object) -> None:
        if isinstance(value, str):
            relative = value.split("#", 1)[0]
            if relative:
                relatives.add(relative)

    for source in load_normative_catalog(root)["required_sources"]:
        if not isinstance(source, dict):
            raise ValueError("normative source entry is not an object")
        add_ref(source.get("path"))

    documentation = _load(gate / "evidence/documentation-inventory.json")
    for entry in documentation.get("current_worktree_documents", []):
        if isinstance(entry, dict):
            add_ref(entry.get("path"))

    product = _load(gate / "product/product-contract.json")
    for family in product.get("contract_families", []):
        if isinstance(family, dict):
            add_ref(family.get("source_ref"))
    for contract in product.get("contract_catalog", []):
        if isinstance(contract, dict):
            add_ref(contract.get("source_ref"))

    schema_bundle = _load(
        gate / "fixtures/golden/target-contract-schema-projections.json"
    )
    for source in schema_bundle.get("authoritative_sources", []):
        add_ref(source)

    examples = _load(gate / "fixtures/golden/contract-examples.json")
    for example in examples.get("examples", {}).values():
        if isinstance(example, dict):
            add_ref(example.get("source_ref"))

    parser = _load(gate / "evidence/current-corpus-baseline.json")
    add_ref(parser.get("parser_source_ref"))

    databases = _load(gate / "evidence/database-inventory.json")
    for database in databases.get("databases", []):
        if not isinstance(database, dict):
            continue
        for migration in database.get("source_migrations", []):
            if isinstance(migration, dict):
                add_ref(migration.get("source_ref"))

    return sorted({
        _validated_repo_input(root, relative)
        for relative in relatives
    })


def _freeze_paths(root: pathlib.Path, gate: pathlib.Path) -> list[pathlib.Path]:
    candidates = _candidate_paths(root, gate)
    tracked = _tracked_paths(root)
    external = authoritative_external_paths(root, gate)
    return sorted({
        *tracked,
        *candidates,
        *external,
    })


def _input_entries(root: pathlib.Path, gate: pathlib.Path) -> list[dict[str, Any]]:
    excluded = {
        *CAPTURE_DEPENDENT_PATHS,
        *RECEIPT_PATHS,
        *REVIEW_SUBMISSION_PATHS,
        PRECATURE_REL,
    }
    return [
        _entry(root, path)
        for path in _freeze_paths(root, gate)
        if path.relative_to(root).as_posix() not in excluded
    ]


def _receipt_entries(root: pathlib.Path) -> list[dict[str, Any]]:
    return [
        _entry(root, root / pathlib.PurePosixPath(relative))
        for relative in sorted(RECEIPT_PATHS)
    ]


def review_tree_digest(root: pathlib.Path) -> str:
    """Digest every exact candidate artifact reviewers assess, without recursion."""

    gate = root / GATE_REL
    entries = [
        _entry(root, path)
        for path in _freeze_paths(root, gate)
        if path.relative_to(root).as_posix() not in REVIEW_MUTABLE_PATHS
    ]
    return digest_bytes(canonical_bytes(entries))


def _stable_time(old: dict[str, Any] | None, new_projection: dict[str, Any]) -> str:
    if old is not None:
        old_projection = {
            key: value
            for key, value in old.items()
            if key not in {"generated_at", "frozen_tree_digest"}
        }
        comparable_new = {
            key: value
            for key, value in new_projection.items()
            if key not in {"generated_at", "frozen_tree_digest"}
        }
        if old_projection == comparable_new:
            return old["generated_at"]
    return dt.datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _refresh_dirty(root: pathlib.Path, gate: pathlib.Path) -> str:
    path = gate / "evidence/dirty-manifest.json"
    old = _load(path)
    head_commit = git(root, "rev-parse", "HEAD")
    branch = git(root, "symbolic-ref", "--short", "-q", "HEAD")
    snapshot = {
        "observed_at": old["observed_at"],
        "repository": {
            "head_commit": head_commit,
            "branch": branch,
            "dirty_entries": _status_entries(root),
        },
        "runtime_release": old["runtime_release"],
    }
    refreshed = normalized_dirty(snapshot)
    old_without_time = {key: value for key, value in old.items() if key != "observed_at"}
    new_without_time = {
        key: value for key, value in refreshed.items() if key != "observed_at"
    }
    observed_at = (
        old["observed_at"]
        if old_without_time == new_without_time
        else dt.datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )
    refreshed["observed_at"] = observed_at
    write_json(path, refreshed)
    return observed_at


def _bind_templates(
    gate: pathlib.Path,
    input_tree_digest: str,
    input_generated_at: str,
) -> None:
    dependencies_path = gate / "evidence/dependency-inventory.json"
    dependencies = _load(dependencies_path)
    verifier = dependencies["verification_toolchain"]
    existing = verifier.get("candidate_binding", {})
    if (
        existing.get("input_tree_digest") == input_tree_digest
        and existing.get("input_generated_at") == input_generated_at
        and set(existing.get("checks", {})) == REQUIRED_VERIFIER_CHECKS
    ):
        binding = existing
    else:
        binding = {
            "status": "rerun_required",
            "reason_code": "FROZEN_INPUT_TREE_CHANGED",
            "input_tree_digest": input_tree_digest,
            "input_generated_at": input_generated_at,
            "lock_refs": [
                "tests/gate0/verifier-requirements.txt",
                "tests/gate0/verifier-toolchain.json",
            ],
            "authority_ref": None,
            "official_sources_only": True,
            "hashes_verified": False,
            "canonical_venv_mutated": False,
            "network_or_install_performed": False,
            "isolated_environment_digest": None,
            "checks": {
                name: {
                    "status": "not_run",
                    "tool_version": verifier["versions"].get(name),
                    "scanned_input_tree_digest": input_tree_digest,
                    "started_at": None,
                    "finished_at": None,
                    "report_sha256": None,
                }
                for name in sorted(REQUIRED_VERIFIER_CHECKS)
            },
        }
    verifier["candidate_binding"] = binding
    write_json(dependencies_path, dependencies)

    tests_path = gate / "evidence/test-inventory.json"
    tests = _load(tests_path)
    existing_tests = tests.get("candidate_binding", {})
    if (
        existing_tests.get("input_tree_digest") == input_tree_digest
        and existing_tests.get("input_generated_at") == input_generated_at
        and set(existing_tests.get("runs", {}))
        == {"targeted_gate0", "full_pytest"}
    ):
        tests_binding = existing_tests
    else:
        tests_binding = {
            "status": "rerun_required",
            "reason_code": "FROZEN_INPUT_TREE_CHANGED",
            "input_tree_digest": input_tree_digest,
            "input_generated_at": input_generated_at,
            "network_or_provider_calls_performed": False,
            "canonical_venv_mutated": False,
            "environment_digest": None,
            "runs": {
                name: {
                    "status": "not_run",
                    "passed": 0,
                    "failed": 0,
                    "skipped": 0,
                    "scanned_input_tree_digest": input_tree_digest,
                    "started_at": None,
                    "finished_at": None,
                    "report_sha256": None,
                }
                for name in ("targeted_gate0", "full_pytest")
            },
        }
    tests["candidate_binding"] = tests_binding
    write_json(tests_path, tests)


def _write_verification_templates(
    gate: pathlib.Path,
    frozen_tree_digest: str,
    capture_digest: str | None = None,
) -> None:
    handoff = _load(gate / "fixtures/contracts/valid/gate-handoff.json")
    core_digest = file_digest(gate / "fixtures/golden/core-digests.json")
    for level in ("l1", "l2", "l3"):
        write_json(
            gate / "verification" / f"{level}.json",
            {
                "schema": "nobus.gate0.verification_receipt.v1",
                "level": level,
                "stage": "post_capture" if capture_digest else "pre_capture",
                "verdict": "pending",
                "observed_at": handoff["generated_at"],
                "candidate_core_digest": core_digest,
                "frozen_tree_digest": frozen_tree_digest,
                "capture_digest": capture_digest,
                "review_tree_digest": review_tree_digest(gate.parents[2]),
                "findings": [],
                "blocking_criteria": handoff["blocking_criteria"],
                "release_blockers": handoff["release_readiness_blockers"],
                "hidden_reasoning_persisted": False,
            },
        )


def prepare_precapture(root: pathlib.Path) -> dict[str, Any]:
    gate = root / GATE_REL
    # Materialize deterministic contract upgrades before hashing frozen inputs.
    normalize(root, gate)
    write_json(gate / "decisions" / "decision-register.json", decision_register())
    # Reject unsafe topology before dirty/evidence metadata can be written.
    _freeze_paths(root, gate)
    _refresh_dirty(root, gate)
    inputs = _input_entries(root, gate)
    input_tree_digest = digest_bytes(canonical_bytes(inputs))
    core_path = root / PRECATURE_REL
    old_core = _load(core_path) if core_path.is_file() else None
    input_generated_at = (
        old_core["input_generated_at"]
        if old_core is not None
        and old_core.get("input_tree_digest") == input_tree_digest
        and isinstance(old_core.get("input_generated_at"), str)
        else dt.datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )
    _bind_templates(gate, input_tree_digest, input_generated_at)

    dirty = _load(gate / "evidence/dirty-manifest.json")
    repository_head = dirty["head_commit"]
    repository_branch = dirty["branch"]
    git_status_digest = digest_bytes(
        canonical_bytes(_normalized_status_projection(dirty["entries"]))
    )

    # The first provisional core makes its own path visible to dirty-manifest.
    provisional = {
        "schema": "nobus.gate0.pre_capture_core.v1",
        "status": "pre_capture_ready",
        "input_entries": inputs,
        "input_tree_digest": input_tree_digest,
        "input_generated_at": input_generated_at,
        "receipt_entries": _receipt_entries(root),
        "repository_head": repository_head,
        "repository_branch": repository_branch,
        "git_status_digest": git_status_digest,
        "capture_dependent_paths": POST_CAPTURE_CHANGED_PATHS,
        "bounded_projection_contract": {
            "max_seconds": 120,
            "reuses_frozen_tests_and_release_scans": True,
            "runtime_or_provider_calls": False,
            "allowed_operations": [
                "sanitized_snapshot_projection",
                "manifest_rebuild",
                "bound_l1_l2_l3_receipts",
                "exact_readback",
            ],
        },
    }
    provisional["frozen_tree_digest"] = digest_bytes(canonical_bytes(provisional))
    provisional["generated_at"] = _stable_time(
        _load(root / PRECATURE_REL) if (root / PRECATURE_REL).is_file() else None,
        provisional,
    )
    write_json(root / PRECATURE_REL, provisional)

    _refresh_dirty(root, gate)
    dirty = _load(gate / "evidence/dirty-manifest.json")
    provisional["repository_head"] = dirty["head_commit"]
    provisional["repository_branch"] = dirty["branch"]
    provisional["git_status_digest"] = digest_bytes(
        canonical_bytes(_normalized_status_projection(dirty["entries"]))
    )
    provisional["receipt_entries"] = _receipt_entries(root)
    projection = {
        key: value for key, value in provisional.items()
        if key not in {"frozen_tree_digest", "generated_at"}
    }
    provisional["frozen_tree_digest"] = digest_bytes(canonical_bytes(projection))
    old = _load(root / PRECATURE_REL)
    provisional["generated_at"] = _stable_time(old, projection)
    write_json(root / PRECATURE_REL, provisional)

    # Rebind all capture-derived evidence refs after receipt templates change.
    baseline = normalized_baseline(root, gate)
    write_json(gate / "evidence/baseline-evidence.json", baseline)
    write_json(gate / "fixtures/contracts/valid/baseline-evidence.json", baseline)
    cases = [
        json.loads(line)
        for line in (gate / "corpus/requests.v1.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    fix_baseline(root, gate, cases)
    fix_capture_enclosure(root, gate)
    fix_handoff(gate)
    normalize(root, gate)
    _rewrite_core_digest(root, gate)
    baseline = _load(gate / "evidence/baseline-evidence.json")
    runtime = _load(gate / "evidence/runtime-inventory.json")
    databases = _load(gate / "evidence/database-inventory.json")
    dependencies = _load(gate / "evidence/dependency-inventory.json")
    handoff = _load(gate / "fixtures/contracts/valid/gate-handoff.json")
    write_acceptance_score(
        gate,
        ready=False,
        blocked_criteria=handoff["blocking_criteria"],
    )
    write_text(
        gate / "HANDOFF.md",
        handoff_markdown(
            baseline,
            runtime,
            databases,
            dependencies,
            handoff,
            handoff["generated_at"],
            ready=False,
        ),
    )
    _write_verification_templates(gate, provisional["frozen_tree_digest"])
    write_json(
        gate / "evidence/evidence-manifest.json",
        build_manifest(root, gate, provisional["generated_at"]),
    )
    verify_precapture(root)
    return provisional


def verify_precapture(root: pathlib.Path) -> dict[str, Any]:
    core = _load(root / PRECATURE_REL)
    gate = root / GATE_REL
    actual_inputs = _input_entries(root, gate)
    actual_receipts = _receipt_entries(root)
    if actual_inputs != core["input_entries"]:
        raise RuntimeError("frozen input tree changed")

    dirty = _load(gate / "evidence/dirty-manifest.json")
    frozen_status = _normalized_status_projection(dirty["entries"])
    current_head = git(root, "rev-parse", "HEAD")
    current_branch = git(root, "symbolic-ref", "--short", "-q", "HEAD")
    current_status = _normalized_status_projection(_status_entries(root))
    if (
        current_head != core.get("repository_head")
        or current_branch != core.get("repository_branch")
        or dirty.get("head_commit") != core.get("repository_head")
        or dirty.get("branch") != core.get("repository_branch")
    ):
        raise RuntimeError("frozen Git identity changed")
    if current_status != frozen_status:
        raise RuntimeError("frozen Git status changed")
    if (
        digest_bytes(canonical_bytes(frozen_status))
        != core.get("git_status_digest")
    ):
        raise RuntimeError("frozen Git status digest mismatch")
    if actual_receipts != core["receipt_entries"]:
        raise RuntimeError("frozen receipt tree changed")
    projection = {
        key: value for key, value in core.items()
        if key not in {"frozen_tree_digest", "generated_at"}
    }
    if digest_bytes(canonical_bytes(projection)) != core["frozen_tree_digest"]:
        raise RuntimeError("pre-capture core digest mismatch")
    return core


def bind_receipts(root: pathlib.Path, receipt: dict[str, Any]) -> dict[str, Any]:
    """Bind sanitized offline verifier/test receipts to the exact frozen input."""

    required = {
        "schema",
        "input_tree_digest",
        "input_generated_at",
        "verification_toolchain",
        "vulnerability_check",
        "secret_scan",
        "test_inventory",
    }
    if set(receipt) != required or receipt.get("schema") != (
        "nobus.gate0.offline_verification_receipt.v1"
    ):
        raise ValueError("offline verification receipt shape is not exact")
    core = verify_precapture(root)
    if (
        receipt["input_tree_digest"] != core["input_tree_digest"]
        or receipt["input_generated_at"] != core["input_generated_at"]
    ):
        raise ValueError("offline verification receipt is not bound to frozen input")
    gate = root / GATE_REL
    dependency_path = gate / "evidence/dependency-inventory.json"
    test_path = gate / "evidence/test-inventory.json"
    dependencies = copy.deepcopy(_load(dependency_path))
    tests = copy.deepcopy(_load(test_path))
    verifier_receipt = receipt["verification_toolchain"]
    test_receipt = receipt["test_inventory"]
    if set(verifier_receipt) != {
        "candidate_binding",
        "dev_checks",
        "pip_audit",
        "gitleaks",
    } or set(test_receipt) != {
        "candidate_binding",
        "targeted_gate0",
        "full_pytest",
        "release_checks",
        "observed_at",
    }:
        raise ValueError("offline verification sub-receipt shape is not exact")
    dependencies["verification_toolchain"].update(verifier_receipt)
    dependencies["vulnerability_check"] = receipt["vulnerability_check"]
    dependencies["secret_scan"] = receipt["secret_scan"]
    tests.update(test_receipt)
    if not verifier_binding_verified(
        dependencies,
        core["input_tree_digest"],
        core["input_generated_at"],
        len(core["input_entries"]),
    ):
        raise ValueError("verifier receipt proof is incomplete or inconsistent")
    if not test_binding_verified(
        tests,
        core["input_tree_digest"],
        core["input_generated_at"],
    ):
        raise ValueError("test receipt proof is incomplete or inconsistent")
    write_json(dependency_path, dependencies)
    write_json(test_path, tests)
    return prepare_precapture(root)


def split_snapshot(snapshot: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    value = copy.deepcopy(snapshot)
    if "runtime_snapshot" in value:
        runtime = value["runtime_snapshot"]
        databases = value["database_snapshot"]
    else:
        databases = value.pop("database_snapshot")
        runtime = value
    if not isinstance(runtime, dict) or not isinstance(databases, dict):
        raise ValueError("sanitized snapshot must contain runtime and database objects")
    return runtime, databases


def projection_plan(
    snapshot: dict[str, Any],
    *,
    as_of: dt.datetime | None = None,
) -> dict[str, Any]:
    runtime, databases = split_snapshot(snapshot)
    lifecycle = capture_lifecycle(runtime, as_of=as_of)
    database_lifecycle = database_capture_lifecycle(
        databases,
        runtime,
        as_of=as_of,
    )
    database_statuses: dict[str, str] = {}
    genesis_verified = False
    raw_databases = databases.get("databases", [])
    for database in raw_databases:
        role = database.get("database_role", "unknown")
        if database.get("database_ref") != f"runtime-db:{role}":
            raise ValueError("database_ref must be runtime-db:<role>")
        _, status, genesis = database_claim(database, database_lifecycle)
        database_statuses[str(role)] = status
        genesis_verified = genesis_verified or genesis
    blockers = []
    role_set_verified = authoritative_database_set(raw_databases)
    all_databases_verified = role_set_verified and all(
        status == "VERIFIED" for status in database_statuses.values()
    )
    genesis_verified = genesis_verified and all_databases_verified
    if lifecycle != "FRESH":
        blockers.append("CAPTURE_NOT_FRESH")
    if database_lifecycle != "FRESH":
        blockers.append("DATABASE_CAPTURE_NOT_FRESH")
    if not runtime_binding_verified(runtime):
        blockers.append("RUNTIME_BINDING_NOT_VERIFIED")
    if not role_set_verified:
        blockers.append("DATABASE_ROLE_SET_INVALID")
    if not all_databases_verified:
        blockers.append("DATABASE_PROOF_NOT_VERIFIED")
    if not genesis_verified:
        blockers.append("TELEGRAM_GENESIS_NOT_VERIFIED")
    return {
        "capture_digest": digest_bytes(
            canonical_bytes(
                {
                    "runtime_snapshot": runtime,
                    "database_snapshot": databases,
                }
            )
        ),
        "capture_lifecycle": lifecycle,
        "database_capture_lifecycle": database_lifecycle,
        "database_statuses": database_statuses,
        "genesis_verified": genesis_verified,
        "blocking_reasons": sorted(set(blockers)),
        "ready_projection": not blockers,
        "changed_paths": POST_CAPTURE_CHANGED_PATHS,
        "reused_checks": [
            "targeted_pytest",
            "full_pytest",
            "jsonschema",
            "hypothesis",
            "import_linter",
            "pip_audit",
            "gitleaks",
        ],
        "forbidden_during_projection": [
            "network",
            "runtime_collection",
            "provider_calls",
            "pytest_or_scanner_rerun",
        ],
    }


def _rewrite_core_digest(root: pathlib.Path, gate: pathlib.Path) -> None:
    paths = core_artifact_paths(root)
    entries = [
        {"path": path.relative_to(root).as_posix(), "sha256": file_digest(path)}
        for path in sorted(paths)
    ]
    write_json(
        gate / "fixtures/golden/core-digests.json",
        {
            "schema": "nobus.gate0.core_digests.v1",
            "entries": entries,
            "core_digest": digest_bytes(canonical_bytes(entries)),
        },
    )


def project_snapshot(
    root: pathlib.Path,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    started = time.monotonic()
    core = verify_precapture(root)
    plan = projection_plan(snapshot)
    runtime, databases = split_snapshot(snapshot)
    gate = root / GATE_REL
    write_json(gate / "evidence/runtime-inventory.json", runtime)
    write_json(gate / "evidence/database-inventory.json", databases)

    baseline = normalized_baseline(root, gate)
    write_json(gate / "evidence/baseline-evidence.json", baseline)
    write_json(gate / "fixtures/contracts/valid/baseline-evidence.json", baseline)
    cases = [
        json.loads(line)
        for line in (gate / "corpus/requests.v1.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    fix_baseline(root, gate, cases)
    fix_capture_enclosure(root, gate)
    fix_handoff(gate)
    baseline = normalized_baseline(root, gate)
    write_json(gate / "evidence/baseline-evidence.json", baseline)
    write_json(gate / "fixtures/contracts/valid/baseline-evidence.json", baseline)
    fix_baseline(root, gate, cases)
    fix_capture_enclosure(root, gate)
    fix_handoff(gate)
    _rewrite_core_digest(root, gate)
    baseline = _load(gate / "evidence/baseline-evidence.json")
    dependencies = _load(gate / "evidence/dependency-inventory.json")
    handoff = _load(gate / "fixtures/contracts/valid/gate-handoff.json")
    write_acceptance_score(
        gate,
        ready=False,
        blocked_criteria=handoff["blocking_criteria"],
    )
    write_text(
        gate / "HANDOFF.md",
        handoff_markdown(
            baseline,
            runtime,
            databases,
            dependencies,
            handoff,
            handoff["generated_at"],
            ready=False,
        ),
    )
    _write_verification_templates(
        gate,
        core["frozen_tree_digest"],
        plan["capture_digest"],
    )
    write_json(
        gate / "evidence/evidence-manifest.json",
        build_manifest(root, gate, runtime["observed_at"]),
    )
    verify_precapture(root)
    plan["elapsed_seconds"] = round(time.monotonic() - started, 6)
    if plan["elapsed_seconds"] >= 120:
        raise RuntimeError("bounded post-capture projection exceeded 120 seconds")
    return plan


def main() -> None:
    parser = ClosedArgumentParser()
    parser.add_argument("mode", choices=("prepare", "bind", "plan", "project", "readback"))
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--snapshot", type=pathlib.Path)
    parser.add_argument("--receipt", type=pathlib.Path)
    args = parser.parse_args()
    root = _validated_cli_root(args.root)
    if args.mode == "prepare":
        result = prepare_precapture(root)
    elif args.mode == "readback":
        result = verify_precapture(root)
    elif args.mode == "bind":
        if args.receipt is None:
            parser.error("bind requires --receipt")
        result = bind_receipts(root, _load(args.receipt))
    else:
        if args.snapshot is None:
            parser.error(f"{args.mode} requires --snapshot")
        snapshot = _load(args.snapshot)
        result = (
            projection_plan(snapshot)
            if args.mode == "plan"
            else project_snapshot(root, snapshot)
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def _closed_failure_stage() -> str:
    allowed = {"prepare", "bind", "plan", "project", "readback"}
    return sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in allowed else "entry"


def cli() -> int:
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        stage = (
            "canonical_repo_authority"
            if isinstance(error, CanonicalRepoAuthorityError)
            else _closed_failure_stage()
        )
        print(
            json.dumps(
                {
                    "schema": "nobus.gate0.precapture.v1",
                    "result": "blocked",
                    "error_stage": stage,
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
