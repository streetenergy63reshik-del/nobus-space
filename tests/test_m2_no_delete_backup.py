"""No-delete backup path: no plaintext staging or control-file removal."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing

from scripts import backup_telegram_runtime as backup
from scripts import run_telegram_backup_cycle as cycle
from src.application import managed_backups, runtime_maintenance as maintenance
from tests.test_c5_backup_recovery import fixture_runtime


def test_quiescent_backup_uses_memory_not_plaintext_staging(tmp_path, monkeypatch):
    source = tmp_path / "source"
    fixture_runtime(source)
    monkeypatch.setattr(
        backup, "application_binding", lambda: {"source_commit": "0" * 40},
    )
    destination = tmp_path / "backup"
    manifest = backup._backup_quiescent(
        maintenance.runtime_database_paths(source), destination,
    )
    values = json.loads(manifest.read_text(encoding="utf-8"))
    assert not any(path.is_dir() for path in destination.iterdir())
    assert len(values["files"]) == 3
    for item in values["files"]:
        cipher = (destination / (item["name"] + ".dpapi")).read_bytes()
        assert not cipher.startswith(b"SQLite format 3")
        plain = maintenance.unprotect_backup(cipher)
        restored_path = tmp_path / ("verified-" + item["name"])
        restored_path.write_bytes(plain)
        with closing(sqlite3.connect(restored_path.as_uri() + "?immutable=1", uri=True)) as restored:
            assert restored.execute("PRAGMA quick_check").fetchone() == ("ok",)
            assert maintenance.database_connection_state_digest(restored) == item["state_digest"]


def test_admission_release_preserves_zero_byte_flag(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    root = tmp_path / "backups"
    ownership = managed_backups.initialize(root, runtime, "sha256:" + "a" * 64)
    managed_backups.hold_admission(root, ownership)
    managed_backups.permit_admission(root, ownership)
    assert not (root / "admission-hold").exists()
    archives = list(tmp_path.glob("backups-admission-hold-released-*.zero"))
    assert len(archives) == 1 and archives[0].read_bytes() == b""


def test_new_generation_preserves_previous_pointer_and_generation(tmp_path):
    runtime = tmp_path / "runtime"
    fixture_runtime(runtime)
    root = tmp_path / "backups"
    ownership = managed_backups.initialize(root, runtime, "sha256:" + "a" * 64)
    first = managed_backups.create_generation(root, runtime, ownership)
    prior_pointer = (root / "latest.dpapi").read_bytes()
    second = managed_backups.create_generation(root, runtime, ownership)
    archives = list(tmp_path.glob("backups-latest-before-*.dpapi"))
    assert first.is_dir() and second.is_dir() and first != second
    assert len(archives) == 1 and archives[0].read_bytes() == prior_pointer


def test_backup_journal_preserves_previous_signed_phase(tmp_path):
    path = tmp_path / "backup-cycle-state.dpapi"
    digest = "sha256:" + "b" * 64
    cycle._journal(path, digest, "closing_admission")
    prior = path.read_bytes()
    cycle._journal(path, digest, "stopped")
    archives = list(tmp_path.glob("cycle-history-*.dpapi"))
    assert len(archives) == 1 and archives[0].read_bytes() == prior
    assert managed_backups._certificate(path)["phase"] == "stopped"
