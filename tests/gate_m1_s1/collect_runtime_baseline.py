"""Read-only, aggregate-only M1-S1 production preservation baseline."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application.runtime_maintenance import (  # noqa: E402
    _read_connection,
    database_state_digest,
    runtime_database_paths,
    runtime_target_binding,
    validate_runtime_set,
)


def _count(connection, table: str) -> int:
    return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def _group(connection, table: str, column: str) -> dict[str, int]:
    return {
        str(key): int(count)
        for key, count in connection.execute(
            f'SELECT "{column}",COUNT(*) FROM "{table}" GROUP BY "{column}" ORDER BY "{column}"'
        )
    }


def collect(runtime: Path) -> dict[str, object]:
    runtime = runtime.resolve(strict=True)
    validate_runtime_set(runtime)
    paths = {path.name: path for path in runtime_database_paths(runtime)}
    digests = {name: database_state_digest(path) for name, path in sorted(paths.items())}
    with closing(_read_connection(paths["task-runtime.sqlite3"])) as connection:
        restore_flag = int(connection.execute(
            "SELECT reconciliation_required FROM miniapp_restore_fence WHERE singleton=1"
        ).fetchone()[0])
        task_runtime = {
            "tasks": _count(connection, "task_snapshots"),
            "ingress_claims": _count(connection, "ingress_claims"),
            "audit_events": _count(connection, "audit_events"),
            "sealed_answers": _count(connection, "sealed_answers"),
            "outbox_messages": _group(connection, "outbox_messages", "status"),
            "outbox_receipts": _count(connection, "outbox_receipts"),
            "outbox_receipt_types": _group(connection, "outbox_receipts", "receipt_type"),
            "delivery_parts": _count(connection, "outbox_delivery_parts"),
            "confirmed_delivery_parts": int(connection.execute(
                "SELECT COUNT(*) FROM outbox_delivery_parts WHERE receipt_json IS NOT NULL"
            ).fetchone()[0]),
            "runtime_reconciliations": _group(connection, "runtime_reconciliations", "state"),
            "restore_reconciliation_required": bool(restore_flag),
        }
    now = datetime.now(UTC)
    with closing(_read_connection(paths["telegram-state.sqlite3"])) as connection:
        telegram_state = {
            "jobs": _group(connection, "telegram_jobs", "status"),
            "lease_rows": int(connection.execute(
                "SELECT COUNT(*) FROM telegram_jobs WHERE lease_id IS NOT NULL"
            ).fetchone()[0]),
            "active_lease_rows": int(connection.execute(
                "SELECT COUNT(*) FROM telegram_jobs WHERE lease_expires_at>?",
                (now.isoformat(),),
            ).fetchone()[0]),
            "progress_rows": _count(connection, "telegram_progress"),
            "capability_rows": _count(connection, "telegram_capabilities"),
            "clarification_rows": _count(connection, "semantic_clarifications"),
        }
    with closing(_read_connection(paths["telegram-checkpoint.sqlite3"])) as connection:
        checkpoints = []
        for consumer_id, offset, lease_id, lease_expires_at, revision in connection.execute(
            "SELECT consumer_id,offset,lease_id,lease_expires_at,revision "
            "FROM telegram_polling_checkpoints ORDER BY consumer_id"
        ):
            binding = hashlib.sha256(str(consumer_id).encode("utf-8")).hexdigest()
            active = lease_expires_at is not None and datetime.fromisoformat(lease_expires_at) > now
            checkpoints.append({
                "consumer_binding": "sha256:" + binding,
                "offset": offset,
                "revision": int(revision),
                "has_lease": lease_id is not None,
                "active_lease": active,
            })
    with closing(_read_connection(paths["business-notes.sqlite3"])) as connection:
        business_notes = {"rows": _count(connection, "business_notes")}
    return {
        "schema": "nobus-m1-runtime-baseline-1",
        "captured_at": now.isoformat(),
        "target_binding": runtime_target_binding(runtime),
        "database_state_digests": digests,
        "task_runtime": task_runtime,
        "telegram_state": telegram_state,
        "telegram_checkpoints": checkpoints,
        "business_notes": business_notes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, required=True)
    values = parser.parse_args(argv)
    try:
        result = {"status": "PASS", **collect(values.runtime_root)}
        code = 0
    except Exception:
        result = {
            "schema": "nobus-m1-runtime-baseline-1",
            "status": "FAIL",
            "error_class": "runtime_baseline_unavailable",
        }
        code = 1
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
