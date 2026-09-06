"""Authorization accounting regressions; no model, subprocess or network calls."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("c2_budget_runner", Path(__file__).with_name("runner.py"))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_small_abrupt_runs_remain_charged_after_restart(tmp_path):
    path = tmp_path / "small.json"
    for index in range(4):
        runner.reserve_budget(path, str(index), 300, small=True)
    with pytest.raises(RuntimeError, match="exhausted"):
        runner.reserve_budget(path, "restart", 10, small=True)
    assert sum(row["charged_seconds"] for row in runner.read_json(path)["runs"]) == 1200


def test_budget_cannot_be_reopened_as_other_model(tmp_path):
    path = tmp_path / "ledger.json"
    runner.reserve_budget(path, "first", 150, small=True)
    with pytest.raises(ValueError, match="constants changed"):
        runner.reserve_budget(path, "other", 150)


def test_unfinished_reservation_cannot_release_unused_time(tmp_path):
    path = tmp_path / "ledger.json"
    ledger, _ = runner.reserve_budget(path, "interrupted", 150, small=True)
    ledger["runs"][0]["charged_seconds"] = 10
    runner.atomic(path, ledger)
    with pytest.raises(ValueError, match="fully charged"):
        runner.reserve_budget(path, "restart", 150, small=True)


def test_finished_run_preserves_usage_and_bounds_next_reservation(tmp_path):
    path = tmp_path / "ledger.json"
    ledger, _ = runner.reserve_budget(path, "finished", 300, small=True)
    ledger["runs"][0].update(state="FINISHED", charged_seconds=250)
    runner.atomic(path, ledger)
    for index in range(3):
        runner.reserve_budget(path, str(index), 300, small=True)
    ledger, reserved = runner.reserve_budget(path, "last", 150, small=True)
    assert reserved == 50
    assert sum(row["charged_seconds"] for row in ledger["runs"]) == 1200


def test_original_giga_prior_and_cap_are_not_reset(tmp_path):
    path = tmp_path / "giga.json"
    for index in range(3):
        ledger, _ = runner.reserve_budget(path, str(index), 300)
    assert ledger["prior_consumed_seconds"] == 169.234
    assert ledger["authorized_seconds"] == 1800
    with pytest.raises(RuntimeError, match="exhausted"):
        runner.reserve_budget(path, "restart", 10)
