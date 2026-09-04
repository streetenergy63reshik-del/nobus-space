"""Explicit opt-in Windows TTS + deterministic PCM renderer. No ASR or network."""
from __future__ import annotations

import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path
import random
import re
import subprocess
import sys
import wave

HERE=Path(__file__).resolve().parent
RATE=16000


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_pcm(path):
    with wave.open(str(path),'rb') as f:
        if (f.getnchannels(),f.getsampwidth(),f.getframerate(),f.getcomptype())!=(1,2,RATE,'NONE'):
            raise ValueError('expected PCM16 mono 16000Hz')
        if f.getnframes()>RATE*300: raise ValueError('audio exceeds 300-second bound')
        raw=f.readframes(f.getnframes())
    result=array('h'); result.frombytes(raw)
    if sys.byteorder!='little': result.byteswap()
    return result


def write_pcm(path, samples):
    if path.exists(): raise FileExistsError('refusing to overwrite rendered bytes')
    data=array('h',samples)
    if sys.byteorder!='little': data.byteswap()
    with wave.open(str(path),'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(RATE); f.writeframes(data.tobytes())


def rms(values):
    return math.sqrt(sum(float(x)*float(x) for x in values)/len(values)) if len(values) else 0.0


def pcm_stats(samples):
    return {'frames':len(samples),'duration_seconds':len(samples)/RATE,'rms_pcm16':rms(samples),
        'peak_pcm16':max(map(abs,samples),default=0),'clipped_samples':sum(abs(x)>=32767 for x in samples)}


def with_noise(samples, *, seed, snr_db):
    if not isinstance(seed,int) or isinstance(seed,bool) or snr_db!=20:
        raise ValueError('only frozen deterministic20dB recipe is permitted')
    mask=[i for i,value in enumerate(samples) if value!=0]
    if not mask: raise ValueError('cannot calibrate SNR on silent speech')
    rng=random.Random(seed)
    noise=[rng.uniform(-1.0,1.0) for _ in samples]
    mean=sum(noise)/len(noise); noise=[x-mean for x in noise]
    speech_rms=math.sqrt(sum(float(samples[i])**2 for i in mask)/len(mask))
    noise_rms=math.sqrt(sum(noise[i]**2 for i in mask)/len(mask))
    scale=speech_rms/(10**(snr_db/20)*noise_rms)
    noise=[x*scale for x in noise]
    mixed=[float(s)+n for s,n in zip(samples,noise)]
    peak=max(map(abs,mixed)); common_scale=min(1.0,32766.0/peak) if peak else 1.0
    output=array('h',(round(x*common_scale) for x in mixed))
    realized_noise=[output[i]-samples[i]*common_scale for i in mask]
    realized_snr=20*math.log10(speech_rms*common_scale/rms(realized_noise))
    return output,{'seed':seed,'target_snr_db':snr_db,'realized_snr_db':realized_snr,
        'snr_mask':'source PCM sample !=0','nonzero_speech_samples':len(mask),
        'distribution':'random.Random(seed).uniform(-1,1), arithmetic mean removed',
        'common_gain':common_scale,'noise_gain':scale,'clipping_prevented_by_common_gain':common_scale<1,
        'rms_clean_nonzero_pcm16':speech_rms,'rounding':'Python round, PCM16, no per-engine processing'}


def combine_segments(segments):
    """Insert literal zero samples, never infer pauses from transcript punctuation."""
    out=array('h'); inserted=[]
    for samples,pause_ms in segments:
        if pause_ms not in (0,750,1500): raise ValueError('unexpected pause recipe')
        out.extend(samples)
        frames=RATE*pause_ms//1000
        if frames:
            inserted.append({'offset_frames':len(out),'frames':frames,'milliseconds':pause_ms})
            out.extend(array('h',[0])*frames)
    if len(out)>RATE*300: raise ValueError('rendered duration exceeds supported limit')
    return out,inserted


def validate_recipes(gold):
    cases=gold['holdout']; ids=[x['id'] for x in cases]
    if len(cases)!=16 or len(set(ids))!=16: raise ValueError('expected16unique holdout cases')
    profiles={'clean','slow','fast','quiet','segmented_pause','white_noise'}
    for item in cases:
        if not re.fullmatch(r'h_[a-z0-9_]{1,48}',item['id']): raise ValueError('unsafe case ID')
        recipe=item['render']; profile=recipe['profile']
        if profile not in profiles: raise ValueError('unknown acoustic profile')
        if recipe.get('rate',0) not in (-1,0,1) or recipe.get('volume',100) not in (25,100): raise ValueError('unexpected TTS controls')
        if profile=='segmented_pause':
            if ' '.join(s['text'] for s in recipe['segments'])!=item['text']: raise ValueError('segment text/reference mismatch')
            if any(s['pause_after_ms'] not in (0,750,1500) for s in recipe['segments']): raise ValueError('unexpected pauses')
        if profile=='white_noise' and (recipe['snr_db']!=20 or type(recipe['seed']) is not int): raise ValueError('unexpected noise config')
    return cases


def main(args):
    gold=json.loads(args.corpus.read_text(encoding='utf-8-sig')); cases=validate_recipes(gold)
    if not args.execute_tts:
        print(json.dumps({'mode':'PLAN_ONLY','cases':len(cases),'corpus_sha256':sha(args.corpus),'tts_executed':False})); return
    if sys.platform!='win32': raise RuntimeError('existing Windows System.Speech required')
    if args.output.exists(): raise FileExistsError('output directory must be new')
    args.output.mkdir(parents=True)
    raw=args.output/'raw-tts'; audio=args.output/'audio'; audio.mkdir()
    # A fixed script argument carries the JSON file path. Text is never shell code or SSML.
    invocation=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(HERE/'render_tts.ps1'),
        '-Corpus',str(args.corpus.resolve()),'-OutputDirectory',str(raw.resolve())]
    result=subprocess.run(invocation,check=False,capture_output=True,text=True,timeout=600,
        creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError(f'TTS script failed with exit{result.returncode}; preserve output directory for diagnosis')
    tts=json.loads((raw/'tts-receipt.json').read_text(encoding='utf-8-sig')); rows=[]
    for item in cases:
        recipe=item['render']; segments=[]; sources=[]
        specs=recipe['segments'] if recipe['profile']=='segmented_pause' else [{'pause_after_ms':0}]
        for index,spec in enumerate(specs):
            source=raw/f"{item['id']}-{index:02d}.wav"
            samples=read_pcm(source); segments.append((samples,spec['pause_after_ms']))
            sources.append({'file':source.name,'sha256':sha(source),**pcm_stats(samples)})
        samples,pauses=combine_segments(segments); clean_stats=pcm_stats(samples); noise=None
        if recipe['profile']=='white_noise': samples,noise=with_noise(samples,seed=recipe['seed'],snr_db=recipe['snr_db'])
        target=audio/f"{item['id']}.wav"; write_pcm(target,samples)
        rows.append({'id':item['id'],'text_sha256':hashlib.sha256(item['text'].encode()).hexdigest(),
            'audio_file':target.name,'audio_sha256':sha(target),'audio_bytes':target.stat().st_size,
            'recipe':recipe,'sources':sources,'inserted_pauses':pauses,'clean':clean_stats,'rendered':pcm_stats(samples),'noise':noise})
    receipt={'version':'c2-acoustic-render-1.0.0','corpus_sha256':sha(args.corpus),
        'python':sys.version,'renderer_sha256':sha(Path(__file__)),'tts_script_sha256':sha(HERE/'render_tts.ps1'),
        'system_speech':tts,'cases':rows,'asr_executed':False,'historical_dev_audio_modified':False,
        'evidence_limit':'single installed synthetic voice; no human/accent/microphone representation'}
    (args.output/'render-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'completed':len(rows),'total_duration_seconds':sum(r['rendered']['duration_seconds'] for r in rows),
        'total_wav_bytes':sum(r['audio_bytes'] for r in rows),'asr_executed':False}))


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--corpus',type=Path,default=HERE/'CORPUS-GOLD.json')
    p.add_argument('--output',type=Path,required=True); p.add_argument('--execute-tts',action='store_true')
    main(p.parse_args())
