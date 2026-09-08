"""Owner-confirmed reopening after a proven quiescent, no-delta restore.

This is intentionally NOT a general UNKNOWN resolver. A later authenticated
snapshot of the ORIGINAL source must prove identical application data, with no
active jobs/effects/deliveries. Any delta stays on hold for manual investigation.
"""
from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

from src.application import runtime_maintenance as m
from src.application.durable_telegram_state import DpapiJsonCodec
from src.application.windows_singleton import WindowsNamedMutex
from src.contracts.models import canonical_json_digest
from src.transport.telegram.bindings import TelegramBindingConfig, load_telegram_bindings

TABLE_DDL = """CREATE TABLE runtime_reconciliations (
    recovery_id TEXT PRIMARY KEY,
    state TEXT NOT NULL CHECK(state IN ('pending','approved')),
    payload BLOB NOT NULL,
    payload_digest TEXT NOT NULL
)"""


def watermark(root):
    return {p.name: m.database_state_digest(p, exclude_reconciliation=True)
            for p in m.runtime_database_paths(root)}


def _write(db, recovery_id, state, payload):
    encoded = DpapiJsonCodec().encode(payload)
    db.execute('INSERT OR REPLACE INTO runtime_reconciliations VALUES (?,?,?,?)',
               (recovery_id, state, encoded, canonical_json_digest(payload)))


def bind_restore(staging, target, manifest):
    """Called on staging after authority invalidation, before atomic installation."""
    with closing(m._read_connection(staging / 'task-runtime.sqlite3')) as db:
        cutoff, hold = db.execute('SELECT auth_not_before,reconciliation_required FROM miniapp_restore_fence').fetchone()
    if hold != 1:
        raise ValueError('restore fence missing')
    payload = {'schema': 'c6-restore-reconciliation-1', 'target_binding': m.runtime_target_binding(target),
        'cutoff': cutoff, 'snapshot': manifest, 'restored_watermark': watermark(staging)}
    with closing(sqlite3.connect(staging / 'task-runtime.sqlite3')) as db:
        _write(db, str(uuid4()), 'pending', payload)
        db.commit()


def validate_records(db):
    for recovery_id, state, encoded, digest in db.execute('SELECT * FROM runtime_reconciliations'):
        payload = DpapiJsonCodec().decode(bytes(encoded))
        if (not re.fullmatch('[0-9a-f-]{36}', recovery_id) or state not in {'pending', 'approved'}
                or canonical_json_digest(payload) != digest
                or payload.get('schema') != 'c6-restore-reconciliation-1'
                or set(payload) != {'schema','target_binding','cutoff','snapshot','restored_watermark'} | ({'decision'} if state=='approved' else set())):
            raise ValueError('reconciliation record invalid')


def _current(root):
    with closing(m._read_connection(root / 'task-runtime.sqlite3')) as db:
        validate_records(db)
        fence = db.execute('SELECT auth_not_before,reconciliation_required FROM miniapp_restore_fence').fetchone()
        if fence is None or fence[1] != 1:
            raise ValueError('no pending restore fence')
        matches = []
        for recovery_id, encoded in db.execute("SELECT recovery_id,payload FROM runtime_reconciliations WHERE state='pending'"):
            payload = DpapiJsonCodec().decode(bytes(encoded))
            if payload['cutoff'] == fence[0] and payload['target_binding'] == m.runtime_target_binding(root):
                matches.append((recovery_id, payload))
        if len(matches) != 1:
            raise ValueError('restore context ambiguous')
        return matches[0]


def _settled(root):
    with closing(m._read_connection(root / 'telegram-state.sqlite3')) as db:
        if db.execute('SELECT count(*) FROM telegram_jobs').fetchone()[0]:
            raise ValueError('jobs require operator reconciliation')
        for encoded, in db.execute('SELECT payload FROM telegram_capabilities'):
            payload = DpapiJsonCodec().decode(bytes(encoded))
            if payload.get('state') not in {'completed','delivered'}:
                raise ValueError('effects require operator reconciliation')
    with closing(m._read_connection(root / 'task-runtime.sqlite3')) as db:
        if db.execute("SELECT count(*) FROM outbox_messages WHERE status!='acked'").fetchone()[0]:
            raise ValueError('delivery requires operator reconciliation')
        if any(json.loads(row[0]).get('status') not in {'answered','completed','failed','rejected'}
               for row in db.execute('SELECT projection_json FROM task_snapshots')):
            raise ValueError('task requires operator reconciliation')


def owner_binding(path):
    path = m.checked_path(path)
    if path.stat().st_size > 65536:
        raise ValueError('owner binding invalid')
    config = TelegramBindingConfig.model_validate_json(path.read_bytes())
    load_telegram_bindings(path, expected_bot_id=config.bot_id, expected_bot_username='Nobusspacebot',
        expected_tenant_id='owner', expected_actor_identity='telegram:owner', expected_role='owner')
    owners = [v for v in config.bindings if v.purpose == 'owner_private']
    if len(owners) != 1:
        raise ValueError('owner binding ambiguous')
    owner = owners[0]
    if (owner.user_id != owner.chat_id or owner.user_id <= 0 or owner.tenant_id != 'owner'
            or owner.actor_identity != 'telegram:owner' or owner.role != 'owner'):
        raise ValueError('private owner binding invalid')
    return canonical_json_digest(config.model_dump(mode='json'))


def prepare(root: Path, evidence_manifest: Path, binding: Path, *, original_runtime: Path):
    from scripts.restore_telegram_runtime import _verified_manifest
    root = m.checked_path(root)
    m.validate_runtime_set(root)
    recovery_id, payload = _current(root)
    observed = watermark(root)
    if payload['restored_watermark'] != observed:
        raise ValueError('restored data changed since hold')
    _settled(root)
    later = _verified_manifest(evidence_manifest)
    snapshot = payload['snapshot']
    if (later['source_binding'] != snapshot['source_binding']
            or datetime.fromisoformat(later['created_at']) < datetime.fromisoformat(payload['cutoff'])
            or later['authentication']['manifest_digest'] == snapshot['authentication']['manifest_digest']
            or datetime.fromisoformat(later['created_at']) > datetime.now(UTC) + timedelta(seconds=30)
            or {x['name']: x['state_digest'] for x in later['files']} != {x['name']: x['state_digest'] for x in snapshot['files']}):
        raise ValueError('post-snapshot change requires operator reconciliation')
    original_runtime = m.checked_path(original_runtime)
    if (original_runtime == root or original_runtime.is_relative_to(root) or root.is_relative_to(original_runtime)
            or m.runtime_target_binding(original_runtime) != snapshot['source_binding']):
        raise ValueError('original runtime binding mismatch')
    m.validate_runtime_set(original_runtime)
    _settled(original_runtime)
    original_watermark = {p.name: m.database_state_digest(p) for p in m.runtime_database_paths(original_runtime)}
    if original_watermark != {x['name']: x['state_digest'] for x in snapshot['files']}:
        raise ValueError('original source changed after evidence snapshot')
    return {'schema': 'c6-reopen-plan-1', 'recovery_id': recovery_id,
        'original_binding': snapshot['source_binding'], 'original_watermark': original_watermark,
        'target_binding': m.runtime_target_binding(root), 'watermark': observed,
        'restore_payload_digest': canonical_json_digest(payload), 'owner_binding': owner_binding(binding),
        'evidence_manifest_digest': later['authentication']['manifest_digest'],
        'snapshot_manifest_digest': snapshot['authentication']['manifest_digest'],
        'expires_at': (datetime.now(UTC) + timedelta(minutes=15)).isoformat()}


def approve(root: Path, evidence_manifest: Path, binding: Path, plan: dict, *, original_runtime: Path, confirmation: str):
    if canonical_json_digest(plan) != confirmation:
        raise ValueError('exact owner confirmation required')
    expires = datetime.fromisoformat(plan['expires_at'])
    if expires.tzinfo is None or not datetime.now(UTC) < expires <= datetime.now(UTC) + timedelta(minutes=15):
        raise ValueError('operator plan expired')
    with WindowsNamedMutex():
        root = m.checked_path(root)
        original_runtime = m.checked_path(original_runtime)
        if original_runtime == root or original_runtime.is_relative_to(root) or root.is_relative_to(original_runtime):
            raise ValueError('separate original runtime required')
        paths = tuple(p for p in m.runtime_database_paths(root) if p.name != 'task-runtime.sqlite3')
        paths += m.runtime_database_paths(original_runtime)
        with m.lock_runtime_databases(paths):
            with closing(sqlite3.connect(root / 'task-runtime.sqlite3', isolation_level=None, timeout=1)) as db:
                db.execute('BEGIN IMMEDIATE')
                try:
                    fresh = prepare(root, evidence_manifest, binding, original_runtime=original_runtime)
                    fresh['expires_at'] = plan['expires_at']
                    if fresh != plan:
                        raise ValueError('operator plan changed')
                    recovery_id, payload = _current(root)
                    updated = db.execute('UPDATE miniapp_restore_fence SET reconciliation_required=0 WHERE singleton=1 AND auth_not_before=? AND reconciliation_required=1', (payload['cutoff'],))
                    if updated.rowcount != 1:
                        raise ValueError('restore fence changed')
                    payload['decision'] = {'owner_binding': plan['owner_binding'], 'confirmation': confirmation,
                        'original_binding': plan['original_binding'], 'original_watermark': plan['original_watermark'],
                        'evidence_manifest_digest': plan['evidence_manifest_digest'], 'approved_at': datetime.now(UTC).isoformat()}
                    _write(db, recovery_id, 'approved', payload)
                    db.commit()
                except BaseException:
                    db.rollback()
                    raise
    return {'status': 'PASS', 'recovery_id': recovery_id, 'receipt_digest': canonical_json_digest(payload)}
