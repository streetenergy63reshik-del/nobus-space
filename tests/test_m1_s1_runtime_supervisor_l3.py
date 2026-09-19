"""Blocking L2/L3 regressions for the M1-S1 supervisor candidate."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_nobus_space_live as supervisor
from src.contracts.models import canonical_json_digest


_BINDING = "sha256:" + "c" * 64


class _Event:
    def is_set(self) -> bool:
        return False

    def wait(self, _seconds: float) -> bool:
        return False


class _Process:
    def __init__(self, code: int | None = None) -> None:
        self.code = code

    def poll(self) -> int | None:
        return self.code


def _terminal(**changes) -> dict[str, object]:
    value = supervisor._runtime_record(
        "f" * 32,
        "a" * 32,
        "terminal",
        activation_binding=_BINDING,
        attempt=1,
        retry_budget=10,
        recovery_disposition="stop_non_retryable",
        stage="steady",
        error_class="core_exit",
        supervisor_exit_code=1,
        core_exit_code=7,
        core_outcome={"status": "FAIL", "code": "telegram_checkpoint_failed"},
        cleanup_outcome="proven",
    )
    value.update(changes)
    return value


def test_m1_missing_input_is_bracketed_by_starting_and_exact_terminal(monkeypatch, tmp_path):
    events: list[dict[str, object]] = []
    monkeypatch.setattr(supervisor, "_operator_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        supervisor,
        "_write_runtime_event",
        lambda value, **_kwargs: events.append(value) or "sha256:" + "1" * 64,
    )

    result = supervisor._run_attempt(
        SimpleNamespace(),
        stop_event=_Event(),
        series_id="f" * 32,
        attempt=1,
        retry_budget=10,
        root=tmp_path,
        activation_binding=_BINDING,
        required_paths=(tmp_path / "missing",),
    )

    assert result == {"status": 1, "recovery_disposition": "stop_non_retryable"}
    assert [event["event"] for event in events] == ["starting", "terminal"]
    assert events[-1]["stage"] == "input_validation"
    assert events[-1]["error_class"] == "runtime_input_missing"


def test_m1_child_exit_after_blocking_readiness_probe_has_priority():
    core = _Process()
    reports: list[dict[str, object]] = []
    calls = 0

    def probe():
        nonlocal calls
        calls += 1
        if calls == 1:
            return True, True
        if calls == 4:
            core.code = 7
        return False, False

    assert supervisor.supervise(
        None,
        None,
        _Process(),
        core,
        _Event(),
        probe=probe,
        report=reports.append,
    ) == 1
    assert reports[-1]["error_class"] == "core_exit"
    assert reports[-1]["core_exit_code"] == 7
    assert reports[-1]["local_ready"] is None
    assert reports[-1]["public_ready"] is None


def test_m1_current_user_authentication_rejects_rebound_history(tmp_path):
    supervisor._initialize_recovery(root=tmp_path, activation_binding=_BINDING)
    path = tmp_path / supervisor.RUNTIME_EVENT_LOG_NAME
    row = json.loads(path.read_text(encoding="ascii"))
    rebound = "sha256:" + "d" * 64
    row["activation_binding"] = rebound
    path.write_text(
        json.dumps(row, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="ascii",
    )

    state = supervisor._recovery_state(root=tmp_path, activation_binding=rebound)
    assert state["state"] == "blocked"
    assert state["reason"] == "runtime_history_invalid"


def test_m1_checkpoint_is_never_accepted_from_current_segment(tmp_path):
    supervisor._initialize_recovery(root=tmp_path, activation_binding=_BINDING)
    supervisor._write_runtime_event(
        supervisor._runtime_record(
            "f" * 32,
            "a" * 32,
            "control_starting",
            activation_binding=_BINDING,
            attempt=1,
            retry_budget=10,
            recovery_disposition="pending",
            stage="recovery_control",
        ),
        root=tmp_path,
    )
    rows, digests = supervisor._runtime_history(
        root=tmp_path, activation_binding=_BINDING
    )
    supervisor._write_compacted_previous(
        tmp_path, rows[0], rows[-1], digests[-1]
    )
    previous = tmp_path / (supervisor.RUNTIME_EVENT_LOG_NAME + ".previous")
    current = tmp_path / supervisor.RUNTIME_EVENT_LOG_NAME
    compacted = previous.read_bytes()
    previous.unlink()
    current.write_bytes(compacted)

    with pytest.raises(ValueError, match="checkpoint placement"):
        supervisor._runtime_history(root=tmp_path, activation_binding=_BINDING)


def test_m1_terminal_matrix_rejects_child_exit_with_readiness_fields():
    with pytest.raises(ValueError, match="state is inconsistent"):
        supervisor._validate_runtime_event(
            _terminal(
                local_ready=False,
                public_ready=False,
                readiness_failures=3,
            )
        )


def test_m1_core_failure_outcome_cannot_contradict_success_exit():
    outcome = {"status": "FAIL", "code": "telegram_unavailable"}
    contradictory = _terminal(core_exit_code=0, core_outcome=outcome)
    with pytest.raises(ValueError, match="contradicts exit code"):
        supervisor._validate_runtime_event(contradictory)
    assert supervisor._recovery_disposition(
        status=1,
        terminal=contradictory,
        core_outcome=outcome,
        core_outcome_error=None,
        cleanup_ok=True,
        attempt=1,
        retry_budget=10,
    ) == "stop_evidence_failed"


def test_m1_control_failure_requires_exact_error_exit_mapping():
    record = supervisor._runtime_record(
        "f" * 32,
        "a" * 32,
        "control_failure",
        activation_binding=_BINDING,
        attempt=1,
        retry_budget=10,
        recovery_disposition="stop_evidence_failed",
        stage="recovery_control",
        error_class="stop_control_create_failed",
        supervisor_exit_code=1,
        cleanup_outcome="proven",
    )
    with pytest.raises(ValueError, match="state is inconsistent"):
        supervisor._validate_runtime_event(record)


def test_m1_missing_runtime_root_has_safe_typed_receipt(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(supervisor, "LOG_ROOT", tmp_path)
    monkeypatch.setattr(
        supervisor.sys,
        "argv",
        ["run_nobus_space_live.py", "--inspect-recovery"],
    )

    assert supervisor.main() == supervisor.EXIT_RUNTIME_COMPOSITION_INVALID
    output = json.loads(capsys.readouterr().out)
    assert output == {
        "command": "inspect_recovery",
        "error_class": "runtime_composition_invalid",
        "exit_code": supervisor.EXIT_RUNTIME_COMPOSITION_INVALID,
        "schema": "nobus-supervisor-cli-failure-1",
        "status": "STOP",
    }
    fallback = tmp_path / supervisor.FALLBACK_EVENT_LOG_NAME
    assert fallback.is_file()
    persisted = json.loads(fallback.read_text(encoding="ascii"))
    assert set(persisted) == set(output) | {"at", "run_id", "authentication"}
    assert not any(key in persisted for key in ("argv", "environment", "path", "payload"))


def test_m1_hardlinked_control_file_blocks_history(tmp_path):
    supervisor._initialize_recovery(root=tmp_path, activation_binding=_BINDING)
    outside = tmp_path.parent / (tmp_path.name + "-operator-source")
    outside.write_text("2026-09-14T00:00:00Z starting\n", encoding="ascii")
    try:
        os.link(outside, tmp_path / "runner-supervisor.log")
        state = supervisor._recovery_state(
            root=tmp_path, activation_binding=_BINDING
        )
        assert state["state"] == "blocked"
        assert state["reason"] == "runtime_history_invalid"
    finally:
        outside.unlink(missing_ok=True)


def test_m1_starting_append_failure_is_an_exact_durable_control_failure(
    monkeypatch, tmp_path
):
    supervisor._initialize_recovery(root=tmp_path, activation_binding=_BINDING)
    original = supervisor._write_runtime_event

    def fail_starting(value, **options):
        if value["event"] == "starting":
            raise RuntimeError("synthetic append failure")
        return original(value, **options)

    class Stop:
        def wait(self, _seconds):
            return False

        def set(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(supervisor, "_write_runtime_event", fail_starting)
    monkeypatch.setattr(supervisor, "StopEvent", Stop)
    status = supervisor._recover(
        SimpleNamespace(),
        root=tmp_path,
        activation_binding=_BINDING,
        run_attempt=supervisor._run_attempt,
    )
    assert status == supervisor.EXIT_RUNTIME_EVIDENCE_FAILED
    state = supervisor._recovery_state(root=tmp_path, activation_binding=_BINDING)
    assert state["state"] == "blocked"
    assert state["reason"] == "runtime_event_write_failed"


def test_m1_pre_control_append_failure_latches_until_exact_reset(
    monkeypatch, tmp_path
):
    initialized = supervisor._initialize_recovery(
        root=tmp_path, activation_binding=_BINDING
    )
    original = supervisor._write_runtime_event
    monkeypatch.setattr(
        supervisor,
        "_write_runtime_event",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("synthetic total history append failure")
        ),
    )

    with pytest.raises(supervisor._CliFailure) as caught:
        supervisor._recover(
            SimpleNamespace(), root=tmp_path, activation_binding=_BINDING,
            run_attempt=lambda *_args, **_kwargs: pytest.fail(
                "no attempt may start without control evidence"
            ),
        )
    assert caught.value.error_class == "runtime_event_write_failed"
    assert initialized["event_digest"] != ""

    monkeypatch.setattr(supervisor, "_write_runtime_event", original)
    blocked = supervisor._recovery_state(
        root=tmp_path, activation_binding=_BINDING
    )
    assert blocked["state"] == "blocked"
    assert blocked["reason"] == "runtime_event_write_failed"
    assert (tmp_path / supervisor.RECOVERY_LATCH_NAME).is_file()

    reset = supervisor._acknowledge_recovery_stop(
        blocked["last_digest"], root=tmp_path, activation_binding=_BINDING
    )
    assert reset["status"] == "RESET"
    assert reset["evidence_latch_digest"] == blocked["last_digest"]
    assert not (tmp_path / supervisor.RECOVERY_LATCH_NAME).exists()
    assert supervisor._recovery_state(
        root=tmp_path, activation_binding=_BINDING
    )["state"] == "new"


def test_m1_activation_binds_every_runtime_input_and_scheduler_signature(
    monkeypatch, tmp_path
):
    worktree = tmp_path / "live"
    runtime = tmp_path / "state"
    voice = tmp_path / "voice"
    backup = tmp_path / "backups"
    health = worktree / ".runtime" / "check-nobus-space-bot.ps1"
    runtime.mkdir()
    voice.mkdir()
    backup.mkdir()
    health.parent.mkdir(parents=True)
    health.write_text("exit 0\n", encoding="utf-8")
    for relative in (
        "docs/11-Контекст-продукта.md",
        "telegram-bindings.local.json",
        "codex-runtime.local.json",
        "src/transport/miniapp_static/app.js",
        "src/transport/miniapp_static/index.html",
        "src/transport/miniapp_static/styles.css",
        "ops/windows/Invoke-NobusSpaceTask.ps1",
        "requirements.txt",
    ):
        path = worktree / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative + "\n", encoding="utf-8")
    for name in ("config.json", "model.bin", "README.md", "tokenizer.json", "vocabulary.txt"):
        (voice / name).write_bytes((name + "\n").encode("ascii"))

    monkeypatch.setattr(supervisor, "WORKTREE", worktree)
    monkeypatch.setattr(supervisor, "_scheduler_activation", lambda *_args, **_kwargs: {
        "tasks": {
            role: {"name": name, "signature": "sha256:" + key * 64}
            for role, name, key in (
                ("main", "NobusSpaceBot", "1"),
                ("health", "NobusSpaceBot-Health", "2"),
                ("backup", "NobusSpaceBot-Backup", "3"),
            )
        },
        "backup_config": {
            "path": ".runtime/backup-cycle.json", "bytes": 1,
            "sha256": "0" * 64,
        },
    })
    values = SimpleNamespace(
        voice_model_directory=voice,
        backup_root=backup,
        backup_ownership="sha256:" + "e" * 64,
        health_launcher=health,
        scheduler_task_name="NobusSpaceBot",
        semantic_admission=True,
    )
    first = supervisor._activation_manifest(values, runtime)
    assert first["schema"] == "nobus-supervisor-activation-3"
    assert first["semantic_admission"] is True
    assert set(first["runtime_inputs"]) == {
        "docs/11-Контекст-продукта.md",
        "telegram-bindings.local.json",
        "codex-runtime.local.json",
        "src/transport/miniapp_static/app.js",
        "src/transport/miniapp_static/index.html",
        "src/transport/miniapp_static/styles.css",
        "ops/windows/Invoke-NobusSpaceTask.ps1",
        "requirements.txt",
    }
    assert first["voice"]["inventory"]["count"] == 5
    assert set(first["scheduler_signatures"]) == {"main", "health", "backup"}
    assert first["installed_runtime"]["distributions"]["count"] > 0

    before = canonical_json_digest(first)
    (worktree / "docs/11-Контекст-продукта.md").write_text(
        "changed runtime input\n", encoding="utf-8"
    )
    after = canonical_json_digest(supervisor._activation_manifest(values, runtime))
    assert before != after


def test_m1_fallback_parser_refuses_tampered_existing_segment(monkeypatch, tmp_path):
    monkeypatch.setattr(supervisor, "LOG_ROOT", tmp_path)
    supervisor._write_fallback_failure(
        "run", "recovery_history_blocked", supervisor.EXIT_RECOVERY_HISTORY_BLOCKED
    )
    path = tmp_path / supervisor.FALLBACK_EVENT_LOG_NAME
    row = json.loads(path.read_text(encoding="ascii"))
    row["error_class"] = "supervisor_startup_failed"
    path.write_text(
        json.dumps(row, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="ascii",
    )
    with pytest.raises((OSError, ValueError)):
        supervisor._write_fallback_failure(
            "run", "recovery_history_blocked",
            supervisor.EXIT_RECOVERY_HISTORY_BLOCKED,
        )


def test_m1_installer_can_keep_generated_health_launcher_in_live_checkout():
    installer = (
        Path(__file__).parents[1] / "ops" / "windows" / "Install-NobusSpaceBot.ps1"
    ).read_text(encoding="utf-8")
    assert "[string]$HealthLauncherRoot" in installer
    assert "--health-launcher" in installer
    assert "$healthLauncherOwner" in installer


def test_m1_empty_recovery_ack_is_rejected_instead_of_starting_runtime(
    monkeypatch, tmp_path, capsys
):
    from src.application import windows_singleton

    monkeypatch.setattr(supervisor, "LOG_ROOT", tmp_path)
    monkeypatch.setattr(
        supervisor.sys,
        "argv",
        ["run_nobus_space_live.py", "--acknowledge-recovery-stop="],
    )
    monkeypatch.setattr(
        supervisor,
        "_runtime_recovery_context",
        lambda _values: (tmp_path / "control", _BINDING),
    )
    monkeypatch.setattr(windows_singleton, "WindowsNamedMutex", lambda *_args: nullcontext())
    monkeypatch.setattr(
        supervisor,
        "_run_owned_recovery",
        lambda *_args, **_kwargs: pytest.fail("empty reset must not start runtime"),
    )

    assert supervisor.main() == supervisor.EXIT_RECOVERY_RESET_REJECTED
    output = json.loads(capsys.readouterr().out)
    assert output["command"] == "acknowledge_recovery_stop"
    assert output["error_class"] == "recovery_reset_rejected"


def test_m1_stop_close_failure_has_one_exact_safe_result(monkeypatch, tmp_path, capsys):
    class BrokenClose:
        def __init__(self, *, request=False):
            assert request is True

        def set(self):
            pass

        def close(self):
            raise RuntimeError("synthetic close failure")

    monkeypatch.setattr(supervisor, "LOG_ROOT", tmp_path)
    monkeypatch.setattr(supervisor, "StopEvent", BrokenClose)
    monkeypatch.setattr(supervisor.sys, "argv", ["run_nobus_space_live.py", "--stop"])

    assert supervisor.main() == supervisor.EXIT_STOP_CONTROL_CLOSE_FAILED
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {
        "command": "stop",
        "error_class": "stop_control_close_failed",
        "exit_code": supervisor.EXIT_STOP_CONTROL_CLOSE_FAILED,
        "schema": "nobus-supervisor-cli-failure-1",
        "status": "STOP",
    }


def test_m1_unknown_starting_can_be_reset_only_by_exact_latest_digest(tmp_path):
    supervisor._initialize_recovery(root=tmp_path, activation_binding=_BINDING)
    series_id = "d" * 32
    run_id = "e" * 32
    for event, stage, exit_code in (
        ("control_starting", "recovery_control", None),
        ("control_ready", "recovery_control", 0),
        ("starting", "setup", None),
    ):
        starting_digest = supervisor._write_runtime_event(
            supervisor._runtime_record(
                series_id,
                run_id,
                event,
                activation_binding=_BINDING,
                attempt=1,
                retry_budget=10,
                recovery_disposition="pending",
                stage=stage,
                supervisor_exit_code=exit_code,
            ),
            root=tmp_path,
        )
    assert supervisor._recovery_state(
        root=tmp_path, activation_binding=_BINDING
    )["reason"] == "previous_attempt_unknown"
    result = supervisor._acknowledge_recovery_stop(
        starting_digest, root=tmp_path, activation_binding=_BINDING
    )
    assert result["status"] == "RESET"
    assert supervisor._recovery_state(
        root=tmp_path, activation_binding=_BINDING
    )["state"] == "new"


def test_m1_activation_rebind_preserves_old_chain_and_requires_exact_head(tmp_path):
    binding_b = "sha256:" + "b" * 64
    initialized = supervisor._initialize_recovery(
        root=tmp_path, activation_binding=_BINDING
    )
    with pytest.raises(RuntimeError, match="precondition"):
        supervisor._rebind_recovery(
            "sha256:" + "0" * 64,
            root=tmp_path,
            activation_binding=binding_b,
        )
    result = supervisor._rebind_recovery(
        initialized["event_digest"],
        root=tmp_path,
        activation_binding=binding_b,
    )
    assert result["status"] == "REBOUND"
    rows, _digests = supervisor._runtime_history(
        root=tmp_path, activation_binding=binding_b
    )
    assert [row["activation_binding"] for row in rows] == [_BINDING, binding_b]
    assert supervisor._recovery_state(
        root=tmp_path, activation_binding=binding_b
    )["state"] == "new"


@pytest.mark.parametrize(
    ("disposition", "status"),
    [("retry", 1), ("stop_non_retryable", 0), ("complete", 1)],
)
def test_m1_control_close_matrix_rejects_impossible_outcomes(disposition, status):
    value = supervisor._runtime_record(
        "f" * 32,
        "a" * 32,
        "control_closed",
        activation_binding=_BINDING,
        attempt=1,
        retry_budget=10,
        recovery_disposition=disposition,
        stage="recovery_control",
        supervisor_exit_code=status,
        cleanup_outcome="proven",
    )
    with pytest.raises(ValueError, match="state is inconsistent"):
        supervisor._validate_runtime_event(value)


def test_m1_fallback_requires_exact_command_error_exit_matrix(monkeypatch, tmp_path):
    monkeypatch.setattr(supervisor, "LOG_ROOT", tmp_path)
    with pytest.raises(ValueError):
        supervisor._write_fallback_failure(
            "run", "runtime_composition_invalid", supervisor.EXIT_RECOVERY_HISTORY_BLOCKED
        )
    assert not (tmp_path / supervisor.FALLBACK_EVENT_LOG_NAME).exists()


def test_m1_fallback_write_failure_returns_evidence_exit(monkeypatch, capsys):
    monkeypatch.setattr(
        supervisor,
        "_write_fallback_failure",
        lambda *_args: (_ for _ in ()).throw(OSError("synthetic fallback failure")),
    )
    assert supervisor._emit_cli_failure(
        "run", "runtime_composition_invalid", supervisor.EXIT_RUNTIME_COMPOSITION_INVALID
    ) == supervisor.EXIT_RUNTIME_EVIDENCE_FAILED
    output = json.loads(capsys.readouterr().out)
    assert output["error_class"] == "fallback_event_write_failed"
    assert output["exit_code"] == supervisor.EXIT_RUNTIME_EVIDENCE_FAILED


def test_m1_invalid_arguments_do_not_inherit_a_partial_command(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(supervisor, "LOG_ROOT", tmp_path)
    monkeypatch.setattr(
        supervisor.sys,
        "argv",
        ["run_nobus_space_live.py", "--stop", "--unsupported"],
    )
    assert supervisor.main() == supervisor.EXIT_RUNTIME_COMPOSITION_INVALID
    output = json.loads(capsys.readouterr().out)
    assert output == {
        "command": "arguments",
        "error_class": "runtime_arguments_invalid",
        "exit_code": supervisor.EXIT_RUNTIME_COMPOSITION_INVALID,
        "schema": "nobus-supervisor-cli-failure-1",
        "status": "STOP",
    }


def test_m1_unexpected_startup_has_distinct_exit(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(supervisor, "LOG_ROOT", tmp_path)
    monkeypatch.setattr(supervisor.sys, "argv", ["run_nobus_space_live.py"])
    monkeypatch.setattr(
        supervisor,
        "_runtime_recovery_context",
        lambda _values: (tmp_path / "control", _BINDING),
    )
    monkeypatch.setattr(
        supervisor,
        "_run_owned_recovery",
        lambda _values: (_ for _ in ()).throw(RuntimeError("synthetic startup failure")),
    )
    assert supervisor.main() == supervisor.EXIT_SUPERVISOR_STARTUP_FAILED
    output = json.loads(capsys.readouterr().out)
    assert output["error_class"] == "supervisor_startup_failed"
    assert output["exit_code"] == supervisor.EXIT_SUPERVISOR_STARTUP_FAILED


def test_m1_control_ready_write_failure_keeps_primary_error(monkeypatch, tmp_path):
    supervisor._initialize_recovery(root=tmp_path, activation_binding=_BINDING)
    original = supervisor._write_runtime_event

    def fail_ready(value, **options):
        if value["event"] == "control_ready":
            raise RuntimeError("synthetic control event failure")
        return original(value, **options)

    class Stop:
        def wait(self, _seconds):
            return False

        def set(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(supervisor, "_write_runtime_event", fail_ready)
    monkeypatch.setattr(supervisor, "StopEvent", Stop)
    assert supervisor._recover(
        SimpleNamespace(), root=tmp_path, activation_binding=_BINDING,
        run_attempt=lambda *_args, **_kwargs: pytest.fail("attempt must not start"),
    ) == supervisor.EXIT_RUNTIME_EVIDENCE_FAILED
    state = supervisor._recovery_state(root=tmp_path, activation_binding=_BINDING)
    assert state["state"] == "blocked"
    assert state["reason"] == "runtime_event_write_failed"


@pytest.mark.parametrize("failed_event", ["control_closing", "control_closed"])
def test_m1_control_close_event_write_failure_keeps_primary_error(
    monkeypatch, tmp_path, failed_event
):
    supervisor._initialize_recovery(root=tmp_path, activation_binding=_BINDING)
    original = supervisor._write_runtime_event

    def fail_close_event(value, **options):
        if value["event"] == failed_event:
            raise RuntimeError("synthetic control event failure")
        return original(value, **options)

    class Stop:
        def wait(self, _seconds):
            return False

        def set(self):
            pass

        def close(self):
            pass

    def attempt(_values, *, stop_event, series_id, attempt, retry_budget,
                root, activation_binding):
        run_id = "2" * 32
        supervisor._write_runtime_event(supervisor._runtime_record(
            series_id, run_id, "starting", activation_binding=activation_binding,
            attempt=attempt, retry_budget=retry_budget,
            recovery_disposition="pending", stage="setup",
        ), root=root)
        supervisor._write_runtime_event(supervisor._runtime_record(
            series_id, run_id, "terminal", activation_binding=activation_binding,
            attempt=attempt, retry_budget=retry_budget,
            recovery_disposition="complete", stage="complete",
            supervisor_exit_code=0, cleanup_outcome="proven",
        ), root=root)
        return {"status": 0, "recovery_disposition": "complete"}

    monkeypatch.setattr(supervisor, "_write_runtime_event", fail_close_event)
    monkeypatch.setattr(supervisor, "StopEvent", Stop)
    assert supervisor._recover(
        SimpleNamespace(), root=tmp_path, activation_binding=_BINDING,
        run_attempt=attempt,
    ) == supervisor.EXIT_RUNTIME_EVIDENCE_FAILED
    state = supervisor._recovery_state(root=tmp_path, activation_binding=_BINDING)
    assert state["state"] == "blocked"
    assert state["reason"] == "runtime_event_write_failed"


def test_m1_next_attempt_start_write_failure_becomes_durable_stop(monkeypatch, tmp_path):
    supervisor._initialize_recovery(root=tmp_path, activation_binding=_BINDING)

    class Stop:
        def wait(self, _seconds):
            return False

        def set(self):
            pass

        def close(self):
            pass

    def attempt(_values, *, stop_event, series_id, attempt, retry_budget,
                root, activation_binding):
        if attempt == 2:
            raise supervisor._RecoveryControlFailure("runtime_event_write_failed")
        run_id = "1" * 32
        supervisor._write_runtime_event(supervisor._runtime_record(
            series_id, run_id, "starting", activation_binding=activation_binding,
            attempt=attempt, retry_budget=retry_budget,
            recovery_disposition="pending", stage="setup",
        ), root=root)
        supervisor._write_runtime_event(supervisor._runtime_record(
            series_id, run_id, "terminal", activation_binding=activation_binding,
            attempt=attempt, retry_budget=retry_budget,
            recovery_disposition="retry", stage="steady",
            error_class="public_readiness_failed", supervisor_exit_code=1,
            local_ready=True, public_ready=False, readiness_failures=3,
            core_outcome={"status": "STOPPED"}, cleanup_outcome="proven",
        ), root=root)
        return {"status": 1, "recovery_disposition": "retry"}

    monkeypatch.setattr(supervisor, "StopEvent", Stop)
    monkeypatch.setattr(supervisor, "RECOVERY_RETRY_INTERVAL_SECONDS", 0.001)
    assert supervisor._recover(
        SimpleNamespace(), root=tmp_path, activation_binding=_BINDING,
        run_attempt=attempt,
    ) == supervisor.EXIT_RUNTIME_EVIDENCE_FAILED
    state = supervisor._recovery_state(root=tmp_path, activation_binding=_BINDING)
    assert state["state"] == "blocked"
    assert state["reason"] == "runtime_event_write_failed"


def _scheduler_snapshot(name, *, role, enabled=True, restart_count=0):
    trigger = {
        "type": "MSFT_TaskLogonTrigger", "enabled": True, "start": None,
        "end": None, "user": "S-1-5-21-1-2-3-1001", "days_interval": None,
        "interval": None, "duration": None, "stop_at_end": False,
        "execution_limit": "", "id": "", "delay": "", "random_delay": "",
    }
    execution_limit = "PT0S"
    if role == "health":
        trigger.update(type="MSFT_TaskTimeTrigger", start=(
            datetime.now().astimezone() - timedelta(minutes=1)
        ).isoformat(),
                       user=None, interval="PT1M", duration="P3650D", stop_at_end=True)
        execution_limit = "PT2M"
    elif role == "backup":
        trigger.update(type="MSFT_TaskDailyTrigger", start=(
            datetime.now().astimezone().replace(
                hour=3, minute=30, second=0, microsecond=0
            )
        ).isoformat(),
                       user=None, days_interval=1)
        execution_limit = "PT20M"
    action = {"execute": "expected.exe", "arguments": "exact", "working_directory": None}
    return {
        "name": name, "state": "Ready", "enabled": enabled, "last_result": 0,
        "current_principal": "S-1-5-21-1-2-3-1001",
        "signature": {
            "principal": "S-1-5-21-1-2-3-1001", "logon_type": 3, "run_level": 0,
            "actions": [action], "triggers": [trigger], "start_when_available": True,
            "disallow_battery": False, "stop_on_battery": False, "wake_to_run": False,
            "restart_count": restart_count, "restart_interval": None,
            "execution_limit": execution_limit, "multiple_instances": 2,
            "compatibility": 3, "allow_demand_start": True,
            "allow_hard_terminate": True, "delete_expired_task_after": "",
            "hidden": False, "priority": 7, "run_only_if_idle": False,
            "idle_duration": "PT10M", "idle_wait_timeout": "PT1H",
            "stop_on_idle_end": True, "restart_on_idle": False,
            "run_only_if_network": False, "network_id": "", "network_name": "",
            "disallow_remote_app_session": False,
            "unified_scheduling_engine": True, "volatile": False,
            "maintenance_settings_present": False,
        },
    }, action


@pytest.mark.parametrize(
    ("change", "role"),
    [({"enabled": False}, "main"), ({"restart_count": 10}, "main")],
)
def test_m1_scheduler_binding_rejects_disabled_or_retrying_task(change, role):
    snapshot, action = _scheduler_snapshot("NobusSpaceBot", role=role, **change)
    with pytest.raises(ValueError, match="scheduler task profile"):
        supervisor._validate_scheduler_task_snapshot(
            snapshot, role=role, task_name="NobusSpaceBot", expected_action=action
        )


def test_m1_scheduler_binding_includes_exact_task_name():
    snapshot, action = _scheduler_snapshot("NobusSpaceBot", role="main")
    binding = supervisor._validate_scheduler_task_snapshot(
        snapshot, role="main", task_name="NobusSpaceBot", expected_action=action
    )
    assert binding["name"] == "NobusSpaceBot"
    with pytest.raises(ValueError, match="scheduler task profile"):
        supervisor._validate_scheduler_task_snapshot(
            dict(snapshot, name="NobusSpaceClone"), role="main",
            task_name="NobusSpaceBot", expected_action=action,
        )


def test_m1_disabled_health_requires_exact_backup_restart_authority():
    snapshot, action = _scheduler_snapshot(
        "NobusSpaceBot-Health", role="health", enabled=False
    )
    snapshot["state"] = "Disabled"
    with pytest.raises(ValueError, match="scheduler task profile"):
        supervisor._validate_scheduler_task_snapshot(
            snapshot, role="health", task_name="NobusSpaceBot-Health",
            expected_action=action,
        )
    binding = supervisor._validate_scheduler_task_snapshot(
        snapshot, role="health", task_name="NobusSpaceBot-Health",
        expected_action=action, allow_disabled_health=True,
    )
    assert binding["name"] == "NobusSpaceBot-Health"


def test_m1_scheduler_activation_accepts_disabled_health_only_in_bound_backup_window(
    monkeypatch, tmp_path
):
    names = {
        "main": "NobusSpaceBot",
        "health": "NobusSpaceBot-Health",
        "backup": "NobusSpaceBot-Backup",
    }
    snapshots = {}
    actions = {}
    for role, name in names.items():
        snapshot, action = _scheduler_snapshot(
            name, role=role, enabled=(role != "health")
        )
        if role == "health":
            snapshot["state"] = "Disabled"
        snapshots[name] = snapshot
        actions[role] = action
    config = tmp_path / "backup-cycle.json"
    digest = "sha256:" + "6" * 64
    monkeypatch.setattr(
        supervisor, "_scheduler_task_signature", lambda name: snapshots[name]
    )
    monkeypatch.setattr(
        supervisor, "_main_scheduler_action",
        lambda *_args, **_kwargs: actions["main"],
    )
    monkeypatch.setattr(
        supervisor, "_health_scheduler_action", lambda *_args: actions["health"]
    )
    monkeypatch.setattr(
        supervisor, "_backup_action_binding",
        lambda *_args: (actions["backup"], config, digest),
    )
    monkeypatch.setattr(
        supervisor,
        "_validate_backup_activation_config",
        lambda *_args, **_kwargs: {"path": "backup-cycle.json"},
    )
    monkeypatch.setattr(
        supervisor, "_backup_restart_authorized", lambda *_args: True
    )
    values = SimpleNamespace(
        scheduler_task_name="NobusSpaceBot",
        backup_root=tmp_path,
        backup_ownership="sha256:" + "5" * 64,
    )
    result = supervisor._scheduler_activation(
        values, tmp_path, application={}, pythonw=tmp_path / "pythonw.exe",
        health_launcher=tmp_path / "health.ps1",
    )
    assert set(result["tasks"]) == {"main", "health", "backup"}

    monkeypatch.setattr(
        supervisor, "_backup_restart_authorized", lambda *_args: False
    )
    with pytest.raises(ValueError, match="scheduler task profile"):
        supervisor._scheduler_activation(
            values, tmp_path, application={}, pythonw=tmp_path / "pythonw.exe",
            health_launcher=tmp_path / "health.ps1",
        )


def test_m1_all_disabled_staging_preserves_binding_but_cannot_launch(monkeypatch, tmp_path):
    snapshots = {}
    actions = {}
    for role, suffix in (("main", ""), ("health", "-Health"), ("backup", "-Backup")):
        name = "NobusSpaceBot" + suffix
        snapshots[name], actions[role] = _scheduler_snapshot(name, role=role)
    monkeypatch.setattr(supervisor, "_scheduler_task_signature", lambda name: snapshots[name])
    monkeypatch.setattr(supervisor, "_main_scheduler_action", lambda *a, **kw: actions["main"])
    monkeypatch.setattr(supervisor, "_health_scheduler_action", lambda *a: actions["health"])
    monkeypatch.setattr(supervisor, "_backup_action_binding", lambda *a: (
        actions["backup"], tmp_path / "backup.json", _BINDING,
    ))
    monkeypatch.setattr(supervisor, "_validate_backup_activation_config", lambda *a, **kw: {})
    monkeypatch.setattr(supervisor, "_backup_restart_authorized", lambda *a: False)
    values = SimpleNamespace(backup_root=tmp_path, backup_ownership=_BINDING)

    def activation(staging=False):
        return supervisor._scheduler_activation(
            values, tmp_path, application={}, pythonw=tmp_path / "pythonw.exe",
            health_launcher=tmp_path / "health.ps1", allow_disabled_staging=staging,
        )

    enabled = activation()
    assert activation(True) == enabled
    for snapshot in snapshots.values():
        snapshot.update(enabled=False, state="Disabled")
    assert activation(True) == enabled
    with pytest.raises(ValueError, match="scheduler task profile"):
        activation()
    snapshots["NobusSpaceBot"].update(enabled=True, state="Ready")
    with pytest.raises(ValueError, match="scheduler task profile"):
        activation(True)


@pytest.mark.parametrize("command", [
    {}, {"initialize_recovery": True}, {"rebind_recovery_from": _BINDING},
    {"inspect_recovery": True}, {"acknowledge_recovery_stop": _BINDING},
])
def test_m1_disabled_staging_is_only_requested_by_recovery_controls(monkeypatch, tmp_path, command):
    observed = []

    def manifest(values, runtime, *, allow_disabled_staging=False):
        observed.append(allow_disabled_staging)
        return {"synthetic": True}

    monkeypatch.setattr(supervisor, "_activation_manifest", manifest)
    supervisor._runtime_recovery_context(SimpleNamespace(runtime_root=tmp_path, **command))
    assert observed == [bool(command)]


def test_m1_scheduler_trigger_identity_and_time_are_owner_local_and_active():
    main, action = _scheduler_snapshot("NobusSpaceBot", role="main")
    main["signature"]["triggers"][0]["user"] = "S-1-5-21-9-9-9-1001"
    with pytest.raises(ValueError, match="scheduler task profile"):
        supervisor._validate_scheduler_task_snapshot(
            main, role="main", task_name="NobusSpaceBot", expected_action=action
        )

    reference = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    health, action = _scheduler_snapshot("NobusSpaceBot-Health", role="health")
    health["signature"]["triggers"][0]["start"] = "2099-09-14T00:00:00+00:00"
    with pytest.raises(ValueError, match="scheduler task profile"):
        supervisor._validate_scheduler_task_snapshot(
            health, role="health", task_name="NobusSpaceBot-Health",
            expected_action=action, now=reference,
        )

    local_offset = datetime.now().astimezone().utcoffset() or timedelta(0)
    wrong_offset = timezone(
        timedelta(hours=1) if local_offset == timedelta(0) else timedelta(0)
    )
    backup, action = _scheduler_snapshot("NobusSpaceBot-Backup", role="backup")
    backup["signature"]["triggers"][0]["start"] = datetime.now(
        wrong_offset
    ).replace(hour=3, minute=30, second=0, microsecond=0).isoformat()
    with pytest.raises(ValueError, match="scheduler task profile"):
        supervisor._validate_scheduler_task_snapshot(
            backup, role="backup", task_name="NobusSpaceBot-Backup",
            expected_action=action,
        )


def test_m1_backup_trigger_rejects_a_first_occurrence_after_the_next_local_0330():
    reference = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    local_reference = reference.astimezone()
    backup, action = _scheduler_snapshot("NobusSpaceBot-Backup", role="backup")
    backup["signature"]["triggers"][0]["start"] = (
        local_reference.replace(
            year=2099, hour=3, minute=30, second=0, microsecond=0
        ).isoformat()
    )

    with pytest.raises(ValueError, match="scheduler task profile"):
        supervisor._validate_scheduler_task_snapshot(
            backup, role="backup", task_name="NobusSpaceBot-Backup",
            expected_action=action, now=reference,
        )


def test_m1_backup_trigger_accepts_past_and_nearest_daily_boundaries():
    reference = datetime.now().astimezone().replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    nearest = (reference + timedelta(days=1)).replace(
        hour=3, minute=30, second=0, microsecond=0
    )
    for start in (nearest - timedelta(days=30), nearest):
        backup, action = _scheduler_snapshot(
            "NobusSpaceBot-Backup", role="backup"
        )
        backup["signature"]["triggers"][0]["start"] = start.isoformat()
        assert supervisor._validate_scheduler_task_snapshot(
            backup, role="backup", task_name="NobusSpaceBot-Backup",
            expected_action=action, now=reference,
        )["name"] == "NobusSpaceBot-Backup"


def test_m1_backup_restart_authority_is_authenticated_bound_and_fresh(tmp_path):
    from src.application.durable_telegram_state import DpapiJsonCodec

    config = tmp_path / "backup-cycle.json"
    digest = "sha256:" + "7" * 64
    journal = tmp_path / "backup-cycle-state.dpapi"

    def write(phase, *, at=None):
        value = {
            "schema": "c6-backup-cycle-state-1",
            "config_digest": digest,
            "phase": phase,
            "at": at or datetime.now().astimezone().isoformat(),
            "attempt_id": "8" * 32,
            "generation": "daily-20260914T033000-" + "9" * 32,
        }
        journal.write_bytes(DpapiJsonCodec().encode(value))

    write("restart_permitted")
    assert supervisor._backup_restart_authorized(config, digest) is True
    write("complete")
    assert supervisor._backup_restart_authorized(config, digest) is False
    write(
        "starting",
        at=(datetime.now().astimezone() - timedelta(minutes=11)).isoformat(),
    )
    assert supervisor._backup_restart_authorized(config, digest) is False


def test_m1_scheduler_binding_rejects_unsafe_identity_action_trigger_and_settings():
    snapshot, action = _scheduler_snapshot("NobusSpaceBot", role="main")
    changes = (
        lambda value: value["signature"].update(principal="S-1-5-21-9-9-9-1001"),
        lambda value: value["signature"].update(logon_type=2),
        lambda value: value["signature"].update(run_level=1),
        lambda value: value["signature"]["actions"][0].update(arguments="changed"),
        lambda value: value["signature"].update(start_when_available=False),
        lambda value: value["signature"].update(disallow_battery=True),
        lambda value: value["signature"].update(multiple_instances=0),
        lambda value: value["signature"].update(allow_demand_start=False),
        lambda value: value["signature"].update(run_only_if_idle=True),
        lambda value: value["signature"].update(run_only_if_network=True),
        lambda value: value["signature"]["triggers"][0].update(type="MSFT_TaskTimeTrigger"),
        lambda value: value["signature"]["triggers"][0].update(delay="PT5M"),
    )
    for change in changes:
        candidate = json.loads(json.dumps(snapshot))
        change(candidate)
        with pytest.raises(ValueError, match="scheduler task profile"):
            supervisor._validate_scheduler_task_snapshot(
                candidate, role="main", task_name="NobusSpaceBot",
                expected_action=action,
            )


def test_m1_backup_activation_config_is_exactly_bound(monkeypatch, tmp_path):
    from src.application.runtime_maintenance import file_evidence
    from src.contracts.models import canonical_json_digest

    runtime = tmp_path / "state"
    backup = tmp_path / "backups"
    runtime.mkdir()
    backup.mkdir()
    inputs = {}
    for relative in (
        "ops/windows/Invoke-NobusSpaceTask.ps1",
        "docs/11-Контекст-продукта.md",
        "codex-runtime.local.json",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative, encoding="utf-8")
        inputs[relative] = file_evidence(path)
    application = {
        "source_commit": "1" * 40,
        "code_digest": "sha256:" + "2" * 64,
        "schema_digest": "sha256:" + "3" * 64,
        "protection": "current-user-dpapi",
        "database_limit_bytes": 1,
    }
    snapshots = {
        "main": {"signature": {"role": "main", "exact": True}},
        "health": {"signature": {"role": "health", "exact": True}},
    }
    value = {
        "schema": "c6-backup-cycle-1",
        "application": application,
        "runtime": str(runtime),
        "backup_root": str(backup),
        "ownership": "sha256:" + "4" * 64,
        "tasks": {
            role: {
                "name": "NobusSpaceBot" + ("" if role == "main" else "-Health"),
                "signature": snapshots[role]["signature"],
            }
            for role in ("main", "health")
        },
        "inputs": inputs,
    }
    config = tmp_path / "backup-cycle.json"
    config.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )
    monkeypatch.setattr(supervisor, "WORKTREE", tmp_path)
    result = supervisor._validate_backup_activation_config(
        config, canonical_json_digest(value), application=application,
        runtime=runtime, backup=backup, ownership=value["ownership"],
        task_name="NobusSpaceBot", snapshots=snapshots,
    )
    assert result == {"path": "backup-cycle.json", **file_evidence(config)}

    value["tasks"]["main"]["signature"] = {"role": "main", "exact": False}
    config.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="backup activation configuration"):
        supervisor._validate_backup_activation_config(
            config, canonical_json_digest(value), application=application,
            runtime=runtime, backup=backup, ownership=value["ownership"],
            task_name="NobusSpaceBot", snapshots=snapshots,
        )


def test_m1_scheduler_inspect_binds_current_windows_principal():
    helper = (
        Path(__file__).parents[1] / "ops" / "windows" / "Invoke-NobusSpaceTask.ps1"
    ).read_text(encoding="utf-8")
    assert "WindowsIdentity]::GetCurrent().User.Value" in helper


def test_m1_fixture_uses_process_handshake_and_proves_cleanup():
    probe = (Path(__file__).parent / "fixtures" / "m1_scheduler_exit_probe.py").read_text(
        encoding="utf-8"
    )
    fixture = (
        Path(__file__).parent / "gate_m1_s1" / "Invoke-SchedulerRetryFixture.ps1"
    ).read_text(encoding="utf-8")
    assert "time.sleep(0.5)" not in probe
    assert "children_started=" in probe
    assert "--fixture-run-id" in probe
    assert "Stop-ScheduledTask" in fixture
    assert "Get-CimInstance Win32_Process" in fixture
    assert "OpenExisting" in fixture
    process_scan = fixture[
        fixture.index("function Get-FixtureProcessCount"):
        fixture.index("$fixtureObjectSuffixes")
    ]
    assert "--controller" not in process_scan
    assert "executable_sha256" in fixture and "executable_bytes" in fixture
    assert fixture.index("Stop-ScheduledTask") < fixture.index("Unregister-ScheduledTask")


def test_m1_backup_installer_replaces_only_an_explicit_stopped_disabled_task():
    installer = (
        Path(__file__).parents[1] / "ops" / "windows" /
        "Install-NobusSpaceBackup.ps1"
    ).read_text(encoding="utf-8-sig")
    assert "[switch]$ReplaceExisting" in installer
    assert "Exact backup task replacement requires a stopped disabled task" in installer
    assert installer.index("Settings.Enabled") < installer.index("Register-ScheduledTask")
    assert "-InputObject $task -Force" in installer


def test_m1_installers_support_exact_disabled_candidate_staging():
    root = Path(__file__).parents[1]
    bot = (root / "ops" / "windows" / "Install-NobusSpaceBot.ps1").read_text(
        encoding="utf-8"
    )
    backup = (
        root / "ops" / "windows" / "Install-NobusSpaceBackup.ps1"
    ).read_text(encoding="utf-8-sig")

    for source in (bot, backup):
        assert "[switch]$StageDisabled" in source
        assert "Get-Sha256Text" in source
        assert "Export-ScheduledTask" in source
        assert "Disable-ScheduledTask" in source
        assert "candidate staging failed closed" in source
    assert "[switch]$ReplaceExisting" in bot
    assert "$ExpectedMainDefinitionDigest" in bot
    assert "$ExpectedHealthDefinitionDigest" in bot
    assert "$ExpectedHealthLauncherDigest" in bot
    assert "$RollbackRoot" in bot
    assert "[System.IO.File]::Replace" in bot
    assert "$ExpectedDefinitionDigest" in backup
    assert bot.index("-Disable") < bot.index("Register-ScheduledTask")
    assert backup.index("-Disable") < backup.index("Register-ScheduledTask")


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell installer")
def test_m1_bot_installer_second_registration_failure_leaves_pair_disabled(
    tmp_path,
):
    root = tmp_path / "repo"
    rollback = tmp_path / "rollback"
    for directory in (
        root / ".venv" / "Scripts",
        root / "scripts",
        root / ".runtime",
        rollback,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    for relative in (
        ".venv/Scripts/python.exe",
        ".venv/Scripts/pythonw.exe",
        "scripts/run_nobus_space_live.py",
        "scripts/check_nobus_space_health.py",
    ):
        (root / relative).write_bytes(b"synthetic\n")
    launcher = root / ".runtime" / "check-nobus-space-bot.ps1"
    launcher.write_bytes(b"# exact old launcher\r\nexit 0\r\n")
    main_xml = "<Task>exact-main</Task>"
    health_xml = "<Task>exact-health</Task>"

    def digest(value: bytes) -> str:
        return "sha256:" + hashlib.sha256(value).hexdigest()

    installer = (
        Path(__file__).parents[1]
        / "ops"
        / "windows"
        / "Install-NobusSpaceBot.ps1"
    ).resolve()

    def ps(value: object) -> str:
        return str(value).replace("'", "''")

    harness = tmp_path / "installer-fail-closed.ps1"
    harness.write_text(
        f"""
$ErrorActionPreference='Stop'
$OutputEncoding=[Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$global:registered=@()
$global:disabled=@()
function Get-ScheduledTask {{
    [CmdletBinding()] param([string]$TaskName,[string]$TaskPath)
    [pscustomobject]@{{Settings=[pscustomobject]@{{Enabled=$false}};State='Ready'}}
}}
function Export-ScheduledTask {{
    [CmdletBinding()] param([string]$TaskName,[string]$TaskPath)
    if($TaskName -like '*-Health'){{'{ps(health_xml)}'}}else{{'{ps(main_xml)}'}}
}}
function New-ScheduledTaskAction {{
    [CmdletBinding()] param($Execute,$Argument,$WorkingDirectory)
    [pscustomobject]@{{Kind='action'}}
}}
function New-ScheduledTaskTrigger {{
    [CmdletBinding()] param([switch]$AtLogOn,[switch]$Once,$At,$User,$RepetitionInterval,$RepetitionDuration)
    [pscustomobject]@{{Kind='trigger'}}
}}
function New-ScheduledTaskSettingsSet {{
    [CmdletBinding()] param([switch]$Disable,[switch]$StartWhenAvailable,[switch]$AllowStartIfOnBatteries,[switch]$DontStopIfGoingOnBatteries,$ExecutionTimeLimit,$MultipleInstances)
    [pscustomobject]@{{Enabled=(-not $Disable.IsPresent)}}
}}
function New-ScheduledTaskPrincipal {{
    [CmdletBinding()] param($UserId,$LogonType,$RunLevel)
    [pscustomobject]@{{Kind='principal'}}
}}
function New-ScheduledTask {{
    [CmdletBinding()] param($Action,$Trigger,$Settings,$Principal,$Description)
    [pscustomobject]@{{Settings=$Settings}}
}}
function Register-ScheduledTask {{
    [CmdletBinding()] param([string]$TaskName,[string]$TaskPath,$InputObject,[switch]$Force)
    $global:registered+=,$TaskName
    if($TaskName -like '*-Health'){{throw 'synthetic second registration failure'}}
}}
function Disable-ScheduledTask {{
    [CmdletBinding()] param([string]$TaskName,[string]$TaskPath)
    $global:disabled+=,$TaskName
}}
try {{
    & '{ps(installer)}' `
      -TaskName 'NobusSpaceM1S1Fixture' `
      -RepositoryRoot '{ps(root)}' `
      -HealthLauncherRoot '{ps(root)}' `
      -ReplaceExisting `
      -StageDisabled `
      -ExpectedMainDefinitionDigest '{digest(main_xml.encode("utf-8"))}' `
      -ExpectedHealthDefinitionDigest '{digest(health_xml.encode("utf-8"))}' `
      -ExpectedHealthLauncherDigest '{digest(launcher.read_bytes())}' `
      -RollbackRoot '{ps(rollback)}'
    $outcome='unexpected_success'
}} catch {{$outcome=$_.Exception.Message}}
[ordered]@{{outcome=$outcome;registered=@($global:registered);disabled=@($global:disabled)}} | ConvertTo-Json -Compress
""".strip()
        + "\n",
        encoding="utf-8-sig",
    )
    result = subprocess.run(
        [
            "powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(harness),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    output = json.loads(result.stdout.decode("utf-8-sig"))
    assert output == {
        "outcome": "candidate staging failed closed: register_health_disabled",
        "registered": ["NobusSpaceM1S1Fixture", "NobusSpaceM1S1Fixture-Health"],
        "disabled": ["NobusSpaceM1S1Fixture", "NobusSpaceM1S1Fixture-Health"],
    }
    assert launcher.read_bytes() == b"# exact old launcher\r\nexit 0\r\n"
    assert (rollback / "NobusSpaceM1S1Fixture.xml").read_text(
        encoding="utf-8"
    ) == main_xml
    assert (rollback / "NobusSpaceM1S1Fixture-Health.xml").read_text(
        encoding="utf-8"
    ) == health_xml
    assert not list((root / ".runtime").glob("*.candidate"))


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell installer")
@pytest.mark.parametrize("local_time", ["00:00", "23:59"])
def test_m1_backup_installer_registration_failure_leaves_task_disabled(tmp_path, local_time):
    root = tmp_path / "repo"
    python = root / ".venv" / "Scripts" / "python.exe"
    script = root / "scripts" / "run_telegram_backup_cycle.py"
    config = root / ".runtime" / "backup-cycle.json"
    for path in (python, script, config):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic\n")
    task_xml = "<Task>exact-backup</Task>"
    expected_definition = "sha256:" + hashlib.sha256(
        task_xml.encode("utf-8")
    ).hexdigest()
    installer = (
        Path(__file__).parents[1]
        / "ops"
        / "windows"
        / "Install-NobusSpaceBackup.ps1"
    ).resolve()

    def ps(value: object) -> str:
        return str(value).replace("'", "''")

    harness = tmp_path / "backup-installer-fail-closed.ps1"
    harness.write_text(
        f"""
$ErrorActionPreference='Stop'
$OutputEncoding=[Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$global:disabled=@()
function Get-ScheduledTask {{
    [CmdletBinding()] param([string]$TaskName,[string]$TaskPath)
    [pscustomobject]@{{Settings=[pscustomobject]@{{Enabled=$false}};State='Ready'}}
}}
function Export-ScheduledTask {{
    [CmdletBinding()] param([string]$TaskName,[string]$TaskPath)
    '{ps(task_xml)}'
}}
function New-ScheduledTaskAction {{
    [CmdletBinding()] param($Execute,$Argument,$WorkingDirectory)
    [pscustomobject]@{{Kind='action'}}
}}
function New-ScheduledTaskTrigger {{
    [CmdletBinding()] param([switch]$Daily,$At)
    if($At -le (Get-Date) -or $At -gt (Get-Date).AddDays(1)) {{throw 'unsafe staged backup boundary'}}
    [pscustomobject]@{{Kind='trigger'}}
}}
function New-ScheduledTaskSettingsSet {{
    [CmdletBinding()] param([switch]$Disable,[switch]$StartWhenAvailable,[switch]$AllowStartIfOnBatteries,[switch]$DontStopIfGoingOnBatteries,$ExecutionTimeLimit,$MultipleInstances)
    [pscustomobject]@{{Enabled=(-not $Disable.IsPresent)}}
}}
function New-ScheduledTaskPrincipal {{
    [CmdletBinding()] param($UserId,$LogonType,$RunLevel)
    [pscustomobject]@{{Kind='principal'}}
}}
function New-ScheduledTask {{
    [CmdletBinding()] param($Action,$Trigger,$Settings,$Principal,$Description)
    [pscustomobject]@{{Settings=$Settings}}
}}
function Register-ScheduledTask {{
    [CmdletBinding()] param([string]$TaskName,[string]$TaskPath,$InputObject,[switch]$Force)
    throw 'synthetic backup registration failure'
}}
function Disable-ScheduledTask {{
    [CmdletBinding()] param([string]$TaskName,[string]$TaskPath)
    $global:disabled+=,$TaskName
}}
try {{
    & '{ps(installer)}' `
      -TaskName 'NobusSpaceM1S1BackupFixture' `
      -RepositoryRoot '{ps(root)}' `
      -Python '{ps(python)}' `
      -Config '{ps(config)}' `
      -ConfigDigest 'sha256:{'d' * 64}' `
      -LocalTime '{local_time}' `
      -ReplaceExisting `
      -StageDisabled `
      -ExpectedDefinitionDigest '{expected_definition}'
    $outcome='unexpected_success'
}} catch {{$outcome=$_.Exception.Message}}
[ordered]@{{outcome=$outcome;disabled=@($global:disabled)}} | ConvertTo-Json -Compress
""".strip()
        + "\n",
        encoding="utf-8-sig",
    )
    result = subprocess.run(
        [
            "powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(harness),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert json.loads(result.stdout.decode("utf-8-sig")) == {
        "outcome": "candidate staging failed closed: register_backup",
        "disabled": ["NobusSpaceM1S1BackupFixture"],
    }
