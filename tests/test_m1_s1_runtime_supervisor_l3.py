"""Blocking L2/L3 regressions for the M1-S1 supervisor candidate."""
from __future__ import annotations

import json
import os
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
    monkeypatch.setattr(
        supervisor,
        "_scheduler_task_signature",
        lambda name: {"task": name, "action": "exact"},
    )
    values = SimpleNamespace(
        voice_model_directory=voice,
        backup_root=backup,
        backup_ownership="sha256:" + "e" * 64,
        health_launcher=health,
        scheduler_task_name="NobusSpaceBot",
        semantic_admission=True,
    )
    first = supervisor._activation_manifest(values, runtime)
    assert first["schema"] == "nobus-supervisor-activation-2"
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
