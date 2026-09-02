from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

import pytest

from scripts.backup_telegram_runtime import backup
from scripts.check_telegram_health import check
from src.application.windows_singleton import RunnerAlreadyActive, WindowsNamedMutex


def _runtime_databases(root: Path) -> tuple[Path, ...]:
    from src.application.business_notes import SQLiteBusinessNotes
    from src.application.durable_telegram_state import SQLiteTelegramState
    from src.storage.sqlite_store import SQLiteStore
    from src.transport.telegram.sqlite_checkpoint import (
        SQLitePollingCheckpointStore,
    )

    sources = (
        root / "telegram-checkpoint.sqlite3",
        root / "task-runtime.sqlite3",
        root / "telegram-state.sqlite3",
        root / "business-notes.sqlite3",
    )
    SQLitePollingCheckpointStore(sources[0], consumer_id="nobus-space-bot")
    SQLiteStore(sources[1])
    SQLiteTelegramState(sources[2])
    SQLiteBusinessNotes(sources[3])
    return sources


def test_health_and_verified_non_overwriting_backup(tmp_path: Path) -> None:
    sources = _runtime_databases(tmp_path)

    assert check(sources)["status"] == "PASS"
    destination = tmp_path / "backup"
    manifest = backup(sources, destination)
    values = json.loads(manifest.read_text(encoding="utf-8"))
    assert values["schema_version"] == 2
    assert {item["name"] for item in values["files"]} == {
        source.name for source in sources
    }
    with pytest.raises(ValueError, match="new directory"):
        backup(sources, destination)


def test_health_rejects_incomplete_but_valid_runtime_set(
    tmp_path: Path,
) -> None:
    sources = _runtime_databases(tmp_path)

    assert check(sources[:1]) == {
        "status": "FAIL",
        "databases": {
            "telegram-checkpoint.sqlite3": "invalid-set",
        },
    }


def test_health_fails_closed_for_missing_database(tmp_path: Path) -> None:
    paths = tuple(
        tmp_path / name
        for name in (
            "telegram-checkpoint.sqlite3",
            "task-runtime.sqlite3",
            "telegram-state.sqlite3",
            "business-notes.sqlite3",
        )
    )
    result = check(paths)
    assert result == {
        "status": "FAIL",
        "databases": {path.name: "missing" for path in paths},
    }


@pytest.mark.skipif(os.name != "nt", reason="Windows named mutex")
def test_named_mutex_rejects_second_runner() -> None:
    first = WindowsNamedMutex()
    second = WindowsNamedMutex()
    with first:
        with pytest.raises(RunnerAlreadyActive):
            with second:
                pass


@pytest.mark.skipif(os.name != "nt", reason="Windows Task Scheduler")
def test_scheduler_whatif_writes_nothing(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / ".venv" / "Scripts").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / ".venv" / "Scripts" / "python.exe").touch()
    (root / ".venv" / "Scripts" / "pythonw.exe").touch()
    (root / "scripts" / "run_nobus_space_live.py").touch()
    (root / "scripts" / "check_telegram_health.py").touch()
    script = (
        Path(__file__).resolve().parents[1]
        / "ops"
        / "windows"
        / "Install-NobusSpaceBot.ps1"
    )

    result = subprocess.run(
        (
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-RepositoryRoot",
            str(root),
            "-TaskName",
            "NobusSpaceBot-Test",
            "-WhatIf",
        ),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

    assert result.returncode == 0
    assert not (root / ".runtime").exists()


def test_backup_rejects_incomplete_or_unknown_runtime_set(tmp_path: Path) -> None:
    sources = _runtime_databases(tmp_path)
    with pytest.raises(ValueError, match="complete runtime database set"):
        backup(sources[:2], tmp_path / "incomplete")
    unknown = tmp_path / "unknown.sqlite3"
    with closing(sqlite3.connect(unknown)) as connection:
        connection.execute("CREATE TABLE marker(value INTEGER)")
    assert check((unknown,))["status"] == "FAIL"


def test_health_rejects_lookalike_schema_without_constraints(
    tmp_path: Path,
) -> None:
    sources = _runtime_databases(tmp_path)
    path = sources[0]
    path.unlink()
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(
            """CREATE TABLE telegram_polling_checkpoints (
                   consumer_id TEXT, offset INTEGER, lease_id TEXT,
                   lease_owner TEXT, lease_expires_at TEXT, revision INTEGER,
                   updated_at TEXT, state_digest TEXT)"""
        )
    result = check(sources)
    assert result["status"] == "FAIL"
    assert result["databases"][path.name] == "unavailable"


def test_health_reports_dead_letter_as_degraded_with_bounded_stopped_recovery(
    tmp_path: Path,
) -> None:
    from src.application.durable_telegram_state import SQLiteTelegramState

    sources = _runtime_databases(tmp_path)
    state = SQLiteTelegramState(sources[2])
    task_id = __import__("uuid").uuid4()
    state.enqueue(
        kind="draft",
        tenant_id="owner",
        task_id=task_id,
        binding_digest="sha256:" + "a" * 64,
        payload={"task": str(task_id)},
    )
    owner = __import__("uuid").uuid4()
    job = state.claim(lease_owner=owner)
    assert job is not None
    state.fail(job, lease_owner=owner, failure_code="test_dead_letter")
    result = check(sources)
    assert result["status"] == "DEGRADED"
    assert result["databases"]["telegram-state.sqlite3"] == "degraded"

    installer = (
        Path(__file__).resolve().parents[1]
        / "ops/windows/Install-NobusSpaceBot.ps1"
    ).read_text(encoding="utf-8")
    assert "-RestartCount 10" in installer
    assert installer.count("-AllowStartIfOnBatteries") == 2
    assert installer.count("-DontStopIfGoingOnBatteries") == 2
    assert "-RestartCount 999" not in installer
    assert "Stop-ScheduledTask" not in installer
    assert installer.count("Start-ScheduledTask") == 1
    assert "`$task.State -eq 'Ready'" in installer
    assert "run_nobus_space_live.py" in installer
    assert "-Execute $pythonw" in installer
    assert "-WindowStyle Hidden" in installer
    assert "-RepetitionInterval (New-TimeSpan -Minutes 1)" in installer
    assert "http://127.0.0.1:8765/readyz" in installer
    assert "https://app.nobusspace.com/readyz" in installer
    assert "Generated health launcher is invalid." in installer
    assert "[System.Text.UTF8Encoding]::new($true)" in installer


def test_health_recomputes_checkpoint_digest(tmp_path: Path) -> None:
    from uuid import uuid4
    from src.transport.telegram.sqlite_checkpoint import (
        SQLitePollingCheckpointStore,
    )

    sources = _runtime_databases(tmp_path)
    checkpoint = SQLitePollingCheckpointStore(
        sources[0],
        consumer_id="nobus-space-bot",
    )
    checkpoint.acquire(uuid4(), __import__("datetime").datetime.now(__import__("datetime").UTC))
    with closing(sqlite3.connect(sources[0])) as connection:
        connection.execute(
            "UPDATE telegram_polling_checkpoints SET state_digest=?",
            ("sha256:" + "0" * 64,),
        )
        connection.commit()
    assert check(sources)["status"] == "FAIL"


def test_health_accepts_supergroup_progress_chat_id(tmp_path: Path) -> None:
    from uuid import uuid4
    from src.application.durable_telegram_state import SQLiteTelegramState

    sources = _runtime_databases(tmp_path)
    state = SQLiteTelegramState(sources[2])
    state.save_progress(
        tenant_id="owner",
        task_id=uuid4(),
        chat_id=-1001234567890,
        message_id=77,
    )

    assert check(sources)["status"] == "PASS"


def test_health_rejects_semantically_invalid_runtime_job(tmp_path: Path) -> None:
    from uuid import uuid4
    from src.application.durable_telegram_state import SQLiteTelegramState

    sources = _runtime_databases(tmp_path)
    state = SQLiteTelegramState(sources[2])
    task_id = uuid4()
    state.enqueue(
        kind="draft",
        tenant_id="owner",
        task_id=task_id,
        binding_digest="sha256:" + "a" * 64,
        payload={"task": str(task_id)},
    )
    with closing(sqlite3.connect(sources[2])) as connection:
        connection.execute("UPDATE telegram_jobs SET job_id='not-a-uuid'")
        connection.commit()

    assert check(sources)["status"] == "FAIL"


def test_health_recomputes_dpapi_payload_digest(tmp_path: Path) -> None:
    from uuid import uuid4
    from src.application.durable_telegram_state import SQLiteTelegramState

    sources = _runtime_databases(tmp_path)
    state = SQLiteTelegramState(sources[2])
    task_id = uuid4()
    state.enqueue(
        kind="draft",
        tenant_id="owner",
        task_id=task_id,
        binding_digest="sha256:" + "a" * 64,
        payload={"task": str(task_id)},
    )
    with closing(sqlite3.connect(sources[2])) as connection:
        connection.execute(
            "UPDATE telegram_jobs SET payload_digest=?",
            ("sha256:" + "0" * 64,),
        )
        connection.commit()
    assert check(sources)["status"] == "FAIL"
