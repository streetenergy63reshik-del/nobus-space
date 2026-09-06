"""Private stdio worker. Wait for Job assignment before importing native code."""
import gc
import json
import os
from pathlib import Path
import struct
import sys
import threading


def _read(stream, size):
    data = stream.read(size)
    if len(data) != size:
        raise EOFError
    return data


def main():
    source = sys.stdin.buffer
    sink = os.fdopen(os.dup(sys.stdout.fileno()), 'wb')
    # Native/Python diagnostic output must not corrupt the bounded protocol.
    with open(os.devnull, 'wb') as null:
        os.dup2(null.fileno(), sys.stdout.fileno())
    size = struct.unpack('!I', _read(source, 4))[0]
    if not 0 < size <= 16384:
        return
    options = json.loads(_read(source, size))
    # Parent sends config only after assigning this child to its kill-on-close Job.
    # Fixed parent runtime dependency directory; never execute venv .pth files.
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_dir():
        return
    sys.path.insert(0, sys.argv[1])
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from src.voice.faster_whisper import FasterWhisperTranscriber
    def deny_network(event, args):
        if event in {'socket.connect', 'socket.getaddrinfo'}:
            raise OSError('offline voice worker')
    sys.addaudithook(deny_network)
    transcriber = FasterWhisperTranscriber(**options)
    while True:
        try:
            size, max_chars = struct.unpack('!II', _read(source, 8))
        except EOFError:
            return
        if size > 10 * 1024**2 or (size and not 0 < max_chars <= 2000) or (not size and max_chars):
            return
        audio = _read(source, size)
        try:
            if size:
                result = transcriber._audio_sync(audio, max_chars, threading.Event()).model_dump(mode='json')
            else:
                transcriber._warmup_sync()
                result = {'ready': True}
            body = json.dumps(result, ensure_ascii=True, allow_nan=False).encode('ascii')
            if len(body) > 64 * 1024:
                raise ValueError
        except Exception:
            body = b'{"error":true}'
        sink.write(struct.pack('!I', len(body)) + body)
        sink.flush()
        audio = result = body = None
        gc.collect()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Never print model exceptions, audio, transcript or local paths.
        sys.exit(1)
