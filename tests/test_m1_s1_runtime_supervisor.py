"""M1-S1 supervisor diagnostics use only synthetic processes and private temp files."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts import run_nobus_space_live as supervisor
from tests.fixtures import m1_scheduler_exit_probe as scheduler_probe
from tests.gate_m1_s1 import audit_dependencies_osv as dependency_audit

_BINDING = "sha256:" + "9" * 64


class _Event:
    def __init__(self, *, stopped: bool = False) -> None:
        self.stopped = stopped
        self.waits = 0

    def is_set(self) -> bool:
        return self.stopped

    def wait(self, _seconds: float) -> bool:
        self.waits += 1
        return self.stopped


class _Process:
    def __init__(self, code: int | None = None) -> None:
        self.code = code

    def poll(self) -> int | None:
        return self.code


@pytest.mark.parametrize(
    ("payload", "overflow", "expected", "error"),
    [
        (
            b'{"status":"FAIL","code":"telegram_mvp1_polling_failed"}\n',
            False,
            {"status": "FAIL", "code": "telegram_mvp1_polling_failed"},
            None,
        ),
        (b'{"status":"STOPPED"}\n', False, {"status": "STOPPED"}, None),
        (b'{"status":"FAIL","code":"telegram_mvp1_polling_failed"}', False, None, "core_outcome_truncated"),
        (b'{"status":"FAIL","code":"safe","code":"forged"}\n', False, None, "core_outcome_invalid"),
        (b'{"status":"FAIL","code":"safe","detail":"raw"}\n', False, None, "core_outcome_invalid"),
        (b'{"status":"FAIL","code":"unsafe path C:/secret"}\n', False, None, "core_outcome_invalid"),
        (b'{"status":"STOPPED"}\n', True, None, "core_outcome_oversize"),
    ],
)
def test_m1_core_outcome_parser_preserves_only_complete_safe_json(payload, overflow, expected, error):
    assert supervisor._parse_core_outcome(payload, overflow=overflow) == (expected, error)


def test_m1_core_outcome_capture_is_bounded_and_drains_oversize_stream():
    stream = io.BytesIO(b"x" * 80)
    capture = supervisor._CoreOutcomeCapture(stream, limit=32)
    assert capture.finish() == (None, "core_outcome_oversize")
    assert stream.tell() == 80


@pytest.mark.skipif(os.name != "nt", reason="real isolated Windows Job proof")
def test_m1_gated_helper_propagates_child_exit_and_safe_outcome():
    api = supervisor._job_api()
    job = api.create_job()
    process = None
    try:
        process = supervisor.spawn_owned(
            api,
            job,
            [
                sys._base_executable,
                "-c",
                "import sys;print('{\"status\":\"FAIL\",\"code\":\"telegram_mvp1_polling_failed\"}');sys.exit(23)",
            ],
            stdout=subprocess.PIPE,
        )
        capture = supervisor._CoreOutcomeCapture(process.stdout)
        process.wait(timeout=10)
        assert process.returncode == 23
        assert capture.finish() == (
            {"status": "FAIL", "code": "telegram_mvp1_polling_failed"},
            None,
        )
    finally:
        api.terminate(job)
        supervisor.wait_job_empty(job)
        api.close(job)
        if process is not None:
            supervisor.close_owned(api, process)


@pytest.mark.parametrize(
    ("core_code", "relay_code", "error_class"),
    [(7, None, "core_exit"), (None, 255, "relay_exit"), (7, 255, "core_and_relay_exit")],
)
def test_m1_supervisor_distinguishes_child_exit(core_code, relay_code, error_class):
    reports = []
    status = supervisor.supervise(
        None,
        None,
        _Process(relay_code),
        _Process(core_code),
        _Event(),
        probe=lambda: (True, True),
        report=reports.append,
    )
    assert status == 1
    assert reports == [
        {
            "stage": "startup",
            "error_class": error_class,
            "core_exit_code": core_code,
            "relay_exit_code": relay_code,
            "local_ready": None,
            "public_ready": None,
            "readiness_failures": 0,
        }
    ]


@pytest.mark.parametrize(
    ("failed_pair", "error_class"),
    [
        ((False, True), "local_readiness_failed"),
        ((True, False), "public_readiness_failed"),
        ((False, False), "local_public_readiness_failed"),
    ],
)
def test_m1_supervisor_records_local_and_public_failures_separately(failed_pair, error_class):
    reports = []
    replies = iter([(True, True), failed_pair, failed_pair, failed_pair])
    event = _Event()
    status = supervisor.supervise(
        None,
        None,
        _Process(),
        _Process(),
        event,
        probe=lambda: next(replies),
        report=reports.append,
    )
    assert status == 1
    assert event.waits == 3
    assert reports[-1] == {
        "stage": "steady",
        "error_class": error_class,
        "core_exit_code": None,
        "relay_exit_code": None,
        "local_ready": failed_pair[0],
        "public_ready": failed_pair[1],
        "readiness_failures": 3,
    }


def test_m1_supervisor_distinguishes_startup_deadline_and_planned_stop(monkeypatch):
    monkeypatch.setattr(supervisor, "STARTUP_SECONDS", 1)
    ticks = iter((0, 0, 1))
    reports = []
    assert supervisor.supervise(
        None,
        None,
        _Process(),
        _Process(),
        _Event(),
        clock=lambda: next(ticks),
        probe=lambda: (False, True),
        report=reports.append,
    ) == 1
    assert reports[-1]["error_class"] == "startup_timeout"
    assert reports[-1]["local_ready"] is False
    assert reports[-1]["public_ready"] is True

    reports.clear()
    assert supervisor.supervise(
        None,
        None,
        _Process(),
        _Process(),
        _Event(stopped=True),
        probe=lambda: pytest.fail("planned stop must not probe"),
        report=reports.append,
    ) == 0
    assert reports[-1]["error_class"] == "planned_stop"


def _event_record(run_id: str = "a" * 32, **changes):
    value = {
        "schema": "nobus-runtime-event-3",
        "series_id": "f" * 32,
        "run_id": run_id,
        "event": "terminal",
        "stage": "steady",
        "error_class": "public_readiness_failed",
        "supervisor_exit_code": 1,
        "core_exit_code": None,
        "relay_exit_code": None,
        "local_ready": True,
        "public_ready": False,
        "readiness_failures": 3,
        "attempt": 1,
        "retry_budget": 10,
        "recovery_disposition": "retry",
        "core_outcome": None,
        "core_outcome_error": None,
        "cleanup_outcome": "proven",
        "activation_binding": _BINDING,
        "previous_event_digest": None,
        "reset_of_digest": None,
        "checkpoint_event": None,
        "anchor_of_digest": None,
    }
    value.update(changes)
    return value


def _record(root, series_id, run_id, event, **values):
    defaults = {
        "activation_binding": _BINDING,
        "attempt": 1,
        "retry_budget": 10,
        "recovery_disposition": "pending",
        "stage": "setup",
    }
    defaults.update(values)
    return supervisor._write_runtime_event(
        supervisor._runtime_record(series_id, run_id, event, **defaults),
        root=root,
    )


def _start_attempt(root, series_id, run_id, *, attempt=1, retry_budget=10):
    control_run = ("e" if attempt == 1 else "d") * 32
    _record(
        root, series_id, control_run, "control_starting", attempt=attempt,
        retry_budget=retry_budget, stage="recovery_control",
    )
    _record(
        root, series_id, control_run, "control_ready", attempt=attempt,
        retry_budget=retry_budget, stage="recovery_control", supervisor_exit_code=0,
    )
    return _record(
        root, series_id, run_id, "starting", attempt=attempt,
        retry_budget=retry_budget,
    )


def _close_control(root, series_id, *, attempt, retry_budget, disposition, status):
    closing_run = "8" * 32
    _record(
        root, series_id, closing_run, "control_closing", attempt=attempt,
        retry_budget=retry_budget, recovery_disposition=disposition,
        stage="recovery_control", supervisor_exit_code=status,
        cleanup_outcome="proven",
    )
    return _record(
        root, series_id, closing_run, "control_closed", attempt=attempt,
        retry_budget=retry_budget, recovery_disposition=disposition,
        stage="recovery_control", supervisor_exit_code=status,
        cleanup_outcome="proven",
    )


def test_m1_runtime_event_is_ascii_bounded_and_rotates_one_owned_file(tmp_path, monkeypatch):
    monkeypatch.setattr(supervisor, "RUNTIME_EVENT_LOG_BYTES", 6500)
    supervisor._initialize_recovery(root=tmp_path, activation_binding=_BINDING)
    for index in range(4):
        series_id = f"{index + 1:032x}"
        run_id = f"{index + 101:032x}"
        _start_attempt(tmp_path, series_id, run_id)
        _record(
            tmp_path, series_id, run_id, "terminal", stage="steady",
            error_class="planned_stop", supervisor_exit_code=0,
            recovery_disposition="stop_planned",
            core_outcome={"status": "STOPPED"}, cleanup_outcome="proven",
        )
        _close_control(
            tmp_path, series_id, attempt=1, retry_budget=10,
            disposition="stop_planned", status=0,
        )
    current = tmp_path / supervisor.RUNTIME_EVENT_LOG_NAME
    previous = tmp_path / (supervisor.RUNTIME_EVENT_LOG_NAME + ".previous")
    assert current.is_file() and previous.is_file()
    assert current.stat().st_size <= 6500 and previous.stat().st_size <= 6500
    for path in (current, previous):
        for line in path.read_bytes().splitlines():
            assert len(line) <= supervisor.RUNTIME_EVENT_LINE_BYTES
            value = json.loads(line.decode("ascii"))
            assert set(value) == supervisor.RUNTIME_EVENT_KEYS | {"at"}
            assert "payload" not in value and "argv" not in value and "environment" not in value


@pytest.mark.parametrize(
    "change",
    [
        {"task_text": "must never be logged"},
        {"run_id": "not-a-run-id"},
        {"attempt": 12},
        {"core_outcome": {"status": "FAIL", "code": "unsafe value"}},
    ],
)
def test_m1_runtime_event_rejects_untrusted_or_unbounded_fields(tmp_path, change):
    with pytest.raises(ValueError, match="runtime event"):
        supervisor._write_runtime_event(_event_record(**change), root=tmp_path)
    assert not (tmp_path / supervisor.RUNTIME_EVENT_LOG_NAME).exists()


def test_m1_runtime_event_write_failure_is_not_reported_as_success(tmp_path, monkeypatch):
    supervisor._initialize_recovery(root=tmp_path, activation_binding=_BINDING)
    monkeypatch.setattr(Path, "open", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("synthetic disk failure")))
    with pytest.raises(RuntimeError, match="runtime event write failed"):
        _record(tmp_path, "f" * 32, "a" * 32, "control_starting", stage="recovery_control")


def test_m1_readiness_cli_probes_local_and_public_even_when_local_fails(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(supervisor.sys, "argv", ["runner", "--check-ready"])
    monkeypatch.setattr(supervisor, "ready", lambda: calls.append("local") or False)
    monkeypatch.setattr(supervisor, "public_ready", lambda: calls.append("public") or True)
    monkeypatch.setattr(supervisor, "_main", lambda *_: pytest.fail("read-only probe started runtime"))
    assert supervisor.main() == 1
    assert calls == ["local", "public"]
    assert json.loads(capsys.readouterr().out) == {
        "status": "FAIL", "local_ready": False, "public_ready": True,
    }


def test_m1_bounded_recovery_retries_serially_then_recovers():
    calls = []
    outcomes = iter(
        (
            {"status": 1, "recovery_disposition": "retry"},
            {"status": 0, "recovery_disposition": "complete"},
        )
    )
    stop = _Event()

    def attempt(number):
        calls.append(number)
        return next(outcomes)

    assert supervisor._run_bounded_recovery(
        attempt,
        stop_event=stop,
        first_attempt=1,
        retry_budget=2,
        retry_interval=60,
    ) == 0
    assert calls == [1, 2]
    assert stop.waits == 1


def test_m1_bounded_recovery_does_not_retry_non_retryable_failure():
    calls = []

    def attempt(number):
        calls.append(number)
        return {"status": 1, "recovery_disposition": "stop_non_retryable"}

    assert supervisor._run_bounded_recovery(
        attempt,
        stop_event=_Event(),
        first_attempt=1,
        retry_budget=10,
        retry_interval=60,
    ) == 1
    assert calls == [1]


def test_m1_bounded_recovery_planned_stop_interrupts_retry_wait():
    stopped = _Event(stopped=True)
    wait_stops = []

    assert supervisor._run_bounded_recovery(
        lambda _number: {"status": 1, "recovery_disposition": "retry"},
        stop_event=stopped,
        first_attempt=1,
        retry_budget=10,
        retry_interval=60,
        on_wait_stop=wait_stops.append,
    ) == 0
    assert stopped.waits == 1
    assert wait_stops == [1]


def test_m1_bounded_recovery_rejects_inconsistent_attempt_outcome():
    with pytest.raises(ValueError, match="attempt outcome"):
        supervisor._run_bounded_recovery(
            lambda _number: {"status": 0, "recovery_disposition": "retry"},
            stop_event=_Event(),
            first_attempt=1,
            retry_budget=2,
            retry_interval=60,
        )


@pytest.mark.parametrize(
    ("terminal", "core_outcome", "cleanup_ok", "attempt", "expected"),
    [
        (
            {
                "stage": "steady",
                "error_class": "relay_exit",
                "local_ready": None,
                "public_ready": None,
            },
            {"status": "STOPPED"},
            True,
            1,
            "retry",
        ),
        (
            {
                "stage": "startup",
                "error_class": "relay_exit",
                "local_ready": None,
                "public_ready": None,
            },
            None,
            True,
            1,
            "stop_non_retryable",
        ),
        (
            {"error_class": "public_readiness_failed", "local_ready": True, "public_ready": False},
            {"status": "STOPPED"},
            True,
            1,
            "retry",
        ),
        (
            {"error_class": "core_exit", "local_ready": None, "public_ready": None},
            {"status": "FAIL", "code": "telegram_unavailable"},
            True,
            1,
            "retry",
        ),
        (
            {"error_class": "core_exit", "local_ready": None, "public_ready": None},
            {"status": "FAIL", "code": "telegram_checkpoint_failed"},
            True,
            1,
            "stop_non_retryable",
        ),
        (
            {"error_class": "local_readiness_failed", "local_ready": False, "public_ready": True},
            None,
            True,
            1,
            "stop_non_retryable",
        ),
        (
            {
                "stage": "steady",
                "error_class": "relay_exit",
                "local_ready": None,
                "public_ready": None,
            },
            None,
            False,
            1,
            "stop_cleanup_failed",
        ),
        (
            {
                "stage": "steady",
                "error_class": "relay_exit",
                "local_ready": None,
                "public_ready": None,
            },
            {"status": "STOPPED"},
            True,
            11,
            "stop_budget_exhausted",
        ),
    ],
)
def test_m1_recovery_classification_is_allowlisted_and_cleanup_gated(
    terminal, core_outcome, cleanup_ok, attempt, expected
):
    assert supervisor._recovery_disposition(
        status=1,
        terminal=terminal,
        core_outcome=core_outcome,
        core_outcome_error=None,
        cleanup_ok=cleanup_ok,
        attempt=attempt,
        retry_budget=10,
    ) == expected


def test_m1_recovery_history_blocks_unknown_and_resumes_known_retry(tmp_path):
    series_id = "b" * 32
    run_id = "c" * 32
    supervisor._initialize_recovery(root=tmp_path, activation_binding=_BINDING)
    _start_attempt(tmp_path, series_id, run_id)
    unknown = supervisor._recovery_state(
        root=tmp_path, activation_binding=_BINDING
    )
    assert unknown["state"] == "blocked"
    assert unknown["reason"] == "previous_attempt_unknown"

    _record(
        tmp_path, series_id, run_id, "terminal",
        stage="steady", error_class="public_readiness_failed",
        supervisor_exit_code=1, local_ready=True, public_ready=False,
        readiness_failures=3, recovery_disposition="retry",
        core_outcome={"status": "STOPPED"}, cleanup_outcome="proven",
    )
    assert supervisor._recovery_state(
        root=tmp_path, activation_binding=_BINDING
    )["reason"] == "retry_transition_missing"
    _record(
        tmp_path, series_id, "7" * 32, "retry_waiting",
        stage="recovery_wait", recovery_disposition="retry",
        cleanup_outcome="proven",
    )
    assert supervisor._recovery_state(
        root=tmp_path, activation_binding=_BINDING
    )["reason"] == "recovery_wait_unknown"
    _record(
        tmp_path, series_id, "6" * 32, "retry_elapsed",
        stage="recovery_wait", recovery_disposition="retry",
        cleanup_outcome="proven",
    )
    resumable = supervisor._recovery_state(
        root=tmp_path, activation_binding=_BINDING
    )
    assert resumable["state"] == "resume"
    assert resumable["series_id"] == series_id
    assert resumable["next_attempt"] == 2


def test_m1_recovery_stop_reset_requires_exact_latest_digest(tmp_path):
    series_id = "d" * 32
    run_id = "c" * 32
    supervisor._initialize_recovery(root=tmp_path, activation_binding=_BINDING)
    _start_attempt(tmp_path, series_id, run_id)
    _record(
        tmp_path, series_id, run_id, "terminal", stage="steady",
        error_class="local_readiness_failed", supervisor_exit_code=1,
        local_ready=False, public_ready=True, readiness_failures=3,
        recovery_disposition="stop_non_retryable",
        core_outcome={"status": "STOPPED"}, cleanup_outcome="proven",
    )
    terminal_digest = _close_control(
        tmp_path, series_id, attempt=1, retry_budget=10,
        disposition="stop_non_retryable", status=1,
    )
    assert supervisor._inspect_recovery(
        root=tmp_path, activation_binding=_BINDING
    )["status"] == "STOP"

    with pytest.raises(RuntimeError, match="precondition"):
        supervisor._acknowledge_recovery_stop(
            "sha256:" + "0" * 64, root=tmp_path,
            activation_binding=_BINDING,
        )
    assert supervisor._recovery_state(
        root=tmp_path, activation_binding=_BINDING
    )["state"] == "blocked"

    result = supervisor._acknowledge_recovery_stop(
        terminal_digest, root=tmp_path, activation_binding=_BINDING
    )
    assert result["status"] == "RESET"
    assert result["reset_of_digest"] == terminal_digest
    assert supervisor._recovery_state(
        root=tmp_path, activation_binding=_BINDING
    )["state"] == "new"


def test_m1_planned_stop_is_distinct_and_allows_a_later_clean_start(tmp_path):
    assert supervisor._recovery_disposition(
        status=0,
        terminal={
            "stage": "steady",
            "error_class": "planned_stop",
            "local_ready": None,
            "public_ready": None,
        },
        core_outcome={"status": "STOPPED"},
        core_outcome_error=None,
        cleanup_ok=True,
        attempt=1,
        retry_budget=10,
    ) == "stop_planned"
    series_id = "f" * 32
    run_id = "a" * 32
    supervisor._initialize_recovery(root=tmp_path, activation_binding=_BINDING)
    _start_attempt(tmp_path, series_id, run_id)
    _record(
        tmp_path, series_id, run_id, "terminal", stage="steady",
        error_class="planned_stop", supervisor_exit_code=0,
        recovery_disposition="stop_planned",
        core_outcome={"status": "STOPPED"}, cleanup_outcome="proven",
    )
    _close_control(
        tmp_path, series_id, attempt=1, retry_budget=10,
        disposition="stop_planned", status=0,
    )
    assert supervisor._recovery_state(
        root=tmp_path, activation_binding=_BINDING
    )["state"] == "new"


def test_m1_runtime_history_rejects_forged_retry_disposition(tmp_path):
    supervisor._initialize_recovery(root=tmp_path, activation_binding=_BINDING)
    _start_attempt(tmp_path, "f" * 32, "a" * 32)
    with pytest.raises(ValueError, match="runtime event"):
        supervisor._write_runtime_event(
            _event_record(
                stage="steady",
                error_class="local_readiness_failed",
                local_ready=False,
                public_ready=True,
                recovery_disposition="retry",
            ),
            root=tmp_path,
        )


def test_m1_recover_resumes_the_same_series_at_the_proven_attempt(monkeypatch, tmp_path):
    calls = []
    series_id = "e" * 32
    outcomes = iter(
        (
            {"status": 1, "recovery_disposition": "retry"},
            {"status": 1, "recovery_disposition": "stop_non_retryable"},
        )
    )
    monkeypatch.setattr(
        supervisor,
        "_recovery_state",
        lambda **_ignored: {
            "state": "resume",
            "reason": None,
            "series_id": series_id,
            "next_attempt": 2,
            "last_digest": "sha256:" + "1" * 64,
        },
    )
    monkeypatch.setattr(supervisor, "RECOVERY_RETRY_BUDGET", 3)
    monkeypatch.setattr(supervisor, "RECOVERY_RETRY_INTERVAL_SECONDS", 0.001)
    def controlled(callback, **callbacks):
        callbacks["on_ready"]()
        status = callback(_Event())
        callbacks["on_closing"](status)
        callbacks["on_closed"](status)
        return status

    monkeypatch.setattr(supervisor, "_with_stop_control", controlled)
    monkeypatch.setattr(
        supervisor, "_write_runtime_event",
        lambda *_args, **_kwargs: "sha256:" + "2" * 64,
    )

    def attempt(_values, *, stop_event, series_id, attempt, retry_budget,
                root, activation_binding):
        calls.append((stop_event, series_id, attempt, retry_budget))
        return next(outcomes)

    monkeypatch.setattr(supervisor, "_run_attempt", attempt)
    assert supervisor._recover(
        supervisor._arguments([]), root=tmp_path,
        activation_binding=_BINDING,
    ) == 1
    assert [(call[1], call[2], call[3]) for call in calls] == [
        (series_id, 2, 3),
        (series_id, 3, 3),
    ]


def test_m1_terminal_event_keeps_cleanup_failure_distinct(monkeypatch):
    events = []

    class Stop:
        def wait(self, _timeout):
            return False

        def close(self):
            pass

    class Api:
        def create_job(self):
            return 7

        def terminate(self, _job):
            pass

        def close(self, _job):
            pass

    child = SimpleNamespace(poll=lambda: None, stdout=io.BytesIO(b'{"status":"STOPPED"}\n'))
    monkeypatch.setattr(supervisor.Path, "exists", lambda _: True)
    monkeypatch.setattr(supervisor, "StopEvent", Stop)
    monkeypatch.setattr(supervisor, "_job_api", Api)
    monkeypatch.setattr(supervisor, "_operator_event", lambda *_, **__: None)
    monkeypatch.setattr(
        supervisor, "_write_runtime_event",
        lambda value, **_ignored: events.append(value),
    )
    monkeypatch.setattr(supervisor, "spawn_owned", lambda *args, **kwargs: child)
    monkeypatch.setattr(
        supervisor,
        "supervise",
        lambda *args, report, **kwargs: report(
            {
                "stage": "steady",
                "error_class": "public_readiness_failed",
                "core_exit_code": None,
                "relay_exit_code": None,
                "local_ready": True,
                "public_ready": False,
                "readiness_failures": 3,
            }
        )
        or 1,
    )
    monkeypatch.setattr(supervisor, "stop_process", lambda *args, **kwargs: False)
    monkeypatch.setattr(supervisor, "wait_job_empty", lambda *_: True)
    monkeypatch.setattr(supervisor, "close_owned", lambda *_: None)
    assert supervisor._main(supervisor._arguments([])) == 1
    assert events[0]["event"] == "starting"
    assert events[-1]["event"] == "terminal"
    assert events[-1]["error_class"] == "public_readiness_failed"
    assert events[-1]["cleanup_outcome"] == "failed"
    assert events[-1]["core_outcome"] == {"status": "STOPPED"}


def _run_scheduler_probe(path: Path, run_id: str, *, succeed_on: int) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            sys.executable,
            str(Path(scheduler_probe.__file__).resolve()),
            "--receipt",
            str(path),
            "--run-id",
            run_id,
            "--restart-budget",
            "2",
            "--succeed-on",
            str(succeed_on),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_m1_scheduler_fixture_transient_failure_recovers_without_raw_output(tmp_path):
    receipt = tmp_path / "transient.jsonl"
    run_id = "1" * 32
    first = _run_scheduler_probe(receipt, run_id, succeed_on=2)
    second = _run_scheduler_probe(receipt, run_id, succeed_on=2)
    assert (first.returncode, second.returncode) == (scheduler_probe.EXIT_RETRYABLE, 0)
    assert first.stdout == first.stderr == second.stdout == second.stderr == b""
    rows = [json.loads(line) for line in receipt.read_text(encoding="ascii").splitlines()]
    assert [row["attempt"] for row in rows] == [1, 2]
    assert [row["outcome"] for row in rows] == ["retryable_failure", "recovered"]


def test_m1_scheduler_fixture_permanent_failure_stops_at_budget(tmp_path):
    receipt = tmp_path / "permanent.jsonl"
    run_id = "2" * 32
    results = [_run_scheduler_probe(receipt, run_id, succeed_on=0) for _ in range(4)]
    assert [result.returncode for result in results] == [23, 23, 23, 125]
    assert all(result.stdout == result.stderr == b"" for result in results)
    rows = [json.loads(line) for line in receipt.read_text(encoding="ascii").splitlines()]
    assert [row["attempt"] for row in rows] == [1, 2, 3]
    assert [row["outcome"] for row in rows] == [
        "retryable_failure",
        "retryable_failure",
        "budget_exhausted",
    ]


def test_m1_scheduler_fixture_controller_uses_product_bounded_recovery(tmp_path):
    receipt = tmp_path / "controller.jsonl"
    result = subprocess.run(
        [
            sys.executable,
            str(Path(scheduler_probe.__file__).resolve()),
            "--receipt",
            str(receipt),
            "--run-id",
            "3" * 32,
            "--restart-budget",
            "2",
            "--succeed-on",
            "2",
            "--controller",
            "--controller-sha256",
            scheduler_probe._controller_sha256(),
            "--retry-interval-seconds",
            "0.001",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == result.stderr == b""
    rows = [json.loads(line) for line in receipt.read_text(encoding="ascii").splitlines()]
    assert [row["attempt"] for row in rows] == [1, 2]
    assert [row["outcome"] for row in rows] == ["retryable_failure", "recovered"]


def test_m1_scheduler_fixture_operator_is_scoped_and_never_touches_production_task():
    source = (
        Path(__file__).parent / "gate_m1_s1" / "Invoke-SchedulerRetryFixture.ps1"
    ).read_text(encoding="utf-8")
    assert "NobusSpace-M1S1-Fixture-Transient-" in source
    assert "NobusSpace-M1S1-Fixture-Permanent-" in source
    assert "$restartBudget = 2" in source
    assert "-RestartCount $restartBudget" not in source
    assert "'--controller'" in source
    assert "'--retry-interval-seconds', '60'" in source
    assert "Unregister-ScheduledTask -TaskName $name" in source
    assert (
        "Register-ScheduledTask -TaskName $definition.name -TaskPath '\\' "
        "-InputObject $task | Out-Null"
    ) in source
    assert "Register-ScheduledTask -TaskName 'NobusSpaceBot'" not in source
    assert "Get-WinEvent" not in source and "wevtutil" not in source.lower()


def test_m1_installer_does_not_claim_normal_exit_retries_from_scheduler_settings():
    installer = (
        Path(__file__).parents[1] / "ops" / "windows" / "Install-NobusSpaceBot.ps1"
    ).read_text(encoding="utf-8")
    assert "-RestartCount 10" not in installer
    assert "run_nobus_space_live.py" in installer
    assert supervisor.RECOVERY_RETRY_BUDGET == 10
    assert supervisor.RECOVERY_RETRY_INTERVAL_SECONDS == 60


def test_m1_runtime_baseline_collector_is_read_only_and_aggregate_only():
    source = (
        Path(__file__).parent / "gate_m1_s1" / "collect_runtime_baseline.py"
    ).read_text(encoding="utf-8")
    assert "_read_connection" in source and "database_state_digest" in source
    assert "SELECT consumer_id,offset,lease_id,lease_expires_at,revision" in source
    assert "consumer_binding" in source
    for forbidden in ("INSERT ", "UPDATE ", "DELETE ", "projection_json", "receipt_json\"]"):
        assert forbidden not in source


def test_m1_dependency_audit_is_inventory_only_without_explicit_network_flag(monkeypatch):
    monkeypatch.setattr(
        dependency_audit,
        "query_osv",
        lambda *_: pytest.fail("inventory-only mode attempted network access"),
    )
    assert dependency_audit.main(["--requirements", str(Path(__file__).parents[1] / "requirements.txt")]) == 0


def test_m1_dependency_audit_has_one_fixed_metadata_endpoint():
    source = Path(dependency_audit.__file__).read_text(encoding="utf-8")
    assert dependency_audit.OSV_ENDPOINT == "https://api.osv.dev/v1/querybatch"
    assert source.count("https://") == 1
    assert "index-url" not in source and "direct_url" not in source
    assert "HTTPRedirectHandler" in source and "ProxyHandler({})" in source
    assert "MAX_RESPONSE_BYTES" in source
