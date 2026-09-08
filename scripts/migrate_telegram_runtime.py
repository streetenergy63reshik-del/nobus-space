"""Stage the exact stopped v1.0.1 stores into a NEW C6 root; preserve source.

This deliberately accepts only terminal legacy tasks, fully ACKed outbox and
an empty queue/capability set. Other histories need a separate reconciliation.
The operator creates a private destination parent before invoking this CLI.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application.runtime_maintenance import (
    EXPECTED_SCHEMA_DIGESTS, _ddl_digest, checked_path, file_evidence,
    protect_backup, unprotect_backup, runtime_database_paths, runtime_target_binding,
    validate_runtime_set, write_bytes_durable,
)
from src.application.windows_singleton import WindowsNamedMutex
from src.application.durable_telegram_state import SQLiteTelegramState
from src.storage.sqlite_store import SQLiteStore
from src.contracts.models import canonical_json_digest
from src.security.dpapi import protect_current_user, unprotect_current_user

LEGACY_REVISION = 'f5a9119cc0aa1bcce735a3c608f9751747002694'
ENTROPY = b'nobus-space:legacy-migration-snapshot:v1'
LEGACY_SCHEMA = {name: dict(items) for name, items in EXPECTED_SCHEMA_DIGESTS.items()}
for name in ('miniapp_requests', 'miniapp_restore_fence', 'miniapp_session_recovery',
             'outbox_delivery_parts', 'sealed_answers', 'runtime_reconciliations'):
    del LEGACY_SCHEMA['task-runtime.sqlite3']['table:' + name]
for name in ('index:idx_semantic_clarification_expiry', 'table:semantic_clarifications'):
    del LEGACY_SCHEMA['telegram-state.sqlite3'][name]
LEGACY_SCHEMA['telegram-state.sqlite3']['table:telegram_jobs'] = (
    '125b252ef8a4ee7e6954813e81e51edea1feee986bf6c308ba6eabe048062dc8')


def _read(path: Path):
    path = checked_path(path)
    wal = path.with_name(path.name + '-wal')
    if wal.exists() and wal.stat().st_size:
        raise ValueError('migration requires a stopped checkpointed source')
    db = sqlite3.connect(path.as_uri() + '?immutable=1', uri=True)
    db.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
    db.setconfig(sqlite3.SQLITE_DBCONFIG_TRUSTED_SCHEMA, False)
    return db


def _rows(db):
    result = {}
    for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        if not re.fullmatch('[a-z_]+', name):
            raise ValueError('invalid migration schema')
        columns = len(db.execute(f'SELECT * FROM "{name}" LIMIT 0').description)
        digest = hashlib.sha256()
        count = 0
        order = ','.join(str(i + 1) for i in range(columns))
        for row in db.execute(f'SELECT * FROM "{name}" ORDER BY {order}'):
            digest.update(json.dumps([{'blob': hashlib.sha256(x).hexdigest()} if isinstance(x, bytes)
                else x for x in row], ensure_ascii=True, separators=(',', ':')).encode() + b'\n')
            count += 1
        result[name] = {'count': count, 'digest': digest.hexdigest()}
    return result


def inspect_legacy(source: Path):
    files, rows = {}, {}
    for path in runtime_database_paths(source):
        before = file_evidence(path)
        if before is None:
            raise ValueError('legacy database missing')
        with closing(_read(path)) as db:
            schema = {f'{t}:{n}': _ddl_digest(s or '') for t, n, s in db.execute(
                "SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
            if schema != LEGACY_SCHEMA[path.name]:
                raise ValueError('unsupported legacy schema')
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise ValueError('legacy integrity failed')
            rows[path.name] = _rows(db)
            if path.name == 'telegram-state.sqlite3' and any(v['count'] for v in rows[path.name].values()):
                raise ValueError('legacy queue or capabilities require reconciliation')
            if path.name == 'task-runtime.sqlite3':
                if any(json.loads(row[0]).get('status') not in {'answered', 'completed', 'failed', 'rejected'}
                       for row in db.execute('SELECT projection_json FROM task_snapshots')):
                    raise ValueError('legacy task requires reconciliation')
                if db.execute("SELECT count(*) FROM outbox_messages WHERE status!='acked'").fetchone()[0]:
                    raise ValueError('legacy delivery requires reconciliation')
        if before != file_evidence(path):
            raise ValueError('legacy source changed')
        files[path.name] = before
    return {'files': files, 'rows': rows, 'source_binding': runtime_target_binding(source)}


def stage(source: Path, destination: Path, *, expected_source: str, expected_target: str):
    source, destination = checked_path(source), checked_path(destination)
    if destination.exists() or source == destination or source.is_relative_to(destination) or destination.is_relative_to(source):
        raise ValueError('migration requires a separate new destination')
    if not destination.parent.is_dir() or expected_target != runtime_target_binding(destination):
        raise ValueError('migration target mismatch')
    with WindowsNamedMutex():
        before = inspect_legacy(source)
        if canonical_json_digest(before) != expected_source:
            raise ValueError('migration source watermark mismatch')
        destination.mkdir()
        originals = destination / 'legacy-snapshot'
        originals.mkdir()
        migrated = destination / 'state'
        migrated.mkdir()
        # A failed stage leaves this marker; admission must never target it.
        write_bytes_durable(destination / 'INCOMPLETE', b'migration incomplete\n')
        encrypted = {}
        for name, evidence in before['files'].items():
            data = (source / name).read_bytes()
            if hashlib.sha256(data).hexdigest() != evidence['sha256']:
                raise ValueError('migration source changed')
            encoded = protect_backup(data)
            write_bytes_durable(originals / (name + '.dpapi'), encoded)
            restored = unprotect_backup(encoded)
            if restored != data:
                raise ValueError('legacy snapshot decrypt mismatch')
            write_bytes_durable(migrated / name, restored)
            encrypted[name] = file_evidence(originals / (name + '.dpapi'))
        snapshot = {'schema': 'c6-legacy-snapshot-1', 'source_revision': LEGACY_REVISION,
            'source': before, 'encrypted': encrypted, 'created_at': datetime.now(UTC).isoformat()}
        blob = json.dumps(snapshot, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode()
        write_bytes_durable(originals / 'manifest.dpapi', protect_current_user(blob, entropy=ENTROPY))
        if unprotect_current_user((originals / 'manifest.dpapi').read_bytes(), entropy=ENTROPY) != blob:
            raise ValueError('legacy snapshot authentication failed')
        SQLiteStore(migrated / 'task-runtime.sqlite3')
        SQLiteTelegramState(migrated / 'telegram-state.sqlite3')
        validate_runtime_set(migrated)
        for path in runtime_database_paths(migrated):
            with closing(sqlite3.connect(path)) as db:
                if db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0]:
                    raise ValueError('migration target busy')
            with closing(_read(path)) as db:
                after = _rows(db)
            if any(after.get(table) != value for table, value in before['rows'][path.name].items()):
                raise ValueError('migration lost or changed retained rows')
        # Fresh authentication is required. This is a forward schema migration,
        # not restoration from an older point in time; no recovery hold is cleared.
        with closing(sqlite3.connect(migrated / 'task-runtime.sqlite3')) as db:
            db.execute('INSERT INTO miniapp_restore_fence VALUES (1, ?, 0)', (datetime.now(UTC).isoformat(),))
            db.commit()
        validate_runtime_set(migrated)
        if inspect_legacy(source) != before:
            raise ValueError('migration source changed')
        receipt = {'schema': 'c6-migration-1', 'status': 'PASS', 'source_watermark': expected_source,
            'target_binding': expected_target, 'state_binding': runtime_target_binding(migrated),
            'snapshot_digest': canonical_json_digest(snapshot), 'source_unchanged': True,
            'preserved_rows': before['rows'], 'created_at': datetime.now(UTC).isoformat()}
        write_bytes_durable(destination / 'receipt.dpapi', protect_current_user(
            json.dumps(receipt, sort_keys=True).encode(), entropy=ENTROPY))
        # Immutable PASS receipt supersedes the retained INCOMPLETE marker. No
        # production start is performed by this tool; activation verifies receipt.
        return receipt


def restore_legacy_snapshot(snapshot_root: Path, destination: Path, *, expected_snapshot: str, expected_target: str):
    """Rehydrate exact original bytes into a NEW private root, never live data."""
    snapshot_root, destination = checked_path(snapshot_root), checked_path(destination)
    if (destination.exists() or not destination.parent.is_dir()
            or destination.is_relative_to(snapshot_root) or snapshot_root.is_relative_to(destination)
            or runtime_target_binding(destination) != expected_target):
        raise ValueError('legacy restore requires a separate new target')
    manifest_path = checked_path(snapshot_root / 'manifest.dpapi', root=snapshot_root)
    if manifest_path.stat().st_size > 65536:
        raise ValueError('legacy manifest too large')
    snapshot = json.loads(unprotect_current_user(manifest_path.read_bytes(), entropy=ENTROPY))
    if (canonical_json_digest(snapshot) != expected_snapshot
            or set(snapshot) != {'schema','source_revision','source','encrypted','created_at'}
            or snapshot['schema'] != 'c6-legacy-snapshot-1' or snapshot['source_revision'] != LEGACY_REVISION
            or set(snapshot['source']) != {'files','rows','source_binding'}
            or set(snapshot['encrypted']) != set(snapshot['source']['files'])
            or set(snapshot['encrypted']) != set(snapshot['source']['rows'])
            or not {'task-runtime.sqlite3','telegram-state.sqlite3','telegram-checkpoint.sqlite3'} <= set(snapshot['encrypted'])
            or not set(snapshot['encrypted']) <= set(LEGACY_SCHEMA)):
        raise ValueError('legacy snapshot binding invalid')
    with WindowsNamedMutex():
        # Authenticate and decrypt every member before creating a destination.
        original = {}
        for name, evidence in snapshot['encrypted'].items():
            path = checked_path(snapshot_root / (name + '.dpapi'), root=snapshot_root)
            if file_evidence(path) != evidence:
                raise ValueError('legacy snapshot member changed')
            data = unprotect_backup(path.read_bytes())
            source_evidence = snapshot['source']['files'][name]
            if hashlib.sha256(data).hexdigest() != source_evidence['sha256'] or len(data) != source_evidence['bytes']:
                raise ValueError('legacy snapshot content mismatch')
            original[name] = data
        destination.mkdir()
        for name, data in original.items():
            write_bytes_durable(destination / name, data)
        restored = inspect_legacy(destination)
        if restored['files'] != snapshot['source']['files'] or restored['rows'] != snapshot['source']['rows']:
            raise ValueError('legacy restore validation failed')
        return {'status':'PASS','source_revision':LEGACY_REVISION,'snapshot_digest':expected_snapshot,
            'target_binding':expected_target,'exact_original_bytes':True,'rows':restored['rows']}


def main():
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--source', type=Path)
    source.add_argument('--restore-snapshot', type=Path)
    parser.add_argument('--snapshot-digest')
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--source-watermark')
    parser.add_argument('--target-binding')
    args = parser.parse_args()
    try:
        if args.restore_snapshot is not None:
            if args.destination is None:
                raise ValueError('new restore destination required')
            result = restore_legacy_snapshot(args.restore_snapshot, args.destination,
                expected_snapshot=args.snapshot_digest, expected_target=args.target_binding)
            print(json.dumps(result, ensure_ascii=True, separators=(',', ':')))
            return 0
        revision = subprocess.run(['git', '-C', str(args.source.parent), 'rev-parse', 'HEAD'],
            capture_output=True, check=True, timeout=10).stdout.decode().strip()
        if revision != LEGACY_REVISION:
            raise ValueError('legacy revision mismatch')
        if args.destination is None:
            value = inspect_legacy(args.source)
            result = {'status': 'PASS', 'source_watermark': canonical_json_digest(value), 'rows': value['rows']}
        else:
            result = stage(args.source, args.destination, expected_source=args.source_watermark,
                           expected_target=args.target_binding)
    except Exception:
        print('{"status":"FAIL","code":"migration_unavailable_reconcile_required"}')
        return 1
    print(json.dumps(result, ensure_ascii=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
