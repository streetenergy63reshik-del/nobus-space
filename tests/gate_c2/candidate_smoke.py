"""Real CURRENT engine through C2 bounded-memory service, synthetic files only."""
import argparse
import ast
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from benchmark import ROOT, score
from src.voice import FasterWhisperTranscriber, VoicePreviewService


async def main(args):
    os.environ['HF_HUB_OFFLINE']='1'
    source=subprocess.check_output(['git','show','43e753c571e1ad8db5af5f453b5db0c0b417cac8:scripts/run_telegram_mvp1.py']).decode()
    config={}
    for node in ast.parse(source).body:
        if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id in {'_VOICE_INITIAL_PROMPT','_VOICE_HOTWORDS'}:
            config[node.targets[0].id]=ast.literal_eval(node.value)
    engine=FasterWhisperTranscriber(str(args.model),device='cpu',compute_type='int8',local_files_only=True,
        language='ru',beam_size=8,patience=1.2,vad_filter=True,condition_on_previous_text=True,
        initial_prompt=config['_VOICE_INITIAL_PROMPT'],hotwords=config['_VOICE_HOTWORDS'])
    service=VoicePreviewService(engine,args.output.parent/'temp-must-not-exist',10*1024**2,2000)
    await engine.warmup()
    cases=json.loads((ROOT/'tests/gate_c2/dataset.json').read_text(encoding='utf-8'))['cases']
    rows=[]
    for item in cases:
        if item['id'] not in {'direct','transform','noise','long'}: continue
        audio=(args.audio/(item['id']+'.wav')).read_bytes(); t=time.perf_counter()
        result=await service.preview_from_bytes(audio)
        assert result.sha256==hashlib.sha256(audio).hexdigest()
        rows.append({'id':item['id'],'seconds':time.perf_counter()-t,
            'audio_sha256':result.sha256,'duration':result.duration_seconds,
            'provider':result.provider,'model':result.model,'provider_version':result.provider_version,
            'language_confidence':result.language_confidence,'quality':result.quality,
            **score(item['text'],result.transcript,item['critical'])})
    assert not service._temp_root.exists()
    args.output.write_text(json.dumps({'measurements':rows,'temp_created':False},indent=2),encoding='utf-8')
    print(json.dumps({'completed':len(rows),'temp_created':False}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('model','audio','output'): parser.add_argument('--'+name,type=Path,required=True)
    asyncio.run(main(parser.parse_args()))
