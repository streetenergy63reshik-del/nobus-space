"""Real OS process lifetime/Job tests, with deterministic native-hang fixtures."""
import asyncio
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from src.voice import isolated
from src.voice import VoiceTranscriptionError

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows Job lifetime')

WORKER = '''import ctypes,json,os,struct,sys,time
stream=sys.stdin.buffer; output=sys.stdout.buffer
def read(n):
    data=stream.read(n)
    if len(data)!=n: sys.exit(0)
    return data
config=json.loads(read(struct.unpack('!I',read(4))[0]))
while True:
    size,limit=struct.unpack('!II',read(8)); audio=read(size)
    if audio==b'hang': ctypes.windll.kernel32.Sleep(60000)
    if audio==b'crash': sys.exit(77)
    if audio==b'oversize': output.write(struct.pack('!I',1000000)); output.flush(); continue
    if audio==b'error': body=b'{"error":true}'
    elif audio==b'identity': body=json.dumps({'text':str(os.getpid()),'language':'ru'}).encode()
    elif not size: body=b'{"ready":true}'
    else:
        time.sleep(.04)
        body=json.dumps({'text':'synthetic '+audio.decode(),'language':'ru'}).encode()
    output.write(struct.pack('!I',len(body))+body); output.flush()
'''


def alive(pid):
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.OpenProcess.argtypes=(ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32)
    api.OpenProcess.restype=ctypes.c_void_p
    api.WaitForSingleObject.argtypes=(ctypes.c_void_p,ctypes.c_uint32)
    api.CloseHandle.argtypes=(ctypes.c_void_p,)
    handle=api.OpenProcess(0x100000,False,pid)
    if not handle: return False
    try: return api.WaitForSingleObject(handle,0)==258
    finally: api.CloseHandle(handle)


@pytest.fixture
def engine(tmp_path,monkeypatch):
    (tmp_path/'isolated_worker.py').write_text(WORKER)
    monkeypatch.setattr(isolated,'__file__',str(tmp_path/'isolated.py'))
    return isolated.IsolatedFasterWhisperTranscriber(local_files_only=True,timeout_seconds=.6)


@pytest.mark.asyncio
async def test_native_hang_is_killed_before_retry(engine):
    await engine.warmup(); pid=engine._process.pid
    start=time.monotonic()
    with pytest.raises(VoiceTranscriptionError,match='recognition failed'):
        await engine.transcribe_audio(b'hang',max_chars=2000)
    assert time.monotonic()-start < 3 and not alive(pid)
    assert (await engine.transcribe_audio(b'new',max_chars=2000)).text=='synthetic new'
    await engine.close()


@pytest.mark.asyncio
async def test_spawned_pid_is_native_interpreter_not_venv_redirector(engine):
    native_pid=int((await engine.transcribe_audio(b'identity',max_chars=2000)).text)
    assert native_pid==engine._process.pid
    await engine.close()
    assert not alive(native_pid)


@pytest.mark.asyncio
async def test_early_idle_callback_reschedules_remaining_lifetime(engine,monkeypatch):
    monkeypatch.setattr(isolated,'_IDLE_SECONDS',.15)
    await engine.warmup(); pid=engine._process.pid
    # Windows timers may fire before the clock-resolution boundary. Drive that
    # callback explicitly so this regression does not depend on scheduler luck.
    engine._idle.cancel()
    await engine._expire_idle()
    assert alive(pid)
    await asyncio.sleep(.35)
    assert not alive(pid) and engine._process is None
    await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('action',['cancel','close','repeated_cancel'])
async def test_cancellation_and_shutdown_reap_native_process(engine,action):
    await engine.warmup(); pid=engine._process.pid
    task=asyncio.create_task(engine.transcribe_audio(b'hang',max_chars=2000))
    await asyncio.sleep(.05)
    if action=='close': await engine.close()
    else:
        task.cancel()
        if action=='repeated_cancel':
            await asyncio.sleep(0); task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert not alive(pid)
    await engine.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('audio',[b'crash',b'oversize',b'error'])
async def test_crash_and_bad_response_cannot_survive_or_leak(engine,audio):
    await engine.warmup(); pid=engine._process.pid
    with pytest.raises(VoiceTranscriptionError) as caught:
        await engine.transcribe_audio(audio,max_chars=2000)
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert not alive(pid)
    await engine.close()


@pytest.mark.asyncio
async def test_concurrent_requests_and_cancelled_waiter(engine):
    await engine.warmup(); pid=engine._process.pid
    first=asyncio.create_task(engine.transcribe_audio(b'first',max_chars=2000))
    await asyncio.sleep(.005)
    waiter=asyncio.create_task(engine.transcribe_audio(b'cancelled',max_chars=2000))
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError): await waiter
    second=asyncio.create_task(engine.transcribe_audio(b'second',max_chars=2000))
    assert [r.text for r in await asyncio.gather(first,second)]==['synthetic first','synthetic second']
    assert engine._process.pid==pid
    await engine.close(); assert not alive(pid)


@pytest.mark.asyncio
async def test_idle_process_memory_expires(engine,monkeypatch):
    monkeypatch.setattr(isolated,'_IDLE_SECONDS',.1)
    await engine.warmup(); pid=engine._process.pid
    await asyncio.sleep(.3)
    assert engine._process is None and not alive(pid)
    await engine.close()


def test_parent_crash_kills_child_job(tmp_path):
    (tmp_path/'isolated_worker.py').write_text(WORKER)
    root=Path(__file__).resolve().parents[1]
    helper=tmp_path/'parent.py'
    helper.write_text('import asyncio,os,sys\nsys.path.insert(0,'+repr(str(root))+')\n'
        'from src.voice import isolated\nisolated.__file__='+repr(str(tmp_path/'isolated.py'))+'\n'
        'async def main():\n'
        ' e=isolated.IsolatedFasterWhisperTranscriber(local_files_only=True)\n'
        ' await e.warmup()\n print(e._process.pid,flush=True)\n os._exit(77)\n'
        'asyncio.run(main())\n',encoding='utf-8')
    result=subprocess.run([sys.executable,str(helper)],capture_output=True,timeout=10,
                          creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode==77,result.stderr.decode(errors='replace')
    pid=int(result.stdout)
    deadline=time.monotonic()+3
    while alive(pid) and time.monotonic()<deadline: time.sleep(.02)
    assert not alive(pid)


def test_invalid_limits_or_online_mode_fail_before_spawn():
    for options in ({'timeout_seconds':0},{'timeout_seconds':181},{'local_files_only':False}):
        with pytest.raises(ValueError): isolated.IsolatedFasterWhisperTranscriber(**options)
