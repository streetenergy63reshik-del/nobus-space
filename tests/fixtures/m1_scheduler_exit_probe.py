"""Bounded, payload-free action for the M1-S1 Task Scheduler retry fixture."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import threading
import time


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import run_nobus_space_live as supervisor


SCHEMA = "nobus-m1-scheduler-fixture-2"
EXIT_RETRYABLE = 23
EXIT_PERMANENT = 29
EXIT_FIXTURE_INVALID = 125
MAX_RECEIPT_BYTES = 8192
_KEYS = frozenset({
    "schema", "run_id", "attempt", "restart_budget", "at", "outcome",
    "exit_code", "controller_sha256", "failure_mode",
})


def _controller_sha256() -> str:
    return hashlib.sha256(Path(supervisor.__file__).resolve().read_bytes()).hexdigest()


def _rows(path: Path, run_id: str, restart_budget: int) -> list[dict[str, object]]:
    if not path.exists():
        return []
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()) or not path.is_file():
        raise ValueError
    content = path.read_bytes()
    if len(content) > MAX_RECEIPT_BYTES or (content and not content.endswith(b"\n")):
        raise ValueError

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError
            value[key] = item
        return value

    rows = []
    for expected, line in enumerate(content.splitlines(), start=1):
        value = json.loads(line.decode("ascii"), object_pairs_hook=unique)
        if (
            type(value) is not dict
            or set(value) != _KEYS
            or value["schema"] != SCHEMA
            or value["run_id"] != run_id
            or value["attempt"] != expected
            or value["restart_budget"] != restart_budget
            or value["failure_mode"] not in {"transient", "permanent"}
            or value["outcome"] not in {
                "retryable_failure", "recovered", "budget_exhausted",
                "permanent_failure",
            }
            or (value["failure_mode"] == "permanent"
                and (value["outcome"] != "permanent_failure" or expected != 1))
            or (value["failure_mode"] == "transient"
                and value["outcome"] == "permanent_failure")
            or type(value["exit_code"]) is not int
            or re.fullmatch(r"[0-9a-f]{64}", value["controller_sha256"]) is None
            or value["controller_sha256"] != _controller_sha256()
        ):
            raise ValueError
        rows.append(value)
    return rows


def _record_attempt(values, attempt: int, *, recovered: bool) -> tuple[int, str]:
    rows = _rows(values.receipt, values.run_id, values.restart_budget)
    if attempt != len(rows) + 1:
        raise ValueError
    total_attempts = 1 if values.failure_mode == "permanent" else values.restart_budget + 1
    if attempt > total_attempts:
        raise ValueError
    if values.failure_mode == "permanent":
        outcome = "permanent_failure"
        exit_code = EXIT_PERMANENT
    else:
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
        "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "outcome": outcome,
        "exit_code": exit_code,
        "controller_sha256": _controller_sha256(),
        "failure_mode": values.failure_mode,
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


def _attempt(values) -> tuple[int, str]:
    attempt = len(_rows(values.receipt, values.run_id, values.restart_budget)) + 1
    return _record_attempt(values, attempt, recovered=values.succeed_on == attempt)


class _Delay:
    @staticmethod
    def wait(seconds: float) -> bool:
        time.sleep(seconds)
        return False


def _child(role: str) -> int:
    if role == "relay":
        time.sleep(300)
        return 0
    if role == "core":
        if sys.stdin.buffer.readline(16) != b"stop\n":
            return EXIT_FIXTURE_INVALID
        sys.stdout.buffer.write(b'{"status":"STOPPED"}\n')
        sys.stdout.buffer.flush()
        return 0
    if role == "core-permanent":
        sys.stdout.buffer.write(
            b'{"status":"FAIL","code":"telegram_checkpoint_failed"}\n'
        )
        sys.stdout.buffer.flush()
        return EXIT_PERMANENT
    return EXIT_FIXTURE_INVALID


def _product_controller(values) -> int:
    controller_digest = _controller_sha256()
    if values.controller_sha256 != controller_digest:
        raise ValueError
    probe_digest = hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()
    binding = "sha256:" + hashlib.sha256(json.dumps({
        "controller_sha256": controller_digest,
        "probe_sha256": probe_digest,
        "run_id": values.run_id,
        "receipt": values.receipt.name,
        "failure_mode": values.failure_mode,
    }, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii")).hexdigest()
    control_root = values.receipt.parent / ("controller-" + values.receipt.stem)
    control_root.mkdir()
    supervisor.RECOVERY_RETRY_BUDGET = values.restart_budget
    supervisor.RECOVERY_RETRY_INTERVAL_SECONDS = values.retry_interval_seconds
    supervisor.READINESS_INTERVAL_SECONDS = 0.01
    supervisor.READINESS_FAILURE_LIMIT = 3
    supervisor.SHUTDOWN_SECONDS = 5
    stop_name = "Local\\NobusSpaceM1S1Stop-" + hashlib.sha256(
        (values.run_id + values.receipt.name).encode("ascii")
    ).hexdigest()[:32]
    original_stop = supervisor.StopEvent

    class FixtureStop(original_stop):
        def __init__(self):
            super().__init__(name=stop_name)

    supervisor.StopEvent = FixtureStop
    supervisor._initialize_recovery(root=control_root, activation_binding=binding)
    last_exit = EXIT_FIXTURE_INVALID
    executable = str(Path(sys.executable).resolve())
    fixture = str(Path(__file__).resolve())

    def run_attempt(_values, *, stop_event, series_id, attempt, retry_budget,
                    root, activation_binding):
        nonlocal last_exit
        permanent = values.failure_mode == "permanent"
        recovered = not permanent and values.succeed_on == attempt
        calls = [0]
        owned_core = [None]

        def children_started(_relay, core):
            owned_core[0] = core

        def probe():
            calls[0] += 1
            if calls[0] == 1:
                if permanent:
                    if owned_core[0] is None:
                        raise RuntimeError
                    owned_core[0].wait(timeout=5)
                if recovered:
                    def request_stop():
                        time.sleep(0.02)
                        stop_event.set()
                    threading.Thread(target=request_stop, daemon=True).start()
                return True, True
            return (True, True) if recovered else (True, False)

        outcome = supervisor._run_attempt(
            _values, stop_event=stop_event, series_id=series_id,
            attempt=attempt, retry_budget=retry_budget, root=root,
            activation_binding=activation_binding,
            relay_command=[
                executable, fixture, "--child-role", "relay",
                "--fixture-run-id", values.run_id,
            ],
            core_command_override=[
                executable, fixture, "--child-role",
                "core-permanent" if permanent else "core",
                "--fixture-run-id", values.run_id,
            ],
            probe=probe,
            required_paths=(Path(executable), Path(fixture)),
            relay_settle_seconds=0.01,
            children_started=children_started,
        )
        last_exit, expected = _record_attempt(
            values, attempt, recovered=recovered
        )
        actual = {
            "complete": "recovered",
            "stop_planned": "recovered",
            "retry": "retryable_failure",
            "stop_budget_exhausted": "budget_exhausted",
            "stop_non_retryable": "permanent_failure",
        }.get(outcome["recovery_disposition"])
        if actual != expected or (outcome["status"] == 0) != recovered:
            raise ValueError
        return outcome

    mutex_name = "Global\\NobusSpaceM1S1Fixture-" + hashlib.sha256(
        (values.run_id + values.receipt.name).encode("ascii")
    ).hexdigest()[:32]
    try:
        status = supervisor._run_owned_recovery(
            values, mutex_name=mutex_name, root=control_root,
            activation_binding=binding, run_attempt=run_attempt,
        )
    finally:
        supervisor.StopEvent = original_stop
    inspection = supervisor._inspect_recovery(
        root=control_root, activation_binding=binding
    )
    if values.failure_mode == "permanent":
        expected_inspection = ("STOP", "blocked", "stop_non_retryable")
    elif values.succeed_on > 0:
        expected_inspection = ("PASS", "new", None)
    else:
        expected_inspection = ("STOP", "blocked", "stop_budget_exhausted")
    if (
        inspection["status"], inspection["state"], inspection["reason"]
    ) != expected_inspection:
        raise ValueError
    return 0 if status == 0 else last_exit


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if (len(arguments) == 4 and arguments[0] == "--child-role"
            and arguments[2] == "--fixture-run-id"
            and re.fullmatch(r"[0-9a-f]{32}", arguments[3]) is not None):
        return _child(arguments[1])
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--restart-budget", type=int, required=True)
    parser.add_argument("--succeed-on", type=int, required=True)
    parser.add_argument(
        "--failure-mode", choices=("transient", "permanent"), default="transient"
    )
    parser.add_argument("--controller", action="store_true")
    parser.add_argument("--controller-sha256")
    parser.add_argument("--retry-interval-seconds", type=float, default=60.0)
    values = parser.parse_args(arguments)
    try:
        if (
            re.fullmatch(r"[0-9a-f]{32}", values.run_id) is None
            or not 1 <= values.restart_budget <= 10
            or not 0 <= values.succeed_on <= values.restart_budget + 1
            or (values.failure_mode == "permanent" and values.succeed_on != 0)
            or not 0.001 <= values.retry_interval_seconds <= 60
            or not values.receipt.is_absolute()
            or (values.controller and re.fullmatch(
                r"[0-9a-f]{64}", values.controller_sha256 or ""
            ) is None)
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
        return _product_controller(values)
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
        return EXIT_FIXTURE_INVALID


if __name__ == "__main__":
    raise SystemExit(main())
