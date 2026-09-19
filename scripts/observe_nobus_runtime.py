"""Independent read-only checks; an admission hold never fabricates zero counts."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import run_nobus_space_live as s
from src.application import runtime_maintenance as m
from src.application import managed_backups as b


def observe(runtime, *, backup_root=None, ownership=None):
    result = {"schema": "nobus-runtime-observation-2", "at": datetime.now(UTC).isoformat(), "checks": {}}
    checks = result["checks"]

    def run(name, operation):
        try:
            checks[name] = {"status": "PASS", "value": operation()}
        except Exception:
            checks[name] = {"status": "FAIL", "reason": "check_unavailable"}

    for path in m.runtime_database_paths(runtime):
        run(path.name, lambda path=path: m.validate_runtime_database(path))
    run("cross_database", lambda: m.validate_runtime_set(runtime))
    def deliveries():
        store = m._read_only_store(runtime / "task-runtime.sqlite3")
        with closing(m._read_connection(runtime / "task-runtime.sqlite3")) as con:
            tenants = [row[0] for row in con.execute("SELECT DISTINCT tenant_id FROM task_snapshots")]
        totals = {key: 0 for key in ("pending", "leased", "unknown", "failed", "confirmed_parts")}
        for tenant in tenants:
            for key, count in store.delivery_counts(tenant).items():
                totals[key] += count
        return {"counts": totals, "reconciliation": store.restore_reconciliation_required()}
    if checks.get("task-runtime.sqlite3", {}).get("status") == "PASS":
        run("delivery", deliveries)
    else:
        checks["delivery"] = {"status": "NOT CHECKED", "reason": "task_database_unverified"}
    def checkpoint():
        with closing(m._read_connection(runtime / "telegram-checkpoint.sqlite3")) as con:
            return [{"offset": row[0], "revision": row[1], "active": row[2] is not None and datetime.fromisoformat(row[2]) > datetime.now(UTC)}
                    for row in con.execute("SELECT offset,revision,lease_expires_at FROM telegram_polling_checkpoints")]
    run("checkpoint", checkpoint)
    if backup_root is not None and ownership is not None:
        def backup():
            path = b.latest_manifest(backup_root, ownership, runtime)
            manifest = b.verify_backup(path)
            return {"generation": path.parents[1].name, "created_at": manifest["created_at"], "verified": True}
        run("backup", backup)
        run("backup_freshness", lambda: b.assert_recent(backup_root, ownership, runtime, for_admission=False))
        run("admission_hold", lambda: m.checked_path(backup_root / 'admission-hold', root=backup_root).exists())
    else:
        checks["backup"] = {"status": "NOT CHECKED", "reason": "backup_inputs_absent"}
    for boundary, probe in (("local", s.ready), ("public", s.public_ready)):
        try:
            passed = probe()
            checks[boundary] = {"status": "PASS" if passed else "FAIL", "detail": next(item for item in s.readiness_details() if item["boundary"] == boundary)}
        except Exception:
            checks[boundary] = {"status": "FAIL", "reason": "probe_unavailable"}
    def history():
        rows, digests = s._runtime_history(root=runtime / s.RECOVERY_DIRECTORY_NAME)
        if not rows:
            raise ValueError('history missing')
        event = s._effective_event(rows[-1])
        return {key: event[key] for key in ('event','stage','attempt','recovery_disposition','error_class')} | {'head':digests[-1]}
    run('history', history)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--backup-root", type=Path)
    parser.add_argument("--ownership")
    args = parser.parse_args()
    result = observe(args.runtime, backup_root=args.backup_root, ownership=args.ownership)
    print(json.dumps(result, separators=(",", ":")))
    return 0 if all(item["status"] == "PASS" for item in result["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
