"""Observation-only scheduled Health with separately retained checks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import check_telegram_health as db
from scripts import run_nobus_space_live as supervisor
from scripts.runtime_diagnostics import write_diagnostic


def check(runtime, diagnostic_root):
    checks = []
    for path in db.runtime_database_paths(runtime):
        started = time.monotonic()
        error = None
        try:
            if not path.is_file():
                error = "database_missing"
            else:
                db.validate_runtime_database(path)
                if db.dead_letter_count(path):
                    error = "database_degraded"
        except Exception:
            error = "database_failed"
        checks.append({"boundary": path.name, "status": "PASS" if error is None else "FAIL",
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "http_status": None, "body_matches": False, "error_class": error,
            "elapsed_ms": round((time.monotonic() - started) * 1000), "deadline_ms": 120000})
    local, public = supervisor._readiness_pair(None)
    checks.extend(supervisor.readiness_details())
    write_diagnostic(diagnostic_root, "health", {"run_id": uuid4().hex, "attempt": 0, "stage": "health", "checks": checks})
    return {"status": "PASS" if all(row["status"] == "PASS" for row in checks) and local and public else "FAIL", "checks": checks}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--diagnostic-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = check(args.runtime, args.diagnostic_root)
    except Exception:
        result = {"status": "FAIL", "error_class": "health_diagnostic_unavailable"}
    print(json.dumps(result, separators=(",", ":")))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
