"""Retention of exact owned generations by reversible quarantine, never deletion."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from src.application import runtime_maintenance as m
from src.application.durable_telegram_state import DpapiJsonCodec
from src.contracts.models import canonical_json_digest

CODEC = DpapiJsonCodec()
GENERATION = re.compile(r'^(daily|prechange)-[0-9]{8}T[0-9]{6}-[0-9a-f]{32}$')


def _certificate(path):
    path = m.checked_path(path)
    if path.stat().st_size > 65536:
        raise ValueError('backup ownership invalid')
    return CODEC.decode(path.read_bytes())


def initialize(root: Path, runtime: Path, owner: str):
    root = m.checked_path(root)
    if root.exists() or not re.fullmatch('sha256:[0-9a-f]{64}', owner):
        raise ValueError('new managed backup root required')
    root.mkdir()
    value = {'schema': 'c6-backup-root-1', 'root_binding': m.runtime_target_binding(root),
        'runtime_binding': m.runtime_target_binding(runtime), 'owner_binding': owner}
    m.write_bytes_durable(root/'ownership.dpapi', CODEC.encode(value))
    return canonical_json_digest(value)


def owned_root(root: Path, expected: str):
    root = m.checked_path(root)
    value = _certificate(root/'ownership.dpapi')
    if (set(value) != {'schema','root_binding','runtime_binding','owner_binding'}
            or value['schema'] != 'c6-backup-root-1'
            or value['root_binding'] != m.runtime_target_binding(root)
            or canonical_json_digest(value) != expected):
        raise ValueError('backup root ownership mismatch')
    return value


def verify_backup(manifest):
    from scripts.restore_telegram_runtime import _verified_manifest
    values = _verified_manifest(manifest)
    for item in values['files']:
        path = m.checked_path(manifest.parent/(item['name']+'.dpapi'))
        if m.file_evidence(path) != {'bytes':item['bytes'],'sha256':item['sha256']}:
            raise ValueError('backup ciphertext mismatch')
        plain=m.unprotect_backup(path.read_bytes())
        if len(plain)!=item['plaintext_bytes'] or hashlib.sha256(plain).hexdigest()!=item['plaintext_sha256']:
            raise ValueError('backup plaintext mismatch')
    return values


def create_generation(root: Path, runtime: Path, expected: str, *, kind='daily', now=None):
    from scripts.backup_telegram_runtime import backup
    value = owned_root(root, expected)
    if value['runtime_binding'] != m.runtime_target_binding(runtime) or kind not in {'daily','prechange'}:
        raise ValueError('backup generation target mismatch')
    now = now or datetime.now().astimezone()
    if now.tzinfo is None:
        raise ValueError('backup timezone required')
    generation=root/(kind+'-'+now.strftime('%Y%m%dT%H%M%S')+'-'+uuid4().hex)
    manifest=backup(m.runtime_database_paths(runtime),generation)
    values=verify_backup(manifest)
    if values['source_binding'] != value['runtime_binding']:
        raise ValueError('backup source mismatch')
    entries={p.name:m.file_evidence(p) for p in generation.iterdir()}
    certificate={'schema':'c6-backup-generation-1','root_ownership':expected,'name':generation.name,
        'identity':[generation.stat().st_dev,generation.stat().st_ino],
        'local_time':now.isoformat(),'files':entries,
        'manifest_digest':values['authentication']['manifest_digest']}
    m.write_bytes_durable(generation/'generation.dpapi',CODEC.encode(certificate))
    latest={'schema':'c6-latest-backup-1','root_ownership':expected,'name':generation.name,
        'manifest_digest':values['authentication']['manifest_digest']}
    temporary=root/('latest-'+uuid4().hex+'.dpapi')
    m.write_bytes_durable(temporary,CODEC.encode(latest))
    os.replace(temporary,m.checked_path(root/'latest.dpapi',root=root))
    return generation


def latest_manifest(root: Path, expected: str, runtime: Path):
    from scripts.restore_telegram_runtime import _verified_manifest
    owner=owned_root(root,expected)
    if owner['runtime_binding']!=m.runtime_target_binding(runtime):
        raise ValueError('backup runtime binding mismatch')
    pointer=_certificate(root/'latest.dpapi')
    if (set(pointer)!={'schema','root_ownership','name','manifest_digest'}
            or pointer['schema']!='c6-latest-backup-1' or pointer['root_ownership']!=expected
            or not isinstance(pointer['name'],str) or not GENERATION.fullmatch(pointer['name'])):
        raise ValueError('latest backup pointer invalid')
    generation=root/pointer['name']
    certificate=_generation(root,generation,expected)
    path=generation/'manifest.json'
    manifest=_verified_manifest(path)
    if (manifest['source_binding']!=owner['runtime_binding']
            or manifest['authentication']['manifest_digest']!=pointer['manifest_digest']
            or certificate['manifest_digest']!=pointer['manifest_digest']):
        raise ValueError('latest backup binding mismatch')
    return path


def assert_recent(root: Path, expected: str, runtime: Path):
    import shutil
    if shutil.disk_usage(m.checked_path(runtime)).free<256*1024*1024:
        raise RuntimeError('admission stopped for disk capacity')
    path=latest_manifest(root,expected,runtime)
    created=datetime.fromisoformat(json.loads(path.read_text())['created_at'])
    age=(datetime.now().astimezone()-created).total_seconds()
    if not 0<=age<=24*3600:
        raise RuntimeError('admission stopped for backup freshness')


def _generation(root, path, expected):
    path=m.checked_path(path,root=root)
    if not path.is_dir() or not GENERATION.fullmatch(path.name):
        raise ValueError('unmanaged backup generation')
    value=_certificate(path/'generation.dpapi')
    if (set(value)!={'schema','root_ownership','name','identity','local_time','files','manifest_digest'}
            or value['schema']!='c6-backup-generation-1' or value['root_ownership']!=expected
            or value['name']!=path.name or value['identity']!=[path.stat().st_dev,path.stat().st_ino]):
        raise ValueError('backup generation ownership mismatch')
    names=set(value['files'])
    if {p.name for p in path.iterdir()}!=names|{'generation.dpapi'}:
        raise ValueError('backup generation contains unowned files')
    for name in names:
        if Path(name).name!=name or m.file_evidence(m.checked_path(path/name,root=path))!=value['files'][name]:
            raise ValueError('backup generation file changed')
    stamp=datetime.fromisoformat(value['local_time'])
    if stamp.tzinfo is None:
        raise ValueError('backup generation timezone missing')
    return value


def retained_names(generations):
    """Newest generation on each of seven days and each of four ISO weeks."""
    days,weeks={},{}
    for item in sorted(generations,key=lambda x:(x['local_time'],x['name']),reverse=True):
        stamp=datetime.fromisoformat(item['local_time'])
        day=stamp.date().isoformat()
        week=stamp.isocalendar()[:2]
        days.setdefault(day,item['name'])
        weeks.setdefault(week,item['name'])
    return set(list(days.values())[:7]) | set(list(weeks.values())[:4])


def retention(root: Path, expected: str, *, apply=False):
    owned_root(root,expected)
    candidates=[]
    # Only direct children of this dedicated owned root. Previous/unowned backups
    # are not adopted by name. Incomplete generations stop retention for inspection.
    entries=list(root.iterdir())
    if len(entries)>128:
        raise ValueError('backup inventory bound exceeded')
    for path in entries:
        if path.name in {'ownership.dpapi','latest.dpapi','quarantine'}:
            m.checked_path(path,root=root)
            continue
        candidates.append(_generation(root,path,expected))
    keep=retained_names(candidates)
    selected=[x for x in candidates if x['name'] not in keep]
    if apply and selected:
        quarantine=m.checked_path(root/'quarantine',root=root)
        quarantine.mkdir(exist_ok=True)
        for item in selected:
            source=m.checked_path(root/item['name'],root=root)
            target=m.checked_path(quarantine/item['name'],root=quarantine)
            if target.exists() or _generation(root,source,expected)!=item:
                raise ValueError('retention target changed')
            # Exact fully enumerated new managed generation; reversible, no delete.
            os.rename(source,target)
            if [target.stat().st_dev,target.stat().st_ino]!=item['identity']:
                raise ValueError('quarantine identity mismatch')
    return {'kept':sorted(keep),'selected':[x['name'] for x in selected],
            'quarantined':len(selected) if apply else 0,'deleted':0}
