"""C5 real SQLite/DPAPI drills in per-test disposable roots; no provider or live I/O."""
from __future__ import annotations

import asyncio
from contextlib import closing
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

import pytest

from scripts import backup_telegram_runtime as backup, restore_telegram_runtime as restore
from scripts.check_telegram_health import check, operator_view, retention_dry_run
from src.application import runtime_maintenance as maintenance
from src.application.durable_telegram_state import SQLiteTelegramState
from src.application.miniapp import MiniAppCore, MiniAppAuthenticationError, MiniAppCoreUnavailableError
from src.application.product_effects import DurableProductEffectVault, ProductEffectKind
from src.contracts.models import canonical_json_digest
from src.security.dpapi import protect_current_user
from src.storage import SQLiteStore
from src.storage.sqlite_store import MiniAppCancelledRequest, MiniAppRequestRecord
from src.transport.telegram.sqlite_checkpoint import SQLitePollingCheckpointStore
from tests.test_miniapp import BOT_TOKEN, OWNER_ID, Clock, signed_init_data
from tests.test_miniapp_result import _answered_store
from tests.test_c3_delivery_parts import Sender, runtime as delivery_runtime, Clock as DeliveryClock


def fixture_runtime(root: Path, *, answer: bool = False):
    root.mkdir(parents=True)
    SQLitePollingCheckpointStore(root / 'telegram-checkpoint.sqlite3', consumer_id='synthetic-c5')
    queue = SQLiteTelegramState(root / 'telegram-state.sqlite3')
    if answer:
        store, task, message = _answered_store(root / 'task-runtime.sqlite3')
    else:
        store, task, message = SQLiteStore(root / 'task-runtime.sqlite3'), None, None
    return store, queue, task, message


def safe_restore(manifest: Path, target: Path):
    values = json.loads(manifest.read_text())
    restore._restore_quiescent(manifest, target, expected_target=maintenance.runtime_target_binding(target),
                               expected_manifest=values['authentication']['manifest_digest'])


def resign(manifest: Path, values: dict):
    values.pop('authentication', None)
    digest = canonical_json_digest(values)
    (manifest.parent / 'manifest-auth.bin').write_bytes(protect_current_user(digest.encode(), entropy=backup._BACKUP_ENTROPY))
    values['authentication'] = {'file': 'manifest-auth.bin', 'manifest_digest': digest}
    manifest.write_text(json.dumps(values), encoding='utf-8')


def service(store, clock):
    return MiniAppCore(store=store, bot_token=BOT_TOKEN, owner_user_id=OWNER_ID, tenant_id='tenant-a', clock=clock)


def test_representative_encrypted_wal_restore_recovers_result_receipts_and_unknown(tmp_path, capsys):
    source, target = tmp_path / 'source', tmp_path / 'restored'
    store, queue, task, message = fixture_runtime(source, answer=True)
    clock = Clock(datetime.now(UTC))
    app = service(store, clock)
    grant = app.authenticate(signed_init_data(auth_date=clock.now))
    cancelled = MiniAppCancelledRequest(tenant_id='tenant-a', auth_context_ref=app._auth_context_ref, idempotency_key='synthetic-cancelled-c5')
    store.cancel_absent_miniapp_request(cancelled)
    envelope = app._task_envelope(app._session(grant.access_token), instruction='synthetic-only',
                                  idempotency_key='synthetic-unknown-c5', display_title=None)
    store.write_miniapp_request(MiniAppRequestRecord(envelope=envelope), claim=True)
    vault = DurableProductEffectVault(queue)
    pending = vault.issue(kind=ProductEffectKind.ARTIFACT, tenant_id='tenant-a', user_id=1, chat_id=1, payload={'synthetic': 'pending'})
    done = vault.issue(kind=ProductEffectKind.ARTIFACT, tenant_id='tenant-a', user_id=1, chat_id=1, payload={'synthetic': 'done'})
    vault.transition(vault.read(done, tenant_id='tenant-a', user_id=1, chat_id=1), state='completed', result={'receipt': 'synthetic-once'})
    delivery_clock = DeliveryClock()
    first = Sender(fail=1)
    asyncio.run(delivery_runtime(store, delivery_clock).deliver_pending('tenant-a', first))
    assert first.calls == [0, 1]
    accepted_at = datetime.now(UTC)
    with closing(sqlite3.connect(store._path, isolation_level=None)) as keeper:
        keeper.execute('PRAGMA wal_autocheckpoint=0')
        keeper.execute('BEGIN')
        keeper.execute('SELECT COUNT(*) FROM task_snapshots').fetchone()
        store.claim_miniapp_auth_replay('tenant-a', 'sha256:' + 'f' * 64,
                                       claimed_at=accepted_at, auth_expires_at=accepted_at + timedelta(minutes=5))
        assert store._path.with_name(store._path.name + '-wal').stat().st_size > 0
        start = time.perf_counter()
        manifest = backup._backup_quiescent(maintenance.runtime_database_paths(source), tmp_path / 'backup')
        backup_seconds = time.perf_counter() - start
    values = json.loads(manifest.read_text())
    assert len(values['files']) == 3 and values['schema_version'] == 3
    assert not list(manifest.parent.glob('*.sqlite3'))
    assert all(not (manifest.parent / (item['name'] + '.dpapi')).read_bytes().startswith(b'SQLite format') for item in values['files'])
    failure_at = datetime.now(UTC)
    start = time.perf_counter()
    safe_restore(manifest, target)
    restore_seconds = time.perf_counter() - start
    assert check(maintenance.runtime_database_paths(target))['status'] == 'PASS'
    reopened = SQLiteStore(target / 'task-runtime.sqlite3')
    assert reopened.read_task('tenant-a', task.id) == store.read_task('tenant-a', task.id)
    assert reopened.read_sealed_answer('tenant-a', task.id) == store.read_sealed_answer('tenant-a', task.id)
    assert reopened.read_task('other-tenant', task.id) is None
    assert reopened.read_miniapp_request('tenant-a', app._auth_context_ref, cancelled.idempotency_key) == cancelled
    assert reopened.read_miniapp_request('tenant-a', app._auth_context_ref, envelope.idempotency_key).state == 'pending'
    restored_vault = DurableProductEffectVault(SQLiteTelegramState(target / 'telegram-state.sqlite3'))
    assert restored_vault.read(pending, tenant_id='tenant-a', user_id=1, chat_id=1).state == 'unknown'
    assert restored_vault.read(done, tenant_id='tenant-a', user_id=1, chat_id=1).result == {'receipt': 'synthetic-once'}
    second = Sender()
    delivery_clock.advance(2)
    asyncio.run(delivery_runtime(reopened, delivery_clock).deliver_pending('tenant-a', second))
    assert second.calls == [1, 2]
    assert asyncio.run(delivery_runtime(reopened, delivery_clock).deliver_pending('tenant-a', second)) == ()
    restored_app = service(reopened, Clock(datetime.now(UTC)))
    with pytest.raises(MiniAppAuthenticationError):
        restored_app.recover_session(grant.recovery_token)
    with pytest.raises(MiniAppCoreUnavailableError):
        restored_app.authenticate(signed_init_data(auth_date=clock.now))
    receipt = {'check': 'c5_storage_drill', 'backup_seconds': round(backup_seconds, 6),
               'restore_and_validation_seconds': round(restore_seconds, 6),
               'snapshot_age_at_simulated_failure_seconds': round((failure_at - datetime.fromisoformat(values['created_at'])).total_seconds(), 6),
               'lost_accepted_tasks': 0, 'lost_confirmed_delivery_parts': 0,
               'repeated_confirmed_delivery_parts': 0, 'full_product_startup_rto_measured': False}
    print(json.dumps(receipt, sort_keys=True))


def test_restore_fence_rejects_consumed_post_snapshot_auth_and_exact_cutoff(tmp_path):
    source = tmp_path / 'source'
    store, _, _, _ = fixture_runtime(source)
    now = datetime.now(UTC)
    app = service(store, Clock(now))
    original = app.authenticate(signed_init_data(auth_date=now, query_id='before-backup'))
    manifest = backup._backup_quiescent(maintenance.runtime_database_paths(source), tmp_path / 'backup')
    post_snapshot = signed_init_data(auth_date=datetime.now(UTC), query_id='consumed-after-snapshot')
    app.authenticate(post_snapshot)
    target = tmp_path / 'target'
    safe_restore(manifest, target)
    restored = SQLiteStore(target / 'task-runtime.sqlite3')
    cutoff = restored.miniapp_restore_cutoff()
    assert cutoff is not None
    assert restored.restore_reconciliation_required()
    with pytest.raises(RuntimeError, match="owner reconciliation"):
        maintenance.assert_runtime_admission_ready(target)
    with pytest.raises(MiniAppCoreUnavailableError):
        service(restored, Clock(cutoff)).authenticate(post_snapshot)
    # Only this synthetic fixture simulates a separately completed owner review.
    # The shipped restore/startup code never clears the hold automatically.
    with sqlite3.connect(restored._path) as connection:
        connection.execute("UPDATE miniapp_restore_fence SET reconciliation_required=0 WHERE singleton=1")
    restored_app = service(restored, Clock(cutoff + timedelta(seconds=2)))
    for raw in (post_snapshot, signed_init_data(auth_date=cutoff, query_id='exact-cutoff')):
        with pytest.raises(MiniAppAuthenticationError):
            restored_app.authenticate(raw)
    with pytest.raises(MiniAppAuthenticationError):
        restored_app.recover_session(original.recovery_token)
    fresh = restored_app.authenticate(signed_init_data(auth_date=cutoff + timedelta(seconds=2), query_id='fresh-open'))
    assert restored_app.list_tasks(fresh.access_token) == ()


@pytest.mark.parametrize('mutation', ['corrupted', 'missing', 'wrong_version', 'wrong_target', 'no_space'])
def test_restore_rejects_bad_inputs_before_target_install(tmp_path, monkeypatch, mutation):
    source = tmp_path / 'source'
    fixture_runtime(source)
    manifest = backup._backup_quiescent(maintenance.runtime_database_paths(source), tmp_path / 'backup')
    values = json.loads(manifest.read_text())
    encrypted = manifest.parent / (values['files'][0]['name'] + '.dpapi')
    if mutation == 'corrupted':
        encrypted.write_bytes(encrypted.read_bytes() + b'synthetic-corruption')
    elif mutation == 'missing':
        encrypted.unlink()  # Exact new C5 fixture, inside this test's owner root.
    elif mutation == 'wrong_version':
        values['application']['code_digest'] = 'sha256:' + '0' * 64
        resign(manifest, values)
    elif mutation == 'no_space':
        monkeypatch.setattr(restore, 'require_free_space', lambda *args: (_ for _ in ()).throw(RuntimeError('runtime disk space insufficient')))
    target = tmp_path / 'target'
    with pytest.raises((ValueError, RuntimeError, OSError)):
        if mutation == 'wrong_target':
            restore._restore_quiescent(manifest, target, expected_target='sha256:' + '0' * 64,
                                       expected_manifest=values['authentication']['manifest_digest'])
        else:
            safe_restore(manifest, target)
    assert not any((target / name).exists() for name in maintenance.RUNTIME_DATABASE_NAMES)
    assert not (target / maintenance.JOURNAL_NAME).exists()


def test_new_accepted_watermark_refuses_rollback(tmp_path):
    source = tmp_path / 'source'
    store, _, _, _ = fixture_runtime(source)
    manifest = backup._backup_quiescent(maintenance.runtime_database_paths(source), tmp_path / 'backup')
    store.cancel_absent_miniapp_request(MiniAppCancelledRequest(tenant_id='owner', auth_context_ref='sha256:'+'a'*64, idempotency_key='new-c5-accepted-tombstone'))
    before = maintenance.database_state_digest(store._path)
    with pytest.raises(RuntimeError, match='reconciliation'):
        safe_restore(manifest, source)
    assert maintenance.database_state_digest(store._path) == before


@pytest.mark.parametrize('operation', ['backup', 'restore'])
def test_database_writer_lock_is_bounded_and_never_overwritten(tmp_path, operation):
    source = tmp_path / 'source'
    fixture_runtime(source)
    manifest = backup._backup_quiescent(maintenance.runtime_database_paths(source), tmp_path / 'backup')
    before = {p.name: maintenance.database_state_digest(p) for p in maintenance.runtime_database_paths(source)}
    with closing(sqlite3.connect(source / 'task-runtime.sqlite3', isolation_level=None)) as locked:
        locked.execute('BEGIN IMMEDIATE')
        start = time.perf_counter()
        with pytest.raises(sqlite3.OperationalError, match='locked'):
            if operation == 'backup':
                backup._backup_quiescent(maintenance.runtime_database_paths(source), tmp_path / 'second-backup')
            else:
                safe_restore(manifest, source)
        assert time.perf_counter() - start < 5
    assert {p.name: maintenance.database_state_digest(p) for p in maintenance.runtime_database_paths(source)} == before


def test_interrupted_install_uses_authenticated_originals_and_rolls_back(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    fixture_runtime(source, answer=True)
    manifest = backup._backup_quiescent(maintenance.runtime_database_paths(source), tmp_path / 'backup')
    before = {p.name: maintenance.database_state_digest(p) for p in maintenance.runtime_database_paths(source)}
    replace = restore.replace_durable
    calls = []
    def interrupt(current, target):
        calls.append(Path(target).name)
        if len(calls) == 2:
            raise OSError('synthetic C5 interruption')
        replace(current, target)
    monkeypatch.setattr(restore, 'replace_durable', interrupt)
    start = time.perf_counter()
    with pytest.raises(OSError, match='synthetic'):
        safe_restore(manifest, source)
    seconds = time.perf_counter() - start
    assert {p.name: maintenance.database_state_digest(p) for p in maintenance.runtime_database_paths(source)} == before
    assert not (source / maintenance.JOURNAL_NAME).exists()
    print(json.dumps({'check': 'c5_interruption_rollback', 'seconds': round(seconds, 6), 'lost_accepted_records': 0}))


def test_cleanup_scope_escape_and_failed_cleanup_are_visible(tmp_path, monkeypatch):
    root = tmp_path / 'owner'
    stage = root / 'restore-owned'
    stage.mkdir(parents=True)
    target = stage / 'task-runtime.sqlite3'
    target.write_bytes(b'synthetic')
    identity = (stage.stat().st_dev, stage.stat().st_ino)
    with pytest.raises(ValueError, match='unsafe'):
        maintenance.checked_path(root / '..' / 'foreign', root=root)
    foreign = stage / 'unowned.txt'
    foreign.write_bytes(b'preserve')
    with pytest.raises(RuntimeError, match='scope'):
        maintenance.cleanup_staging(root, stage, identity, {'task-runtime.sqlite3'})
    assert foreign.read_bytes() == b'preserve' and target.exists()
    foreign.unlink()
    original = Path.unlink
    def failure(path, *args, **kwargs):
        if path == target:
            raise PermissionError('synthetic cleanup denial')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', failure)
    with pytest.raises(PermissionError):
        maintenance.cleanup_staging(root, stage, identity, {'task-runtime.sqlite3'})
    assert target.exists()


def test_operator_view_and_retention_do_not_claim_running_or_ownership(tmp_path):
    source = tmp_path / 'source'
    fixture_runtime(source)
    result = operator_view(source)
    assert result['runtime'] == 'not_probed'
    assert result['backup_age_seconds'] is None and result['drill_age_seconds'] is None
    temp = tmp_path / 'temp'; temp.mkdir(); (temp / 'synthetic.tmp').write_bytes(b'x')
    view = retention_dry_run({'temp': temp})
    assert view['temp']['deleted'] == 0 and view['temp']['ownership'] == 'unresolved_no_deletion'
    assert (temp / 'synthetic.tmp').read_bytes() == b'x'


def test_process_crash_after_first_install_recovers_on_next_start(tmp_path):
    import subprocess
    import sys
    from scripts import run_nobus_space_live as supervisor
    from src.workers.windows_job import _Kernel32JobApi
    source = tmp_path / "source"
    fixture_runtime(source, answer=True)
    manifest = backup._backup_quiescent(maintenance.runtime_database_paths(source), tmp_path / "backup")
    before = {p.name: maintenance.database_state_digest(p) for p in maintenance.runtime_database_paths(source)}
    child = """
import os,sys,json
sys.stderr = sys.stdout
print(json.dumps({"child_started": True, "executable_is_venv": "venv" in sys.executable}), flush=True)
from pathlib import Path
try:
    from scripts import restore_telegram_runtime as r
    from src.application.runtime_maintenance import runtime_target_binding
except Exception as error:
    print(json.dumps({"import_error": type(error).__name__, "module": getattr(error, "name", None)}), flush=True)
    raise SystemExit(69)
manifest, runtime = map(Path, sys.argv[1:])
print(json.dumps({"child_imports": "ok", "executable_is_venv": "venv" in sys.executable}), flush=True)
replace = r.replace_durable
calls = 0
def crash(source, target):
    global calls
    calls += 1
    if calls == 2:
        os._exit(71)
    replace(source, target)
r.replace_durable = crash
try:
    r._restore_quiescent(manifest, runtime, expected_target=runtime_target_binding(runtime),
                        expected_manifest=json.loads(manifest.read_text())["authentication"]["manifest_digest"])
except Exception as error:
    print(json.dumps({"child_error_type": type(error).__name__, "static_error": str(error) if str(error) in {"backup application version mismatch", "restore target requires reconciliation", "backup manifest authentication failed"} else "redacted"}), flush=True)
    raise SystemExit(70)
"""
    api = _Kernel32JobApi()
    job = api.create_job(memory_limit_bytes=2 * 1024**3, active_process_limit=8)
    process = None
    start = time.perf_counter()
    try:
        with (tmp_path / "child-safe.log").open("wb") as diagnostic:
            process = supervisor.spawn_owned(api, job, [sys.executable, "-c", child, str(manifest), str(source)], stdout=diagnostic)
            exit_code = process.wait(timeout=30)
        assert exit_code == 71, " | ".join(line for line in (tmp_path / "child-safe.log").read_text().splitlines() if line.startswith(("{", "RuntimeError:", "ValueError:", "ModuleNotFoundError:", "ImportError:", "MemoryError", "SyntaxError:")))
        supervisor.close_owned(api, process)
        assert supervisor.wait_job_empty(job)
    finally:
        api.terminate(job)
        api.close(job)
    crash_seconds = time.perf_counter() - start
    assert (source / maintenance.JOURNAL_NAME).exists()
    start = time.perf_counter()
    assert maintenance.recover_interrupted_restore(source)
    recovery_seconds = time.perf_counter() - start
    assert {p.name: maintenance.database_state_digest(p) for p in maintenance.runtime_database_paths(source)} == before
    assert not maintenance.recover_interrupted_restore(source)
    assert not (source / maintenance.JOURNAL_NAME).exists()
    print(json.dumps({"check": "c5_actual_process_crash", "crash_process_seconds": round(crash_seconds, 6),
                      "startup_recovery_seconds": round(recovery_seconds, 6), "job_active_processes_after": 0,
                      "lost_accepted_records": 0, "full_product_startup_rto_measured": False}))


def test_tampered_authenticated_journal_never_changes_targets(tmp_path):
    root = tmp_path / "source"
    fixture_runtime(root)
    stage = root / "restore-fixture"
    stage.mkdir()
    names = {p.name for p in maintenance.runtime_database_paths(root)}
    for name in names:
        maintenance.copy_durable(root / name, stage / name)
        maintenance.copy_durable(root / name, stage / (name + ".previous"))
    maintenance.write_journal(root, maintenance.restore_journal_values(root, stage, names))
    journal = root / maintenance.JOURNAL_NAME
    envelope = json.loads(journal.read_text())
    envelope["payload"]["files"][0]["previous"] = None
    journal.write_text(json.dumps(envelope), encoding="utf-8")
    before = {p.name: maintenance.file_evidence(p) for p in maintenance.runtime_database_paths(root)}
    with pytest.raises(RuntimeError, match="recovery failed"):
        maintenance.recover_interrupted_restore(root)
    assert {p.name: maintenance.file_evidence(p) for p in maintenance.runtime_database_paths(root)} == before
    assert journal.exists()


def test_backup_capacity_and_mid_write_disk_full_fail_without_plaintext_residue(tmp_path, monkeypatch):
    import errno
    root = tmp_path / "source"
    fixture_runtime(root)
    with monkeypatch.context() as scoped:
        scoped.setattr(backup, "MAX_BACKUP_DATABASE_BYTES", 1)
        with pytest.raises(RuntimeError, match="size limit"):
            backup._backup_quiescent(maintenance.runtime_database_paths(root), tmp_path / "over-limit")
    original = backup.write_bytes_durable
    def disk_full(path, content):
        if path.name.endswith(".dpapi"):
            raise OSError(errno.ENOSPC, "synthetic disk full")
        return original(path, content)
    monkeypatch.setattr(backup, "write_bytes_durable", disk_full)
    destination = tmp_path / "full-disk"
    with pytest.raises(OSError) as error:
        backup._backup_quiescent(maintenance.runtime_database_paths(root), destination)
    assert error.value.errno == errno.ENOSPC
    assert not (destination / "manifest.json").exists()
    assert not list(destination.rglob("*.sqlite3"))
    assert check(maintenance.runtime_database_paths(root))["status"] == "PASS"


def test_read_connection_enables_sqlite_defensive_controls(tmp_path):
    root = tmp_path / "source"
    fixture_runtime(root)
    with closing(maintenance._read_connection(root / "task-runtime.sqlite3")) as connection:
        assert connection.getconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE)
        assert not connection.getconfig(sqlite3.SQLITE_DBCONFIG_TRUSTED_SCHEMA)


def test_artifact_cleanup_failure_reports_failure_without_mutating_sealed_result(tmp_path, monkeypatch):
    from src.transport.telegram.bot_api import _project_artifact, TelegramBotApiError
    source = tmp_path / "source"
    store, _, task, message = fixture_runtime(source, answer=True)
    before = maintenance.database_state_digest(store._path)
    directory = tmp_path / "artifacts"
    directory.mkdir()
    original = Path.unlink
    def deny_owned_temp(path, *args, **kwargs):
        if path.parent == directory and path.name.startswith(".nobus-"):
            raise PermissionError("synthetic cleanup failure")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", deny_owned_temp)
    with pytest.raises(TelegramBotApiError) as failure:
        _project_artifact(directory, "synthetic.txt", b"synthetic result")
    assert failure.value.code == "telegram_artifact_projection_failed"
    assert (directory / "synthetic.txt").read_bytes() == b"synthetic result"
    assert maintenance.database_state_digest(store._path) == before
    assert len(tuple(directory.glob(".nobus-*.tmp"))) == 1


def test_staging_cleanup_rejects_actual_hardlink_and_preserves_external_fixture(tmp_path):
    import os
    root = tmp_path / "root"
    stage = root / "restore-owned"
    stage.mkdir(parents=True)
    outside = tmp_path / "outside.sqlite3"
    outside.write_bytes(b"synthetic external fixture")
    os.link(outside, stage / "task-runtime.sqlite3")
    identity = (stage.stat().st_dev, stage.stat().st_ino)
    with pytest.raises((ValueError, RuntimeError)):
        maintenance.cleanup_staging(root, stage, identity, {"task-runtime.sqlite3"})
    assert outside.read_bytes() == b"synthetic external fixture"
    assert (stage / "task-runtime.sqlite3").exists()
