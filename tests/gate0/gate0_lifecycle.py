"""Pure lifecycle/proof rules shared by Gate 0 generators and tests."""

from __future__ import annotations

import copy
import datetime as dt
import re
from typing import Any


UTC = dt.timezone.utc
AUTHORITATIVE_DATABASE_ROLES = frozenset(
    {"business_notes", "core", "checkpoint", "telegram_state"}
)
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
REQUIRED_VERIFIER_CHECKS = frozenset(
    {"jsonschema", "hypothesis", "import_linter", "pip_audit", "gitleaks"}
)
VERIFIER_BINDING_KEYS = {
    "status",
    "reason_code",
    "input_tree_digest",
    "input_generated_at",
    "lock_refs",
    "authority_ref",
    "official_sources_only",
    "hashes_verified",
    "canonical_venv_mutated",
    "network_or_install_performed",
    "isolated_environment_digest",
    "checks",
}
VERIFIER_CHECK_KEYS = {
    "status",
    "tool_version",
    "scanned_input_tree_digest",
    "started_at",
    "finished_at",
    "report_sha256",
}
TEST_BINDING_KEYS = {
    "status",
    "reason_code",
    "input_tree_digest",
    "input_generated_at",
    "network_or_provider_calls_performed",
    "canonical_venv_mutated",
    "environment_digest",
    "runs",
}
TEST_RUN_KEYS = {
    "status",
    "passed",
    "failed",
    "skipped",
    "scanned_input_tree_digest",
    "started_at",
    "finished_at",
    "report_sha256",
}


def authoritative_database_set(value: object) -> bool:
    if not isinstance(value, list):
        return False
    roles = [
        item.get("database_role")
        for item in value
        if isinstance(item, dict)
    ]
    return len(roles) == len(AUTHORITATIVE_DATABASE_ROLES) and set(roles) == AUTHORITATIVE_DATABASE_ROLES


def _utc(value: object) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        return None
    return parsed.astimezone(UTC)


def capture_lifecycle(
    snapshot: dict[str, Any] | None,
    *,
    as_of: dt.datetime | None = None,
) -> str:
    """Return FRESH, STALE, UNVERIFIABLE, or NO_CAPTURE."""

    if not snapshot:
        return "NO_CAPTURE"
    explicit_status = str(snapshot.get("status", "")).upper()
    if explicit_status == "STALE":
        return "STALE"
    if explicit_status and explicit_status not in {"FRESH", "VERIFIED"}:
        return "UNVERIFIABLE"
    clock = snapshot.get("clock")
    if not isinstance(clock, dict) or clock.get("trusted") is not True:
        return "UNVERIFIABLE"
    observed_at = _utc(snapshot.get("observed_at"))
    if observed_at is None:
        return "NO_CAPTURE"
    fresh_until = _utc(snapshot.get("fresh_until"))
    if fresh_until is None:
        for claim in snapshot.get("claims", []):
            if claim.get("claim_id") == "current.telegram.runner":
                fresh_until = _utc(claim.get("fresh_until"))
                break
    if fresh_until is None:
        return "UNVERIFIABLE"
    now = (as_of or dt.datetime.now(UTC)).astimezone(UTC)
    return "FRESH" if observed_at <= now <= fresh_until else "STALE"


def runtime_binding_verified(snapshot: object) -> bool:
    """Require one scheduler-bound runner and one internally consistent commit/root."""

    if not isinstance(snapshot, dict):
        return False
    runtime_claim = snapshot.get("runtime_claim")
    database_binding = snapshot.get("database_binding")
    scheduler = snapshot.get("scheduler")
    if not all(
        isinstance(value, dict)
        for value in (runtime_claim, database_binding, scheduler)
    ):
        return False
    processes = [
        process
        for process in snapshot.get("processes", [])
        if isinstance(process, dict)
        and process.get("process_role") == "telegram_runner"
    ]
    if len(processes) != 1:
        return False
    process = processes[0]
    instances = process.get("instances")
    if (
        str(runtime_claim.get("status", "")).casefold() != "verified"
        or str(database_binding.get("status", "")).casefold() != "verified"
        or str(scheduler.get("status", "")).casefold() != "verified"
        or str(process.get("status", "")).casefold() != "verified"
        or process.get("observed_count") != 1
        or not isinstance(instances, list)
        or len(instances) != 1
        or not isinstance(instances[0], dict)
    ):
        return False
    instance = instances[0]
    commits = (
        runtime_claim.get("scheduled_commit"),
        runtime_claim.get("process_loaded_commit"),
        database_binding.get("scheduled_commit"),
        scheduler.get("scheduled_commit"),
        process.get("scheduled_commit"),
        process.get("loaded_commit"),
        instance.get("loaded_commit"),
    )
    if not all(
        isinstance(commit, str) and COMMIT_PATTERN.fullmatch(commit)
        for commit in commits
    ) or len(set(commits)) != 1:
        return False
    roots = (
        database_binding.get("root_profile"),
        scheduler.get("root_profile"),
        process.get("root_profile"),
    )
    return all(isinstance(root, str) and root for root in roots) and len(set(roots)) == 1


def database_capture_lifecycle(
    database_snapshot: object,
    runtime_snapshot: object,
    *,
    as_of: dt.datetime | None = None,
) -> str:
    """Return DB evidence lifecycle with its own 15-minute TTL and enclosure."""

    if not isinstance(database_snapshot, dict):
        return "NO_CAPTURE"
    if not isinstance(runtime_snapshot, dict):
        return "UNVERIFIABLE"
    if capture_lifecycle(runtime_snapshot, as_of=as_of) != "FRESH":
        return "UNVERIFIABLE"
    database_observed = _utc(database_snapshot.get("observed_at"))
    capture_started = _utc(runtime_snapshot.get("capture_started_at"))
    runtime_observed = _utc(runtime_snapshot.get("observed_at"))
    if None in (database_observed, capture_started, runtime_observed):
        return "UNVERIFIABLE"
    now = (as_of or dt.datetime.now(UTC)).astimezone(UTC)
    if not capture_started <= database_observed <= runtime_observed <= now:
        return "UNVERIFIABLE"
    if now - database_observed > dt.timedelta(minutes=15):
        return "STALE"
    return "FRESH"


def _valid_window(
    record: object,
    *,
    not_before: dt.datetime,
    before: dt.datetime | None,
) -> bool:
    if not isinstance(record, dict):
        return False
    started = _utc(record.get("started_at"))
    finished = _utc(record.get("finished_at"))
    return (
        started is not None
        and finished is not None
        and not_before <= started <= finished
        and (before is None or finished <= before)
    )


def verifier_binding_verified(
    dependencies: object,
    input_tree_digest: object,
    input_generated_at: object,
    expected_gitleaks_scanned_file_count: object,
    *,
    before: dt.datetime | None = None,
) -> bool:
    """Validate digest-, version-, report-, and time-bound isolated checks."""

    if (
        not isinstance(dependencies, dict)
        or not isinstance(input_tree_digest, str)
        or not SHA256_PATTERN.fullmatch(input_tree_digest)
        or isinstance(expected_gitleaks_scanned_file_count, bool)
        or not isinstance(expected_gitleaks_scanned_file_count, int)
        or expected_gitleaks_scanned_file_count <= 0
    ):
        return False
    generated = _utc(input_generated_at)
    if generated is None:
        return False
    verifier = dependencies.get("verification_toolchain")
    if not isinstance(verifier, dict):
        return False
    binding = verifier.get("candidate_binding")
    versions = verifier.get("versions")
    checks = binding.get("checks") if isinstance(binding, dict) else None
    if (
        not isinstance(binding, dict)
        or set(binding) != VERIFIER_BINDING_KEYS
        or binding.get("status") != "verified"
        or binding.get("reason_code") is not None
        or binding.get("input_tree_digest") != input_tree_digest
        or binding.get("input_generated_at") != input_generated_at
        or not isinstance(binding.get("authority_ref"), str)
        or not binding["authority_ref"].startswith("owner-authority:")
        or binding.get("official_sources_only") is not True
        or binding.get("hashes_verified") is not True
        or binding.get("canonical_venv_mutated") is not False
        or not isinstance(binding.get("network_or_install_performed"), bool)
        or not isinstance(binding.get("isolated_environment_digest"), str)
        or not SHA256_PATTERN.fullmatch(binding["isolated_environment_digest"])
        or binding.get("lock_refs") != [
            "tests/gate0/verifier-requirements.txt",
            "tests/gate0/verifier-toolchain.json",
        ]
        or not isinstance(versions, dict)
        or not isinstance(checks, dict)
        or set(checks) != REQUIRED_VERIFIER_CHECKS
    ):
        return False
    for name, check in checks.items():
        if (
            not isinstance(check, dict)
            or set(check) != VERIFIER_CHECK_KEYS
            or check.get("status") != "passed"
            or check.get("tool_version") != versions.get(name)
            or check.get("scanned_input_tree_digest") != input_tree_digest
            or not isinstance(check.get("report_sha256"), str)
            or not SHA256_PATTERN.fullmatch(check["report_sha256"])
            or not _valid_window(check, not_before=generated, before=before)
        ):
            return False
    dev_checks = verifier.get("dev_checks")
    if (
        not isinstance(dev_checks, dict)
        or set(dev_checks) != {"jsonschema", "hypothesis", "import_linter"}
        or any(
            dev_checks.get(name) != "passed"
            for name in ("jsonschema", "hypothesis", "import_linter")
        )
    ):
        return False
    release_environment = verifier.get("release_environment")
    if (
        not isinstance(release_environment, dict)
        or release_environment.get("canonical_venv_mutated") is not False
    ):
        return False
    vulnerability = dependencies.get("vulnerability_check")
    secret_scan = dependencies.get("secret_scan")
    pip_report = verifier.get("pip_audit")
    gitleaks_report = verifier.get("gitleaks")
    if not all(
        isinstance(value, dict)
        for value in (vulnerability, secret_scan, pip_report, gitleaks_report)
    ):
        return False
    if (
        set(vulnerability)
        != {
            "finding_count", "findings", "package_count", "raw_report_sha256",
            "status", "tool", "triage",
        }
        or set(secret_scan)
        != {
            "finding_count", "findings", "raw_report_sha256",
            "scanned_file_count", "status", "tool", "triage",
        }
        or set(pip_report)
        != {"finding_count", "findings", "package_count", "raw_report_sha256", "status"}
        or set(gitleaks_report)
        != {
            "finding_count", "findings", "raw_report_sha256",
            "scanned_file_count", "status",
        }
        or not isinstance(vulnerability.get("triage"), dict)
        or set(vulnerability["triage"])
        != {
            "affected_component",
            "canonical_environment_mutated",
            "minimum_all_findings_fixed_version",
            "production_imported",
        }
        or vulnerability["triage"].get("canonical_environment_mutated") is not False
        or vulnerability["triage"].get("production_imported") is not False
        or not isinstance(secret_scan.get("triage"), dict)
        or set(secret_scan["triage"])
        != {
            "candidate_fix_status",
            "classification",
            "files_changed",
            "raw_match_values_persisted",
        }
        or secret_scan["triage"].get("raw_match_values_persisted") is not False
        or vulnerability.get("findings") != []
        or secret_scan.get("findings") != []
        or pip_report.get("findings") != []
        or gitleaks_report.get("findings") != []
    ):
        return False
    return (
        vulnerability.get("tool") == "pip-audit"
        and vulnerability.get("status") == "passed"
        and vulnerability.get("finding_count") == 0
        and vulnerability.get("raw_report_sha256")
        == checks["pip_audit"]["report_sha256"]
        == pip_report.get("raw_report_sha256")
        and pip_report.get("status") == "passed"
        and pip_report.get("finding_count") == 0
        and secret_scan.get("tool") == "gitleaks"
        and secret_scan.get("status") == "passed"
        and secret_scan.get("finding_count") == 0
        and secret_scan.get("raw_report_sha256")
        == checks["gitleaks"]["report_sha256"]
        == gitleaks_report.get("raw_report_sha256")
        and gitleaks_report.get("status") == "passed"
        and gitleaks_report.get("finding_count") == 0
        and secret_scan.get("scanned_file_count")
        == expected_gitleaks_scanned_file_count
        and gitleaks_report.get("scanned_file_count")
        == expected_gitleaks_scanned_file_count
    )


def test_binding_verified(
    test_inventory: object,
    input_tree_digest: object,
    input_generated_at: object,
    *,
    before: dt.datetime | None = None,
) -> bool:
    """Validate exact targeted/full pytest receipts for the frozen input."""

    if (
        not isinstance(test_inventory, dict)
        or not isinstance(input_tree_digest, str)
        or not SHA256_PATTERN.fullmatch(input_tree_digest)
    ):
        return False
    generated = _utc(input_generated_at)
    binding = test_inventory.get("candidate_binding")
    runs = binding.get("runs") if isinstance(binding, dict) else None
    if (
        generated is None
        or not isinstance(binding, dict)
        or set(binding) != TEST_BINDING_KEYS
        or binding.get("status") != "verified"
        or binding.get("reason_code") is not None
        or binding.get("input_tree_digest") != input_tree_digest
        or binding.get("input_generated_at") != input_generated_at
        or binding.get("network_or_provider_calls_performed") is not False
        or binding.get("canonical_venv_mutated") is not False
        or not isinstance(binding.get("environment_digest"), str)
        or not SHA256_PATTERN.fullmatch(binding["environment_digest"])
        or not isinstance(runs, dict)
        or set(runs) != {"targeted_gate0", "full_pytest"}
    ):
        return False
    for name, receipt in runs.items():
        reported = test_inventory.get(name)
        if (
            not isinstance(receipt, dict)
            or set(receipt) != TEST_RUN_KEYS
            or not isinstance(reported, dict)
            or set(reported)
            != {
                "status",
                "passed",
                "failed",
                "skipped",
                "started_at",
                "finished_at",
            }
            or receipt.get("status") != "pass"
            or receipt.get("scanned_input_tree_digest") != input_tree_digest
            or not isinstance(receipt.get("report_sha256"), str)
            or not SHA256_PATTERN.fullmatch(receipt["report_sha256"])
            or not _valid_window(receipt, not_before=generated, before=before)
            or any(
                receipt.get(key) != reported.get(key)
                for key in (
                    "status",
                    "passed",
                    "failed",
                    "skipped",
                    "started_at",
                    "finished_at",
                )
            )
            or receipt.get("failed") != 0
        ):
            return False
    return True


def _empty_migration_inventory(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"applied", "pending", "unknown"}
        and all(isinstance(value[key], list) and not value[key] for key in value)
    )


def database_claim(
    database: dict[str, Any],
    capture_state: str,
) -> tuple[dict[str, Any], str, bool]:
    """Sanitize one DB claim and return (claim, lifecycle status, genesis proof)."""

    claim = copy.deepcopy(database)
    role = claim.get("database_role")
    expected_ref = f"runtime-db:{role}" if isinstance(role, str) else None
    reference_verified = expected_ref is not None and claim.get("database_ref") == expected_ref
    binding_verified = str(claim.get("runtime_binding_status", "")).casefold() == "verified"
    snapshot = claim.get("snapshot") if isinstance(claim.get("snapshot"), dict) else {}
    snapshot_verified = (
        snapshot.get("mode") == "sqlite_read_transaction"
        and snapshot.get("wal_aware") is True
        and snapshot.get("data_version_stable") is True
        and snapshot.get("consistent") is True
    )
    integrity = claim.get("integrity") if isinstance(claim.get("integrity"), dict) else {}
    integrity_verified = (
        integrity.get("quick_check") == "ok"
        and integrity.get("foreign_key_check") == "ok"
    )
    common_proof = (
        reference_verified
        and binding_verified
        and claim.get("source_schema_match") is True
        and snapshot_verified
        and integrity_verified
        and _empty_migration_inventory(claim.get("migration_inventory"))
    )
    lineage = str(claim.get("migration_lineage_status", "")).casefold()
    genesis = claim.get("genesis_baseline")
    genesis_verified = (
        capture_state == "FRESH"
        and role == "telegram_state"
        and common_proof
        and lineage == "genesis_baseline_verified"
        and isinstance(genesis, dict)
        and genesis.get("genesis_id")
        == "genesis_baseline:telegram_state_current_schema"
        and genesis.get("authority_ref")
        == "owner-authority:gate0-evidence-closure-2026-07-29"
        and genesis.get("schema_digest") == claim.get("schema_digest")
        and genesis.get("historical_legacy_migration_proven") is False
        and genesis.get("durable_ledger_deferred_to_gate") == 2
        and genesis.get("production_database_mutated") is False
    )
    lineage_verified = (
        genesis_verified
        if role == "telegram_state"
        else common_proof and lineage == "verified_absent"
    )
    if not lineage_verified:
        claim["migration_lineage_status"] = "contradictory"
        claim["genesis_baseline"] = None
    elif role != "telegram_state":
        claim["genesis_baseline"] = None

    if capture_state == "FRESH":
        status = "VERIFIED" if common_proof and lineage_verified else "CONTRADICTORY"
    elif capture_state == "STALE":
        status = "STALE"
    else:
        status = "UNVERIFIABLE"
    return claim, status, genesis_verified
