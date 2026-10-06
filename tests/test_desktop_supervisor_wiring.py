"""Desktop bridge must survive the scheduler → supervisor → Core chain."""

from __future__ import annotations

import sys
import sqlite3
from uuid import uuid4
from pathlib import Path

import pytest

from scripts import run_nobus_space_live as supervisor
from scripts import run_telegram_backup_cycle as backup_cycle
from src.application.desktop_bridge_state import (
    BridgeRequestStatus, SQLiteDesktopBridgeState,
)
from src.application.durable_telegram_state import SQLiteTelegramState
from src.application.runtime_maintenance import (
    EXPECTED_SCHEMA_DIGESTS, _ddl_digest, validate_runtime_database,
)


def test_supervisor_passes_exact_desktop_bridge_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(supervisor, "WORKTREE", tmp_path)
    inventory = tmp_path / "desktop-projects.local.json"
    inventory.write_text('{"version":1,"projects":[]}', encoding="utf-8")
    values = supervisor._arguments([
        "--desktop-bridge", "--desktop-projects-file", str(inventory),
    ])
    command = supervisor.core_command(Path(sys.executable), values)
    assert command.count("--desktop-bridge") == 1
    assert command[command.index("--desktop-projects-file") + 1] == str(inventory.resolve())
    assert "--desktop-bridge" not in supervisor.core_command(
        Path(sys.executable), supervisor._arguments([])
    )


def test_supervisor_rejects_unpaired_desktop_configuration(tmp_path: Path) -> None:
    inventory = tmp_path / "desktop-projects.local.json"
    inventory.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        supervisor.core_command(
            Path(sys.executable), supervisor._arguments(["--desktop-bridge"])
        )
    with pytest.raises(ValueError):
        supervisor.core_command(
            Path(sys.executable),
            supervisor._arguments(["--desktop-projects-file", str(inventory)]),
        )


def test_supervisor_passes_only_explicit_owner_artifact_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = tmp_path / "АГЕНТ"
    worktree = owner / "project"
    worktree.mkdir(parents=True)
    documents = owner / "documents"
    documents.mkdir()
    inventory = worktree / "desktop-projects.local.json"
    inventory.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(supervisor, "WORKTREE", worktree)
    values = supervisor._arguments([
        "--desktop-bridge", "--desktop-projects-file", str(inventory),
        "--desktop-artifact-root", str(documents),
    ])
    command = supervisor.core_command(Path(sys.executable), values)
    assert command[command.index("--desktop-artifact-root") + 1] == str(documents)
    with pytest.raises(ValueError):
        supervisor.core_command(Path(sys.executable), supervisor._arguments([
            "--desktop-bridge", "--desktop-projects-file", str(inventory),
            "--desktop-artifact-root", str(owner),
        ]))


def test_scheduler_installer_exposes_bridge_switch_only_when_configured() -> None:
    installer = (Path(__file__).parents[1] / "ops/windows/Install-NobusSpaceBot.ps1").read_text(
        encoding="utf-8"
    )
    assert "[switch]$DesktopBridge" in installer
    assert "[string]$DesktopProjectsFile" in installer
    assert "if ([bool]$DesktopBridge.IsPresent -ne [bool]$desktopInventory)" in installer
    assert "$runnerArguments += @('--desktop-bridge', '--desktop-projects-file'" in installer
    assert "$runnerArguments += @('--desktop-artifact-root'" in installer


def test_backup_schema_accepts_fresh_and_migrated_bridge_table(tmp_path: Path) -> None:
    fresh = tmp_path / "telegram-state.sqlite3"
    SQLiteTelegramState(fresh)
    SQLiteDesktopBridgeState(fresh)
    validate_runtime_database(fresh, content=False)
    with sqlite3.connect(fresh) as connection:
        ddl = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='desktop_bridge_requests'"
        ).fetchone()[0]
    expected = EXPECTED_SCHEMA_DIGESTS["telegram-state.sqlite3"]["table:desktop_bridge_requests"]
    assert _ddl_digest(ddl) in (expected if isinstance(expected, tuple) else (expected,))

    migrated_dir = tmp_path / "migrated"
    migrated_dir.mkdir()
    migrated = migrated_dir / "telegram-state.sqlite3"
    with sqlite3.connect(migrated) as connection:
        connection.execute(ddl.replace("bootstrap_turn_id TEXT,", ""))
    SQLiteTelegramState(migrated)
    SQLiteDesktopBridgeState(migrated)
    validate_runtime_database(migrated, content=False)
    with sqlite3.connect(migrated) as connection:
        migrated_ddl = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='desktop_bridge_requests'"
        ).fetchone()[0]
    assert _ddl_digest(migrated_ddl) in (
        expected if isinstance(expected, tuple) else (expected,)
    )

    state = SQLiteDesktopBridgeState(migrated)
    request_id, thread_id, turn_id = uuid4(), str(uuid4()), str(uuid4())
    state.create_request(
        request_id=request_id, ingress_key="sha256:" + "a" * 64,
        tenant_id="owner", author_user_id=41,
        author_identity="telegram:member:41", chat_id=-1001, topic_id=7,
        source_message_id=12, operation="create", project_name="project",
        payload={"instruction": "test"},
    )
    state.bind_desktop(
        request_id, thread_id=thread_id, turn_id=None,
        client_message_id=f"nobus:{request_id}",
        status=BridgeRequestStatus.RECEIVED,
    )
    assert state.bind_bootstrap_turn(
        request_id, thread_id=thread_id, turn_id=turn_id
    )
    validate_runtime_database(migrated)


def test_backup_rebind_migrates_only_the_exact_previous_bridge_schema(tmp_path: Path) -> None:
    fresh = tmp_path / "fresh" / "telegram-state.sqlite3"
    fresh.parent.mkdir()
    SQLiteTelegramState(fresh)
    with sqlite3.connect(fresh) as connection:
        ddl = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='desktop_bridge_requests'"
        ).fetchone()[0]

    old = tmp_path / "old" / "telegram-state.sqlite3"
    old.parent.mkdir()
    SQLiteTelegramState(old)
    with sqlite3.connect(old) as connection:
        indexes = [row[0] for row in connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' "
            "AND tbl_name='desktop_bridge_requests' AND sql IS NOT NULL"
        )]
        connection.execute("DROP TABLE desktop_bridge_menu_prompts")
        connection.execute("DROP TABLE desktop_bridge_menus")
        connection.execute("DROP TABLE desktop_bridge_requests")
        connection.execute(ddl.replace("bootstrap_turn_id TEXT,", ""))
        for index in indexes:
            connection.execute(index)
    assert backup_cycle._migrate_exact_previous_desktop_schema(old.parent)
    with sqlite3.connect(old) as connection:
        assert "bootstrap_turn_id" in {
            row[1] for row in connection.execute("PRAGMA table_info(desktop_bridge_requests)")
        }
    assert not backup_cycle._migrate_exact_previous_desktop_schema(old.parent)

    current = tmp_path / "current" / "telegram-state.sqlite3"
    current.parent.mkdir()
    SQLiteTelegramState(current)
    with sqlite3.connect(current) as connection:
        connection.execute("DROP TABLE desktop_bridge_menu_prompts")
        connection.execute("DROP TABLE desktop_bridge_menus")
    assert backup_cycle._migrate_exact_previous_desktop_schema(current.parent)
    validate_runtime_database(current, content=False)
    assert not backup_cycle._migrate_exact_previous_desktop_schema(current.parent)

    unknown = tmp_path / "unknown" / "telegram-state.sqlite3"
    unknown.parent.mkdir()
    with sqlite3.connect(unknown) as connection:
        connection.execute("CREATE TABLE desktop_bridge_requests (request_id TEXT)")
    assert not backup_cycle._migrate_exact_previous_desktop_schema(unknown.parent)
    with sqlite3.connect(unknown) as connection:
        assert connection.execute("PRAGMA table_info(desktop_bridge_requests)").fetchall() == [
            (0, "request_id", "TEXT", 0, None, 0)
        ]
