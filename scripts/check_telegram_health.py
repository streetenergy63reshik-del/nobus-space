"""Read-only SQLite and protected-payload health probe."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import UTC, datetime
from contextlib import closing
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.application.runtime_maintenance import (
    RUNTIME_DATABASE_NAMES, REQUIRED_RUNTIME_DATABASE_NAMES, MAX_BACKUP_DATABASE_BYTES,
    application_binding, checked_path, file_evidence, runtime_database_paths, runtime_target_binding,
    _read_connection, _read_only_store, validate_runtime_set,
    dead_letter_count,
    validate_runtime_database,
)

_DATABASES = runtime_database_paths(ROOT / ".runtime")



def check(databases: tuple[Path, ...] = _DATABASES) -> dict[str, object]:
    results: dict[str, str] = {}
    names = [path.name for path in databases]
    parents = {path.resolve().parent for path in databases}
    if (
        len(names) != len(set(names))
        or not REQUIRED_RUNTIME_DATABASE_NAMES <= set(names) <= RUNTIME_DATABASE_NAMES
        or len(parents) != 1
        or any(path.exists() and path.name not in names for path in runtime_database_paths(next(iter(parents))))
    ):
        return {
            "status": "FAIL",
            "databases": {name: "invalid-set" for name in names},
        }
    healthy = True
    for path in databases:
        name = path.name
        if not path.is_file():
            results[name] = "missing"
            healthy = False
            continue
        try:
            validate_runtime_database(path)
            results[name] = (
                "degraded"
                if dead_letter_count(path)
                else "ok"
            )
        except Exception:
            results[name] = "unavailable"
        healthy &= results[name] in {"ok", "degraded"}
    degraded = healthy and any(value == "degraded" for value in results.values())
    return {
        "status": "DEGRADED" if degraded else ("PASS" if healthy else "FAIL"),
        "databases": results,
    }


def operator_view(runtime: Path, *, backup_manifest: Path | None = None,
                  drill_receipt: Path | None = None) -> dict[str, object]:
    """Safe local diagnostics; this does not claim a running worker or public ingress."""
    paths = runtime_database_paths(runtime)
    result = check(paths)
    result.update({"runtime": "not_probed", "application": application_binding(),
                   "target_binding": runtime_target_binding(runtime),
                   "runbook": "docs/08-Runbook-эксплуатации.md", "signals": [],
                   "backup_age_seconds": None, "drill_age_seconds": None})
    metrics = {}
    for path in paths:
        if path.exists():
            main_bytes = path.stat().st_size
            wal = path.with_name(path.name + "-wal")
            wal_bytes = wal.stat().st_size if wal.is_file() else 0
            metrics[path.name] = {"bytes": main_bytes, "wal_bytes": wal_bytes,
                                  "backup_limit_bytes": MAX_BACKUP_DATABASE_BYTES}
            if main_bytes + wal_bytes >= 36 * 1024 * 1024:
                result["signals"].append("store_growth_review_at_36_mib")
    result["stores"] = metrics
    free = shutil.disk_usage(checked_path(runtime)).free if runtime.exists() else None
    result["disk_free_bytes"] = free
    if free is not None and free < 256 * 1024 * 1024:
        result["signals"].append("disk_below_256_mib_stop_new_admission")
    if result["status"] in {"PASS", "DEGRADED"}:
        try:
            validate_runtime_set(runtime)
            with closing(_read_connection(runtime / "telegram-state.sqlite3")) as connection:
                result["queue"] = dict(connection.execute("SELECT status,COUNT(*) FROM telegram_jobs GROUP BY status"))
                oldest = connection.execute("SELECT MIN(created_at) FROM telegram_jobs WHERE status IN ('pending','leased')").fetchone()[0]
                age = max(0, (datetime.now(UTC) - datetime.fromisoformat(oldest)).total_seconds()) if oldest else 0
                result["oldest_queue_age_seconds"] = round(age, 3)
                if age >= 3600:
                    result["signals"].append("queue_age_over_1h_reconcile")
            with closing(_read_connection(runtime / "task-runtime.sqlite3")) as connection:
                tenants = [row[0] for row in connection.execute("SELECT DISTINCT tenant_id FROM task_snapshots")]
            store = _read_only_store(runtime / "task-runtime.sqlite3")
            result["restore_reconciliation_required"] = store.restore_reconciliation_required()
            if result["restore_reconciliation_required"]:
                result["signals"].append("restored_runtime_admission_blocked_pending_owner_reconciliation")
                result["status"] = "DEGRADED"
            counts = [store.delivery_counts(tenant) for tenant in tenants]
            result["delivery_unknown"] = sum(item.get("unknown", 0) for item in counts)
            if result["delivery_unknown"]:
                result["signals"].append("unknown_delivery_reconcile_no_repeat")
        except Exception:
            result["status"] = "FAIL"
            result["signals"].append("store_reconciliation_required")
    if backup_manifest is not None:
        try:
            from scripts.restore_telegram_runtime import _verified_manifest
            manifest = _verified_manifest(backup_manifest)
            if manifest["source_binding"] != runtime_target_binding(runtime):
                raise ValueError
            for item in manifest["files"]:
                if file_evidence(backup_manifest.parent / (item["name"] + ".dpapi")) != {"bytes": item["bytes"], "sha256": item["sha256"]}:
                    raise ValueError
            result["backup_age_seconds"] = round(max(0, (datetime.now(UTC) - datetime.fromisoformat(manifest["created_at"])).total_seconds()), 3)
            result["backup_manifest_digest"] = manifest["authentication"]["manifest_digest"]
            if result["backup_age_seconds"] > 86400:
                result["signals"].append("backup_over_24h_create_verified_backup")
        except Exception:
            result["signals"].append("backup_unverified_do_not_restore")
    if drill_receipt is not None:
        try:
            receipt_path = checked_path(drill_receipt)
            if receipt_path.stat().st_size > 64 * 1024:
                raise ValueError
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if (receipt["status"] != "PASS" or receipt["application_code_digest"] != result["application"]["code_digest"]
                    or receipt["manifest_digest"] != result.get("backup_manifest_digest")):
                raise ValueError
            result["drill_age_seconds"] = round(max(0, (datetime.now(UTC) - datetime.fromisoformat(receipt["completed_at"])).total_seconds()), 3)
        except Exception:
            result["signals"].append("drill_unverified")
    if result["backup_age_seconds"] is None:
        result["signals"].append("backup_age_unknown")
    if result["drill_age_seconds"] is None:
        result["signals"].append("drill_age_unknown")
    return result


def retention_dry_run(roots: dict[str, Path]) -> dict[str, object]:
    """Inventory only: file ownership cannot be inferred from a directory or name."""
    result = {}
    for label, supplied in roots.items():
        if label not in {"voice", "temp", "downloads", "logs", "staging"}:
            raise ValueError("retention root class invalid")
        root = checked_path(supplied)
        count = total = blocked = 0
        pending = [root] if root.is_dir() else []
        while pending:
            directory = pending.pop()
            for child in directory.iterdir():
                count += 1
                if count > 10000:
                    raise RuntimeError("retention inventory limit exceeded")
                try:
                    checked_path(child, root=root)
                except ValueError:
                    blocked += 1
                    continue
                if child.is_dir():
                    pending.append(child)
                elif child.is_file():
                    total += child.stat().st_size
        result[label] = {"root_binding": runtime_target_binding(root), "exists": root.exists(),
                         "entries": count, "bytes": total, "blocked_links": blocked,
                         "ownership": "unresolved_no_deletion", "deleted": 0}
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database", action="append", type=Path, default=None
    )
    parser.add_argument("--runtime", type=Path, default=ROOT / ".runtime")
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--backup-manifest", type=Path)
    parser.add_argument("--drill-receipt", type=Path)
    parser.add_argument("--retention-root", action="append", default=[])
    values = parser.parse_args()
    try:
        result = check(
            tuple(values.database) if values.database else runtime_database_paths(values.runtime)
        )
        if values.details:
            result = operator_view(values.runtime, backup_manifest=values.backup_manifest, drill_receipt=values.drill_receipt)
        if values.retention_root:
            roots = dict(item.split("=", 1) for item in values.retention_root)
            result["retention_dry_run"] = retention_dry_run({label: Path(path) for label, path in roots.items()})
    except Exception:
        result = {"status": "FAIL", "code": "operator_probe_unavailable"}
    print(
        json.dumps(
            result,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return {"PASS": 0, "FAIL": 1, "DEGRADED": 2}[str(result["status"])]


if __name__ == "__main__":
    raise SystemExit(main())
