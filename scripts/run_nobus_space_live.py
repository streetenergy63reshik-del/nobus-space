"""Run the local Nobus Core and its restricted public reverse relay."""

from __future__ import annotations

import atexit
import ctypes
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from ctypes import wintypes
from pathlib import Path


WORKTREE = Path(__file__).resolve().parents[1]
CODE_ROOT = WORKTREE.parent if WORKTREE.name == "nobus-orchestrator-dev" else WORKTREE.parents[1]
CANONICAL_REPOSITORY = CODE_ROOT / "nobus-orchestrator-dev"
RUNNER = WORKTREE / "scripts" / "run_telegram_mvp1.py"
SSH = Path(os.environ["SYSTEMROOT"]) / "System32" / "OpenSSH" / "ssh.exe"
LOG_ROOT = CANONICAL_REPOSITORY / ".runtime" / "logs"
PUBLIC_ORIGIN = "https://app.nobusspace.com"
RELAY_TARGET = "nobus-relay@76.13.9.125"
REVERSE_BINDING = "127.0.0.1:18765:127.0.0.1:8765"

JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
CREATE_NO_WINDOW = 0x08000000


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION_STRUCT(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def create_kill_job() -> int:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.SetInformationJobObject.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    information = JOBOBJECT_EXTENDED_LIMIT_INFORMATION_STRUCT()
    information.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(
        handle,
        JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(information),
        ctypes.sizeof(information),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(handle)


def assign_to_job(handle: int, process: subprocess.Popen[bytes]) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    if not kernel32.AssignProcessToJobObject(
        wintypes.HANDLE(handle),
        wintypes.HANDLE(process._handle),
    ):
        raise ctypes.WinError(ctypes.get_last_error())


def close_handle(handle: int) -> None:
    if not handle:
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle(wintypes.HANDLE(handle))


def rotate(path: Path) -> None:
    if path.is_file() and path.stat().st_size > 5 * 1024 * 1024:
        os.replace(path, path.with_name(path.name + ".previous"))


def stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def ready() -> bool:
    request = urllib.request.Request(
        "http://127.0.0.1:8765/readyz",
        headers={"Host": "app.nobusspace.com"},
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status == 200 and response.read(256) == b'{"status":"ready"}'
    except Exception:
        return False


def main() -> int:
    python = Path(sys.executable).resolve()
    private_key = Path.home() / ".ssh" / "nobus-space-vps-relay"
    known_hosts = Path.home() / ".ssh" / "nobus-space-vps-known_hosts"
    for required in (WORKTREE, CANONICAL_REPOSITORY, python, RUNNER, SSH, private_key, known_hosts):
        if not required.exists():
            return 1
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    supervisor_log = LOG_ROOT / "runner-supervisor.log"
    core_out = LOG_ROOT / "runner-core.out.log"
    core_err = LOG_ROOT / "runner-core.err.log"
    relay_out = LOG_ROOT / "runner-relay.out.log"
    relay_err = LOG_ROOT / "runner-relay.err.log"
    for path in (supervisor_log, core_out, core_err, relay_out, relay_err):
        rotate(path)

    stop_event = threading.Event()
    for named_signal in (signal.SIGINT, signal.SIGTERM):
        signal.signal(named_signal, lambda *_: stop_event.set())

    try:
        job_handle = create_kill_job()
    except OSError as error:
        with supervisor_log.open("a", encoding="ascii") as stream:
            stream.write(f"job setup failed winerror={error.winerror}\n")
        return 1
    atexit.register(close_handle, job_handle)
    relay: subprocess.Popen[bytes] | None = None
    core: subprocess.Popen[bytes] | None = None
    try:
        with (
            relay_out.open("ab", buffering=0) as relay_stdout,
            relay_err.open("ab", buffering=0) as relay_stderr,
            core_out.open("ab", buffering=0) as core_stdout,
            core_err.open("ab", buffering=0) as core_stderr,
        ):
            relay_deadline = time.monotonic() + 300
            while not stop_event.is_set() and time.monotonic() < relay_deadline:
                relay = subprocess.Popen(
                    [
                        str(SSH),
                        "-NT",
                        "-i",
                        str(private_key),
                        "-o",
                        "UserKnownHostsFile=" + str(known_hosts),
                        "-o",
                        "StrictHostKeyChecking=yes",
                        "-o",
                        "IdentitiesOnly=yes",
                        "-o",
                        "KexAlgorithms=curve25519-sha256",
                        "-o",
                        "ExitOnForwardFailure=yes",
                        "-o",
                        "ServerAliveInterval=20",
                        "-o",
                        "ServerAliveCountMax=3",
                        "-R",
                        REVERSE_BINDING,
                        RELAY_TARGET,
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=relay_stdout,
                    stderr=relay_stderr,
                    creationflags=CREATE_NO_WINDOW,
                )
                assign_to_job(job_handle, relay)
                if stop_event.wait(2):
                    break
                if relay.poll() is None:
                    break
                relay = None
                stop_event.wait(10)
            if relay is None or relay.poll() is not None or stop_event.is_set():
                return 1

            core_deadline = time.monotonic() + 360
            while not stop_event.is_set() and time.monotonic() < core_deadline:
                core = subprocess.Popen(
                    [
                        str(python),
                        str(RUNNER),
                        "--serve",
                        "--timeout",
                        "30",
                        "--announce",
                        "--miniapp-bind",
                        "127.0.0.1",
                        "--miniapp-port",
                        "8765",
                        "--miniapp-origin",
                        PUBLIC_ORIGIN,
                    ],
                    cwd=WORKTREE,
                    stdin=subprocess.DEVNULL,
                    stdout=core_stdout,
                    stderr=core_stderr,
                    creationflags=CREATE_NO_WINDOW,
                )
                assign_to_job(job_handle, core)
                ready_at: float | None = None
                attempt_deadline = time.monotonic() + 120
                while (
                    not stop_event.is_set()
                    and time.monotonic() < attempt_deadline
                    and core.poll() is None
                    and relay.poll() is None
                ):
                    if ready():
                        if ready_at is None:
                            ready_at = time.monotonic()
                        elif time.monotonic() - ready_at >= 70:
                            break
                    elif ready_at is not None:
                        ready_at = None
                    stop_event.wait(1)
                if (
                    ready_at is not None
                    and time.monotonic() - ready_at >= 70
                    and core.poll() is None
                    and relay.poll() is None
                ):
                    break
                stop_process(core)
                core = None
                if relay.poll() is not None:
                    return 1
                stop_event.wait(10)
            if core is None or core.poll() is not None or stop_event.is_set():
                return 1

            with supervisor_log.open("a", encoding="ascii") as stream:
                stream.write(
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    + " product composition stable\n"
                )
            while not stop_event.wait(2):
                if relay.poll() is not None or core.poll() is not None:
                    return 1
            return 0
    except Exception:
        with supervisor_log.open("a", encoding="ascii") as stream:
            stream.write(
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                + " product composition failed\n"
            )
        return 1
    finally:
        stop_process(core)
        stop_process(relay)


if __name__ == "__main__":
    raise SystemExit(main())
