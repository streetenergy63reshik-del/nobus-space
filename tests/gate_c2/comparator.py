"""Authorized offline synthetic GigaAM pilot; no production integration."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as ct
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[2]


def bounds():
    # Native job limit applies before any model is imported or allocated.
    class Basic(ct.Structure):
        _fields_ = [('process_time',ct.c_int64),('job_time',ct.c_int64),('flags',ct.c_uint32),
            ('min_working',ct.c_size_t),('max_working',ct.c_size_t),('active',ct.c_uint32),
            ('affinity',ct.c_size_t),('priority',ct.c_uint32),('scheduling',ct.c_uint32)]
    class Extended(ct.Structure):
        _fields_ = [('basic',Basic),('io',ct.c_uint64*6),('process_memory',ct.c_size_t),
            ('job_memory',ct.c_size_t),('peak_process',ct.c_size_t),('peak_job',ct.c_size_t)]
    kernel=ct.WinDLL('kernel32',use_last_error=True)
    kernel.CreateJobObjectW.restype=ct.c_void_p
    kernel.GetCurrentProcess.restype=ct.c_void_p
    for name,types in [('SetInformationJobObject',[ct.c_void_p,ct.c_int,ct.c_void_p,ct.c_uint32]),
        ('AssignProcessToJobObject',[ct.c_void_p,ct.c_void_p]),
        ('SetProcessAffinityMask',[ct.c_void_p,ct.c_size_t])]:
        getattr(kernel,name).argtypes=types
    job=kernel.CreateJobObjectW(None,None)
    config=Extended(); config.basic.flags=0x100; config.process_memory=4*1024**3
    if not job or not kernel.SetInformationJobObject(job,9,ct.byref(config),ct.sizeof(config)):
        raise OSError('qualification memory limit unavailable')
    if not kernel.AssignProcessToJobObject(job,kernel.GetCurrentProcess()):
        raise OSError('qualification job assignment unavailable')
    if not kernel.SetProcessAffinityMask(kernel.GetCurrentProcess(),15):
        raise OSError('qualification CPU limit unavailable')
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
        os.environ[key]='4'
    os.environ['HF_HUB_OFFLINE']='1'
    def deny_network(event,args):
        if event in {'socket.connect','socket.getaddrinfo','socket.bind'}:
            raise RuntimeError('qualification network denied')
    sys.addaudithook(deny_network)
    return job


def memory():
    class Counters(ct.Structure):
        _fields_=[('cb',ct.c_ulong),('faults',ct.c_ulong)]+[(n,ct.c_size_t) for n in
            ('peak','working','qpp','qp','qpnp','qnp','pagefile','peak_pagefile')]
    values=Counters(); values.cb=ct.sizeof(values)
    kernel=ct.WinDLL('kernel32'); kernel.GetCurrentProcess.restype=ct.c_void_p
    fn=ct.WinDLL('psapi').GetProcessMemoryInfo
    fn.argtypes=[ct.c_void_p,ct.c_void_p,ct.c_ulong]
    if not fn(kernel.GetCurrentProcess(),ct.byref(values),values.cb):
        raise OSError('qualification RAM measurement unavailable')
    return values.peak


def main(args):
    job=bounds()
    import onnx_asr
    import onnxruntime as rt
    rt.disable_telemetry_events()
    from onnx_asr.loader import Manager
    options=rt.SessionOptions(); options.intra_op_num_threads=4; options.inter_op_num_threads=1
    options.execution_mode=rt.ExecutionMode.ORT_SEQUENTIAL
    manager=Manager(options,['CPUExecutionProvider'],preprocessor_config={'max_concurrent_workers':1})
    t=time.perf_counter()
    model=manager.create_asr('gigaam-v3-e2e-rnnt',args.models,offline=True)
    vad=manager.create_vad('silero',args.models/'silero',offline=True)
    model=model.with_vad(vad,batch_size=1,threshold=0.5,neg_threshold=0.35,
        min_speech_duration_ms=250,max_speech_duration_s=20,min_silence_duration_ms=100,speech_pad_ms=30)
    result={'cold_readiness_seconds':time.perf_counter()-t,'versions':{x:metadata.version(x) for x in
        ('onnx-asr','onnxruntime','numpy')},'measurements':[],
        'network':'offline=True, Python socket audit deny; ORT telemetry explicitly disabled; native egress not observed',
        'bounds':{'memory_bytes':4*1024**3,'cpu_affinity':15,'intra_op':4,'inter_op':1},
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    cases=json.loads((ROOT/'tests/gate_c2/dataset.json').read_text(encoding='utf-8'))['cases']
    def recognize(item):
        path=args.audio/(item['id']+'.wav')
        with wave.open(str(path)) as f: duration=f.getnframes()/f.getframerate()
        t=time.perf_counter(); cpu=time.process_time()
        text=' '.join(segment.text for segment in model.recognize(path))
        return {'id':item['id'],'hypothesis':text,'duration':duration,'seconds':time.perf_counter()-t,
            'cpu_seconds':time.process_time()-cpu,'peak_ram_bytes':memory(),
            'audio_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    for iteration in range(1 if args.smoke else 3):
        for item in (cases[:1] if args.smoke else cases):
            row=recognize(item); row['iteration']=iteration
            result['measurements'].append(row)
            args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({k:v for k,v in row.items() if k!='hypothesis'}),flush=True)
    if not args.smoke:
        t=time.perf_counter()
        with ThreadPoolExecutor(max_workers=2) as pool:
            concurrent=list(pool.map(recognize,cases[:2]))
        result['concurrency']={'jobs':2,'completed':len(concurrent),'seconds':time.perf_counter()-t,
            'peak_ram_bytes':memory()}
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--models',type=Path,required=True)
    parser.add_argument('--audio',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--smoke',action='store_true')
    main(parser.parse_args())
