"""Frozen offline pilot; never imports the runner or contacts a provider."""
from __future__ import annotations

import argparse
import ast
import asyncio
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.voice import FasterWhisperTranscriber


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def distance(a, b):
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(current[-1]+1, previous[j]+1, previous[j-1]+(x != y)))
        previous = current
    return previous[-1]


def words(text):
    return re.findall(r"\w+", text.casefold().replace('ё', 'е'))


def score(reference, hypothesis, critical):
    a, b = words(reference), words(hypothesis)
    ca, cb = ' '.join(a), ' '.join(b)
    return dict(word_errors=distance(a,b), words=len(a), char_errors=distance(ca,cb), chars=len(ca),
                critical_errors=sum(a.count(w) != b.count(w) for w in critical),
                lexical_exact=a == b, semantic_exactness=None)


def memory():
    class Counters(ctypes.Structure):
        _fields_ = [('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(n,ctypes.c_size_t) for n in
            ('peak','working','quota_peak_paged','quota_paged','quota_peak_nonpaged','quota_nonpaged','pagefile','peak_pagefile')]
    values = Counters(); values.cb=ctypes.sizeof(values)
    kernel=ctypes.WinDLL('kernel32'); kernel.GetCurrentProcess.restype=ctypes.c_void_p
    fn=ctypes.WinDLL('psapi').GetProcessMemoryInfo
    fn.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong]
    if not fn(kernel.GetCurrentProcess(),ctypes.byref(values),values.cb): return None
    return values.peak


async def run(args):
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
    dataset_path=Path(__file__).with_name('dataset.json')
    manifest=ROOT/'docs/gates/gate-c2-voice-parity/BENCHMARK-MANIFEST.json'
    data=json.loads(dataset_path.read_text(encoding='utf-8'))
    source=subprocess.check_output(['git','show','43e753c571e1ad8db5af5f453b5db0c0b417cac8:scripts/run_telegram_mvp1.py']).decode()
    config={}
    for node in ast.parse(source).body:
        if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id in {'_VOICE_INITIAL_PROMPT','_VOICE_HOTWORDS'}:
            config[node.targets[0].id]=ast.literal_eval(node.value)
    model=FasterWhisperTranscriber(model_size=str(args.model.resolve()),device='cpu',compute_type='int8',local_files_only=True,
        language='ru',beam_size=8,patience=1.2,vad_filter=True,condition_on_previous_text=True,
        initial_prompt=config['_VOICE_INITIAL_PROMPT'],hotwords=config['_VOICE_HOTWORDS'])
    evidence=dict(dataset_sha256=sha(dataset_path),manifest_sha256=sha(manifest),scorer_sha256=sha(Path(__file__)),
        model_files={p.name:sha(p) for p in sorted(args.model.iterdir()) if p.is_file()},audio_files={},measurements=[],
        semantic_exactness=None,semantic_gap='Requires independent semantic scoring; lexical score is not semantics.',network='offline local files only')
    t=time.perf_counter(); await model.warmup(); evidence['cold_readiness_seconds']=time.perf_counter()-t
    for iteration in range(3):
        for item in data['cases']:
            path=args.audio/(item['id']+'.wav')
            evidence['audio_files'][path.name]=sha(path)
            with wave.open(str(path)) as f: duration=f.getnframes()/f.getframerate()
            t=time.perf_counter(); cpu=time.process_time()
            result=await model.transcribe(path,max_chars=2000)
            elapsed=time.perf_counter()-t
            row=dict(id=item['id'],iteration=iteration,duration=duration,seconds=elapsed,cpu_seconds=time.process_time()-cpu,
                     rtf=elapsed/duration,peak_ram_bytes=memory(),**score(item['text'],result.text,item['critical']))
            evidence['measurements'].append(row)
            print(json.dumps(row),flush=True)
            args.output.write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    concurrent=data['cases'][:2]
    t=time.perf_counter()
    results=await asyncio.gather(*(model.transcribe(args.audio/(x['id']+'.wav'),max_chars=2000) for x in concurrent))
    evidence['concurrency']={'jobs':2,'seconds':time.perf_counter()-t,'peak_ram_bytes':memory(),'completed':len(results)}
    rows=evidence['measurements']; first=[r for r in rows if r['iteration']==0]
    p95=lambda xs: sorted(xs)[max(0,__import__('math').ceil(.95*len(xs))-1)]
    evidence['summary']=dict(wer=sum(r['word_errors'] for r in first)/sum(r['words'] for r in first),
        cer=sum(r['char_errors'] for r in first)/sum(r['chars'] for r in first),
        critical_errors=sum(r['critical_errors'] for r in first),
        latency_p50=statistics.median(r['seconds'] for r in rows),latency_p95=p95([r['seconds'] for r in rows]),
        rtf_p95=p95([r['rtf'] for r in rows]),peak_ram_bytes=memory(),asr_decision='BLOCKED')
    args.output.write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    print(json.dumps(evidence['summary']),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--audio',type=Path,required=True)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    asyncio.run(run(parser.parse_args()))
