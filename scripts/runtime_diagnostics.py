"""Bounded technical observations. Raw child output never leaves memory."""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

RELAY_CAUSES = frozenset({
    "transport_timeout", "transport_refused", "transport_reset", "transport_unreachable",
    "authentication", "host_verification", "key", "configuration", "unknown",
})
TRANSIENT_RELAY_CAUSES = frozenset({
    "transport_timeout", "transport_refused", "transport_reset", "transport_unreachable",
})


def classify_relay(payload: bytes, *, complete: bool = True) -> str:
    """Recognize OpenSSH diagnostics, with permanent/ambiguous evidence winning.

    The full stream must fit the bound and end normally. A matched remote banner
    alone cannot authorize retry: require the OpenSSH transport error prefix.
    """
    if not complete or len(payload) > 8192:
        return "unknown"
    text = payload.decode("ascii", errors="replace").lower()
    permanent = (
        ("host_verification", ("host key verification failed", "remote host identification has changed")),
        ("authentication", ("permission denied", "authentication failed", "too many authentication failures")),
        ("key", ("load key ", "identity file ", "invalid format", "unprotected private key")),
        ("configuration", ("bad configuration", "bad forwarding", "remote port forwarding failed", "unknown option", "no matching ")),
    )
    for category, patterns in permanent:
        if any(pattern in text for pattern in patterns):
            return category
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    host = r"[a-z0-9_.:%\[\]-]+"
    endings = {
        "connection timed out": "transport_timeout",
        "connection refused": "transport_refused",
        "connection reset by peer": "transport_reset",
        "broken pipe": "transport_reset",
        "no route to host": "transport_unreachable",
        "network is unreachable": "transport_unreachable",
    }
    def transport_line(line):
        for suffix, category in endings.items():
            prefix = (rf"(?:ssh: connect to host {host} port [0-9]+|"
                      rf"read from remote host {host}|client_loop: send disconnect)")
            if re.fullmatch(prefix + ": " + re.escape(suffix), line):
                return category
        if re.fullmatch(rf"timeout, server {host} not responding\.", line):
            return "transport_timeout"
        if re.fullmatch(rf"connection to {host} closed by remote host\.", line):
            # EOF/EPIPE is an established transport loss, not an auth decision.
            return "transport_reset"
        return "unknown"

    if len(lines) == 1:
        return transport_line(lines[0])
    # OpenSSH can report the failed read and then the failed disconnect packet.
    # Accept only that complete ordered pair with matching categories. Arbitrary
    # banners, conflicting errors, truncation and permanent failures stay STOP.
    if (len(lines) == 2 and
            (lines[0].startswith("read from remote host ") or
             lines[0].startswith("connection to ")) and
            lines[1].startswith("client_loop: send disconnect: ")):
        first, second = map(transport_line, lines)
        if first == second:
            return first
    return "unknown"


class RelayCapture:
    def __init__(self, stream, *, limit=8192):
        self.stream, self.limit = stream, limit
        self.content = bytearray()
        self.overflow = self.failed = False
        self.thread = threading.Thread(target=self._drain, daemon=True, name="nobus-relay-diagnostic")
        self.thread.start()

    def _drain(self):
        try:
            while chunk := self.stream.read(1024):
                available = self.limit - len(self.content)
                self.content.extend(chunk[:available])
                self.overflow |= len(chunk) > available
        except Exception:
            self.failed = True

    def finish(self):
        self.thread.join(2)
        complete = not (self.thread.is_alive() or self.failed or self.overflow)
        result = classify_relay(bytes(self.content), complete=complete)
        if not self.thread.is_alive():
            self.content.clear()
            self.stream.close()
        return result


def write_diagnostic(root: Path, kind: str, value: dict):
    """Only safe, typed fields; append-only archived journal, never raw output."""
    from scripts import run_nobus_space_live as s
    if kind not in {"readiness", "health"} or set(value) != {"run_id", "attempt", "stage", "checks"}:
        raise ValueError("diagnostic schema invalid")
    if (not isinstance(value["run_id"], str) or s.re.fullmatch("[0-9a-f]{32}", value["run_id"]) is None
            or type(value["attempt"]) is not int or not 0 <= value["attempt"] <= 11
            or value["stage"] not in {"startup", "steady", "health"}
            or type(value["checks"]) is not list or len(value["checks"]) > 6):
        raise ValueError("diagnostic value invalid")
    for check in value["checks"]:
        if type(check) is not dict or set(check) != {"boundary", "status", "at", "http_status", "body_matches", "error_class", "elapsed_ms", "deadline_ms"}:
            raise ValueError("diagnostic check invalid")
        if (check["boundary"] not in {"local", "public", "databases", "task-runtime.sqlite3", "telegram-state.sqlite3", "telegram-checkpoint.sqlite3", "business-notes.sqlite3"}
                or check["status"] not in {"PASS", "FAIL", "NOT CHECKED"}
                or check["error_class"] not in {None, "deadline", "cancelled", "probe_busy", "http_error", "transport_error", "probe_error", "response_mismatch", "database_failed", "database_degraded", "database_missing", "not_run"}
                or type(check["body_matches"]) is not bool
                or s.re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", check["at"]) is None
                or (check["http_status"] is not None and (type(check["http_status"]) is not int or not 100 <= check["http_status"] <= 599))
                or any(type(check[k]) is not int or not 0 <= check[k] <= 120000 for k in ("elapsed_ms", "deadline_ms"))):
            raise ValueError("diagnostic check value invalid")
    root = Path(root)
    identity = s._plain_root(root, create=True)
    path = root / (kind + ".jsonl")
    previous = root / (kind + ".previous.jsonl")
    for item in (path, previous):
        if item.exists() and (s._path_is_reparse(item) or not item.is_file() or not s._single_link_file(item) or item.stat().st_size > 1024 * 1024):
            raise OSError("diagnostic target invalid")
    record = {"schema": "nobus-runtime-diagnostic-1", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **value}
    record["authentication"] = s._authentication(record, entropy=b"nobus:diagnostic:1")
    line = s._canonical_ascii(record) + b"\n"
    if len(line) > 4096:
        raise ValueError("diagnostic size invalid")
    if path.exists() and path.stat().st_size + len(line) > 1024 * 1024:
        # ponytail: archives accumulate until an explicitly approved retention policy exists.
        archive = root / (kind + ".previous." + uuid4().hex + ".jsonl")
        if archive.exists():
            raise OSError("diagnostic archive collision")
        os.rename(path, archive)
    if identity != s._plain_root(root, create=False):
        raise OSError("diagnostic root changed")
    with path.open("ab") as stream:
        metadata = os.fstat(stream.fileno())
        if metadata.st_nlink != 1:
            raise OSError("diagnostic link invalid")
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())
        current = path.stat(follow_symlinks=False)
        if (metadata.st_dev, metadata.st_ino) != (current.st_dev, current.st_ino) or s._path_is_reparse(path):
            raise OSError("diagnostic target changed")


def start_loop_stall_capture(loop, runtime_root: Path):
    """Capture only the blocked Core stack, never task content or locals."""
    from src.application.runtime_maintenance import checked_path

    owner_thread = threading.get_ident()
    stopped = threading.Event()
    last_beat = [time.monotonic()]

    def beat():
        last_beat[0] = time.monotonic()
        if not stopped.is_set():
            loop.call_later(0.25, beat)

    loop.call_soon(beat)

    def watch():
        captured = False
        while not stopped.wait(0.25):
            lag = time.monotonic() - last_beat[0]
            if lag < 0.75:
                captured = False
            if lag < 1.5 or captured:
                continue
            captured = True
            frame = sys._current_frames().get(owner_thread)
            if frame is None:
                continue
            stack = []
            while frame is not None and len(stack) < 24:
                stack.append([Path(frame.f_code.co_filename).name,
                              frame.f_code.co_name, frame.f_lineno])
                frame = frame.f_back
            record = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                      "lag_ms": round(lag * 1000), "stack": stack}
            line = json.dumps(record, ensure_ascii=True, separators=(",", ":")).encode() + b"\n"
            try:
                path = checked_path(runtime_root / "core-loop-stalls.jsonl", root=runtime_root)
                if len(line) > 4096 or (path.exists() and path.stat().st_size + len(line) > 128 * 1024):
                    continue  # Fixed capture ceiling; never prune or replace evidence.
                with path.open("ab") as stream:
                    metadata = os.fstat(stream.fileno())
                    current = checked_path(path, root=runtime_root).stat(follow_symlinks=False)
                    if (metadata.st_nlink != 1 or
                            (metadata.st_dev, metadata.st_ino) != (current.st_dev, current.st_ino)):
                        continue
                    stream.write(line)
                    stream.flush()
                    os.fsync(stream.fileno())
            except (OSError, ValueError):
                pass  # Diagnostic failure must not change product authority.

    thread = threading.Thread(target=watch, name="nobus-core-loop-stall", daemon=True)
    thread.start()

    def close():
        stopped.set()
        thread.join(timeout=1)

    return close
