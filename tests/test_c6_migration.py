from contextlib import closing
from pathlib import Path
import sqlite3

import pytest

from scripts import migrate_telegram_runtime as migration
from src.application.runtime_maintenance import runtime_database_paths, runtime_target_binding, validate_runtime_set
from src.contracts.models import canonical_json_digest
from tests.test_c5_backup_recovery import fixture_runtime


LEGACY_JOB = """CREATE TABLE telegram_jobs (
 job_id TEXT PRIMARY KEY,
 kind TEXT NOT NULL CHECK( kind IN ('draft','miniapp_draft','patch','effect') ),
 tenant_id TEXT NOT NULL, task_id TEXT NOT NULL, binding_digest TEXT NOT NULL,
 payload_digest TEXT NOT NULL, payload BLOB NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('pending','leased','failed')),
 attempt_count INTEGER NOT NULL CHECK(attempt_count>=0), failure_code TEXT,
 lease_id TEXT, lease_owner TEXT, lease_expires_at TEXT,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(tenant_id,task_id,kind) )"""


def legacy(root):
    fixture_runtime(root)
    with closing(sqlite3.connect(root / 'task-runtime.sqlite3')) as db:
        for name in ('miniapp_requests','miniapp_restore_fence','miniapp_session_recovery',
                     'outbox_delivery_parts','sealed_answers','runtime_reconciliations'):
            db.execute('DROP TABLE '+name)
        db.commit()
    with closing(sqlite3.connect(root / 'telegram-state.sqlite3')) as db:
        db.execute('DROP TABLE semantic_clarifications')
        db.execute('DROP TABLE telegram_jobs')
        db.execute(LEGACY_JOB)
        db.execute('CREATE INDEX idx_telegram_jobs_ready ON telegram_jobs(status,created_at)')
        db.commit()
    for path in runtime_database_paths(root):
        with closing(sqlite3.connect(path)) as db:
            db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    return root


def run(source, dest):
    return migration.stage(source,dest,
        expected_source=canonical_json_digest(migration.inspect_legacy(source)),
        expected_target=runtime_target_binding(dest))


def test_preserves_exact_legacy_rows_and_sets_fresh_auth_cutoff(tmp_path):
    source=legacy(tmp_path/'source')
    before=migration.inspect_legacy(source)
    result=run(source,tmp_path/'candidate')
    assert result['source_unchanged']
    assert migration.inspect_legacy(source)==before
    validate_runtime_set(tmp_path/'candidate/state')
    with closing(sqlite3.connect(tmp_path/'candidate/state/task-runtime.sqlite3')) as db:
        cutoff,hold=db.execute('SELECT auth_not_before,reconciliation_required FROM miniapp_restore_fence').fetchone()
        assert cutoff and hold==0
    assert (tmp_path/'candidate/legacy-snapshot/manifest.dpapi').is_file()
    assert not list((tmp_path/'candidate/legacy-snapshot').glob('*.sqlite3'))
    with pytest.raises(ValueError):
        run(source,tmp_path/'candidate')


@pytest.mark.parametrize('what',['source','target'])
def test_wrong_binding_has_no_destination_side_effect(tmp_path,what):
    source=legacy(tmp_path/'source')
    target=tmp_path/'candidate'
    with pytest.raises(ValueError):
        migration.stage(source,target,
            expected_source='sha256:'+'0'*64 if what=='source' else canonical_json_digest(migration.inspect_legacy(source)),
            expected_target='sha256:'+'0'*64 if what=='target' else runtime_target_binding(target))
    assert not target.exists()


def test_unexpected_schema_and_nonempty_wal_fail_before_copy(tmp_path):
    source=legacy(tmp_path/'source')
    wal=source/'task-runtime.sqlite3-wal'
    wal.write_bytes(b'unknown-wal')
    with pytest.raises(ValueError):
        migration.inspect_legacy(source)
    wal.write_bytes(b'')
    with closing(sqlite3.connect(source/'telegram-state.sqlite3')) as db:
        db.execute('CREATE TABLE unexpected (value TEXT)')
        db.commit()
    with pytest.raises(ValueError):
        migration.inspect_legacy(source)


def test_copy_corruption_never_produces_pass_receipt(tmp_path,monkeypatch):
    source=legacy(tmp_path/'source')
    monkeypatch.setattr(migration,'unprotect_backup',lambda x:b'wrong')
    with pytest.raises(ValueError):
        run(source,tmp_path/'candidate')
    assert not (tmp_path/'candidate/receipt.dpapi').exists()
    assert migration.inspect_legacy(source)


def test_original_snapshot_restores_exact_bytes_only_to_new_bound_target(tmp_path):
    source=legacy(tmp_path/'source')
    result=run(source,tmp_path/'candidate')
    target=tmp_path/'old-version-recovery'
    receipt=migration.restore_legacy_snapshot(tmp_path/'candidate/legacy-snapshot',target,
        expected_snapshot=result['snapshot_digest'],expected_target=runtime_target_binding(target))
    assert receipt['exact_original_bytes']
    assert migration.inspect_legacy(target)['files']==migration.inspect_legacy(source)['files']
    with pytest.raises(ValueError):
        migration.restore_legacy_snapshot(tmp_path/'candidate/legacy-snapshot',target,
            expected_snapshot=result['snapshot_digest'],expected_target=runtime_target_binding(target))
    wrong=tmp_path/'wrong'
    with pytest.raises(ValueError):
        migration.restore_legacy_snapshot(tmp_path/'candidate/legacy-snapshot',wrong,
            expected_snapshot='sha256:'+'0'*64,expected_target=runtime_target_binding(wrong))
    assert not wrong.exists()
    member=tmp_path/'candidate/legacy-snapshot/task-runtime.sqlite3.dpapi'
    member.write_bytes(member.read_bytes()+b'corrupted')
    with pytest.raises(ValueError):
        migration.restore_legacy_snapshot(tmp_path/'candidate/legacy-snapshot',wrong,
            expected_snapshot=result['snapshot_digest'],expected_target=runtime_target_binding(wrong))
    assert not wrong.exists()
