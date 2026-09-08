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
from src.application.durable_telegram_state import DpapiJsonCodec
from src.application.windows_singleton import WindowsNamedMutex
from src.contracts.models import canonical_json_digest


def _task(operation,name):
    if not re.fullmatch('NobusSpace[A-Za-z0-9-]{1,64}',name) or operation not in {'Inspect','Disable','Enable','Start'}:
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
    if helper not in value['inputs'] or 'docs/11-Контекст-продукта.md' not in value['inputs']:
        raise ValueError('required input binding missing')
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
        _journal(journal,expected,'closing_admission',recovery_confirmation=recover_failure_digest)
        try:
            _task('Disable',health)
            _task('Disable',main)
            # A missed run may find admission stopped by the 24-hour freshness
            # guard. Create a fresh snapshot before restarting that enabled task.
            if _task('Inspect',main)['state']=='Running' and not _runner('--stop'):
                raise ValueError('graceful stop request failed')
            deadline=clock()+115
            while clock()<deadline:
                state=_task('Inspect',main)
                if state['state']!='Running' and (recovering or cold_start or state['last_result']==0) and _port_closed():
                    break
                wait(1)
            else:
                raise ValueError('runtime stop not proven')
            _journal(journal,expected,'stopped')
            if shutil.disk_usage(runtime).free<256*1024*1024:
                raise ValueError('runtime disk pressure')
            generation=managed.create_generation(backups,runtime,config['ownership'])
            retention=managed.retention(backups,config['ownership'],apply=True)
            _journal(journal,expected,'backed_up',generation=generation.name)
            # Recheck exact inputs/actions after snapshot before resuming the one task.
            load_config(config_path,expected)
            _task('Enable',main)
            _task('Start',main)
            _journal(journal,expected,'starting',generation=generation.name)
            deadline=clock()+375
            while clock()<deadline:
                if _task('Inspect',main)['state']=='Running' and _runner('--check-ready'):
                    break
                wait(3)
            else:
                raise ValueError('runtime restart readiness failed')
            _task('Enable',health)
            _journal(journal,expected,'complete',generation=generation.name)
            return {'status':'PASS','backup_created':True,'generation':generation.name,
                'quarantined':retention['quarantined'],'runtime_ready':True}
        except BaseException:
            # No automatic data restore or retry. A copy/retention/restart failure
            # cannot publish PASS or reset Scheduler retry budgets indefinitely.
            for name in (main,health):
                try: _task('Disable',name)
                except Exception: pass
            try: _runner('--stop')
            except Exception: pass
            _journal(journal,expected,'failed_operator_required')
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
