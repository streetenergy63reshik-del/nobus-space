"""One approved quiescent backup cycle; failure leaves admission stopped.

The local config and its digest are reviewed in the activation plan. This
command never creates Scheduler tasks or adopts existing backup directories.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from src.application import managed_backups as managed
from src.application import runtime_maintenance as m
from src.application.codex_runtime import PROFILE_NAME, qualified_codex_executable
from src.application.durable_telegram_state import DpapiJsonCodec
from src.application.windows_singleton import WindowsNamedMutex
from src.contracts.models import canonical_json_digest


def _task(operation,name):
    if not re.fullmatch('NobusSpace[A-Za-z0-9-]{1,64}',name) or operation not in {'Inspect','Disable','Enable','Start','Stop'}:
        raise ValueError('scheduler command invalid')
    ps=Path(os.environ['SYSTEMROOT'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    result=subprocess.run([str(ps),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',
        str(ROOT/'ops/windows/Invoke-NobusSpaceTask.ps1'),'-Operation',operation,'-TaskName',name],
        capture_output=True,timeout=30,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    return json.loads(result.stdout.decode('utf-8-sig'))


def _runner(mode):
    result=subprocess.run([sys.executable,str(ROOT/'scripts/run_nobus_space_live.py'),mode],
        capture_output=True,timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
    return result.returncode==0


def _port_closed():
    with socket.socket() as sock:
        sock.settimeout(1)
        return sock.connect_ex(('127.0.0.1',8765))!=0


def load_config(path,expected):
    path=m.checked_path(path)
    if path.stat().st_size>65536:
        raise ValueError('backup configuration too large')
    value=json.loads(path.read_text(encoding='utf-8-sig'))
    if (canonical_json_digest(value)!=expected or set(value)!={'schema','application','runtime','backup_root','ownership','tasks','inputs'}
            or value['schema']!='c6-backup-cycle-1' or value['application']!=m.application_binding()
            or set(value['tasks'])!={'main','health'}):
        raise ValueError('backup configuration mismatch')
    for name in ('runtime','backup_root'):
        if not Path(value[name]).is_absolute():
            raise ValueError('absolute backup paths required')
        m.checked_path(Path(value[name]))
    for relative,evidence in value['inputs'].items():
        if Path(relative).is_absolute() or m.file_evidence(m.checked_path(ROOT/relative,root=ROOT))!=evidence:
            raise ValueError('runtime input changed')
    helper='ops/windows/Invoke-NobusSpaceTask.ps1'
    if helper not in value['inputs'] or 'docs/11-Контекст-продукта.md' not in value['inputs'] or PROFILE_NAME not in value['inputs']:
        raise ValueError('required input binding missing')
    qualified_codex_executable(ROOT)
    for item in value['tasks'].values():
        if set(item)!={'name','signature'} or not re.fullmatch('NobusSpace[A-Za-z0-9-]{1,64}',item['name']):
            raise ValueError('task binding invalid')
        actual=_task('Inspect',item['name'])
        if actual['signature']!=item['signature']:
            raise ValueError('scheduler task changed')
    if value['tasks']['main']['name']==value['tasks']['health']['name']:
        raise ValueError('scheduler tasks must differ')
    managed.owned_root(Path(value['backup_root']),value['ownership'])
    return value


def _journal(path,config_digest,phase,**details):
    value={'schema':'c6-backup-cycle-state-1','config_digest':config_digest,'phase':phase,
        'at':datetime.now(UTC).isoformat(),**details}
    temporary=m.checked_path(path.with_name('cycle-'+uuid4().hex+'.dpapi'),root=path.parent)
    m.write_bytes_durable(temporary,DpapiJsonCodec().encode(value))
    os.replace(temporary,m.checked_path(path,root=path.parent))


def _bound_task(config,operation,name):
    binding=next(item for item in config['tasks'].values() if item['name']==name)
    if _task('Inspect',name)['signature']!=binding['signature']:
        raise ValueError('scheduler task changed before action')
    return _task(operation,name)


def _stopped(config):
    for item in config['tasks'].values():
        actual=_task('Inspect',item['name'])
        if actual['signature']!=item['signature'] or actual['enabled'] or actual['state']=='Running':
            return False
    if not _port_closed():
        return False
    try:
        with WindowsNamedMutex(r'Global\NobusSpaceBotSupervisor'), WindowsNamedMutex():
            return True
    except RuntimeError:
        return False


def _cleanup(config,clock,wait):
    # Disable does not stop an already running task. The supervisor Job closes
    # every owned child on termination; verify both mutexes and the loopback port.
    for item in config['tasks'].values():
        try: _bound_task(config,'Disable',item['name'])
        except Exception: pass
    try: _runner('--stop')
    except Exception: pass
    for item in config['tasks'].values():
        try: _bound_task(config,'Stop',item['name'])
        except Exception: pass
    deadline=clock()+30
    while clock()<deadline:
        try:
            if _stopped(config):
                return True
        except Exception: pass
        wait(1)
    return False


def cycle(config_path,expected,*,recover_failure_digest=None,clock=time.monotonic,wait=time.sleep):
    with WindowsNamedMutex(r'Global\NobusSpaceBackupCycle'):
        config=load_config(config_path,expected)
        runtime,backups=Path(config['runtime']),Path(config['backup_root'])
        journal=m.checked_path(config_path.parent/'backup-cycle-state.dpapi')
        recovering=False
        if journal.exists():
            old=managed._certificate(journal)
            if old.get('schema')!='c6-backup-cycle-state-1' or old.get('config_digest')!=expected:
                raise ValueError('previous backup cycle requires operator reconciliation')
            if old.get('phase')!='complete':
                if recover_failure_digest != canonical_json_digest(old):
                    raise ValueError('previous backup cycle requires operator reconciliation')
                recovering=True
        if recover_failure_digest is not None and not recovering:
            raise ValueError('no matching failed cycle')
        main,health=config['tasks']['main']['name'],config['tasks']['health']['name']
        initial=_task('Inspect',main)
        cold_start=initial['state']!='Running' and _port_closed()
        if recovering:
            health_state=_task('Inspect',health)
            if (initial['enabled'] or health_state['enabled'] or initial['state']=='Running'
                    or health_state['state']=='Running' or not _port_closed()):
                raise ValueError('failure recovery requires both tasks stopped and disabled')
            # Retain the authenticated failed journal before any fresh attempt.
            archive=m.checked_path(journal.with_name('failed-cycle-'+uuid4().hex+'.dpapi'),root=journal.parent)
            m.write_bytes_durable(archive,journal.read_bytes())
            m.validate_runtime_set(runtime)
        else:
            if not initial['enabled']:
                return {'status':'SKIPPED','reason':'runtime_intentionally_disabled','backup_created':False}
            if initial['state']!='Running' and not cold_start:
                raise ValueError('runtime stop state is ambiguous')
        attempt_id=old.get('attempt_id') if recovering else uuid4().hex
        if not isinstance(attempt_id,str) or not re.fullmatch('[0-9a-f]{32}',attempt_id):
            raise ValueError('failed cycle attempt binding invalid')
        def record(phase,**details):
            _journal(journal,expected,phase,attempt_id=attempt_id,**details)
        try:
            managed.hold_admission(backups,config['ownership'])
            record('closing_admission',recovery_confirmation=recover_failure_digest)
            _bound_task(config,'Disable',health)
            _bound_task(config,'Disable',main)
            _bound_task(config,'Stop',health)
            # A missed run may find admission stopped by the 24-hour freshness
            # guard. Create a fresh snapshot before restarting that enabled task.
            if _task('Inspect',main)['state']=='Running' and not _runner('--stop'):
                raise ValueError('graceful stop request failed')
            deadline=clock()+115
            while clock()<deadline:
                state=_task('Inspect',main)
                if state['state']!='Running' and (recovering or cold_start or state['last_result']==0) and _stopped(config):
                    break
                wait(1)
            else:
                raise ValueError('runtime stop not proven')
            record('stopped')
            if recovering:
                managed.recover_partial(backups,config['ownership'],old.get('attempt_id'))
            if shutil.disk_usage(runtime).free<256*1024*1024:
                raise ValueError('runtime disk pressure')
            generation=managed.create_generation(backups,runtime,config['ownership'],attempt_id=attempt_id)
            retention=managed.retention(backups,config['ownership'],apply=True)
            record('backed_up',generation=generation.name)
            # Recheck exact inputs/actions after snapshot before resuming the one task.
            load_config(config_path,expected)
            if not _stopped(config):
                raise ValueError('runtime changed before restart')
            record('restart_permitted',generation=generation.name)
            managed.permit_admission(backups,config['ownership'])
            _bound_task(config,'Enable',main)
            _bound_task(config,'Start',main)
            record('starting',generation=generation.name)
            deadline=clock()+375
            while clock()<deadline:
                if _task('Inspect',main)['state']=='Running' and _runner('--check-ready'):
                    break
                wait(3)
            else:
                raise ValueError('runtime restart readiness failed')
            _bound_task(config,'Enable',health)
            record('complete',generation=generation.name)
            return {'status':'PASS','backup_created':True,'generation':generation.name,
                'quarantined':retention['quarantined'],'runtime_ready':True}
        except BaseException:
            hold_proven=False
            try:
                managed.hold_admission(backups,config['ownership'])
                hold_proven=True
            except Exception: pass
            cleanup_proven=_cleanup(config,clock,wait)
            record('failed_operator_required',admission_hold=hold_proven,cleanup_proven=cleanup_proven)
            raise



def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--config-digest',required=True)
    parser.add_argument('--recover-failure-digest')
    parser.add_argument('--inspect-failure',action='store_true')
    args=parser.parse_args()
    try:
        if args.inspect_failure:
            load_config(args.config,args.config_digest)
            old=managed._certificate(m.checked_path(args.config.parent/'backup-cycle-state.dpapi'))
            result={'phase':old['phase'],'confirmation_digest':canonical_json_digest(old)}
        else:
            result=cycle(args.config,args.config_digest,recover_failure_digest=args.recover_failure_digest)
    except Exception:
        print('{"status":"FAIL","code":"backup_cycle_operator_required"}')
        return 1
    print(json.dumps(result,separators=(',',':')))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
