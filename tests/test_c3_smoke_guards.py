"""Offline verification of C3 smoke authorization and aggregate accounting."""

import asyncio
import json
import sqlite3
from types import SimpleNamespace

import pytest

from tests.gate_c3 import budget, product_smoke as smoke
from src.workers.codex_cli import CodexCliError, CodexCliResult
from src.workers.codex_sdk import ResilientCodexAdapter
from tests.test_codex_sdk import _contract


BINDING = "a" * 64


def test_unfinished_reservation_is_charged_and_blocks_other_process(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    ledger = budget.Budget(path)
    number = ledger.reserve("model", "direct_text", "compiler", BINDING, 180)
    reopened = budget.Budget(path)
    assert reopened.snapshot()["resources"]["model"]["charged_seconds"] == 180
    with pytest.raises(RuntimeError, match="unfinished_budget_reservation"):
        reopened.reserve("asr", "direct_voice", "native_inference", BINDING, 190)
    ledger.finish(number, 0.5, "RETURNED")
    assert reopened.snapshot()["resources"]["model"]["charged_seconds"] == 0.5
    assert reopened.snapshot()["active_reservations"] == 0


@pytest.mark.parametrize("resource", ("model", "asr"))
def test_budget_requires_enough_full_call_and_time_reserve(tmp_path, monkeypatch, resource):
    monkeypatch.setitem(budget.LIMITS, resource, (2, 5.0))
    ledger = budget.Budget(tmp_path / "ledger.sqlite3")
    first = ledger.reserve(resource, "direct_text", "compiler", BINDING, 4)
    ledger.finish(first, 3, "RETURNED")
    with pytest.raises(RuntimeError, match="authorization_budget_exhausted"):
        ledger.reserve(resource, "direct_text", "compiler", BINDING, 3)
    second = ledger.reserve(resource, "direct_text", "compiler", BINDING, 2)
    ledger.finish(second, 0, "RETURNED")
    with pytest.raises(RuntimeError, match="authorization_budget_exhausted"):
        ledger.reserve(resource, "direct_text", "compiler", BINDING, 1)


def test_three_transients_allow_only_one_explicit_diagnostic(tmp_path):
    ledger = budget.Budget(tmp_path / "ledger.sqlite3")
    for _ in range(3):
        n = ledger.reserve("model", "direct_text", "compiler", BINDING, 180)
        ledger.finish(n, 1, "worker_failed")
    with pytest.raises(RuntimeError, match="requires_one_diagnostic"):
        ledger.reserve("model", "direct_text", "compiler", BINDING, 180)
    n = ledger.reserve("model", "direct_text", "compiler", BINDING, 180, diagnostic=True)
    ledger.finish(n, 1, "worker_failed")
    with pytest.raises(RuntimeError, match="requires_one_diagnostic"):
        ledger.reserve("model", "direct_text", "compiler", BINDING, 180, diagnostic=True)


def test_actual_turn_and_finish_are_one_shot(tmp_path):
    ledger = budget.Budget(tmp_path / "ledger.sqlite3")
    facade = budget.TurnBudget(ledger)
    with pytest.raises(RuntimeError, match="without_active"):
        facade.reserve("direct_text", "compiler")
    number = ledger.reserve("model", "direct_text", "compiler", BINDING, 180)
    facade.active = number
    assert facade.reserve("direct_text", "compiler") == number
    facade.finish(number, "RETURNED")
    assert ledger.snapshot()["active_reservations"] == 1
    assert ledger.snapshot()["resources"]["model"]["actual_model_turns"] == 1
    with pytest.raises(RuntimeError, match="one_reservation"):
        facade.reserve("direct_text", "compiler")
    ledger.finish(number, 1, "RETURNED")
    with pytest.raises(RuntimeError, match="outcome_conflict"):
        ledger.finish(number, 0, "RETURNED")


@pytest.mark.asyncio
async def test_wrapper_accounts_after_sdk_release_and_serializes(tmp_path):
    ledger = budget.Budget(tmp_path / "ledger.sqlite3")
    facade = budget.TurnBudget(ledger)
    entered, release = asyncio.Event(), asyncio.Event()

    class Primary:
        async def execute(self, contract):
            facade.reserve("direct_text", "downstream")
            facade.finish(facade.active, "RETURNED")
            entered.set()
            await release.wait()  # Represents SDK generation release/cleanup.
            return "ready"

    wrapper = smoke.BudgetedPrimary(Primary(), ledger, facade, "direct_text", BINDING)
    task = asyncio.create_task(wrapper.execute(None))
    await entered.wait()
    assert ledger.snapshot()["active_reservations"] == 1
    release.set()
    assert await task == "ready"
    assert ledger.snapshot()["active_reservations"] == 0
    with sqlite3.connect(ledger.path) as db:
        assert db.execute("SELECT status,model_turn_started FROM calls").fetchone() == ("RETURNED", 1)


def test_fixture_reuses_accepted_synthetic_material():
    assert smoke.fixture("direct_text") == smoke.fixture("direct_voice")
    assert "три пункта" in smoke.fixture("direct_voice")
    assert "цитата" in smoke.fixture("material_text")
    with pytest.raises(RuntimeError, match="not_authorized"):
        smoke.fixture("unknown")


@pytest.mark.asyncio
async def test_inspect_cannot_start_provider_or_asr(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("inspection cannot start inference or account calls")

    monkeypatch.setattr(smoke, "LEDGER", tmp_path / "ledger.sqlite3")
    monkeypatch.setattr(smoke, "bind_sources", lambda *args: {"synthetic": True})
    monkeypatch.setattr(smoke.old, "cli_status", forbidden)
    monkeypatch.setattr(smoke.old, "GuardedClient", forbidden)
    monkeypatch.setattr(smoke, "BudgetedVoice", forbidden)
    args = SimpleNamespace(run=tmp_path / "run", model=tmp_path, audio=None,
        scenario="direct_text", phase="inspect", authorized_run=False)
    args.run.mkdir()
    await smoke.run(args)
    result = json.loads((args.run / "direct_text/inspect.json").read_text("utf-8"))
    assert result["inference"] is False
    assert result["budget"]["resources"]["model"]["reserved_calls"] == 0
    assert result["budget"]["resources"]["asr"]["reserved_calls"] == 0


@pytest.mark.asyncio
async def test_execution_requires_opt_in_before_login(tmp_path, monkeypatch):
    monkeypatch.setattr(smoke, "LEDGER", tmp_path / "ledger.sqlite3")
    monkeypatch.setattr(smoke, "bind_sources", lambda *args: {"synthetic": True})
    monkeypatch.setattr(smoke.old, "cli_status", lambda *args: pytest.fail("unauthorized login"))
    args = SimpleNamespace(run=tmp_path / "run", model=tmp_path, audio=None,
        scenario="direct_text", phase="admit", authorized_run=False)
    args.run.mkdir()
    with pytest.raises(RuntimeError, match="explicit_authorized_run_required"):
        await smoke.run(args)


def test_source_guard_rejects_non_c3_output_and_other_model(tmp_path):
    with pytest.raises(RuntimeError, match="run_must_stay_in_c3"):
        smoke.bind_sources(smoke.ROOT / "outside-c3", tmp_path, None)
    with pytest.raises(RuntimeError, match="model_must_be_pinned_c2_cache"):
        smoke.bind_sources((smoke.C3 / "guard").resolve(), tmp_path, None)


def test_unproven_cleanup_blocks_following_calls(tmp_path):
    ledger = budget.Budget(tmp_path / "ledger.sqlite3")
    number = ledger.reserve("model", "direct_text", "compiler", BINDING, 180)
    ledger.finish(number, 1.5, "RETURNED")
    ledger.add_cleanup(number, 0.5)
    assert ledger.snapshot()["resources"]["model"]["charged_seconds"] == 2
    ledger.hold_cleanup_failure(number)
    assert ledger.snapshot()["resources"]["model"]["charged_seconds"] == 180
    with pytest.raises(RuntimeError, match="unfinished_budget_reservation"):
        ledger.reserve("model", "direct_text", "compiler", BINDING, 180)


@pytest.mark.asyncio
async def test_resilient_retry_reserves_each_actual_attempt(tmp_path):
    ledger = budget.Budget(tmp_path / "ledger.sqlite3")
    facade = budget.TurnBudget(ledger)

    class Primary:
        calls = 0

        async def execute(self, contract):
            self.calls += 1
            facade.reserve("direct_text", "downstream")
            if self.calls == 1:
                facade.finish(facade.active, "worker_failed")
                raise CodexCliError("worker_failed")
            facade.finish(facade.active, "RETURNED")
            return CodexCliResult(message='{"answer":"ready"}')

    class ForbiddenFallback:
        async def execute(self, contract):
            pytest.fail("non-web fallback")

        async def verify(self, *args):
            pytest.fail("non-web verifier")

    counted = smoke.BudgetedPrimary(Primary(), ledger, facade, "direct_text", BINDING)
    forbidden = ForbiddenFallback()
    result = await ResilientCodexAdapter(counted, forbidden, forbidden).execute(_contract(tmp_path))
    assert result.message == '{"answer":"ready"}'
    snapshot = ledger.snapshot()
    assert snapshot["resources"]["model"]["reserved_calls"] == 2
    assert snapshot["resources"]["model"]["actual_model_turns"] == 2
    assert snapshot["active_reservations"] == 0


@pytest.mark.asyncio
async def test_bootstrap_charges_startup_and_release_without_model_turn(tmp_path):
    ledger = budget.Budget(tmp_path / "ledger.sqlite3")
    facade = budget.TurnBudget(ledger)
    events = []
    client = object()

    class Primary:
        generation_available = False

        async def _client_instance(self):
            events.append("start")
            assert ledger.snapshot()["active_reservations"] == 1
            self.generation_available = True
            return client

        async def _release_client(self, value):
            assert value is client
            events.append("release")
            assert ledger.snapshot()["active_reservations"] == 1

    counted = smoke.BudgetedPrimary(Primary(), ledger, facade, "direct_text", BINDING)
    await counted.bootstrap()
    await counted.bootstrap()
    assert events == ["start", "release"]
    snapshot = ledger.snapshot()
    assert snapshot["resources"]["model"]["reserved_calls"] == 1
    assert snapshot["resources"]["model"]["actual_model_turns"] == 0
    assert snapshot["active_reservations"] == 0


@pytest.mark.asyncio
async def test_failed_retired_generation_cleanup_holds_reservation(tmp_path):
    ledger = budget.Budget(tmp_path / "ledger.sqlite3")
    facade = budget.TurnBudget(ledger)

    class Primary:
        _retired_clients = {1: object()}
        _retired_outcomes = {1: False}

        async def execute(self, contract):
            facade.reserve("direct_text", "downstream")
            facade.finish(facade.active, "worker_failed")
            raise CodexCliError("worker_failed")

    counted = smoke.BudgetedPrimary(Primary(), ledger, facade, "direct_text", BINDING)
    with pytest.raises(CodexCliError) as error:
        await counted.execute(None)
    assert error.value.code == "worker_failed"
    snapshot = ledger.snapshot()
    assert snapshot["active_reservations"] == 1
    assert snapshot["resources"]["model"]["charged_seconds"] == 180
    with pytest.raises(RuntimeError, match="unfinished_budget_reservation"):
        await counted.execute(None)
    ledger.add_cleanup(counted.last_reservation, 0.5)
    assert ledger.snapshot()["active_reservations"] == 1
    assert ledger.snapshot()["resources"]["model"]["charged_seconds"] == 180.5


@pytest.mark.asyncio
async def test_startup_client_failed_close_is_observable_without_retired_generation(tmp_path, monkeypatch):
    ledger = budget.Budget(tmp_path / "ledger.sqlite3")
    facade = budget.TurnBudget(ledger)
    primary = SimpleNamespace()
    counted = smoke.BudgetedPrimary(primary, ledger, facade, "direct_text", BINDING)

    def fake_init(self, *args):
        pass

    async def failed_close(self):
        raise RuntimeError("app_server_remains_alive")

    monkeypatch.setattr(smoke.old.GuardedClient, "__init__", fake_init)
    monkeypatch.setattr(smoke.old.GuardedClient, "close", failed_close)
    client = smoke.CleanupObservedClient(None, facade, "direct_text", tmp_path)
    counted.clients.append(client)

    async def failed_start():
        # SDK _client_instance currently suppresses this close outcome when
        # __aenter__ fails before the generation is registered as active.
        with pytest.raises(RuntimeError, match="remains_alive"):
            await client.close()
        raise CodexCliError("worker_start_failed")

    with pytest.raises(CodexCliError) as error:
        await counted._call("startup", failed_start)
    assert error.value.code == "worker_start_failed"
    assert ledger.snapshot()["active_reservations"] == 1
    assert ledger.snapshot()["resources"]["model"]["actual_model_turns"] == 0
