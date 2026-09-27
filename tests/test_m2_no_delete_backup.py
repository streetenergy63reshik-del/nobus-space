"""No-delete backup path: no plaintext staging or control-file removal."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import ExitStack, closing, nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts import backup_telegram_runtime as backup
from scripts import run_telegram_backup_cycle as cycle
from scripts import restore_telegram_runtime as restore
from src.application import managed_backups, runtime_maintenance as maintenance
from tests.test_c5_backup_recovery import fixture_runtime


def test_control_file_promotion_preserves_file_identity(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    source, target, archive = (tmp_path / name for name in ("pending", "current", "previous"))
    source.write_bytes(b"new")
    target.write_bytes(b"old")
    old_id, new_id = target.stat().st_ino, source.stat().st_ino

    maintenance.promote_preserving_previous(source, target, archive)

    assert archive.read_bytes() == b"old" and archive.stat().st_ino == old_id
    assert target.read_bytes() == b"new" and target.stat().st_ino == new_id
    assert not source.exists()


def test_control_file_promotion_refuses_archive_collision(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    source, target, archive = (tmp_path / name for name in ("pending", "current", "previous"))
    source.write_bytes(b"new")
    target.write_bytes(b"old")
    archive.write_bytes(b"unrelated")

    try:
        maintenance.promote_preserving_previous(source, target, archive)
    except ValueError:
        pass
    else:
        raise AssertionError("archive collision was accepted")

    assert source.read_bytes() == b"new"
    assert target.read_bytes() == b"old"
    assert archive.read_bytes() == b"unrelated"


def test_partial_windows_promotion_restores_original(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    source, target, archive = (tmp_path / name for name in ("pending", "current", "previous"))
    source.write_bytes(b"new")
    target.write_bytes(b"old")

    def fail_after_archiving(*_args):
        os.rename(target, archive)
        return 0

    with patch.object(maintenance.ctypes, "WinDLL", return_value=SimpleNamespace(ReplaceFileW=fail_after_archiving)), patch.object(
        maintenance.ctypes, "get_last_error", return_value=1177
    ):
        try:
            maintenance.promote_preserving_previous(source, target, archive)
        except OSError as error:
            assert error.errno == 1177
        else:
            raise AssertionError("partial replacement was accepted")

    assert target.read_bytes() == b"old"
    assert source.read_bytes() == b"new"
    assert not archive.exists()


def test_unknown_windows_promotion_keeps_both_files_and_stops(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    source, target, archive = (tmp_path / name for name in ("pending", "current", "previous"))
    source.write_bytes(b"new")
    target.write_bytes(b"old")

    def fail_after_both_moves(*_args):
        os.rename(target, archive)
        os.rename(source, target)
        return 0

    with patch.object(maintenance.ctypes, "WinDLL", return_value=SimpleNamespace(ReplaceFileW=fail_after_both_moves)), patch.object(
        maintenance.ctypes, "get_last_error", return_value=1177
    ):
        try:
            maintenance.promote_preserving_previous(source, target, archive)
        except maintenance.ControlPromotionIndeterminate:
            pass
        else:
            raise AssertionError("unknown replacement outcome was accepted")

    assert target.read_bytes() == b"new"
    assert archive.read_bytes() == b"old"


def test_backup_cycle_does_not_rewrite_unknown_journal(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    config_path = tmp_path / "backup-cycle.json"
    config = {
        "runtime": str(tmp_path), "backup_root": str(tmp_path),
        "tasks": {"main": {"name": "NobusSpaceBot"}, "health": {"name": "NobusSpaceBot-Health"}},
        "ownership": "sha256:" + "a" * 64,
    }
    journal_write = Mock(side_effect=maintenance.ControlPromotionIndeterminate("unknown"))
    with ExitStack() as stack:
        stack.enter_context(patch.object(cycle, "WindowsNamedMutex", lambda *_args: nullcontext()))
        stack.enter_context(patch.object(cycle, "load_config", return_value=config))
        stack.enter_context(patch.object(cycle, "_task", return_value={"state": "Running", "enabled": True}))
        stack.enter_context(patch.object(cycle.managed, "hold_admission"))
        cleanup = stack.enter_context(patch.object(cycle, "_cleanup", return_value=True))
        stack.enter_context(patch.object(cycle, "_journal", journal_write))
        try:
            cycle.cycle(config_path, "sha256:" + "b" * 64)
        except maintenance.ControlPromotionIndeterminate:
            pass
        else:
            raise AssertionError("unknown journal outcome was accepted")

    assert journal_write.call_count == 1
    cleanup.assert_called_once()


def test_missing_latest_pointer_with_prior_generation_fails_closed(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    root = tmp_path / "backups"
    ownership = managed_backups.initialize(root, runtime, "sha256:" + "a" * 64)
    (root / ("daily-20260927T000000-" + "b" * 32)).mkdir()

    try:
        managed_backups.create_generation(root, runtime, ownership)
    except ValueError as error:
        assert str(error) == "latest pointer missing with existing generation"
    else:
        raise AssertionError("missing latest pointer was accepted")


def test_missing_backup_journal_with_history_fails_closed(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    config = tmp_path / "backup-cycle.json"
    (tmp_path / ("cycle-history-" + "c" * 32 + ".dpapi")).write_bytes(b"preserved")
    with patch.object(cycle, "WindowsNamedMutex", lambda *_args: nullcontext()), patch.object(
        cycle, "load_config", return_value={"runtime": str(tmp_path), "backup_root": str(tmp_path)}
    ):
        try:
            cycle.cycle(config, "sha256:" + "d" * 64)
        except ValueError as error:
            assert str(error) == "backup journal promotion incomplete"
        else:
            raise AssertionError("missing backup journal was accepted")


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


def test_new_generation_preserves_previous_pointer_and_generation(tmp_path, monkeypatch):
    synthetic_binding = {"source_commit": "0" * 40}
    monkeypatch.setattr(backup, "application_binding", lambda: synthetic_binding)
    monkeypatch.setattr(restore, "application_binding", lambda: synthetic_binding)
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
    os.rename(root / "latest.dpapi", tmp_path / "preserved-current.dpapi")
    try:
        managed_backups.create_generation(root, runtime, ownership)
    except ValueError as error:
        assert str(error) == "latest pointer missing with existing generation"
    else:
        raise AssertionError("missing published pointer was accepted")


def test_missing_first_published_pointer_is_not_mistaken_for_recovery(tmp_path, monkeypatch):
    synthetic_binding = {"source_commit": "0" * 40}
    monkeypatch.setattr(backup, "application_binding", lambda: synthetic_binding)
    monkeypatch.setattr(restore, "application_binding", lambda: synthetic_binding)
    runtime = tmp_path / "runtime"
    fixture_runtime(runtime)
    root = tmp_path / "backups"
    ownership = managed_backups.initialize(root, runtime, "sha256:" + "a" * 64)
    first = managed_backups.create_generation(root, runtime, ownership)
    preserved = tmp_path / "preserved-first-pointer.dpapi"
    os.rename(root / "latest.dpapi", preserved)

    try:
        managed_backups.create_generation(root, runtime, ownership)
    except ValueError as error:
        assert str(error) == "latest pointer missing with existing generation"
    else:
        raise AssertionError("missing first published pointer was accepted")

    assert first.is_dir() and preserved.is_file()


def test_backup_journal_preserves_previous_signed_phase(tmp_path):
    path = tmp_path / "backup-cycle-state.dpapi"
    digest = "sha256:" + "b" * 64
    cycle._journal(path, digest, "closing_admission")
    prior = path.read_bytes()
    cycle._journal(path, digest, "stopped")
    archives = list(tmp_path.glob("cycle-history-*.dpapi"))
    assert len(archives) == 1 and archives[0].read_bytes() == prior
    assert managed_backups._certificate(path)["phase"] == "stopped"
