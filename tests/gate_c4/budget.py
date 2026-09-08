"""C4 counts actual model turns; all startup/failure time stays in its original ledger."""

from pathlib import Path
import math
import re
import sqlite3
import subprocess
import time

from tests.gate_c3.budget import Budget as ReservationBudget, LIMITS, TRANSIENT, TurnBudget


class Budget(ReservationBudget):
    """Keep the C3 ledger schema/cleanup, enforcing the C4 prompt's 64 turns.

    Closed zero-turn SDK startups/failed starts retain their time and history.
    A non-startup reservation holds one potential turn until finish; mark_turn
    is called before the SDK and cannot convert a startup into inference.
    """

    def snapshot(self):
        result = super().snapshot()
        with sqlite3.connect(self.path) as db:
            potential = db.execute("SELECT COUNT(*) FROM calls WHERE resource='model' AND finished IS NULL AND model_turn_started=0 AND kind!='startup'").fetchone()[0]
        model = result['resources']['model']
        model.update(counting_basis='actual_model_turns_plus_active_potential_turns',
                     active_potential_turns=potential, max_model_turns=LIMITS['model'][0],
                     remaining_calls=max(0, LIMITS['model'][0]-model['actual_model_turns']-potential))
        return result

    def reserve(self, resource, scenario, kind, binding, seconds, *, diagnostic=False):
        if (resource not in LIMITS or not all(isinstance(v, str) and re.fullmatch(r'[a-z_]{1,80}', v) for v in (scenario, kind))
            or not isinstance(binding, str) or re.fullmatch(r'[0-9a-f]{64}', binding) is None
            or isinstance(seconds, bool) or not math.isfinite(seconds) or seconds <= 0):
            raise RuntimeError('budget_reservation_invalid')
        maximum, allowed_seconds = LIMITS[resource]
        with sqlite3.connect(self.path, timeout=5) as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT COUNT(*) FROM calls WHERE finished IS NULL').fetchone()[0]:
                raise RuntimeError('unfinished_budget_reservation')
            count, charged, turns = db.execute('SELECT COUNT(*),COALESCE(SUM(charged),0),COALESCE(SUM(model_turn_started),0) FROM calls WHERE resource=?', (resource,)).fetchone()
            used = turns if resource == 'model' else count
            needs_slot = resource != 'model' or kind != 'startup'
            if (needs_slot and used >= maximum) or charged + seconds > allowed_seconds:
                raise RuntimeError('authorization_budget_exhausted')
            previous = [row[0] for row in db.execute("SELECT status FROM calls WHERE resource='model' ORDER BY n DESC LIMIT 3")]
            stalled = resource == 'model' and len(previous) == 3 and previous[0] in TRANSIENT and len(set(previous)) == 1
            if stalled:
                if not diagnostic or db.execute('SELECT COUNT(*) FROM calls WHERE diagnostic=1').fetchone()[0]:
                    raise RuntimeError('repeated_transient_requires_one_diagnostic')
            elif diagnostic:
                raise RuntimeError('diagnostic_repeat_not_applicable')
            cursor = db.execute("INSERT INTO calls(resource,scenario,kind,binding,started,reserved,charged,status,diagnostic) VALUES(?,?,?,?,?,?,?,'RESERVED',?)",
                                (resource,scenario,kind,binding,time.time(),seconds,seconds,int(stalled)))
            return cursor.lastrowid

    def mark_turn(self, n):
        with sqlite3.connect(self.path, timeout=5) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT resource,kind,finished,model_turn_started,status FROM calls WHERE n=?',(n,)).fetchone()
            if row is None or row[0]!='model' or row[1]=='startup' or row[2] is not None or row[3]!=0 or row[4]!='RESERVED':
                raise RuntimeError('model_turn_not_bound_to_one_reservation')
            turns = db.execute("SELECT COALESCE(SUM(model_turn_started),0) FROM calls WHERE resource='model'").fetchone()[0]
            if turns >= LIMITS['model'][0]:
                raise RuntimeError('authorization_budget_exhausted')
            db.execute('UPDATE calls SET model_turn_started=1 WHERE n=?',(n,))


ROOT = Path(__file__).resolve().parents[2]


def ledger_path() -> Path:
    # git-common-dir identifies the canonical repository from review worktrees too.
    common = Path(subprocess.check_output(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=ROOT, text=True, encoding="utf-8",
    ).strip())
    return common.parent / ".runtime/worktrees/mvp1-closure-c4-frontend-journey/.runtime/c4/execution-budget.sqlite3"


__all__ = ["Budget", "LIMITS", "TurnBudget", "ledger_path"]
