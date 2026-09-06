"""Single root executor: charge small ASR phases to the existing ledger."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import msvcrt
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
FOLDER=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('qualification_budget',ROOT/'tests/gate_c2/qualification/runner.py')
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)

def trial_timeout(args):
    """Bound every phase, including replay, by the one existing trial clock."""
    if args.unknown_authorized_trial:
        name, seconds = 'unknown-trial-20260906', 600
    elif args.closure_authorized_trial:
        name, seconds = getattr(args,'closure_trial_name','closure-trial-20260906'), 1200
        if name not in {'closure-trial-20260906','material-trial-20260906'}:
            raise ValueError('unknown_closure_trial')
    else:
        return 150
    ledger = ROOT/'.runtime/c2/closure/product-plan'/name/'budget.sqlite3'
    if not ledger.exists():
        return 150  # Authorization/source guards still run in the worker before inference.
    with sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True) as db:
        started = db.execute('SELECT started FROM budget WHERE singleton=1').fetchone()[0]
    return 150 if started is None else min(150,max(0,seconds-(time.time()-started)))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--scenario',required=True)
    parser.add_argument('--phase',required=True)
    parser.add_argument('--run',required=True,type=Path)
    parser.add_argument('--model',required=True,type=Path)
    parser.add_argument('--audio',type=Path)
    parser.add_argument('--correction',action='store_true')
    trial = parser.add_mutually_exclusive_group()
    trial.add_argument('--unknown-authorized-trial',action='store_true')
    trial.add_argument('--closure-authorized-trial',action='store_true')
    parser.add_argument('--closure-trial-name',
                        choices=('closure-trial-20260906','material-trial-20260906'),
                        default='closure-trial-20260906')
    args=parser.parse_args()
    small=ROOT/'.runtime/asr-qualification/faster-whisper-small'
    current=ROOT.parents[2]/'.runtime/voice-models/models--Systran--faster-whisper-base/snapshots/ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66'
    if args.model.resolve() not in {small/'models',current}: raise ValueError('unapproved model path')
    name='Local\\Nobus-C2-product-'+uuid4().hex
    command=[sys.executable,str(Path(__file__).resolve()),'--worker-job',name,'--run',str(args.run),'--scenario',args.scenario,'--phase',args.phase,
        '--model',str(args.model),'--codex-home','C:/Users/CGC1ub/.codex','--authorized-run']
    if args.audio:command+=['--audio',str(args.audio)]
    if args.correction:command+=['--correction']
    if args.unknown_authorized_trial:command+=['--unknown-authorized-trial']
    if args.closure_authorized_trial:
        command+=['--closure-authorized-trial','--closure-trial-name',args.closure_trial_name]
    timeout=trial_timeout(args)
    if timeout<=6:raise SystemExit('authorization_time_exhausted')
    ledger=None; lock=None; started=None; process=None; job=None; api=module.kernel(); final_stats=None; status='NOT_STARTED'; exit_code=None
    ledger_path=small/'execution-ledger.json'
    receipt=args.run/(args.scenario+'-'+args.phase+'-executor-'+str(time.time_ns())+'.json')
    receipt.parent.mkdir(parents=True,exist_ok=True)
    try:
        if args.model.resolve()==small/'models' and args.scenario.endswith('_voice') and args.phase=='admit':
            lock=ledger_path.with_name(ledger_path.name+'.lock').open('a+b');lock.seek(0)
            msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            ledger,reserved=module.reserve_budget(ledger_path,'b02-'+uuid4().hex,150,small=True)
            timeout=min(timeout,reserved)
        job=module.create_job(api,name)
        started=time.perf_counter()
        process=subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            output=process.communicate(timeout=max(0,min(timeout,trial_timeout(args))-6))[0];exit_code=process.returncode;status='EXITED'
        except subprocess.TimeoutExpired:
            status='EXECUTION_DEADLINE';api.TerminateJobObject(job,124);process.kill();output=process.communicate(timeout=4)[0];exit_code=124
        # smoke deliberately prints only bounded safe enums/counts, never provider exceptions.
        print(output.decode('utf-8',errors='replace')[-2000:])
    finally:
        if job:
            api.TerminateJobObject(job,125)
            for _ in range(80):
                final_stats=module.job_stats(api,job)
                if final_stats['active_processes']==0:break
                time.sleep(.025)
            api.CloseHandle(job)
            if final_stats['active_processes']!=0:exit_code=125;status='CLEANUP_NOT_PROVEN'
        if process is not None and process.poll() is None:process.kill();process.wait(timeout=3)
        elapsed=time.perf_counter()-started if started is not None else 0.0
        if ledger is not None:
            ledger['runs'][-1].update(state='FINISHED',charged_seconds=elapsed,actual_seconds=elapsed,outcome=status,
                finished_at_utc=datetime.now(timezone.utc).isoformat())
            ledger['charged_total_seconds']=ledger['prior_consumed_seconds']+sum(row['charged_seconds'] for row in ledger['runs'])
            module.atomic(ledger_path,ledger)
        if lock:lock.close()
        module.atomic(receipt,{'scenario':args.scenario,'phase':args.phase,'status':status,'exit_code':exit_code,'elapsed_seconds':elapsed,
            'job_final_stats':final_stats,'small_charged':ledger is not None,'cumulative_small_seconds':ledger['charged_total_seconds'] if ledger else None,
            'harness_sha256':module.sha(FOLDER/'product_smoke.py'),'executor_sha256':module.sha(Path(__file__))})
    raise SystemExit(exit_code if exit_code is not None else 2)

if __name__=='__main__':
    if len(sys.argv)>2 and sys.argv[1]=='--worker-job':
        module.join_job(module.kernel(),sys.argv[2])
        import runpy
        sys.argv=[str(FOLDER/'product_smoke.py'),*sys.argv[3:]]
        runpy.run_path(str(FOLDER/'product_smoke.py'),run_name='__main__')
    else:main()
