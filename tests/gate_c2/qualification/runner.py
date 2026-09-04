"""Bounded local qualification only. Explicit engine execution; no provider downloads."""
from __future__ import annotations

import argparse
import ast
import asyncio
import ctypes as ct
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4
import wave

HERE=Path(__file__).resolve().parent
RAM=4*1024**3
PRIOR_GIGA_SECONDS=169.234
AUTHORIZED_GIGA_SECONDS=1800.0
QUALIFICATION_GIGA_CAP=900.0


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path, value):
    temporary=path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    with temporary.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.flush(); os.fsync(stream.fileno())
    for attempt in range(21):
        try:
            os.replace(temporary,path)
            break
        except PermissionError as error:
            # Windows readers briefly hold a share-delete exclusion. Keep the
            # complete previous receipt visible and retry only that bounded race.
            if attempt == 20 or getattr(error, 'winerror', None) not in (5,32):
                raise
            time.sleep(.01)


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


class BasicLimit(ct.Structure):
    _fields_=[('process_time',ct.c_int64),('job_time',ct.c_int64),('flags',ct.c_uint32),
        ('min_working',ct.c_size_t),('max_working',ct.c_size_t),('active',ct.c_uint32),
        ('affinity',ct.c_size_t),('priority',ct.c_uint32),('scheduling',ct.c_uint32)]


class ExtendedLimit(ct.Structure):
    _fields_=[('basic',BasicLimit),('io',ct.c_uint64*6),('process_memory',ct.c_size_t),
        ('job_memory',ct.c_size_t),('peak_process',ct.c_size_t),('peak_job',ct.c_size_t)]


class Accounting(ct.Structure):
    _fields_=[('user',ct.c_int64),('kernel',ct.c_int64),('period_user',ct.c_int64),('period_kernel',ct.c_int64),
        ('faults',ct.c_uint32),('total_processes',ct.c_uint32),('active_processes',ct.c_uint32),('terminated_processes',ct.c_uint32)]


def kernel():
    if os.name!='nt': raise RuntimeError('Windows qualification required')
    api=ct.WinDLL('kernel32',use_last_error=True)
    signatures={
        'CreateJobObjectW':([ct.c_void_p,ct.c_wchar_p],ct.c_void_p),
        'OpenJobObjectW':([ct.c_uint32,ct.c_int,ct.c_wchar_p],ct.c_void_p),
        'GetCurrentProcess':([],ct.c_void_p),
        'SetInformationJobObject':([ct.c_void_p,ct.c_int,ct.c_void_p,ct.c_uint32],ct.c_int),
        'QueryInformationJobObject':([ct.c_void_p,ct.c_int,ct.c_void_p,ct.c_uint32,ct.c_void_p],ct.c_int),
        'AssignProcessToJobObject':([ct.c_void_p,ct.c_void_p],ct.c_int),
        'TerminateJobObject':([ct.c_void_p,ct.c_uint32],ct.c_int),
        'CloseHandle':([ct.c_void_p],ct.c_int),
    }
    for name,(inputs,output) in signatures.items():
        fn=getattr(api,name); fn.argtypes=inputs; fn.restype=output
    return api


def create_job(api, name):
    handle=api.CreateJobObjectW(None,name)
    if not handle: raise OSError('qualification Job creation failed')
    info=ExtendedLimit(); info.basic.flags=0x2000|0x300|0x10
    info.basic.affinity=15; info.process_memory=RAM; info.job_memory=RAM
    if not api.SetInformationJobObject(handle,9,ct.byref(info),ct.sizeof(info)):
        api.CloseHandle(handle); raise OSError('qualification Job bounds failed')
    return handle


def join_job(api,name):
    # The actual venv runtime joins itself; its redirector cannot race ahead with model imports.
    handle=api.OpenJobObjectW(0x1,False,name)
    if not handle: raise OSError('qualification parent Job missing')
    try:
        if not api.AssignProcessToJobObject(handle,api.GetCurrentProcess()):
            raise OSError('qualification Job assignment failed')
    finally:
        api.CloseHandle(handle)  # Sole persistent handle remains in supervisor: kill on parent death.


def job_stats(api,handle=None):
    limits=ExtendedLimit(); accounting=Accounting()
    if not api.QueryInformationJobObject(handle,9,ct.byref(limits),ct.sizeof(limits),None):
        raise OSError('qualification Job memory query failed')
    if not api.QueryInformationJobObject(handle,1,ct.byref(accounting),ct.sizeof(accounting),None):
        raise OSError('qualification Job CPU query failed')
    return {'cpu_seconds':(accounting.user+accounting.kernel)/10_000_000,
        'peak_job_memory_bytes':limits.peak_job,'peak_process_memory_bytes':limits.peak_process,
        'total_processes':accounting.total_processes,'active_processes':accounting.active_processes,
        'memory_metric':'Windows Job committed memory, including descendants; not peak working set'}


def corpus_cases(args):
    sys.path.insert(0,str(HERE))
    from scorer import load_cases
    all_cases=load_cases(args.corpus,args.dev_dataset)
    selected=[value for value in all_cases.values() if value['split']==args.split]
    return selected,all_cases['direct']


def audio_metadata(args,item):
    root=args.dev_audio if item['split']=='dev' else args.holdout_audio
    path=root/(item['id']+'.wav')
    size=path.stat().st_size
    if not 0<size<=10*1024**2: raise ValueError('qualification audio size invalid')
    with wave.open(str(path)) as audio:
        if (audio.getnchannels(),audio.getsampwidth(),audio.getcomptype())!=(1,2,'NONE') or audio.getframerate() not in (16000,22050):
            raise ValueError('qualification requires frozen PCM16 mono at 16000 or 22050 Hz')
        duration=audio.getnframes()/audio.getframerate()
    if not 0<duration<=300: raise ValueError('qualification audio duration invalid')
    return path,{'duration':duration,'audio_sha256':sha(path),'audio_bytes':size}


def fw_options(args):
    script=args.repo/'scripts/run_telegram_mvp1.py'; tree=ast.parse(script.read_text(encoding='utf-8'))
    constants={}
    for node in tree.body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            if node.targets[0].id in {'_VOICE_INITIAL_PROMPT','_VOICE_HOTWORDS'}:
                constants[node.targets[0].id]=ast.literal_eval(node.value)
    calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='IsolatedFasterWhisperTranscriber']
    if len(calls)!=1 or len(constants)!=2: raise ValueError('CURRENT ASR configuration is not uniquely identified')
    source={}
    for option in calls[0].keywords:
        if option.arg=='download_root':
            if not isinstance(option.value,ast.Name) or option.value.id!='_VOICE_MODEL_ROOT': raise ValueError('CURRENT download root changed')
            continue
        source[option.arg]=constants[option.value.id] if isinstance(option.value,ast.Name) else ast.literal_eval(option.value)
    expected={'model_size':'base','device':'cpu','compute_type':'int8','local_files_only':True,'language':'ru',
        'beam_size':8,'patience':1.2,'vad_filter':True,'condition_on_previous_text':True,
        'initial_prompt':constants['_VOICE_INITIAL_PROMPT'],'hotwords':constants['_VOICE_HOTWORDS']}
    if source!=expected: raise ValueError('CURRENT decoding configuration differs from frozen contract')
    options={**source,'model_size':str(args.models.resolve())}
    overrides = None
    if args.fw_options:
        overrides = read_json(args.fw_options)
        if not isinstance(overrides,dict) or not set(overrides) <= {'initial_prompt','hotwords','beam_size','patience','condition_on_previous_text','vad_filter'}:
            raise ValueError('development overrides exceed decoding configuration')
        options.update(overrides)
    return options,{'source_script_sha256':sha(script),'source_options':source,
        'candidate_overrides':overrides,'overrides_sha256':sha(args.fw_options) if args.fw_options else None,
        'binding':'base identifier resolved to explicit pinned local snapshot path; no download/cache fallback',
        'model_directory_name':args.models.name}


def offline_environment():
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
        os.environ[key]='4'
    os.environ.update(HF_HUB_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',DO_NOT_TRACK='1')
    def deny_network(event,unused):
        if event in {'socket.connect','socket.getaddrinfo','socket.bind'}: raise OSError('offline qualification only')
    sys.addaudithook(deny_network)


async def worker(args):
    api=kernel(); join_job(api,args.worker_job)
    offline_environment()
    cases,cold_case=corpus_cases(args)
    evidence=read_json(args.output); evidence['worker_started_perf_counter']=time.perf_counter()
    evidence['worker_pid']=os.getpid(); evidence['bounds_verified']=job_stats(api)
    atomic(args.output,evidence)
    lock=asyncio.Lock(); engine=None
    try:
        started=time.perf_counter()
        if args.engine=='fw':
            sys.path.insert(0,str(args.repo))
            from src.voice import IsolatedFasterWhisperTranscriber
            evidence['import_seconds']=time.perf_counter()-started
            options,configuration=fw_options(args); engine=IsolatedFasterWhisperTranscriber(**options)
            started=time.perf_counter(); await engine.warmup()
            evidence['load_readiness_seconds']=time.perf_counter()-started
            evidence['load_phase_scope']='isolated child spawn/import/model load and existing encoder warmup'
            evidence['versions']={name:metadata.version(name) for name in ('faster-whisper','ctranslate2','av','numpy')}
        else:
            import onnx_asr
            import onnxruntime as rt
            rt.disable_telemetry_events()
            from onnx_asr.loader import Manager
            evidence['import_seconds']=time.perf_counter()-started
            options=rt.SessionOptions(); options.intra_op_num_threads=4; options.inter_op_num_threads=1
            options.execution_mode=rt.ExecutionMode.ORT_SEQUENTIAL
            manager=Manager(options,['CPUExecutionProvider'],preprocessor_config={'max_concurrent_workers':1})
            started=time.perf_counter()
            engine=manager.create_asr('gigaam-v3-e2e-rnnt',args.models,offline=True)
            vad=manager.create_vad('silero',args.models/'silero',offline=True)
            vad_options={'batch_size':1,'threshold':0.5,'neg_threshold':0.35,'min_speech_duration_ms':250,
                'max_speech_duration_s':20,'min_silence_duration_ms':100,'speech_pad_ms':30}
            engine=engine.with_vad(vad,**vad_options)
            evidence['load_readiness_seconds']=time.perf_counter()-started
            evidence['load_phase_scope']='ASR+Silero sessions; first inference measured separately'
            evidence['versions']={name:metadata.version(name) for name in ('onnx-asr','onnxruntime','numpy')}
            configuration={'model':'gigaam-v3-e2e-rnnt','offline':True,'providers':['CPUExecutionProvider'],
                'intra_op':4,'inter_op':1,'execution_mode':'ORT_SEQUENTIAL','preprocessor_max_workers':1,
                'vad':vad_options,'ort_telemetry_disabled_before_sessions':True,
                'source_comparator_sha256':sha(args.repo/'tests/gate_c2/comparator.py')}
        evidence['configuration']=configuration
        atomic(args.output,evidence)

        async def recognize(item,section):
            admitted=time.perf_counter()
            async with lock:
                service=time.perf_counter(); before=job_stats(api)
                row={'id':item['id'],'iteration':args.iteration,'split':item['split'],'hypothesis':'',
                    'wait_seconds':service-admitted,'error':None,'truncated':False}
                try:
                    path,audio=audio_metadata(args,item); row.update(audio)
                    if args.engine=='fw':
                        result=await engine.transcribe_audio(path.read_bytes(),max_chars=2000)
                        text=result.text
                    else:
                        def infer(): return ' '.join(segment.text for segment in engine.recognize(path))
                        text=await asyncio.to_thread(infer)
                    if not isinstance(text,str) or len(text)>2000:
                        row['truncated']=isinstance(text,str) and len(text)>2000
                        raise ValueError('malformed or oversized transcript')
                    row['hypothesis']=text
                    if not text.strip(): row['error']='EMPTY_TRANSCRIPT'
                except Exception as error:
                    row['error']=type(error).__name__  # Never persist library exception text/paths/payload.
                done=time.perf_counter(); after=job_stats(api)
                row.update(seconds=done-service,end_to_end_seconds=done-admitted,
                    cpu_seconds=after['cpu_seconds']-before['cpu_seconds'],peak_ram_bytes=after['peak_job_memory_bytes'],
                    peak_job_memory_bytes=after['peak_job_memory_bytes'],job_total_processes=after['total_processes'])
                if section=='cold':
                    evidence['cold_first']=row; evidence['first_transcript_completed_perf_counter']=done
                    evidence['first_transcript_usable']=not bool(row['error'])
                else: evidence[section].append(row)
                atomic(args.output,evidence)
                return row

        await recognize(cold_case,'cold')
        for item in cases: await recognize(item,'measurements')
        if args.concurrency:
            started=time.perf_counter()
            await asyncio.gather(*(recognize(item,'concurrency_measurements') for item in cases[:2]))
            evidence['concurrency_seconds']=time.perf_counter()-started
        evidence['worker_status']='COMPLETE'
    except Exception as error:
        evidence['worker_status']='FAILED'; evidence['worker_error']=type(error).__name__
    finally:
        if args.engine=='fw' and engine is not None:
            try: await engine.close()
            except Exception as error:
                evidence['worker_status']='FAILED'; evidence['cleanup_error']=type(error).__name__
        evidence['worker_final_stats']=job_stats(api)
        atomic(args.output,evidence)


def reserve_budget(path,run_id,requested):
    # The caller holds a Windows byte-range lock until execution and accounting finish.
    if path.exists(): ledger=read_json(path)
    else:
        ledger={'version':'c2-giga-execution-ledger-1.0.0','prior_consumed_seconds':PRIOR_GIGA_SECONDS,
            'authorized_seconds':AUTHORIZED_GIGA_SECONDS,'qualification_cap_seconds':QUALIFICATION_GIGA_CAP,'runs':[]}
    if (ledger.get('prior_consumed_seconds'),ledger.get('authorized_seconds'),ledger.get('qualification_cap_seconds'))!=(PRIOR_GIGA_SECONDS,AUTHORIZED_GIGA_SECONDS,QUALIFICATION_GIGA_CAP):
        raise ValueError('budget ledger constants changed')
    if not isinstance(ledger.get('runs'),list) or len({row['run_id'] for row in ledger['runs']})!=len(ledger['runs']):
        raise ValueError('budget ledger run identities invalid')
    for row in ledger['runs']:
        if row['state'] not in ('RESERVED','FINISHED') or type(row['charged_seconds']) not in (int,float) or not math.isfinite(row['charged_seconds']) or row['charged_seconds']<0:
            raise ValueError('budget ledger charge invalid')
        if row['state']=='RESERVED' and row['charged_seconds']!=row['reserved_seconds']:
            raise ValueError('unfinished reservation must remain fully charged')
    charged=sum(row['charged_seconds'] for row in ledger['runs'])
    remaining=min(AUTHORIZED_GIGA_SECONDS-PRIOR_GIGA_SECONDS-charged,QUALIFICATION_GIGA_CAP-charged)
    if remaining<10: raise RuntimeError('cumulative GigaAM budget exhausted')
    reserved=min(requested,remaining)
    ledger['runs'].append({'run_id':run_id,'state':'RESERVED','reserved_seconds':reserved,'charged_seconds':reserved,
        'started_at_utc':datetime.now(timezone.utc).isoformat()})
    atomic(path,ledger)
    return ledger,reserved


def worker_command(args,name):
    command=[sys.executable,'-I','-B',str(Path(__file__).resolve()),'--engine',args.engine,
        '--split',args.split,'--iteration',str(args.iteration),'--timeout',str(args.timeout),'--worker-job',name]
    for option in ('repo','output','dev_audio','holdout_audio','models','corpus','dev_dataset'):
        command.extend(('--'+option.replace('_','-'),str(getattr(args,option))))
    if args.ledger is not None: command.extend(('--ledger',str(args.ledger)))
    if args.fw_options is not None: command.extend(('--fw-options',str(args.fw_options)))
    if args.concurrency: command.append('--concurrency')
    return command


def supervisor(args):
    if os.name!='nt': raise RuntimeError('Windows qualification required')
    if not args.models.is_dir(): raise ValueError('existing pinned model directory required')
    if args.engine=='giga' and args.ledger is None: raise ValueError('GigaAM requires the persistent cumulative ledger')
    if not math.isfinite(args.timeout) or not 10<=args.timeout<=300: raise ValueError('execution reservation must be10..300seconds')
    cases,cold_case=corpus_cases(args)
    audio={item['id']:audio_metadata(args,item)[1] for item in cases+[cold_case]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    initial={'version':'c2-matched-qualification-run-1.0.0','engine':args.engine,'split':args.split,'iteration':args.iteration,
        'runner_sha256':sha(Path(__file__)),'corpus_gold_sha256':sha(args.corpus),'dev_dataset_sha256':sha(args.dev_dataset),
        'source_root_commit_unchecked_by_runner':True,'audio':audio,'measurements':[],'concurrency_measurements':[],
        'bounds':{'job_memory_bytes':RAM,'cpu_affinity':15,'serial_native_slots':1,'concurrent_admission':2 if args.concurrency else 1},
        'network':'local-only; Python socket deny and explicit telemetry off; not proof of native egress isolation',
        'worker_status':'NOT_STARTED','complete':False,'semantic_exactness':None}
    with args.output.open('x',encoding='utf-8') as stream: json.dump(initial,stream,ensure_ascii=False,allow_nan=False)
    api=kernel(); handle=None; process=None; budget=None; lease=None; started=None; timeout=args.timeout
    run_id=uuid4().hex; outcome='SUPERVISOR_FAILURE'; final_stats=None; child_exit=None; supervisor_error=None
    try:
        if args.engine=='giga':
            import msvcrt
            args.ledger.parent.mkdir(parents=True,exist_ok=True)
            lease=args.ledger.with_name(args.ledger.name+'.lock').open('a+b')
            lease.seek(0,2)
            if lease.tell()==0: lease.write(b'0'); lease.flush()
            lease.seek(0); msvcrt.locking(lease.fileno(),msvcrt.LK_NBLCK,1)
            budget,timeout=reserve_budget(args.ledger,run_id,timeout)
        name='Local\\Nobus-C2-qualification-'+run_id; handle=create_job(api,name)
        command=worker_command(args,name)
        environment={key:value for key,value in os.environ.items() if key.upper() in
            {'SYSTEMROOT','WINDIR','TEMP','TMP','USERPROFILE','LOCALAPPDATA'}}
        environment.update(HF_HUB_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',DO_NOT_TRACK='1',
            OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',NUMEXPR_NUM_THREADS='4')
        started=time.perf_counter()
        process=subprocess.Popen(command,cwd=args.repo,env=environment,stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        outcome='EXITED'
        while process.poll() is None:
            if time.perf_counter()-started>=timeout-6:
                outcome='EXECUTION_DEADLINE'; api.TerminateJobObject(handle,124); process.kill(); break
            current=read_json(args.output)
            if 'first_transcript_completed_perf_counter' not in current and time.perf_counter()-started>=120:
                outcome='COLD_DEADLINE'; api.TerminateJobObject(handle,124); process.kill(); break
            time.sleep(0.05)
        child_exit=process.wait(timeout=4)
        final_stats=job_stats(api,handle)
    except Exception as error:
        supervisor_error=type(error).__name__
    finally:
        if handle:
            api.TerminateJobObject(handle,125)
            if final_stats is None:
                try: final_stats=job_stats(api,handle)
                except OSError: pass
            api.CloseHandle(handle)
        if process is not None and process.poll() is None:
            process.kill(); process.wait(timeout=4)
        elapsed=time.perf_counter()-started if started is not None else 0.0
        if budget is not None:
            entry=budget['runs'][-1]
            entry.update(state='FINISHED',charged_seconds=elapsed,actual_seconds=elapsed,outcome=outcome,
                finished_at_utc=datetime.now(timezone.utc).isoformat())
            budget['charged_total_seconds']=PRIOR_GIGA_SECONDS+sum(row['charged_seconds'] for row in budget['runs'])
            atomic(args.ledger,budget)
        if lease is not None: lease.close()
        result=read_json(args.output)
        present={row['id'] for row in result['measurements']}
        for item in cases:
            if item['id'] not in present:
                result['measurements'].append({'id':item['id'],'iteration':args.iteration,'split':args.split,
                    'hypothesis':'','error':'NOT_COMPLETED_'+outcome,'seconds':None,**audio[item['id']]})
        if args.concurrency:
            present={row['id'] for row in result['concurrency_measurements']}
            for item in cases[:2]:
                if item['id'] not in present:
                    result['concurrency_measurements'].append({'id':item['id'],'iteration':args.iteration,
                        'hypothesis':'','error':'NOT_COMPLETED_'+outcome,'seconds':None,**audio[item['id']]})
        first=result.get('first_transcript_completed_perf_counter')
        cold_seconds=first-started if first is not None and started is not None else None
        result['supervisor']={'outcome':outcome,'child_exit_code':child_exit,'elapsed_seconds':elapsed,
            'error':supervisor_error,
            'reservation_seconds':timeout,'process_cold_seconds':cold_seconds,'job_final_stats':final_stats,
            'process_cold_boundary':'before interpreter spawn through first dev-direct transcript; OS file cache uncontrolled',
            'controller_not_in_job':'stdlib supervisor and venv redirector have no model/audio inference allocation',
            'cumulative_ledger_sha256':sha(args.ledger) if budget is not None else None}
        result['complete']=result.get('worker_status')=='COMPLETE' and outcome=='EXITED' and child_exit==0
        atomic(args.output,result)
    print(json.dumps({'complete':result['complete'],'measurements':len(result['measurements']),
        'error_rows':sum(bool(row.get('error')) for row in result['measurements']),
        'process_cold_seconds':cold_seconds,'elapsed_seconds':elapsed,'outcome':outcome},allow_nan=False))
    return 0 if result['complete'] else 2


def arguments():
    p=argparse.ArgumentParser()
    p.add_argument('--engine',choices=('fw','giga'),required=True)
    p.add_argument('--split',choices=('dev','holdout'),required=True)
    p.add_argument('--iteration',type=int,choices=(0,1,2),required=True)
    p.add_argument('--output',type=Path,required=True); p.add_argument('--repo',type=Path,required=True)
    p.add_argument('--dev-audio',type=Path,required=True); p.add_argument('--holdout-audio',type=Path,required=True)
    p.add_argument('--models',type=Path,required=True); p.add_argument('--ledger',type=Path)
    p.add_argument('--fw-options',type=Path)
    p.add_argument('--corpus',type=Path,default=HERE/'CORPUS-GOLD.json')
    p.add_argument('--dev-dataset',type=Path,required=True)
    p.add_argument('--timeout',type=float,default=150); p.add_argument('--concurrency',action='store_true')
    p.add_argument('--worker-job',help=argparse.SUPPRESS)
    args=p.parse_args()
    for key in ('output','repo','dev_audio','holdout_audio','models','ledger','corpus','dev_dataset','fw_options'):
        value=getattr(args,key)
        if value is not None: setattr(args,key,value.resolve())
    return args


if __name__=='__main__':
    args=arguments()
    if args.worker_job: asyncio.run(worker(args))
    else: raise SystemExit(supervisor(args))
