"""One bounded Windows ASR process; no second queue or audio files."""
from __future__ import annotations

import asyncio
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import time

from .base import TranscriptResult, VoiceTranscriptionError
from .faster_whisper import FasterWhisperTranscriber

_AUDIO_LIMIT = 10 * 1024**2
_RESPONSE_LIMIT = 64 * 1024
_IDLE_SECONDS = 60


class IsolatedFasterWhisperTranscriber:
    """Keep a warm model, kill its Job on timeout/cancel/close or parent death.

    The child blocks on stdin until the parent assigns the Job. Configuration
    and audio travel only over bounded anonymous pipes, never argv or files.
    Sixty seconds of inactivity also destroys the model's process memory.
    """

    def __init__(self, *, timeout_seconds: float = 180, **options) -> None:
        if os.name != 'nt':
            raise ValueError('isolated voice requires Windows Job Objects')
        if isinstance(timeout_seconds, bool) or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 180:
            raise ValueError('voice timeout is invalid')
        FasterWhisperTranscriber(**options)  # Validate before starting a child.
        if options.get('local_files_only') is not True:
            raise ValueError('isolated voice requires local model files')
        self._options = {key: str(value) if isinstance(value, Path) else value for key, value in options.items()}
        self._timeout = timeout_seconds
        self._lock = asyncio.Lock()
        self._process = None
        self._job = None
        self._closed = False
        self._idle = None
        self._last_used = 0.0
        self._active = None
        from src.workers.windows_job import _Kernel32JobApi
        self._api = _Kernel32JobApi()

    async def warmup(self) -> None:
        result = await self._request(b'', 0, min(120, self._timeout))
        if result != {'ready': True}:
            raise VoiceTranscriptionError('voice model warmup failed')

    async def transcribe_audio(self, audio: bytes, *, max_chars: int) -> TranscriptResult:
        if type(audio) is not bytes or not 0 < len(audio) <= _AUDIO_LIMIT or type(max_chars) is not int or not 0 < max_chars <= 2000:
            raise VoiceTranscriptionError('voice input is invalid')
        result = await self._request(audio, max_chars, self._timeout)
        failed = False
        try:
            return TranscriptResult.model_validate(result)
        except Exception:
            failed = True
        if failed:
            raise VoiceTranscriptionError('voice recognition failed')
        raise AssertionError('unreachable')

    async def transcribe(self, path: Path, *, max_chars: int) -> TranscriptResult:
        # Compatibility with the existing service protocol; production uses bytes.
        failed = False
        try:
            with path.open('rb') as stream:
                audio = stream.read(_AUDIO_LIMIT + 1)
        except OSError:
            failed = True
        if failed:
            raise VoiceTranscriptionError('voice input is invalid')
        return await self.transcribe_audio(audio, max_chars=max_chars)

    async def _start(self) -> None:
        if self._process is not None and self._process.returncode is None:
            return
        await self._stop()
        # Launch the actual interpreter, not the venv redirector: a redirector
        # can spawn a child before Job assignment, escaping future Job cleanup.
        self._job = self._api.create_job(memory_limit_bytes=4 * 1024**3,
                                        active_process_limit=1, affinity_mask=15)
        env = {key: value for key, value in os.environ.items() if key.upper() in
               {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'USERPROFILE', 'LOCALAPPDATA'}}
        env.update(HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', DO_NOT_TRACK='1',
                   OMP_NUM_THREADS='4', OPENBLAS_NUM_THREADS='4')
        spawn = asyncio.create_task(asyncio.create_subprocess_exec(
            sys._base_executable, '-I', '-S', str(Path(__file__).with_name('isolated_worker.py')),
            str(Path(sys.prefix) / 'Lib' / 'site-packages'),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, env=env,
            creationflags=subprocess.CREATE_NO_WINDOW))
        try:
            self._process = await asyncio.shield(spawn)
        except asyncio.CancelledError:
            # Retain ownership even if cancellation races with OS process creation.
            while not spawn.done():
                try:
                    await asyncio.shield(spawn)
                except asyncio.CancelledError:
                    continue
            self._process = spawn.result()
            raise
        self._api.assign(self._job, self._process.pid)
        config = json.dumps(self._options, ensure_ascii=True).encode('ascii')
        if len(config) > 16384:
            raise ValueError('voice configuration exceeds limit')
        self._process.stdin.write(struct.pack('!I', len(config)) + config)
        await self._process.stdin.drain()

    async def _request(self, audio: bytes, max_chars: int, timeout: float) -> dict:
        async with self._lock:
            if self._closed:
                raise VoiceTranscriptionError('voice recognizer is closed')
            if self._idle is not None:
                self._idle.cancel()
                self._idle = None
            self._active = asyncio.current_task()
            failed = False
            cancelled = False
            try:
                async with asyncio.timeout(timeout):
                    await self._start()
                    self._process.stdin.write(struct.pack('!II', len(audio), max_chars) + audio)
                    await self._process.stdin.drain()
                    size = struct.unpack('!I', await self._process.stdout.readexactly(4))[0]
                    if not 0 < size <= _RESPONSE_LIMIT:
                        raise ValueError('voice response exceeds limit')
                    result = json.loads(await self._process.stdout.readexactly(size))
                    if not isinstance(result, dict) or result.get('error'):
                        raise ValueError('voice recognition failed')
                self._last_used = time.monotonic()
                self._active = None
                self._idle = asyncio.get_running_loop().call_later(_IDLE_SECONDS, self._schedule_idle)
                return result
            except asyncio.CancelledError:
                cancelled = True
            except Exception:
                failed = True
            # Cleanup is awaited before releasing the serialization lock. A new
            # request cannot start while the failed native process still exists.
            cleanup = asyncio.create_task(self._stop())
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    cancelled = True
            cleanup.result()
            self._active = None
            if cancelled:
                raise asyncio.CancelledError()
            if failed:
                raise VoiceTranscriptionError('voice recognition failed')
        raise AssertionError('unreachable')

    def _schedule_idle(self) -> None:
        task = asyncio.create_task(self._expire_idle())
        task.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)

    async def _expire_idle(self) -> None:
        async with self._lock:
            remaining = _IDLE_SECONDS - (time.monotonic() - self._last_used)
            if remaining <= 0:
                await self._stop()
            else:
                # Event-loop timers may fire one clock-resolution tick early.
                self._idle = asyncio.get_running_loop().call_later(remaining, self._schedule_idle)

    async def _stop(self) -> None:
        if self._idle is not None:
            self._idle.cancel()
            self._idle = None
        process, job = self._process, self._job
        failed = False
        if job is not None:
            try:
                self._api.close(job)  # KILL_ON_JOB_CLOSE, including parent death.
                self._job = None
            except Exception:
                failed = True
        if process is not None:
            try:
                if process.returncode is None:
                    process.kill()  # Also covers a launch cancelled before assignment.
                await asyncio.wait_for(process.wait(), 5)
                if process.stdin is not None:
                    process.stdin.close()
                self._process = None
            except Exception:
                failed = True
        if failed:
            self._closed = True  # No restart when cleanup was not proven.
            raise VoiceTranscriptionError('voice process cleanup failed')

    async def close(self) -> None:
        self._closed = True
        if self._active is not None and self._active is not asyncio.current_task():
            self._active.cancel()
        async with self._lock:
            await self._stop()
