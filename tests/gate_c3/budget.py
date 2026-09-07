"""One durable C3 budget; unfinished reservations remain charged and block work."""

from __future__ import annotations

import math
from pathlib import Path
import re
import sqlite3
import time


LIMITS = {"model": (64, 5400.0), "asr": (20, 1200.0)}
TRANSIENT = frozenset({"worker_failed", "worker_start_failed", "worker_timeout"})


class Budget:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS calls (
                n INTEGER PRIMARY KEY, resource TEXT NOT NULL, scenario TEXT NOT NULL,
                kind TEXT NOT NULL, binding TEXT NOT NULL, started REAL NOT NULL,
                reserved REAL NOT NULL, charged REAL NOT NULL, finished REAL,
                status TEXT NOT NULL, model_turn_started INTEGER NOT NULL DEFAULT 0,
                diagnostic INTEGER NOT NULL DEFAULT 0)""")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_active_call ON calls((1)) WHERE finished IS NULL")

    def snapshot(self):
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT resource,COUNT(*),COALESCE(SUM(charged),0),SUM(model_turn_started) FROM calls GROUP BY resource").fetchall()
            active = db.execute("SELECT COUNT(*) FROM calls WHERE finished IS NULL").fetchone()[0]
        totals = {resource: {"reserved_calls": 0, "charged_seconds": 0.0, "actual_model_turns": 0} for resource in LIMITS}
        for resource, count, charged, started in rows:
            totals[resource] = {"reserved_calls": count, "charged_seconds": charged, "actual_model_turns": started}
        for resource, (count, seconds) in LIMITS.items():
            totals[resource].update(max_calls=count, max_seconds=seconds,
                remaining_calls=max(0, count-totals[resource]["reserved_calls"]),
                remaining_seconds=max(0.0, seconds-totals[resource]["charged_seconds"]))
        return {"resources": totals, "active_reservations": active}

    def reserve(self, resource, scenario, kind, binding, seconds, *, diagnostic=False):
        if (resource not in LIMITS or not all(isinstance(value, str) and re.fullmatch(r"[a-z_]{1,80}", value) for value in (scenario, kind))
            or not isinstance(binding, str) or re.fullmatch(r"[0-9a-f]{64}", binding) is None
            or isinstance(seconds, bool) or not math.isfinite(seconds) or seconds <= 0):
            raise RuntimeError("budget_reservation_invalid")
        maximum, allowed_seconds = LIMITS[resource]
        with sqlite3.connect(self.path, timeout=5) as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM calls WHERE finished IS NULL").fetchone()[0]:
                raise RuntimeError("unfinished_budget_reservation")
            count, charged = db.execute("SELECT COUNT(*),COALESCE(SUM(charged),0) FROM calls WHERE resource=?", (resource,)).fetchone()
            if count >= maximum or charged + seconds > allowed_seconds:
                raise RuntimeError("authorization_budget_exhausted")
            previous = [row[0] for row in db.execute("SELECT status FROM calls WHERE resource='model' ORDER BY n DESC LIMIT 3")]
            stalled = resource == "model" and len(previous) == 3 and previous[0] in TRANSIENT and len(set(previous)) == 1
            if stalled:
                if not diagnostic or db.execute("SELECT COUNT(*) FROM calls WHERE diagnostic=1").fetchone()[0]:
                    raise RuntimeError("repeated_transient_requires_one_diagnostic")
            elif diagnostic:
                raise RuntimeError("diagnostic_repeat_not_applicable")
            cursor = db.execute("INSERT INTO calls(resource,scenario,kind,binding,started,reserved,charged,status,diagnostic) VALUES(?,?,?,?,?,?,?,'RESERVED',?)",
                (resource, scenario, kind, binding, time.time(), seconds, seconds, int(stalled)))
            return cursor.lastrowid

    def mark_turn(self, n):
        with sqlite3.connect(self.path) as db:
            cursor = db.execute("UPDATE calls SET model_turn_started=1 WHERE n=? AND resource='model' AND finished IS NULL AND model_turn_started=0", (n,))
            if cursor.rowcount != 1:
                raise RuntimeError("model_turn_not_bound_to_one_reservation")

    def finish(self, n, elapsed, status):
        if (isinstance(elapsed, bool) or not math.isfinite(elapsed) or elapsed < 0
            or not isinstance(status, str) or re.fullmatch(r"[A-Za-z_]{1,80}", status) is None):
            raise RuntimeError("budget_outcome_invalid")
        with sqlite3.connect(self.path) as db:
            cursor = db.execute("UPDATE calls SET finished=?,charged=?,status=? WHERE n=? AND finished IS NULL", (time.time(), elapsed, status, n))
            if cursor.rowcount != 1:
                raise RuntimeError("budget_outcome_conflict")

    def add_cleanup(self, n, elapsed):
        if isinstance(elapsed, bool) or not math.isfinite(elapsed) or elapsed < 0:
            raise RuntimeError("budget_cleanup_invalid")
        with sqlite3.connect(self.path) as db:
            cursor = db.execute("UPDATE calls SET charged=charged+? WHERE n=?", (elapsed, n))
            if cursor.rowcount != 1:
                raise RuntimeError("budget_cleanup_conflict")

    def hold_cleanup_failure(self, n):
        """Unproven process cleanup retains its full reservation and blocks starts."""
        with sqlite3.connect(self.path) as db:
            if db.execute("UPDATE calls SET finished=NULL,charged=MAX(charged,reserved),status='CLEANUP_FAILED' WHERE n=?", (n,)).rowcount != 1:
                raise RuntimeError("budget_cleanup_conflict")


class TurnBudget:
    """C2 recording adapter: count the actual turn, finish only after SDK cleanup."""
    def __init__(self, ledger):
        self.ledger = ledger
        self.active = None

    def reserve(self, scenario, kind):
        if self.active is None:
            raise RuntimeError("model_turn_without_active_budget")
        self.ledger.mark_turn(self.active)
        return self.active

    def finish(self, number, status, usage=None):
        if number != self.active:
            raise RuntimeError("model_turn_budget_mismatch")
        # GuardedTurn persists usage/response; durable time includes outer cleanup.
