"""Regressions found by the independent M1-S1 review of the first freeze."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import re
import subprocess
import threading
from types import SimpleNamespace

import pytest

from scripts import run_nobus_space_live as supervisor
from tests.gate_m1_s1 import audit_dependencies_osv as dependency_audit


_BINDING = "sha256:" + "b" * 64
_PRODUCTION_RUNTIME_EVENT_LOG_BYTES = supervisor.RUNTIME_EVENT_LOG_BYTES


class _Process:
    def __init__(self, code: int | None = None) -> None:
        self.code = code

    def poll(self) -> int | None:
        return self.code


class _RaceStop:
    def __init__(self, core: _Process) -> None:
        self.core = core
        self.stopped = False

    def is_set(self) -> bool:
        return self.stopped

    def wait(self, _seconds: float) -> bool:
        self.core.code = 23
        self.stopped = True
        return True


def test_m1_core_failure_code_is_an_exact_allowlist_not_a_safe_shape():
    secret_shaped = b'{"status":"FAIL","code":"token_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}\n'
    assert supervisor._parse_core_outcome(secret_shaped) == (
        None,
        "core_outcome_invalid",
    )


@pytest.mark.parametrize(
    "terminal",
    [
        {
            "stage": "steady",
            "error_class": "relay_exit",
            "local_ready": None,
            "public_ready": None,
        },
        {
            "stage": "steady",
            "error_class": "public_readiness_failed",
            "local_ready": True,
            "public_ready": False,
        },
        {
            "stage": "startup",
            "error_class": "startup_timeout",
            "local_ready": True,
            "public_ready": False,
        },
    ],
)
def test_m1_transient_supervisor_failure_requires_proven_stopped_core(terminal):
    assert supervisor._recovery_disposition(
        status=1,
        terminal=terminal,
        core_outcome=None,
        core_outcome_error="core_outcome_invalid",
        cleanup_ok=True,
        attempt=1,
        retry_budget=10,
    ) == "stop_evidence_failed"
    assert supervisor._recovery_disposition(
        status=1,
        terminal=terminal,
        core_outcome={"status": "FAIL", "code": "telegram_checkpoint_failed"},
        core_outcome_error=None,
        cleanup_ok=True,
        attempt=1,
        retry_budget=10,
    ) == "stop_non_retryable"


def test_m1_child_exit_wins_a_simultaneous_planned_stop():
    core = _Process()
    reports: list[dict[str, object]] = []
    assert supervisor.supervise(
        None,
        None,
        _Process(),
        core,
        _RaceStop(core),
        probe=lambda: (True, True),
        report=reports.append,
    ) == 1
    assert reports[-1]["error_class"] == "core_exit"
    assert reports[-1]["core_exit_code"] == 23


def test_m1_readiness_failure_wins_a_later_stop_during_child_settle():
    class LateStop:
        stopped = False

        def is_set(self):
            return self.stopped

        def wait(self, _seconds):
            return self.stopped

    stop = LateStop()
    reports = []
    replies = iter([(True, True), (False, False), (False, False), (False, False)])
    status = supervisor.supervise(
        None,
        None,
        _Process(),
        _Process(),
        stop,
        probe=lambda: next(replies),
        report=reports.append,
        settle=lambda _seconds: setattr(stop, "stopped", True),
    )
    assert status == 1
    assert reports[-1]["error_class"] == "local_public_readiness_failed"
    assert reports[-1]["readiness_failures"] == 3


def test_m1_relay_exit_during_pre_core_stop_settle_is_not_planned(
    monkeypatch, tmp_path
):
    events = []

    class Api:
        @staticmethod
        def create_job():
            return 1

        @staticmethod
        def terminate(_job):
            return None

        @staticmethod
        def close(_job):
            return None

    class Stop:
        @staticmethod
        def wait(_seconds):
            return True

        @staticmethod
        def is_set():
            return True

    relay = _Process(23)
    monkeypatch.setattr(supervisor, "_job_api", Api)
    monkeypatch.setattr(supervisor, "spawn_owned", lambda *_args, **_kwargs: relay)
    monkeypatch.setattr(supervisor, "stop_process", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(supervisor, "wait_job_empty", lambda *_args: True)
    monkeypatch.setattr(supervisor, "close_owned", lambda *_args: None)
    monkeypatch.setattr(supervisor, "_operator_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        supervisor,
        "_write_runtime_event",
        lambda value, **_kwargs: events.append(value) or "sha256:" + "1" * 64,
    )
    result = supervisor._run_attempt(
        SimpleNamespace(),
        stop_event=Stop(),
        series_id="a" * 32,
        attempt=1,
        retry_budget=10,
        root=tmp_path,
        activation_binding=_BINDING,
        relay_command=["synthetic-relay"],
        core_command_override=["synthetic-core"],
        required_paths=(tmp_path,),
        relay_settle_seconds=0.01,
    )
    assert result == {"status": 1, "recovery_disposition": "stop_non_retryable"}
    assert events[-1]["error_class"] == "relay_exit"
    assert events[-1]["relay_exit_code"] == 23
    assert events[-1]["stage"] == "relay_start"


def test_m1_relay_exit_during_graceful_core_stop_overrides_planned_stop(
    monkeypatch, tmp_path
):
    events = []

    class Api:
        @staticmethod
        def create_job():
            return 1

        @staticmethod
        def terminate(_job):
            return None

        @staticmethod
        def close(_job):
            return None

    class Stop:
        @staticmethod
        def wait(_seconds):
            return False

        @staticmethod
        def is_set():
            return False

    relay = _Process()
    core = _Process()
    core.stdout = io.BytesIO(b'{"status":"STOPPED"}\n')

    def stop_core(process, *, graceful=False):
        assert process is core and graceful is True
        core.code = 0
        core.returncode = 0
        relay.code = 255
        return True

    children = iter((relay, core))
    monkeypatch.setattr(supervisor, "_job_api", Api)
    monkeypatch.setattr(
        supervisor, "spawn_owned", lambda *_args, **_kwargs: next(children)
    )
    monkeypatch.setattr(
        supervisor,
        "supervise",
        lambda *_args, report, **_kwargs: report({
            "stage": "steady", "error_class": "planned_stop",
            "core_exit_code": None, "relay_exit_code": None,
            "local_ready": None, "public_ready": None,
            "readiness_failures": 0,
        }) or 0,
    )
    monkeypatch.setattr(supervisor, "stop_process", stop_core)
    monkeypatch.setattr(supervisor, "wait_job_empty", lambda *_args: True)
    monkeypatch.setattr(supervisor, "close_owned", lambda *_args: None)
    monkeypatch.setattr(supervisor, "_operator_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        supervisor,
        "_write_runtime_event",
        lambda value, **_kwargs: events.append(value) or "sha256:" + "1" * 64,
    )

    result = supervisor._run_attempt(
        SimpleNamespace(), stop_event=Stop(), series_id="a" * 32,
        attempt=1, retry_budget=10, root=tmp_path,
        activation_binding=_BINDING,
        relay_command=["synthetic-relay"],
        core_command_override=["synthetic-core"], required_paths=(tmp_path,),
        relay_settle_seconds=0.01,
    )

    assert result == {"status": 1, "recovery_disposition": "retry"}
    assert events[-1]["error_class"] == "relay_exit"
    assert events[-1]["relay_exit_code"] == 255


def test_m1_core_exit_at_cleanup_boundary_overrides_readiness_retry(
    monkeypatch, tmp_path
):
    events = []
    core = _Process()
    core.stdout = io.BytesIO(b'{"status":"STOPPED"}\n')

    class Relay(_Process):
        def __init__(self):
            super().__init__()
            self.polls = 0

        def poll(self):
            self.polls += 1
            if self.polls == 2:
                core.code = 0
            return self.code

    class Api:
        @staticmethod
        def create_job():
            return 1

        @staticmethod
        def terminate(_job):
            return None

        @staticmethod
        def close(_job):
            return None

    class Stop:
        @staticmethod
        def wait(_seconds):
            return False

        @staticmethod
        def is_set():
            return False

    children = iter((Relay(), core))
    monkeypatch.setattr(supervisor, "_job_api", Api)
    monkeypatch.setattr(
        supervisor, "spawn_owned", lambda *_args, **_kwargs: next(children)
    )
    monkeypatch.setattr(
        supervisor,
        "supervise",
        lambda *_args, report, **_kwargs: report({
            "stage": "steady", "error_class": "public_readiness_failed",
            "core_exit_code": None, "relay_exit_code": None,
            "local_ready": True, "public_ready": False,
            "readiness_failures": 3,
        }) or 1,
    )
    monkeypatch.setattr(supervisor, "wait_job_empty", lambda *_args: True)
    monkeypatch.setattr(supervisor, "close_owned", lambda *_args: None)
    monkeypatch.setattr(supervisor, "_operator_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        supervisor,
        "_write_runtime_event",
        lambda value, **_kwargs: events.append(value) or "sha256:" + "1" * 64,
    )

    result = supervisor._run_attempt(
        SimpleNamespace(), stop_event=Stop(), series_id="b" * 32,
        attempt=1, retry_budget=10, root=tmp_path,
        activation_binding=_BINDING,
        relay_command=["synthetic-relay"],
        core_command_override=["synthetic-core"], required_paths=(tmp_path,),
        relay_settle_seconds=0.01,
    )

    assert result == {
        "status": 1, "recovery_disposition": "stop_non_retryable"
    }
    assert events[-1]["error_class"] == "core_exit"
    assert events[-1]["core_exit_code"] == 0


def test_m1_local_and_public_readiness_have_independent_bounded_slots():
    assert supervisor._LOCAL_READINESS_PROBE is not supervisor._PUBLIC_READINESS_PROBE
    blocker = threading.Event()
    public_done = threading.Event()

    def stalled() -> bool:
        blocker.wait(1)
        public_done.set()
        return False

    thread = threading.Thread(
        target=lambda: supervisor._PUBLIC_READINESS_PROBE.run(stalled, seconds=0.01),
        daemon=True,
    )
    thread.start()
    thread.join(timeout=0.1)
    assert supervisor._LOCAL_READINESS_PROBE.run(lambda: True, seconds=0.1) is True
    blocker.set()
    public_done.wait(1)


def test_m1_missing_recovery_history_is_unknown_until_explicit_bootstrap(tmp_path):
    missing = supervisor._recovery_state(root=tmp_path, activation_binding=_BINDING)
    assert missing["state"] == "blocked"
    assert missing["reason"] == "runtime_history_missing"
    result = supervisor._initialize_recovery(root=tmp_path, activation_binding=_BINDING)
    assert result["status"] == "INITIALIZED"
    initialized = supervisor._recovery_state(root=tmp_path, activation_binding=_BINDING)
    assert initialized["state"] == "new"

    for name in (
        supervisor.RUNTIME_EVENT_LOG_NAME,
        supervisor.RUNTIME_EVENT_LOG_NAME + ".previous",
    ):
        (tmp_path / name).unlink(missing_ok=True)
    lost = supervisor._recovery_state(root=tmp_path, activation_binding=_BINDING)
    assert lost["state"] == "blocked"
    assert lost["reason"] == "runtime_history_missing"


@pytest.mark.parametrize("missing_segment", ["current", "previous"])
def test_m1_deleting_one_rotated_history_segment_cannot_reopen_runtime(
    tmp_path, monkeypatch, missing_segment
):
    monkeypatch.setattr(supervisor, "RUNTIME_EVENT_LOG_BYTES", 6500)
    supervisor._initialize_recovery(root=tmp_path, activation_binding=_BINDING)

    class Stop:
        def wait(self, _seconds):
            return False

        def set(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(supervisor, "StopEvent", Stop)

    def attempt(_values, *, stop_event, series_id, attempt, retry_budget,
                root, activation_binding):
        return _write_fake_attempt(
            root, activation_binding, series_id, attempt, retry_budget, "complete"
        )

    for _ in range(4):
        assert supervisor._recover(
            SimpleNamespace(), root=tmp_path, activation_binding=_BINDING,
            run_attempt=attempt,
        ) == 0

    current = tmp_path / supervisor.RUNTIME_EVENT_LOG_NAME
    previous = tmp_path / (supervisor.RUNTIME_EVENT_LOG_NAME + ".previous")
    assert current.is_file() and previous.is_file()
    (current if missing_segment == "current" else previous).unlink()
    state = supervisor._recovery_state(
        root=tmp_path, activation_binding=_BINDING
    )
    assert state["state"] == "blocked"
    assert state["reason"] == "runtime_history_invalid"


def _raw_record(**changes) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": "nobus-runtime-event-2",
        "series_id": "f" * 32,
        "run_id": "a" * 32,
        "event": "terminal",
        "stage": "steady",
        "error_class": "public_readiness_failed",
        "supervisor_exit_code": 1,
        "core_exit_code": None,
        "relay_exit_code": None,
        "local_ready": True,
        "public_ready": False,
        "readiness_failures": 3,
        "attempt": 10,
        "retry_budget": 10,
        "recovery_disposition": "retry",
        "core_outcome": None,
        "core_outcome_error": None,
        "cleanup_outcome": "proven",
        "at": "2026-09-14T00:00:00Z",
    }
    value.update(changes)
    return value


@pytest.mark.parametrize(
    "record",
    [
        _raw_record(),
        _raw_record(
            event="recovery_reset",
            stage="recovery_control",
            error_class=None,
            supervisor_exit_code=0,
            local_ready=None,
            public_ready=None,
            readiness_failures=0,
            attempt=1,
            recovery_disposition="reset",
        ),
    ],
)
def test_m1_standalone_terminal_or_reset_cannot_open_a_recovery_series(tmp_path, record):
    path = tmp_path / supervisor.RUNTIME_EVENT_LOG_NAME
    path.write_text(json.dumps(record, separators=(",", ":")) + "\n", encoding="ascii")
    state = supervisor._recovery_state(root=tmp_path, activation_binding=_BINDING)
    assert state["state"] == "blocked"
    assert state["reason"] == "runtime_history_invalid"


@pytest.mark.parametrize("event", ["terminal", "recovery_reset"])
def test_m1_linked_but_out_of_sequence_event_cannot_bypass_bootstrap(tmp_path, event):
    initialized = supervisor._initialize_recovery(
        root=tmp_path, activation_binding=_BINDING
    )
    if event == "terminal":
        record = supervisor._runtime_record(
            "f" * 32, "a" * 32, "terminal", activation_binding=_BINDING,
            attempt=1, retry_budget=10, recovery_disposition="retry",
            stage="steady", error_class="public_readiness_failed",
            supervisor_exit_code=1, local_ready=True, public_ready=False,
            readiness_failures=3, core_outcome={"status": "STOPPED"},
            cleanup_outcome="proven",
        )
    else:
        record = supervisor._runtime_record(
            "f" * 32, "a" * 32, "recovery_reset",
            activation_binding=_BINDING, attempt=1, retry_budget=10,
            recovery_disposition="reset", stage="recovery_control",
            supervisor_exit_code=0, cleanup_outcome="proven",
            reset_of_digest=initialized["event_digest"],
        )
    record["previous_event_digest"] = initialized["event_digest"]
    line = {
        "at": "2026-09-14T00:00:01Z",
        **record,
    }
    with (tmp_path / supervisor.RUNTIME_EVENT_LOG_NAME).open("ab") as stream:
        stream.write(json.dumps(
            line, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        ).encode("ascii") + b"\n")
    state = supervisor._recovery_state(
        root=tmp_path, activation_binding=_BINDING
    )
    assert state["state"] == "blocked"
    assert state["reason"] == "runtime_history_invalid"


def test_m1_runtime_writer_rejects_a_reparse_ancestor(tmp_path, monkeypatch):
    parent = tmp_path / "junction"
    root = parent / "logs"
    root.mkdir(parents=True)
    original = Path.is_junction
    monkeypatch.setattr(
        Path,
        "is_junction",
        lambda value: value == parent or original(value),
    )
    with pytest.raises(RuntimeError, match="runtime event write failed"):
        supervisor._initialize_recovery(root=root, activation_binding=_BINDING)
    with pytest.raises(RuntimeError, match="operator event write failed"):
        supervisor._operator_event("starting", root=root)


def test_m1_oversize_operator_history_blocks_recovery(tmp_path, monkeypatch):
    monkeypatch.setattr(supervisor, "OPERATOR_EVENT_LOG_BYTES", 64)
    supervisor._initialize_recovery(root=tmp_path, activation_binding=_BINDING)
    operator_log = tmp_path / "runner-supervisor.log"
    operator_log.write_bytes(b"x" * 65)
    state = supervisor._recovery_state(
        root=tmp_path, activation_binding=_BINDING
    )
    assert state["state"] == "blocked"
    assert state["reason"] == "runtime_history_invalid"


def test_m1_stop_control_setup_failure_has_a_typed_exit_and_reason(monkeypatch):
    class BrokenStop:
        def __init__(self):
            raise RuntimeError("synthetic control failure")

    reasons: list[str] = []
    monkeypatch.setattr(supervisor, "StopEvent", BrokenStop)
    status = supervisor._with_stop_control(
        lambda _stop: pytest.fail("callback must not run"),
        on_failure=reasons.append,
    )
    assert status == supervisor.EXIT_STOP_CONTROL_CREATE_FAILED
    assert reasons == ["stop_control_create_failed"]


def test_m1_recover_persists_stop_control_create_failure(tmp_path, monkeypatch):
    supervisor._initialize_recovery(root=tmp_path, activation_binding=_BINDING)

    class BrokenStop:
        def __init__(self):
            raise RuntimeError("synthetic control failure")

    monkeypatch.setattr(supervisor, "StopEvent", BrokenStop)
    status = supervisor._recover(
        SimpleNamespace(), root=tmp_path, activation_binding=_BINDING,
        run_attempt=lambda *_args, **_kwargs: pytest.fail("attempt must not run"),
    )
    assert status == supervisor.EXIT_STOP_CONTROL_CREATE_FAILED
    state = supervisor._recovery_state(
        root=tmp_path, activation_binding=_BINDING
    )
    assert state["state"] == "blocked"
    assert state["reason"] == "stop_control_create_failed"


def _write_fake_attempt(root, binding, series_id, attempt, retry_budget, disposition):
    run_id = f"{attempt:032x}"
    supervisor._write_runtime_event(supervisor._runtime_record(
        series_id, run_id, "starting", activation_binding=binding,
        attempt=attempt, retry_budget=retry_budget,
        recovery_disposition="pending", stage="setup",
    ), root=root)
    if disposition == "retry":
        values = {
            "stage": "steady", "error_class": "public_readiness_failed",
            "supervisor_exit_code": 1, "local_ready": True,
            "public_ready": False, "readiness_failures": 3,
            "core_outcome": {"status": "STOPPED"},
        }
    else:
        values = {
            "stage": "complete", "error_class": None,
            "supervisor_exit_code": 0,
        }
    supervisor._write_runtime_event(supervisor._runtime_record(
        series_id, run_id, "terminal", activation_binding=binding,
        attempt=attempt, retry_budget=retry_budget,
        recovery_disposition=disposition, cleanup_outcome="proven", **values,
    ), root=root)
    return {"status": 1 if disposition == "retry" else 0,
            "recovery_disposition": disposition}


class _CleanStop:
    def wait(self, _seconds):
        return False

    def set(self):
        pass

    def close(self):
        pass


def _complete_recovery(values, *, stop_event, series_id, attempt, retry_budget,
                       root, activation_binding):
    return _write_fake_attempt(
        root, activation_binding, series_id, attempt, retry_budget, "complete"
    )


def _force_next_history_rotation(monkeypatch, root):
    current = root / supervisor.RUNTIME_EVENT_LOG_NAME
    previous = root / (supervisor.RUNTIME_EVENT_LOG_NAME + ".previous")
    failure = supervisor._runtime_record(
        "a" * 32, "b" * 32, "control_failure",
        activation_binding=_BINDING, attempt=1, retry_budget=10,
        recovery_disposition="stop_evidence_failed", stage="recovery_control",
        error_class="runtime_event_write_failed",
        supervisor_exit_code=supervisor.EXIT_RUNTIME_EVIDENCE_FAILED,
        cleanup_outcome="proven",
    )
    failure["previous_event_digest"] = "sha256:" + "c" * 64
    failure_line_size = len(supervisor._encoded_record({
        "at": "2026-09-14T00:00:00Z", **failure,
    }))
    monkeypatch.setattr(
        supervisor, "RUNTIME_EVENT_LOG_BYTES",
        max(
            current.stat().st_size,
            previous.stat().st_size if previous.exists() else 0,
            failure_line_size,
        ) + 1,
    )


def _assert_latched_rotation_can_be_acknowledged(
    root, *, reason="runtime_event_write_failed"
):
    state = supervisor._recovery_state(
        root=root, activation_binding=_BINDING
    )
    assert state["state"] == "blocked"
    assert state["reason"] == reason
    assert state["last_digest"].startswith("sha256:")
    reset = supervisor._acknowledge_recovery_stop(
        state["last_digest"], root=root, activation_binding=_BINDING
    )
    assert reset["status"] == "RESET"
    assert supervisor._recovery_state(
        root=root, activation_binding=_BINDING
    )["state"] == "new"


def test_m1_first_rotation_interruption_is_latch_reconcilable(
    monkeypatch, tmp_path
):
    supervisor._initialize_recovery(root=tmp_path, activation_binding=_BINDING)
    monkeypatch.setattr(supervisor, "StopEvent", _CleanStop)
    production_limit = supervisor.RUNTIME_EVENT_LOG_BYTES
    _force_next_history_rotation(monkeypatch, tmp_path)
    original_replace = supervisor.os.replace
    interrupted = False

    def interrupt_after_first_rotation(source, destination):
        nonlocal interrupted
        result = original_replace(source, destination)
        if (not interrupted and Path(destination).name ==
                supervisor.RUNTIME_EVENT_LOG_NAME + ".previous"):
            interrupted = True
            raise OSError("synthetic first rotation interruption")
        return result

    monkeypatch.setattr(supervisor.os, "replace", interrupt_after_first_rotation)
    with pytest.raises(supervisor._CliFailure, match="runtime_event_write_failed"):
        supervisor._recover(
            SimpleNamespace(), root=tmp_path, activation_binding=_BINDING,
            run_attempt=_complete_recovery,
        )
    monkeypatch.setattr(supervisor.os, "replace", original_replace)
    assert interrupted is True
    monkeypatch.setattr(supervisor, "RUNTIME_EVENT_LOG_BYTES", production_limit)
    _assert_latched_rotation_can_be_acknowledged(tmp_path)


def _seed_split_history(monkeypatch, root):
    monkeypatch.setattr(supervisor, "RUNTIME_EVENT_LOG_BYTES", 6500)
    monkeypatch.setattr(supervisor, "StopEvent", _CleanStop)
    supervisor._initialize_recovery(root=root, activation_binding=_BINDING)
    for _ in range(2):
        assert supervisor._recover(
            SimpleNamespace(), root=root, activation_binding=_BINDING,
            run_attempt=_complete_recovery,
        ) == 0
    assert (root / (supervisor.RUNTIME_EVENT_LOG_NAME + ".previous")).is_file()


def test_m1_compaction_interruption_is_latch_reconcilable(
    monkeypatch, tmp_path
):
    _seed_split_history(monkeypatch, tmp_path)
    production_limit = _PRODUCTION_RUNTIME_EVENT_LOG_BYTES
    _force_next_history_rotation(monkeypatch, tmp_path)
    original_unlink = Path.unlink
    interrupted = False

    def interrupt_before_new_current(path, *args, **kwargs):
        nonlocal interrupted
        if (not interrupted and path.name == supervisor.RUNTIME_EVENT_LOG_NAME):
            interrupted = True
            raise OSError("synthetic compaction interruption")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", interrupt_before_new_current)
    with pytest.raises(supervisor._CliFailure, match="runtime_event_write_failed"):
        supervisor._recover(
            SimpleNamespace(), root=tmp_path, activation_binding=_BINDING,
            run_attempt=_complete_recovery,
        )
    monkeypatch.setattr(Path, "unlink", original_unlink)
    assert interrupted is True
    monkeypatch.setattr(supervisor, "RUNTIME_EVENT_LOG_BYTES", production_limit)
    _assert_latched_rotation_can_be_acknowledged(tmp_path)


def test_m1_compacted_control_starting_survives_latch_clear_failure(
    monkeypatch, tmp_path
):
    _seed_split_history(monkeypatch, tmp_path)
    production_limit = _PRODUCTION_RUNTIME_EVENT_LOG_BYTES
    _force_next_history_rotation(monkeypatch, tmp_path)
    original_clear = supervisor._clear_recovery_latch
    monkeypatch.setattr(
        supervisor, "_clear_recovery_latch",
        lambda **_kwargs: (_ for _ in ()).throw(
            OSError("synthetic latch clear interruption")
        ),
    )
    with pytest.raises(supervisor._CliFailure, match="runtime_event_write_failed"):
        supervisor._recover(
            SimpleNamespace(), root=tmp_path, activation_binding=_BINDING,
            run_attempt=_complete_recovery,
    )
    monkeypatch.setattr(supervisor, "_clear_recovery_latch", original_clear)
    monkeypatch.setattr(supervisor, "RUNTIME_EVENT_LOG_BYTES", production_limit)
    _assert_latched_rotation_can_be_acknowledged(
        tmp_path, reason="previous_control_setup_unknown"
    )


def test_m1_recovery_wait_event_write_failure_is_durable_stop(tmp_path, monkeypatch):
    supervisor._initialize_recovery(root=tmp_path, activation_binding=_BINDING)

    class StopDuringWait:
        def wait(self, _seconds):
            return True

        def set(self):
            pass

        def close(self):
            pass

    original_write = supervisor._write_runtime_event

    def fail_wait_stop(value, **options):
        if value["event"] == "recovery_wait_stopped":
            raise RuntimeError("synthetic evidence failure")
        return original_write(value, **options)

    monkeypatch.setattr(supervisor, "StopEvent", StopDuringWait)
    monkeypatch.setattr(supervisor, "_write_runtime_event", fail_wait_stop)

    def attempt(_values, *, stop_event, series_id, attempt, retry_budget,
                root, activation_binding):
        return _write_fake_attempt(
            root, activation_binding, series_id, attempt, retry_budget, "retry"
        )

    status = supervisor._recover(
        SimpleNamespace(), root=tmp_path, activation_binding=_BINDING,
        run_attempt=attempt,
    )
    assert status == supervisor.EXIT_RUNTIME_EVIDENCE_FAILED
    state = supervisor._recovery_state(
        root=tmp_path, activation_binding=_BINDING
    )
    assert state["state"] == "blocked"
    assert state["reason"] == "recovery_wait_event_write_failed"


def test_m1_stop_control_close_failure_is_durable_stop(tmp_path, monkeypatch):
    supervisor._initialize_recovery(root=tmp_path, activation_binding=_BINDING)

    class BrokenClose:
        def wait(self, _seconds):
            return False

        def set(self):
            pass

        def close(self):
            raise RuntimeError("synthetic close failure")

    monkeypatch.setattr(supervisor, "StopEvent", BrokenClose)

    def attempt(_values, *, stop_event, series_id, attempt, retry_budget,
                root, activation_binding):
        return _write_fake_attempt(
            root, activation_binding, series_id, attempt, retry_budget, "complete"
        )

    status = supervisor._recover(
        SimpleNamespace(), root=tmp_path, activation_binding=_BINDING,
        run_attempt=attempt,
    )
    assert status == supervisor.EXIT_STOP_CONTROL_CLOSE_FAILED
    state = supervisor._recovery_state(
        root=tmp_path, activation_binding=_BINDING
    )
    assert state["state"] == "blocked"
    assert state["reason"] == "stop_control_close_failed"


def test_m1_signal_restore_failure_after_close_is_durable_stop(tmp_path, monkeypatch):
    supervisor._initialize_recovery(root=tmp_path, activation_binding=_BINDING)

    class Stop:
        def wait(self, _seconds):
            return False

        def set(self):
            pass

        def close(self):
            pass

    signal_calls = 0

    def signal_control(_named_signal, _handler):
        nonlocal signal_calls
        signal_calls += 1
        if signal_calls == 3:
            raise RuntimeError("synthetic signal restore failure")
        return object()

    monkeypatch.setattr(supervisor, "StopEvent", Stop)
    monkeypatch.setattr(supervisor.signal, "signal", signal_control)

    def attempt(_values, *, stop_event, series_id, attempt, retry_budget,
                root, activation_binding):
        return _write_fake_attempt(
            root, activation_binding, series_id, attempt, retry_budget, "complete"
        )

    status = supervisor._recover(
        SimpleNamespace(), root=tmp_path, activation_binding=_BINDING,
        run_attempt=attempt,
    )
    assert status == supervisor.EXIT_RUNTIME_EVIDENCE_FAILED
    state = supervisor._recovery_state(
        root=tmp_path, activation_binding=_BINDING
    )
    assert state["state"] == "blocked"
    assert state["reason"] == "stop_control_callback_failed"


def test_m1_health_launcher_never_persists_raw_child_streams():
    installer = (
        Path(__file__).parents[1] / "ops" / "windows" / "Install-NobusSpaceBot.ps1"
    ).read_text(encoding="utf-8")
    assert "*>>" not in installer
    assert "health.log" not in installer


def test_m1_scheduler_fixture_binds_and_runs_the_product_controller():
    fixture = (
        Path(__file__).parent
        / "gate_m1_s1"
        / "Invoke-SchedulerRetryFixture.ps1"
    ).read_text(encoding="utf-8")
    probe = (
        Path(__file__).parent / "fixtures" / "m1_scheduler_exit_probe.py"
    ).read_text(encoding="utf-8")
    assert "controller_sha256" in fixture
    assert "controller_sha256" in probe
    assert "_run_owned_recovery" in probe
    assert "_run_attempt" in probe


def test_m1_scheduler_fixture_rejects_an_unsupported_operator_before_registration():
    fixture = (
        Path(__file__).parent
        / "gate_m1_s1"
        / "Invoke-SchedulerRetryFixture.ps1"
    ).read_text(encoding="utf-8")
    runtime_guard = fixture.index("fixture_runtime_unsupported")
    registration = fixture.index("Register-ScheduledTask")
    assert runtime_guard < registration
    assert "$PSVersionTable.PSEdition -cne 'Core'" in fixture
    assert "[version]'7.4.0'" in fixture
    assert "operator_executable_sha256" in fixture
    assert "operator_version" in fixture


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell fixture")
def test_m1_scheduler_fixture_writes_a_typed_ps5_preflight_stop(tmp_path):
    root = tmp_path / "fixture-root"
    pythonw = root / ".venv" / "Scripts" / "pythonw.exe"
    pythonw.parent.mkdir(parents=True)
    pythonw.write_bytes(b"synthetic pythonw\n")
    fixture = (
        Path(__file__).parent
        / "gate_m1_s1"
        / "Invoke-SchedulerRetryFixture.ps1"
    ).resolve()
    run_id = "2" * 32
    result = subprocess.run(
        [
            "powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(fixture),
            "-RunId", run_id, "-RepositoryRoot", str(root),
            "-Pythonw", str(pythonw),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert result.returncode == 1
    assert result.stderr == b""
    output = json.loads(result.stdout.decode("utf-8-sig"))
    assert output["status"] == "FAIL"
    assert output["error_class"] == "fixture_runtime_unsupported"
    assert output["operator"]["edition"] == "Desktop"
    assert output["operator"]["executable"] == "powershell.exe"
    assert re.fullmatch(
        r"[0-9a-f]{64}", output["operator"]["operator_executable_sha256"]
    )
    assert output["transient"]["rows"] == []
    assert output["exhausted"]["rows"] == []
    assert output["permanent"]["rows"] == []
    assert output["cleanup"] == {
        "outcome": "proven", "deadline_seconds": 30, "task_states": {},
        "process_count": 0, "mutexes_absent": True,
        "stop_events_absent": True, "definitions_absent": True,
    }
    result_path = (
        root / ".runtime" / "m1-s1" / "scheduler-fixture" / run_id
        / "result.json"
    )
    assert json.loads(result_path.read_text(encoding="utf-8")) == output


def test_m1_osv_response_rejects_duplicate_json_keys():
    with pytest.raises(ValueError, match="duplicate JSON key"):
        dependency_audit._decode_osv_response(
            b'{"results":[],"results":[]}'
        )


def test_m1_dependency_inventory_rejects_duplicate_direct_pins(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("Py-Test==1\npy_test==1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        dependency_audit.inventory(requirements)
