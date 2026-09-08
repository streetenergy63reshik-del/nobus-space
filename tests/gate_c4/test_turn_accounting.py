"""C4 authorization counts SDK turns, retaining every startup/failure/cleanup row."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from tests.gate_c3.budget import Budget as LegacyBudget
from tests.gate_c4.budget import Budget, TurnBudget


def reserve(ledger, kind='compiler', resource='model', seconds=1):
    return ledger.reserve(resource, 'guard', kind, 'a'*64, seconds)


def completed(ledger, *, turn=True, kind='compiler', seconds=1):
    n=reserve(ledger,kind)
    if turn:ledger.mark_turn(n)
    ledger.finish(n,seconds,'RETURNED')
    return n


def test_closed_no_turn_operations_preserve_rows_time_and_do_not_spend_turns(tmp_path):
    path=tmp_path/'ledger.sqlite3';old=LegacyBudget(path)
    completed(old,turn=False,kind='startup',seconds=2)
    n=reserve(old);old.finish(n,3,'worker_start_failed')
    with sqlite3.connect(path) as db:before=db.execute('select * from calls order by n').fetchall()
    ledger=Budget(path)
    for _ in range(63):completed(ledger)
    state=ledger.snapshot()['resources']['model']
    assert state['reserved_calls']==65 and state['actual_model_turns']==63
    assert state['remaining_calls']==1 and state['charged_seconds']==68
    with sqlite3.connect(path) as db:assert db.execute('select * from calls order by n limit 2').fetchall()==before
    last=reserve(ledger)
    assert ledger.snapshot()['resources']['model']['remaining_calls']==0
    assert ledger.snapshot()['resources']['model']['active_potential_turns']==1
    ledger.mark_turn(last);ledger.finish(last,2,'worker_timeout')
    with pytest.raises(RuntimeError,match='authorization_budget_exhausted'):reserve(ledger)
    assert Budget(path).snapshot()['resources']['model']['actual_model_turns']==64


def test_startup_can_never_become_an_unreserved_model_turn(tmp_path):
    ledger=Budget(tmp_path/'ledger.sqlite3');n=reserve(ledger,'startup')
    with pytest.raises(RuntimeError,match='model_turn_not_bound'):ledger.mark_turn(n)
    assert ledger.snapshot()['resources']['model']['actual_model_turns']==0
    ledger.finish(n,2,'RETURNED')


def test_two_concurrent_reservations_cannot_share_last_potential_turn(tmp_path):
    ledger=Budget(tmp_path/'ledger.sqlite3')
    for _ in range(63):completed(ledger)
    def attempt():
        try:return reserve(Budget(ledger.path))
        except RuntimeError as e:return str(e)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:attempt(),range(2)))
    assert sum(isinstance(x,int) for x in results)==1
    assert 'unfinished_budget_reservation' in results
    n=next(x for x in results if isinstance(x,int));ledger.mark_turn(n)
    with pytest.raises(RuntimeError,match='model_turn_not_bound'):ledger.mark_turn(n)
    ledger.finish(n,1,'RETURNED')


def test_mark_occurs_before_sdk_and_failed_sdk_still_spends_turn(tmp_path):
    ledger=Budget(tmp_path/'ledger.sqlite3');n=reserve(ledger);turns=TurnBudget(ledger);turns.active=n
    assert turns.reserve('guard','compiler')==n
    assert ledger.snapshot()['resources']['model']['actual_model_turns']==1
    ledger.finish(n,3,'worker_failed')
    assert Budget(ledger.path).snapshot()['resources']['model']['actual_model_turns']==1


@pytest.mark.parametrize('kind',['startup','compiler'])
def test_unproven_zero_turn_cleanup_blocks_reserve_and_mark(tmp_path,kind):
    ledger=Budget(tmp_path/'ledger.sqlite3');n=completed(ledger,turn=False,kind=kind)
    ledger.hold_cleanup_failure(n)
    with pytest.raises(RuntimeError,match='unfinished_budget_reservation'):reserve(ledger)
    with pytest.raises(RuntimeError,match='model_turn_not_bound'):ledger.mark_turn(n)


@pytest.mark.parametrize('resource,limit',[('model',5400),('asr',1200)])
def test_full_time_reservation_includes_startup_and_cleanup(tmp_path,resource,limit):
    ledger=Budget(tmp_path/'ledger.sqlite3');n=reserve(ledger,'startup' if resource=='model' else 'native_inference',resource)
    ledger.finish(n,limit-3,'RETURNED');ledger.add_cleanup(n,2)
    with pytest.raises(RuntimeError,match='authorization_budget_exhausted'):reserve(ledger,resource=resource,seconds=2)
    assert ledger.snapshot()['resources'][resource]['remaining_seconds']==1


def test_native_asr_remains_twenty_runs_even_without_model_turns(tmp_path):
    ledger=Budget(tmp_path/'ledger.sqlite3')
    for _ in range(20):
        n=reserve(ledger,'native_inference','asr');ledger.finish(n,1,'RETURNED')
    with pytest.raises(RuntimeError,match='authorization_budget_exhausted'):reserve(ledger,'native_inference','asr')
    assert ledger.snapshot()['resources']['asr']['reserved_calls']==20


def test_sixty_four_marked_turns_are_blocked_at_sdk_guard_even_if_reservation_is_old(tmp_path):
    ledger=Budget(tmp_path/'ledger.sqlite3')
    for _ in range(63):completed(ledger)
    n=reserve(ledger)
    # Simulate a pre-existing additional spent turn loaded from retained history.
    with sqlite3.connect(ledger.path) as db:
        db.execute("INSERT INTO calls(resource,scenario,kind,binding,started,reserved,charged,finished,status,model_turn_started) VALUES('model','history','compiler',?,0,1,1,1,'RETURNED',1)",('a'*64,))
    with pytest.raises(RuntimeError,match='authorization_budget_exhausted'):ledger.mark_turn(n)
    ledger.finish(n,0,'FAILED')
    assert ledger.snapshot()['resources']['model']['actual_model_turns']==64
