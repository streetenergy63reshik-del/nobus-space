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
MAX_QUARANTINE_ENTRIES = 64
MAX_QUARANTINE_BYTES = 2*1024*1024*1024
MAX_GENERATION_BYTES = 768*1024*1024
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


def _identity(path):
    info=m.checked_path(path).stat()
    return [info.st_dev,info.st_ino]


def hold_admission(root, expected):
    owned_root(root,expected)
    path=m.checked_path(root/'admission-hold',root=root)
    if not path.exists():
        m.write_bytes_durable(path,b'')
    elif m.file_evidence(path)!={'bytes':0,'sha256':hashlib.sha256(b'').hexdigest()}:
        raise ValueError('admission hold changed')


def permit_admission(root, expected):
    owned_root(root,expected)
    path=m.checked_path(root/'admission-hold',root=root)
    if m.file_evidence(path)!={'bytes':0,'sha256':hashlib.sha256(b'').hexdigest()}:
        raise ValueError('admission hold missing or changed')
    # This is an exact zero-byte control flag, never a user-data cleanup.
    m.unlink_durable(path)


def _inventory(path):
    """Bounded, no-alias inventory of one authenticated wrapper, including staging."""
    path=m.checked_path(path)
    result={}
    total=0
    def visit(directory, depth):
        nonlocal total
        if depth>3:
            raise ValueError('backup inventory depth exceeded')
        for child in directory.iterdir():
            m.checked_path(child,root=path)
            if len(result)>=64:
                raise ValueError('backup inventory file bound exceeded')
            relative=child.relative_to(path).as_posix()
            if child.is_dir():
                result[relative]={'identity':_identity(child)}
                visit(child,depth+1)
            elif child.is_file():
                total+=child.stat().st_size
                if total>MAX_GENERATION_BYTES:
                    raise ValueError('backup inventory size exceeded')
                result[relative]=m.file_evidence(child)
            else:
                raise ValueError('backup inventory entry invalid')
    visit(path,0)
    return result,total


def _intent(root,path,expected):
    path=m.checked_path(path,root=root)
    value=_certificate(path/'intent.dpapi')
    if (set(value)!={'schema','root_ownership','name','identity','attempt_id','local_time'}
            or value['schema']!='c6-backup-intent-1' or value['root_ownership']!=expected
            or value['name']!=path.name or not GENERATION.fullmatch(path.name)
            or value['identity']!=_identity(path)
            or not re.fullmatch('[0-9a-f]{32}',value['attempt_id'])):
        raise ValueError('backup attempt ownership mismatch')
    return value


def create_generation(root: Path, runtime: Path, expected: str, *, kind='daily', now=None, attempt_id=None):
    from scripts.backup_telegram_runtime import backup
    value=owned_root(root,expected)
    if value['runtime_binding']!=m.runtime_target_binding(runtime) or kind not in {'daily','prechange'}:
        raise ValueError('backup generation target mismatch')
    now=now or datetime.now().astimezone()
    attempt_id=attempt_id or uuid4().hex
    if now.tzinfo is None or not re.fullmatch('[0-9a-f]{32}',attempt_id):
        raise ValueError('backup attempt invalid')
    generation=m.checked_path(root/(kind+'-'+now.strftime('%Y%m%dT%H%M%S')+'-'+uuid4().hex),root=root)
    generation.mkdir()
    intent={'schema':'c6-backup-intent-1','root_ownership':expected,'name':generation.name,
        'identity':_identity(generation),'attempt_id':attempt_id,'local_time':now.isoformat()}
    # Before C5 writes any data, ownership of its enclosing directory is durable.
    m.write_bytes_durable(generation/'intent.dpapi',CODEC.encode(intent))
    manifest=backup(m.runtime_database_paths(runtime),generation/'snapshot')
    values=verify_backup(manifest)
    if values['source_binding']!=value['runtime_binding']:
        raise ValueError('backup source mismatch')
    latest={'schema':'c6-latest-backup-1','root_ownership':expected,'name':generation.name,
        'manifest_digest':values['authentication']['manifest_digest']}
    pointer_bytes=CODEC.encode(latest)
    entries,_=_inventory(generation)
    certificate={'schema':'c6-backup-generation-2','root_ownership':expected,'name':generation.name,
        'identity':_identity(generation),'local_time':now.isoformat(),'files':entries,
        'pending_pointer':{'bytes':len(pointer_bytes),'sha256':hashlib.sha256(pointer_bytes).hexdigest()},
        'manifest_digest':values['authentication']['manifest_digest']}
    m.write_bytes_durable(generation/'generation.dpapi',CODEC.encode(certificate))
    temporary=m.checked_path(generation/'latest-pending.dpapi',root=generation)
    m.write_bytes_durable(temporary,pointer_bytes)
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
    path=generation/'snapshot/manifest.json'
    manifest=_verified_manifest(path)
    if (manifest['source_binding']!=owner['runtime_binding']
            or manifest['authentication']['manifest_digest']!=pointer['manifest_digest']
            or certificate['manifest_digest']!=pointer['manifest_digest']):
        raise ValueError('latest backup binding mismatch')
    return path


def assert_recent(root: Path, expected: str, runtime: Path):
    import shutil
    if m.checked_path(root/'admission-hold',root=root).exists():
        raise RuntimeError('admission stopped for backup cycle')
    if shutil.disk_usage(m.checked_path(runtime)).free<256*1024*1024:
        raise RuntimeError('admission stopped for disk capacity')
    path=latest_manifest(root,expected,runtime)
    created=datetime.fromisoformat(json.loads(path.read_text())['created_at'])
    age=(datetime.now().astimezone()-created).total_seconds()
    if not 0<=age<=24*3600:
        raise RuntimeError('admission stopped for backup freshness')


def _generation(root, path, expected):
    intent=_intent(root,path,expected)
    value=_certificate(path/'generation.dpapi')
    if (set(value)!={'schema','root_ownership','name','identity','local_time','files','manifest_digest','pending_pointer'}
            or value['schema']!='c6-backup-generation-2' or value['root_ownership']!=expected
            or value['name']!=path.name or value['identity']!=_identity(path)
            or value['local_time']!=intent['local_time']):
        raise ValueError('backup generation ownership mismatch')
    actual,_=_inventory(path)
    actual.pop('generation.dpapi',None)
    pending=actual.pop('latest-pending.dpapi',None)
    if pending is not None and pending!=value['pending_pointer']:
        raise ValueError('backup pending pointer changed')
    if actual!=value['files']:
        raise ValueError('backup generation contains unowned or changed files')
    stamp=datetime.fromisoformat(value['local_time'])
    if stamp.tzinfo is None:
        raise ValueError('backup generation timezone missing')
    return value


def _quarantine(root,expected):
    path=m.checked_path(root/'quarantine',root=root)
    if not path.exists():
        return path,0,0
    entries=list(path.iterdir())
    if len(entries)>MAX_QUARANTINE_ENTRIES:
        raise ValueError('quarantine capacity requires operator archive')
    size=0
    for entry in entries:
        _intent(root,entry,expected)
        inventory,amount=_inventory(entry)
        if (entry/'recovery.dpapi').exists():
            receipt=_certificate(entry/'recovery.dpapi')
            inventory.pop('recovery.dpapi')
            if (set(receipt)!={'schema','root_ownership','identity','inventory'}
                    or receipt['schema']!='c6-partial-quarantine-1' or receipt['root_ownership']!=expected
                    or receipt['identity']!=_identity(entry) or receipt['inventory']!=inventory):
                raise ValueError('partial quarantine changed')
        else:
            _generation(root,entry,expected)
        size+=amount
        if size>MAX_QUARANTINE_BYTES:
            raise ValueError('quarantine capacity requires operator archive')
    return path,len(entries),size


def _move_to_quarantine(root,expected,selected):
    quarantine,count,size=_quarantine(root,expected)
    inventories={path:_inventory(path) for path in selected}
    if count+len(selected)>MAX_QUARANTINE_ENTRIES or size+sum(v[1] for v in inventories.values())>MAX_QUARANTINE_BYTES:
        raise ValueError('quarantine capacity requires operator archive')
    # All paths, bytes and total capacity are checked before the first move.
    for path in selected:
        if m.checked_path(quarantine/path.name,root=root).exists():
            raise ValueError('quarantine target already exists')
    if selected:
        quarantine.mkdir(exist_ok=True)
    for path in selected:
        identity=_identity(path)
        if _inventory(path)!=inventories[path]:
            raise ValueError('quarantine source changed')
        target=m.checked_path(quarantine/path.name,root=quarantine)
        os.rename(m.checked_path(path,root=root),target)
        if _identity(target)!=identity or _inventory(target)!=inventories[path]:
            raise ValueError('quarantine move verification failed')


def recover_partial(root,expected,attempt_id):
    """Only called after explicit failed-cycle confirmation and proven STOP."""
    owned_root(root,expected)
    selected=[]
    entries=list(root.iterdir())
    if len(entries)>128:
        raise ValueError('backup inventory bound exceeded')
    for path in entries:
        if path.name in {'ownership.dpapi','latest.dpapi','quarantine','admission-hold'}:
            m.checked_path(path,root=root)
            continue
        intent=_intent(root,path,expected)
        try:
            _generation(root,path,expected)
            continue
        except (OSError,ValueError):
            if intent['attempt_id']!=attempt_id:
                raise ValueError('partial backup belongs to another cycle')
        inventory,_=_inventory(path)
        # Own wrapper may contain interrupted C5 plaintext staging, kept private.
        # Unknown top-level members are never adopted even inside this wrapper.
        if {name.split('/')[0] for name in inventory}-{'intent.dpapi','snapshot','generation.dpapi','latest-pending.dpapi','recovery.dpapi'}:
            raise ValueError('partial backup contains unowned files')
        database_names=set(m.REQUIRED_RUNTIME_DATABASE_NAMES)|{'business-notes.sqlite3'}
        for name in inventory:
            parts=name.split('/')
            if parts[0]!='snapshot' or len(parts)==1:
                continue
            if len(parts)==2 and parts[1] in {'manifest.json','manifest-auth.bin'}|{n+'.dpapi' for n in database_names}:
                continue
            if (re.fullmatch('backup-[a-z0-9_]{8}',parts[1]) and len(parts)<=3
                    and (len(parts)==2 or parts[2] in {n+suffix for n in database_names for suffix in ('','-wal','-shm','.previous','.rollback')})):
                continue
            raise ValueError('partial backup contains unowned snapshot member')
        inventory.pop('recovery.dpapi',None)
        receipt={'schema':'c6-partial-quarantine-1','root_ownership':expected,
            'identity':_identity(path),'inventory':inventory}
        evidence=m.checked_path(path/'recovery.dpapi',root=path)
        if evidence.exists():
            if _certificate(evidence)!=receipt:
                raise ValueError('partial recovery inventory changed')
        else:
            m.write_bytes_durable(evidence,CODEC.encode(receipt))
        selected.append(path)
    _move_to_quarantine(root,expected,selected)
    return len(selected)


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
    _quarantine(root,expected)
    candidates=[]
    entries=list(root.iterdir())
    if len(entries)>128:
        raise ValueError('backup inventory bound exceeded')
    for path in entries:
        if path.name in {'ownership.dpapi','latest.dpapi','quarantine','admission-hold'}:
            m.checked_path(path,root=root)
            continue
        candidates.append(_generation(root,path,expected))
    keep=retained_names(candidates)
    if (root/'latest.dpapi').exists():
        pointer=_certificate(root/'latest.dpapi')
        if pointer.get('root_ownership')!=expected or pointer.get('name') not in {x['name'] for x in candidates}:
            raise ValueError('latest backup retention binding invalid')
        keep.add(pointer['name'])
    selected=[x for x in candidates if x['name'] not in keep]
    if apply:
        _move_to_quarantine(root,expected,[root/x['name'] for x in selected])
    return {'kept':sorted(keep),'selected':[x['name'] for x in selected],
            'quarantined':len(selected) if apply else 0,'deleted':0}
