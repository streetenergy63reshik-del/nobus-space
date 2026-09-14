"""Bounded, payload-free action for the M1-S1 Task Scheduler retry fixture."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import run_nobus_space_live as supervisor


SCHEMA = "nobus-m1-scheduler-fixture-1"
EXIT_RETRYABLE = 23
EXIT_FIXTURE_INVALID = 125
MAX_RECEIPT_BYTES = 8192
_KEYS = frozenset({
    "schema", "run_id", "attempt", "restart_budget", "at", "outcome", "exit_code"
})


def _rows(path: Path, run_id: str, restart_budget: int) -> list[dict[str, object]]:
    if not path.exists():
        return []
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()) or not path.is_file():
        raise ValueError
    content = path.read_bytes()
    if len(content) > MAX_RECEIPT_BYTES or (content and not content.endswith(b"\n")):
        raise ValueError
    rows = []
    for expected, line in enumerate(content.splitlines(), start=1):
        value = json.loads(line.decode("ascii"))
        if (
            type(value) is not dict
            or set(value) != _KEYS
            or value["schema"] != SCHEMA
            or value["run_id"] != run_id
            or value["attempt"] != expected
            or value["restart_budget"] != restart_budget
            or value["outcome"] not in {"retryable_failure", "recovered", "budget_exhausted"}
            or type(value["exit_code"]) is not int
        ):
            raise ValueError
        rows.append(value)
    return rows


def _attempt(values) -> tuple[int, str]:
    rows = _rows(values.receipt, values.run_id, values.restart_budget)
    attempt = len(rows) + 1
    total_attempts = values.restart_budget + 1
    if attempt > total_attempts:
        raise ValueError
    recovered = values.succeed_on == attempt
    outcome = (
        "recovered"
        if recovered
        else ("budget_exhausted" if attempt == total_attempts else "retryable_failure")
    )
    exit_code = 0 if recovered else EXIT_RETRYABLE
    record = {
        "schema": SCHEMA,
        "run_id": values.run_id,
        "attempt": attempt,
        "restart_budget": values.restart_budget,
        "at": datetime.now(UTC).isoformat(),
        "outcome": outcome,
        "exit_code": exit_code,
    }
    line = json.dumps(record, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii") + b"\n"
    if len(line) > 1024 or values.receipt.exists() and values.receipt.stat().st_size + len(line) > MAX_RECEIPT_BYTES:
        raise ValueError
    descriptor = os.open(values.receipt, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        if os.write(descriptor, line) != len(line):
            raise OSError
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return exit_code, outcome


class _Delay:
    @staticmethod
    def wait(seconds: float) -> bool:
        time.sleep(seconds)
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--restart-budget", type=int, required=True)
    parser.add_argument("--succeed-on", type=int, required=True)
    parser.add_argument("--controller", action="store_true")
    parser.add_argument("--retry-interval-seconds", type=float, default=60.0)
    values = parser.parse_args(argv)
    try:
        if (
            re.fullmatch(r"[0-9a-f]{32}", values.run_id) is None
            or not 1 <= values.restart_budget <= 10
            or not 0 <= values.succeed_on <= values.restart_budget + 1
            or not 0.001 <= values.retry_interval_seconds <= 60
            or not values.receipt.is_absolute()
        ):
            raise ValueError
        parent = values.receipt.parent.resolve(strict=True)
        if (
            not parent.is_dir()
            or parent.is_symlink()
            or (hasattr(parent, "is_junction") and parent.is_junction())
            or values.receipt.resolve(strict=False).parent != parent
        ):
            raise ValueError
        if not values.controller:
            return _attempt(values)[0]
        last_exit = EXIT_FIXTURE_INVALID

        def run_attempt(_number: int) -> dict[str, object]:
            nonlocal last_exit
            last_exit, outcome = _attempt(values)
            disposition = {
                "recovered": "complete",
                "retryable_failure": "retry",
                "budget_exhausted": "stop_budget_exhausted",
            }[outcome]
            return {
                "status": 0 if last_exit == 0 else 1,
                "recovery_disposition": disposition,
            }

        status = supervisor._run_bounded_recovery(
            run_attempt,
            stop_event=_Delay(),
            first_attempt=1,
            retry_budget=values.restart_budget,
            retry_interval=values.retry_interval_seconds,
        )
        return 0 if status == 0 else last_exit
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
        return EXIT_FIXTURE_INVALID


if __name__ == "__main__":
    raise SystemExit(main())
