"""Own one local Core/relay Job and bounded, evidence-gated recovery series."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import time
import threading
import urllib.request
from ctypes import wintypes
from pathlib import Path
from uuid import uuid4

WORKTREE = Path(__file__).resolve().parents[1]
CANONICAL_REPOSITORY = next(
    (path for path in (WORKTREE, *WORKTREE.parents) if path.name == "nobus-orchestrator-dev"),
    WORKTREE.parents[1] / "nobus-orchestrator-dev",
)
CODE_ROOT = CANONICAL_REPOSITORY.parent
RUNNER = WORKTREE / "scripts" / "run_telegram_mvp1.py"
SSH = Path(os.environ["SYSTEMROOT"]) / "System32" / "OpenSSH" / "ssh.exe"
LOG_ROOT = CANONICAL_REPOSITORY / ".runtime" / "logs"
PUBLIC_ORIGIN = "https://app.nobusspace.com"
RELAY_TARGET = "nobus-relay@76.13.9.125"
REVERSE_BINDING = "127.0.0.1:18765:127.0.0.1:8765"
CREATE_NO_WINDOW = 0x08000000
STARTUP_SECONDS = 360
SHUTDOWN_SECONDS = 90
READINESS_INTERVAL_SECONDS = 10
READINESS_FAILURE_LIMIT = 3
RECOVERY_RETRY_BUDGET = 10
RECOVERY_RETRY_INTERVAL_SECONDS = 60
CORE_OUTCOME_BYTES = 4096
RUNTIME_EVENT_LOG_NAME = "runner-supervisor-v2.jsonl"
RUNTIME_EVENT_LOG_BYTES = 1024 * 1024
RUNTIME_EVENT_LINE_BYTES = 2048
RUNTIME_EVENT_KEYS = frozenset({
    "schema", "series_id", "run_id", "event", "stage", "error_class",
    "supervisor_exit_code", "core_exit_code", "relay_exit_code",
    "local_ready", "public_ready", "readiness_failures",
    "attempt", "retry_budget", "recovery_disposition", "core_outcome",
    "core_outcome_error", "cleanup_outcome",
})
_EVENT_STAGES = frozenset({
    "input_validation", "setup", "job_setup", "relay_start", "core_start",
    "startup", "steady", "cleanup", "complete", "recovery_wait",
    "recovery_control",
})
_EVENT_ERRORS = frozenset({
    None, "runtime_input_missing", "supervisor_setup_failed",
    "operator_event_write_failed", "runtime_event_write_failed",
    "job_setup_failed", "relay_launch_failed", "core_launch_failed",
    "supervision_failed", "core_exit", "relay_exit", "core_and_relay_exit",
    "startup_timeout", "local_readiness_failed", "public_readiness_failed",
    "local_public_readiness_failed", "planned_stop",
})
_RECOVERY_DISPOSITIONS = frozenset({
    "pending", "complete", "retry", "stop_non_retryable",
    "stop_budget_exhausted", "stop_cleanup_failed", "stop_evidence_failed",
    "stop_planned", "reset",
})
_ATTEMPT_DISPOSITIONS = frozenset({
    "complete", "retry", "stop_non_retryable", "stop_budget_exhausted",
    "stop_cleanup_failed", "stop_evidence_failed", "stop_planned",
})
_EVIDENCE_ERRORS = frozenset({
    "operator_event_write_failed", "runtime_event_write_failed",
})
_CORE_OUTCOME_ERRORS = frozenset({
    None, "core_outcome_missing", "core_outcome_truncated",
    "core_outcome_invalid", "core_outcome_oversize", "core_outcome_unavailable",
})


def _parse_core_outcome(payload: bytes, *, overflow: bool = False):
    """Return only the Core's existing bounded safe terminal JSON."""
    if overflow or len(payload) > CORE_OUTCOME_BYTES:
        return None, "core_outcome_oversize"
    if not payload:
        return None, "core_outcome_missing"
    if payload.endswith(b"\r\n"):
        body = payload[:-2]
    elif payload.endswith(b"\n"):
        body = payload[:-1]
    else:
        return None, "core_outcome_truncated"
    if b"\r" in body or b"\n" in body:
        return None, "core_outcome_invalid"

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError
            value[key] = item
        return value

    try:
        value = json.loads(body.decode("ascii"), object_pairs_hook=unique)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None, "core_outcome_invalid"
    if type(value) is not dict or type(value.get("status")) is not str:
        return None, "core_outcome_invalid"
    if value["status"] == "FAIL":
        if (set(value) != {"status", "code"} or type(value.get("code")) is not str
                or re.fullmatch(r"[a-z][a-z0-9_]{0,95}", value["code"]) is None):
            return None, "core_outcome_invalid"
    elif value["status"] in {"STOPPED", "ALREADY_RUNNING"}:
        if set(value) != {"status"}:
            return None, "core_outcome_invalid"
    else:
        return None, "core_outcome_invalid"
    return dict(value), None


class _CoreOutcomeCapture:
    """Drain one Core stdout pipe while retaining at most a small safe candidate."""

    def __init__(self, stream, *, limit: int = CORE_OUTCOME_BYTES):
        self.stream = stream
        self.limit = limit
        self.content = bytearray()
        self.overflow = False
        self.failed = False
        self.thread = threading.Thread(target=self._drain, name="nobus-core-outcome", daemon=True)
        self.thread.start()

    def _drain(self):
        try:
            while True:
                chunk = self.stream.read(1024)
                if not chunk:
                    return
                if not isinstance(chunk, bytes):
                    self.failed = True
                    return
                remaining = max(0, self.limit - len(self.content))
                self.content.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    self.overflow = True
        except Exception:
            self.failed = True

    def finish(self):
        self.thread.join(timeout=2)
        if self.thread.is_alive() or self.failed:
            return None, "core_outcome_unavailable"
        return _parse_core_outcome(bytes(self.content), overflow=self.overflow)


def _validate_runtime_event(value, *, recorded: bool = False):
    keys = RUNTIME_EVENT_KEYS | ({"at"} if recorded else set())
    if type(value) is not dict or set(value) != keys:
        raise ValueError("runtime event fields are invalid")
    if (value["schema"] != "nobus-runtime-event-2"
            or re.fullmatch(r"[0-9a-f]{32}", value["series_id"]) is None
            or re.fullmatch(r"[0-9a-f]{32}", value["run_id"]) is None
            or value["event"] not in {
                "starting", "terminal", "recovery_wait_stopped", "recovery_reset"
            }
            or value["stage"] not in _EVENT_STAGES
            or value["error_class"] not in _EVENT_ERRORS
            or value["recovery_disposition"] not in _RECOVERY_DISPOSITIONS
            or value["core_outcome_error"] not in _CORE_OUTCOME_ERRORS
            or value["cleanup_outcome"] not in {"not_started", "proven", "failed"}):
        raise ValueError("runtime event value is invalid")
    if recorded and re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
        value["at"],
    ) is None:
        raise ValueError("runtime event timestamp is invalid")
    for name in ("supervisor_exit_code", "core_exit_code", "relay_exit_code"):
        if value[name] is not None and type(value[name]) is not int:
            raise ValueError("runtime event exit code is invalid")
    for name in ("local_ready", "public_ready"):
        if value[name] is not None and type(value[name]) is not bool:
            raise ValueError("runtime event readiness is invalid")
    if (type(value["readiness_failures"]) is not int
            or not 0 <= value["readiness_failures"] <= READINESS_FAILURE_LIMIT
            or type(value["retry_budget"]) is not int
            or not 0 <= value["retry_budget"] <= RECOVERY_RETRY_BUDGET
            or type(value["attempt"]) is not int
            or not 1 <= value["attempt"] <= value["retry_budget"] + 1):
        raise ValueError("runtime event retry data is invalid")
    if value["core_outcome"] is not None:
        try:
            encoded = json.dumps(value["core_outcome"], ensure_ascii=True, separators=(",", ":")).encode("ascii") + b"\n"
        except (TypeError, ValueError, UnicodeEncodeError):
            raise ValueError("runtime event Core outcome is invalid") from None
        parsed, error = _parse_core_outcome(encoded)
        if error is not None or parsed != value["core_outcome"]:
            raise ValueError("runtime event Core outcome is invalid")
    if value["core_outcome"] is not None and value["core_outcome_error"] is not None:
        raise ValueError("runtime event Core outcome is inconsistent")

    empty_process_fields = (
        value["core_exit_code"] is None
        and value["relay_exit_code"] is None
        and value["local_ready"] is None
        and value["public_ready"] is None
        and value["readiness_failures"] == 0
        and value["core_outcome"] is None
        and value["core_outcome_error"] is None
    )
    if value["event"] == "starting":
        if not (
            value["stage"] == "setup"
            and value["error_class"] is None
            and value["supervisor_exit_code"] is None
            and value["recovery_disposition"] == "pending"
            and value["cleanup_outcome"] == "not_started"
            and empty_process_fields
        ):
            raise ValueError("runtime event starting state is inconsistent")
    elif value["event"] == "recovery_wait_stopped":
        if not (
            value["stage"] == "recovery_wait"
            and value["error_class"] == "planned_stop"
            and value["supervisor_exit_code"] == 0
            and value["attempt"] <= value["retry_budget"]
            and value["recovery_disposition"] == "stop_planned"
            and value["cleanup_outcome"] == "proven"
            and empty_process_fields
        ):
            raise ValueError("runtime event recovery wait state is inconsistent")
    elif value["event"] == "recovery_reset":
        if not (
            value["stage"] == "recovery_control"
            and value["error_class"] is None
            and value["supervisor_exit_code"] == 0
            and value["recovery_disposition"] == "reset"
            and value["cleanup_outcome"] == "proven"
            and empty_process_fields
        ):
            raise ValueError("runtime event reset state is inconsistent")
    else:
        if (
            value["recovery_disposition"] not in _ATTEMPT_DISPOSITIONS
            or value["supervisor_exit_code"] not in {0, 1}
            or value["cleanup_outcome"] not in {"proven", "failed"}
        ):
            raise ValueError("runtime event terminal state is inconsistent")
        expected = _recovery_disposition(
            status=value["supervisor_exit_code"],
            terminal=value,
            core_outcome=value["core_outcome"],
            core_outcome_error=value["core_outcome_error"],
            cleanup_ok=value["cleanup_outcome"] == "proven",
            attempt=value["attempt"],
            retry_budget=value["retry_budget"],
        )
        if value["recovery_disposition"] != expected:
            raise ValueError("runtime event recovery disposition is inconsistent")


def _write_runtime_event(value, *, root: Path = LOG_ROOT):
    """Append one fixed-schema ASCII event; rotate only this owned bounded log."""
    _validate_runtime_event(value)
    record = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **value}
    line = json.dumps(record, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii") + b"\n"
    if len(line) > RUNTIME_EVENT_LINE_BYTES:
        raise ValueError("runtime event line is too large")
    try:
        root.mkdir(parents=True, exist_ok=True)
        if root.is_symlink() or root.is_junction():
            raise OSError
        path = root / RUNTIME_EVENT_LOG_NAME
        previous = root / (RUNTIME_EVENT_LOG_NAME + ".previous")
        for candidate in (path, previous):
            if candidate.exists() and (candidate.is_symlink() or candidate.is_junction() or not candidate.is_file()):
                raise OSError
        if path.exists() and path.stat().st_size + len(line) > RUNTIME_EVENT_LOG_BYTES:
            os.replace(path, previous)
        with path.open("ab") as stream:
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())
        if path.stat().st_size > RUNTIME_EVENT_LOG_BYTES:
            raise OSError
    except OSError:
        raise RuntimeError("runtime event write failed") from None
    return "sha256:" + hashlib.sha256(line).hexdigest()


def _runtime_record(series_id: str, run_id: str, event: str, *, attempt: int,
                    retry_budget: int, recovery_disposition: str,
                    stage: str, error_class=None,
                    supervisor_exit_code=None, core_exit_code=None, relay_exit_code=None,
                    local_ready=None, public_ready=None, readiness_failures=0,
                    core_outcome=None, core_outcome_error=None, cleanup_outcome="not_started"):
    return {
        "schema": "nobus-runtime-event-2", "series_id": series_id,
        "run_id": run_id, "event": event,
        "stage": stage, "error_class": error_class,
        "supervisor_exit_code": supervisor_exit_code,
        "core_exit_code": core_exit_code, "relay_exit_code": relay_exit_code,
        "local_ready": local_ready, "public_ready": public_ready,
        "readiness_failures": readiness_failures,
        "attempt": attempt, "retry_budget": retry_budget,
        "recovery_disposition": recovery_disposition,
        "core_outcome": core_outcome, "core_outcome_error": core_outcome_error,
        "cleanup_outcome": cleanup_outcome,
    }


def _recovery_disposition(*, status, terminal, core_outcome, core_outcome_error,
                          cleanup_ok, attempt, retry_budget):
    """Classify only explicitly safe transient failures as retryable."""
    if not cleanup_ok:
        return "stop_cleanup_failed"
    if terminal["error_class"] in _EVIDENCE_ERRORS:
        return "stop_evidence_failed"
    if terminal["error_class"] == "planned_stop":
        return "stop_planned" if status == 0 else "stop_non_retryable"
    if status == 0:
        return "complete"
    transient = (
        (
            terminal["error_class"] == "relay_exit"
            and terminal.get("stage") == "steady"
        )
        or (
            terminal["error_class"] in {"public_readiness_failed", "startup_timeout"}
            and terminal["local_ready"] is True
            and terminal["public_ready"] is False
        )
        or (
            terminal["error_class"] == "core_exit"
            and core_outcome_error is None
            and core_outcome == {"status": "FAIL", "code": "telegram_unavailable"}
        )
    )
    if not transient:
        return "stop_non_retryable"
    return "retry" if attempt <= retry_budget else "stop_budget_exhausted"


def _run_bounded_recovery(run_attempt, *, stop_event, first_attempt,
                          retry_budget, retry_interval, on_wait_stop=None):
    """Run one serial recovery series; the first attempt is not a retry."""
    if (type(first_attempt) is not int or type(retry_budget) is not int
            or not 0 <= retry_budget <= RECOVERY_RETRY_BUDGET
            or not 1 <= first_attempt <= retry_budget + 1
            or retry_interval <= 0):
        raise ValueError("recovery budget is invalid")
    for attempt in range(first_attempt, retry_budget + 2):
        outcome = run_attempt(attempt)
        if (type(outcome) is not dict
                or set(outcome) != {"status", "recovery_disposition"}
                or outcome["status"] not in {0, 1}
                or outcome["recovery_disposition"] not in _ATTEMPT_DISPOSITIONS
                or (outcome["status"] == 0) != (
                    outcome["recovery_disposition"] in {"complete", "stop_planned"}
                )
                or (
                    outcome["recovery_disposition"] == "retry"
                    and attempt > retry_budget
                )
                or (
                    outcome["recovery_disposition"] == "stop_budget_exhausted"
                    and attempt != retry_budget + 1
                )):
            raise ValueError("recovery attempt outcome is invalid")
        if outcome["status"] == 0 or outcome["recovery_disposition"] != "retry":
            return outcome["status"]
        if attempt > retry_budget:
            return 1
        if stop_event.wait(retry_interval):
            if on_wait_stop is not None:
                on_wait_stop(attempt)
            return 0
    return 1


def _decode_runtime_event(line: bytes):
    if not line.endswith(b"\n") or len(line) > RUNTIME_EVENT_LINE_BYTES + 1:
        raise ValueError("runtime history is invalid")

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError
            value[key] = item
        return value

    try:
        value = json.loads(line[:-1].decode("ascii"), object_pairs_hook=unique)
        _validate_runtime_event(value, recorded=True)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError, TypeError):
        raise ValueError("runtime history is invalid") from None
    return value


def _last_runtime_event(*, root: Path = LOG_ROOT):
    """Return the newest bounded event and a digest suitable for exact reset."""
    try:
        if root.exists() and (root.is_symlink() or root.is_junction() or not root.is_dir()):
            raise OSError
        current = root / RUNTIME_EVENT_LOG_NAME
        previous = root / (RUNTIME_EVENT_LOG_NAME + ".previous")
        for path in (current, previous):
            if path.exists() and (path.is_symlink() or path.is_junction() or not path.is_file()):
                raise OSError
        path = current if current.exists() and current.stat().st_size else previous
        if not path.exists():
            return None, None
        if path.stat().st_size > RUNTIME_EVENT_LOG_BYTES:
            raise OSError
        content = path.read_bytes()
        if not content or not content.endswith(b"\n"):
            raise OSError
        line = content.splitlines(keepends=True)[-1]
        digest = "sha256:" + hashlib.sha256(line).hexdigest()
        return _decode_runtime_event(line), digest
    except OSError:
        raise RuntimeError("runtime history unavailable") from None


def _recovery_state(*, root: Path = LOG_ROOT):
    """Resume a proven retry, or fail closed on STOP/UNKNOWN history."""
    try:
        event, digest = _last_runtime_event(root=root)
    except (RuntimeError, ValueError):
        return {"state": "blocked", "reason": "runtime_history_invalid",
                "series_id": None, "next_attempt": None, "last_digest": None}
    if event is None or event["event"] in {"recovery_reset", "recovery_wait_stopped"}:
        return {"state": "new", "reason": None, "series_id": None,
                "next_attempt": 1, "last_digest": digest}
    if event["event"] == "starting":
        return {"state": "blocked", "reason": "previous_attempt_unknown",
                "series_id": event["series_id"], "next_attempt": None,
                "last_digest": digest}
    disposition = event["recovery_disposition"]
    if event["event"] == "terminal" and disposition == "retry":
        if event["attempt"] <= event["retry_budget"]:
            return {"state": "resume", "reason": None,
                    "series_id": event["series_id"],
                    "next_attempt": event["attempt"] + 1,
                    "last_digest": digest}
        return {"state": "blocked", "reason": "runtime_history_invalid",
                "series_id": event["series_id"], "next_attempt": None,
                "last_digest": digest}
    if event["event"] == "terminal" and disposition in {"complete", "stop_planned"}:
        return {"state": "new", "reason": None, "series_id": None,
                "next_attempt": 1, "last_digest": digest}
    return {"state": "blocked", "reason": disposition,
            "series_id": event["series_id"], "next_attempt": None,
            "last_digest": digest}


def _inspect_recovery(*, root: Path = LOG_ROOT):
    state = _recovery_state(root=root)
    return {
        "schema": "nobus-recovery-control-1",
        "status": "PASS" if state["state"] != "blocked" else "STOP",
        **state,
    }


def _acknowledge_recovery_stop(expected_digest: str, *, root: Path = LOG_ROOT):
    if re.fullmatch(r"sha256:[0-9a-f]{64}", expected_digest) is None:
        raise ValueError("recovery reset digest is invalid")
    state = _recovery_state(root=root)
    event, digest = _last_runtime_event(root=root)
    if (state["state"] != "blocked" or event is None
            or digest != expected_digest or state["last_digest"] != digest):
        raise RuntimeError("recovery reset precondition failed")
    reset_digest = _write_runtime_event(_runtime_record(
        event["series_id"], uuid4().hex, "recovery_reset",
        attempt=event["attempt"], retry_budget=event["retry_budget"],
        recovery_disposition="reset", stage="recovery_control",
        supervisor_exit_code=0, cleanup_outcome="proven",
    ), root=root)
    return {
        "schema": "nobus-recovery-control-1",
        "status": "RESET",
        "reset_of_digest": expected_digest,
        "reset_event_digest": reset_digest,
    }


class StopEvent:
    """Current-session control, bound to the one supervised runtime by its mutex."""

    def __init__(self, name=r"Local\NobusSpaceBotSupervisorStop", *, request=False):
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = wintypes.HANDLE
        self.api.CreateEventW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR)
        self.api.CreateEventW.restype = handle
        self.api.OpenEventW.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
        self.api.OpenEventW.restype = handle
        self.api.SetEvent.argtypes = (handle,)
        self.api.SetEvent.restype = wintypes.BOOL
        self.api.WaitForSingleObject.argtypes = (handle, wintypes.DWORD)
        self.api.WaitForSingleObject.restype = wintypes.DWORD
        self.api.CloseHandle.argtypes = (handle,)
        self.api.CloseHandle.restype = wintypes.BOOL
        self.handle = (self.api.OpenEventW(0x2, False, name) if request else
                       self.api.CreateEventW(None, True, False, name))
        if not self.handle:
            raise RuntimeError("runtime stop control unavailable")
        if not request and ctypes.get_last_error() == 183:
            self.close()
            raise RuntimeError("runtime stop control already active")

    def set(self):
        if not self.api.SetEvent(self.handle):
            raise RuntimeError("runtime stop request failed")

    def wait(self, timeout):
        outcome = self.api.WaitForSingleObject(self.handle, int(timeout * 1000))
        if outcome not in (0, 258):
            raise RuntimeError("runtime stop control failed")
        return outcome == 0

    def is_set(self):
        return self.wait(0)

    def close(self):
        if self.handle is not None:
            handle, self.handle = self.handle, None
            if not self.api.CloseHandle(handle):
                raise RuntimeError("runtime stop control close failed")


def _operator_event(code):
    if code not in {"starting", "stopped", "runtime_failed", "cleanup_failed"}:
        raise ValueError("runtime event is invalid")
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    path = LOG_ROOT / "runner-supervisor.log"
    if path.exists() and path.stat().st_size > 5 * 1024 * 1024:
        # Stop if bounded logging cannot continue; retention is operator-owned.
        raise RuntimeError("runtime log capacity exhausted")
    with path.open("a", encoding="ascii") as stream:
        stream.write(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + " " + code + "\n")


def _job_api():
    if str(WORKTREE) not in sys.path:
        sys.path.insert(0, str(WORKTREE))
    from src.workers.windows_job import _Kernel32JobApi
    return _Kernel32JobApi()


def _gated_child(argv: list[str]) -> int:
    # The base interpreter cannot fork a venv redirector before Job assignment.
    # This helper runs only local supervisor-supplied argv; no remote input.
    try:
        if len(argv) < 3 or argv[1] != "--" or sum(map(len, argv)) > 16384:
            return 125
        gate, command = argv[0], argv[2:]
        import re
        if re.fullmatch(r"Local\\NobusOrchestrator-[0-9a-f]{32}", gate) is None:
            return 125
        target = Path(command[0]).resolve(strict=True)
        if not target.is_file() or not Path(command[0]).is_absolute():
            return 125
        helper = WORKTREE / "src" / "workers" / "windows_job_helper.py"
        spec = importlib.util.spec_from_file_location("nobus_runtime_gate", helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module._wait_for_gate(gate)
        child = subprocess.Popen(command, stdin=sys.stdin.buffer,
                                 stdout=sys.stdout.buffer, stderr=sys.stderr.buffer,
                                 creationflags=CREATE_NO_WINDOW, close_fds=True)
        return child.wait()
    except BaseException:
        return 125


def spawn_owned(api, job: int, command: list[str], *, stdout=subprocess.DEVNULL):
    gate, name = api.create_gate()
    process = None
    try:
        process = subprocess.Popen(
            [str(Path(sys._base_executable).with_name("python.exe")), "-I", "-S", str(Path(__file__).resolve()),
             "--gated-child", name, "--", *command],
            cwd=WORKTREE, stdin=subprocess.PIPE, stdout=stdout,
            stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW,
            env={key: value for key, value in os.environ.items() if key.upper() in
                 {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "USERPROFILE",
                  "PROGRAMDATA", "LOCALAPPDATA", "APPDATA", "USERNAME", "USERDOMAIN", "COMSPEC"}},
        )
        api.assign(job, process.pid)
        api.signal(gate)
        process._nobus_gate = gate
        gate = None  # Keep the event alive until the gated helper has exited.
        return process
    except BaseException:
        if process is not None:
            process.kill()
            process.wait(timeout=10)
        raise RuntimeError("owned runtime launch failed") from None
    finally:
        if gate is not None:
            api.close(gate)


def close_owned(api, process):
    process.wait(timeout=10)
    process.stdin.close()
    gate = getattr(process, "_nobus_gate", None)
    if gate is not None:
        api.close(gate)
        process._nobus_gate = None


def wait_job_empty(job: int) -> bool:
    class Accounting(ctypes.Structure):
        _fields_ = [(name, ctypes.c_int64) for name in ("user", "kernel", "period_user", "period_kernel")] + [
            (name, wintypes.DWORD) for name in ("faults", "total", "active", "terminated")]
    native = ctypes.WinDLL("kernel32", use_last_error=True)
    native.QueryInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p)
    native.QueryInformationJobObject.restype = wintypes.BOOL
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        information = Accounting()
        if not native.QueryInformationJobObject(job, 1, ctypes.byref(information), ctypes.sizeof(information), None):
            return False
        if information.active == 0:
            return True
        time.sleep(.02)
    return False


def stop_process(process, *, graceful: bool = False) -> bool:
    if process is None or process.poll() is not None:
        return True
    if graceful:
        try:
            process.stdin.write(b"stop\n")
            process.stdin.flush()
            process.wait(timeout=SHUTDOWN_SECONDS)
            return process.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False  # Caller terminates its Job, including every descendant.
    return False


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


class _ReadinessProbe:
    """One read-only daemon slot; timed-out/DNS-stalled work cannot accumulate."""

    def __init__(self):
        self._lock = threading.Lock()
        self._thread = None

    def run(self, read, *, seconds, stop_event=None):
        deadline = time.monotonic() + seconds
        if stop_event is not None and stop_event.is_set():
            return False
        done = threading.Event()
        result = [False]

        def work():
            try:
                result[0] = read() is True
            except Exception:
                pass
            finally:
                done.set()

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            worker = threading.Thread(target=work, name="nobus-readiness", daemon=True)
            self._thread = worker
            worker.start()
        while True:
            if stop_event is not None and stop_event.is_set():
                return False
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            if done.wait(min(.05, remaining)):
                worker.join(timeout=max(0.0, deadline - time.monotonic()))
                # Never consume a late PASS or carry it into another request.
                return (not worker.is_alive() and time.monotonic() < deadline
                        and (stop_event is None or not stop_event.is_set())
                        and result[0])


_READINESS_PROBE = _ReadinessProbe()


def _ready_request(url, *, seconds, headers=None, stop_event=None):
    def read():
        request = urllib.request.Request(url, headers={"User-Agent": "NobusSpace-Health/1.0", **(headers or {})})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        with opener.open(request, timeout=seconds) as response:
            return response.status == 200 and response.read(256) == b'{"status":"ready"}'
    return _READINESS_PROBE.run(read, seconds=seconds, stop_event=stop_event)


def ready(*, stop_event=None) -> bool:
    return _ready_request("http://127.0.0.1:8765/readyz", seconds=2,
                          headers={"Host": "app.nobusspace.com"}, stop_event=stop_event)


def public_ready(*, stop_event=None) -> bool:
    return _ready_request(PUBLIC_ORIGIN + "/readyz", seconds=5, stop_event=stop_event)


def _readiness_pair(stop_event):
    local = ready(stop_event=stop_event)
    public = public_ready(stop_event=stop_event)
    return local, public


def _readiness_error(local: bool, public: bool) -> str:
    if not local and not public:
        return "local_public_readiness_failed"
    return "local_readiness_failed" if not local else "public_readiness_failed"


def supervise(api, job, relay, core, stop_event, *, clock=time.monotonic, probe=None,
              report=None) -> int:
    if probe is None:
        probe = lambda: _readiness_pair(stop_event)
    if report is None:
        report = lambda _value: None

    def readiness():
        result = probe()
        if type(result) is bool:  # Compatibility for existing deterministic C5 fixtures.
            return result, result
        if (type(result) is not tuple or len(result) != 2
                or any(type(item) is not bool for item in result)):
            raise ValueError("readiness result is invalid")
        return result

    def child_exit(stage):
        relay_code = relay.poll()
        core_code = core.poll()
        if relay_code is None and core_code is None:
            return False
        error = ("core_and_relay_exit" if relay_code is not None and core_code is not None
                 else ("core_exit" if core_code is not None else "relay_exit"))
        report({"stage": stage, "error_class": error,
                "core_exit_code": core_code, "relay_exit_code": relay_code,
                "local_ready": None, "public_ready": None,
                "readiness_failures": 0})
        return True

    deadline = clock() + STARTUP_SECONDS
    last_local = last_public = None
    while not stop_event.is_set() and clock() < deadline:
        if child_exit("startup"):
            return 1
        local, public = readiness()
        last_local, last_public = local, public
        if local and public:
            break
        stop_event.wait(1)
    else:
        stopped = stop_event.is_set()
        report({"stage": "startup", "error_class": "planned_stop" if stopped else "startup_timeout",
                "core_exit_code": None, "relay_exit_code": None,
                "local_ready": last_local, "public_ready": last_public,
                "readiness_failures": 0})
        return 0 if stopped else 1
    failures = 0
    while not stop_event.wait(READINESS_INTERVAL_SECONDS):
        if child_exit("steady"):
            return 1
        local, public = readiness()
        failures = 0 if local and public else failures + 1
        if failures >= READINESS_FAILURE_LIMIT:
            report({"stage": "steady", "error_class": _readiness_error(local, public),
                    "core_exit_code": None, "relay_exit_code": None,
                    "local_ready": local, "public_ready": public,
                    "readiness_failures": failures})
            return 1
    report({"stage": "steady", "error_class": "planned_stop",
            "core_exit_code": None, "relay_exit_code": None,
            "local_ready": None, "public_ready": None,
            "readiness_failures": failures})
    return 0


def _arguments(argv=None):
    parser = argparse.ArgumentParser()
    commands = parser.add_mutually_exclusive_group()
    commands.add_argument("--stop", action="store_true")
    commands.add_argument("--check-ready", action="store_true")
    commands.add_argument("--inspect-recovery", action="store_true")
    commands.add_argument("--acknowledge-recovery-stop")
    parser.add_argument("--semantic-admission", action="store_true")
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--voice-model-directory", type=Path)
    parser.add_argument("--backup-root", type=Path)
    parser.add_argument("--backup-ownership")
    return parser.parse_args(argv)


def core_command(python: Path, values) -> list[str]:
    command = [str(python), str(RUNNER), "--serve", "--timeout", "30",
               "--shutdown-stdin", "--miniapp-bind", "127.0.0.1",
               "--miniapp-port", "8765", "--miniapp-origin", PUBLIC_ORIGIN]
    if values.semantic_admission:
        command.append("--semantic-admission")
    for name in ("runtime_root", "voice_model_directory", "backup_root"):
        value = getattr(values, name, None)
        if value is not None:
            if not value.is_absolute() or not value.is_dir():
                raise ValueError("runtime composition is invalid")
            for candidate in (value, *value.parents):
                if candidate.is_symlink() or candidate.is_junction():
                    raise ValueError("runtime composition is invalid")
            command.extend(["--" + name.replace("_", "-"), str(value.resolve(strict=True))])
    backup_owner = getattr(values, "backup_ownership", None)
    if bool(getattr(values, "backup_root", None)) != bool(backup_owner):
        raise ValueError("backup root and ownership must be supplied together")
    if backup_owner:
        command.extend(["--backup-ownership", backup_owner])
    return command


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--gated-child":
        return _gated_child(sys.argv[2:])
    if str(WORKTREE) not in sys.path:
        sys.path.insert(0, str(WORKTREE))
    from src.application.windows_singleton import WindowsNamedMutex, RunnerAlreadyActive
    try:
        values = _arguments()
        if values.check_ready:
            local = ready()
            public = public_ready()
            healthy = local and public
            print('{"status":"PASS"}' if healthy else '{"status":"FAIL"}')
            return 0 if healthy else 1
        if values.inspect_recovery:
            print(json.dumps(
                _inspect_recovery(), ensure_ascii=True,
                separators=(",", ":"), sort_keys=True,
            ))
            return 0
        if values.stop:
            event = StopEvent(request=True)
            try:
                event.set()
                print('{"status":"stop_requested"}')
                return 0
            finally:
                event.close()
        if values.acknowledge_recovery_stop:
            try:
                with WindowsNamedMutex(r"Global\NobusSpaceBotSupervisor"):
                    result = _acknowledge_recovery_stop(
                        values.acknowledge_recovery_stop
                    )
            except RunnerAlreadyActive:
                return 1
            print(json.dumps(
                result, ensure_ascii=True, separators=(",", ":"), sort_keys=True
            ))
            return 0
        with WindowsNamedMutex(r"Global\NobusSpaceBotSupervisor"):
            return _recover(values)
    except RunnerAlreadyActive:
        return 0
    except Exception:
        return 1


def _with_stop_control(callback) -> int:
    stop_event = None
    previous_signals = {}
    status = 1
    try:
        stop_event = StopEvent()
        for named_signal in (signal.SIGINT, signal.SIGTERM):
            previous_signals[named_signal] = signal.signal(
                named_signal, lambda *_: stop_event.set()
            )
        status = callback(stop_event)
    except Exception:
        status = 1
    finally:
        if stop_event is not None:
            try:
                stop_event.close()
            except Exception:
                status = 1
        for named_signal, handler in previous_signals.items():
            signal.signal(named_signal, handler)
    return status


def _recover(values) -> int:
    state = _recovery_state()
    if state["state"] == "blocked":
        return 1
    series_id = state["series_id"] or uuid4().hex

    def controlled(stop_event):
        def attempt(number):
            return _run_attempt(
                values,
                stop_event=stop_event,
                series_id=series_id,
                attempt=number,
                retry_budget=RECOVERY_RETRY_BUDGET,
            )

        def wait_stopped(number):
            _write_runtime_event(_runtime_record(
                series_id, uuid4().hex, "recovery_wait_stopped",
                attempt=number, retry_budget=RECOVERY_RETRY_BUDGET,
                recovery_disposition="stop_planned", stage="recovery_wait",
                error_class="planned_stop", supervisor_exit_code=0,
                cleanup_outcome="proven",
            ))

        return _run_bounded_recovery(
            attempt,
            stop_event=stop_event,
            first_attempt=state["next_attempt"],
            retry_budget=RECOVERY_RETRY_BUDGET,
            retry_interval=RECOVERY_RETRY_INTERVAL_SECONDS,
            on_wait_stop=wait_stopped,
        )

    return _with_stop_control(controlled)


def _main(values) -> int:
    """Run one attempt for deterministic drills; production uses _recover."""
    return _with_stop_control(
        lambda stop_event: _run_attempt(
            values,
            stop_event=stop_event,
            series_id=uuid4().hex,
            attempt=1,
            retry_budget=RECOVERY_RETRY_BUDGET,
        )["status"]
    )


def _run_attempt(values, *, stop_event, series_id, attempt, retry_budget):
    python = Path(sys.executable).with_name("python.exe").resolve()
    private_key = Path.home() / ".ssh" / "nobus-space-vps-relay"
    known_hosts = Path.home() / ".ssh" / "nobus-space-vps-known_hosts"
    run_id = uuid4().hex
    terminal = {"stage": "input_validation", "error_class": "runtime_input_missing",
                "core_exit_code": None, "relay_exit_code": None,
                "local_ready": None, "public_ready": None,
                "readiness_failures": 0}
    api = None
    job = None
    relay = core = None
    core_capture = None
    status = 1
    try:
        for required in (WORKTREE, CANONICAL_REPOSITORY, python, RUNNER, SSH, private_key, known_hosts):
            if not required.exists():
                raise RuntimeError("runtime input unavailable")
        command = core_command(python, values)
        terminal.update(stage="setup", error_class="supervisor_setup_failed")
        api = _job_api()
        terminal.update(error_class="operator_event_write_failed")
        _operator_event("starting")
        terminal.update(error_class="runtime_event_write_failed")
        _write_runtime_event(_runtime_record(
            series_id, run_id, "starting", attempt=attempt,
            retry_budget=retry_budget, recovery_disposition="pending",
            stage="setup",
        ))
        terminal.update(stage="job_setup", error_class="job_setup_failed")
        job = api.create_job()
        terminal.update(stage="relay_start", error_class="relay_launch_failed")
        relay = spawn_owned(api, job, [str(SSH), "-NT", "-F", "NUL", "-i", str(private_key),
            "-o", "BatchMode=yes", "-o", "UserKnownHostsFile=" + str(known_hosts),
            "-o", "StrictHostKeyChecking=yes", "-o", "IdentitiesOnly=yes",
            "-o", "KexAlgorithms=curve25519-sha256", "-o", "ExitOnForwardFailure=yes",
            "-o", "ServerAliveInterval=20", "-o", "ServerAliveCountMax=3",
            "-o", "ConnectTimeout=15", "-R", REVERSE_BINDING, RELAY_TARGET])
        if not stop_event.wait(2) and relay.poll() is None:
            terminal.update(stage="core_start", error_class="core_launch_failed")
            core = spawn_owned(api, job, command, stdout=subprocess.PIPE)
            if getattr(core, "stdout", None) is not None:
                core_capture = _CoreOutcomeCapture(core.stdout)
            terminal.update(stage="startup", error_class="supervision_failed")
            status = supervise(api, job, relay, core, stop_event,
                               report=lambda value: terminal.update(value))
        elif stop_event.is_set():
            terminal.update(stage="setup", error_class="planned_stop")
            status = 0
        else:
            terminal.update(stage="relay_start", error_class="relay_exit",
                            relay_exit_code=relay.poll())
    except Exception:
        status = 1
    finally:
        cleanup_ok = True
        try:
            cleanup_ok = stop_process(core, graceful=True)
        except Exception:
            cleanup_ok = False
        if job is not None:
            try:
                api.terminate(job)
                cleanup_ok = wait_job_empty(job) and cleanup_ok
            except Exception:
                cleanup_ok = False
            try:
                api.close(job)
            except Exception:
                cleanup_ok = False
        for child in (core, relay):
            if child is not None and api is not None:
                try:
                    close_owned(api, child)
                except Exception:
                    cleanup_ok = False
        core_outcome = None
        core_outcome_error = None
        if core_capture is not None:
            core_outcome, core_outcome_error = core_capture.finish()
        elif core is not None:
            core_outcome_error = "core_outcome_missing"
        if not cleanup_ok:
            status = 1
        try:
            _operator_event("cleanup_failed" if not cleanup_ok else
                            ("stopped" if status == 0 else "runtime_failed"))
        except Exception:
            status = 1
            terminal.update(stage="cleanup", error_class="operator_event_write_failed")
        disposition = _recovery_disposition(
            status=status,
            terminal=terminal,
            core_outcome=core_outcome,
            core_outcome_error=core_outcome_error,
            cleanup_ok=cleanup_ok,
            attempt=attempt,
            retry_budget=retry_budget,
        )
        try:
            _write_runtime_event(_runtime_record(
                series_id, run_id, "terminal", attempt=attempt,
                retry_budget=retry_budget, recovery_disposition=disposition,
                stage=terminal["stage"],
                error_class=terminal["error_class"], supervisor_exit_code=status,
                core_exit_code=terminal["core_exit_code"],
                relay_exit_code=terminal["relay_exit_code"],
                local_ready=terminal["local_ready"],
                public_ready=terminal["public_ready"],
                readiness_failures=terminal["readiness_failures"],
                core_outcome=core_outcome, core_outcome_error=core_outcome_error,
                cleanup_outcome="proven" if cleanup_ok else "failed",
            ))
        except Exception:
            status = 1
            disposition = "stop_evidence_failed"
    return {"status": status, "recovery_disposition": disposition}


if __name__ == "__main__":
    raise SystemExit(main())
