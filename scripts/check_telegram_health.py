"""Read-only SQLite and protected-payload health probe."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.application.runtime_maintenance import (
    RUNTIME_DATABASE_NAMES,
    dead_letter_count,
    validate_runtime_database,
)

_DATABASES = (
    ROOT / ".runtime" / "telegram-checkpoint.sqlite3",
    ROOT / ".runtime" / "task-runtime.sqlite3",
    ROOT / ".runtime" / "telegram-state.sqlite3",
    ROOT / ".runtime" / "business-notes.sqlite3",
)



def check(databases: tuple[Path, ...] = _DATABASES) -> dict[str, object]:
    results: dict[str, str] = {}
    names = [path.name for path in databases]
    parents = {path.resolve().parent for path in databases}
    if (
        len(names) != len(RUNTIME_DATABASE_NAMES)
        or set(names) != RUNTIME_DATABASE_NAMES
        or len(parents) != 1
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database", action="append", type=Path, default=None
    )
    values = parser.parse_args()
    result = check(
        tuple(values.database) if values.database else _DATABASES
    )
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
