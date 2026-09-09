"""Own one local Core/relay Job; fail closed and leave retries to Task Scheduler."""
from __future__ import annotations

import argparse
import ctypes
import importlib.util
import os
import signal
import subprocess
import sys
import time
import threading
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
CREATE_NO_WINDOW = 0x08000000
STARTUP_SECONDS = 360
SHUTDOWN_SECONDS = 90
READINESS_INTERVAL_SECONDS = 10
READINESS_FAILURE_LIMIT = 3


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


def supervise(api, job, relay, core, stop_event, *, clock=time.monotonic, probe=None) -> int:
    if probe is None:
        probe = lambda: ready(stop_event=stop_event) and public_ready(stop_event=stop_event)
    deadline = clock() + STARTUP_SECONDS
    while not stop_event.is_set() and clock() < deadline:
        if relay.poll() is not None or core.poll() is not None:
            return 1
        if probe():
            break
        stop_event.wait(1)
    else:
        return 0 if stop_event.is_set() else 1
    failures = 0
    while not stop_event.wait(READINESS_INTERVAL_SECONDS):
        if relay.poll() is not None or core.poll() is not None:
            return 1
        failures = 0 if probe() else failures + 1
        if failures >= READINESS_FAILURE_LIMIT:
            return 1
    return 0


def _arguments(argv=None):
    parser = argparse.ArgumentParser()
    commands = parser.add_mutually_exclusive_group()
    commands.add_argument("--stop", action="store_true")
    commands.add_argument("--check-ready", action="store_true")
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
            healthy = ready() and public_ready()
            print('{"status":"PASS"}' if healthy else '{"status":"FAIL"}')
            return 0 if healthy else 1
        if values.stop:
            event = StopEvent(request=True)
            try:
                event.set()
                print('{"status":"stop_requested"}')
                return 0
            finally:
                event.close()
        with WindowsNamedMutex(r"Global\NobusSpaceBotSupervisor"):
            return _main(values)
    except RunnerAlreadyActive:
        return 0
    except Exception:
        return 1


def _main(values) -> int:
    python = Path(sys.executable).with_name("python.exe").resolve()
    private_key = Path.home() / ".ssh" / "nobus-space-vps-relay"
    known_hosts = Path.home() / ".ssh" / "nobus-space-vps-known_hosts"
    for required in (WORKTREE, CANONICAL_REPOSITORY, python, RUNNER, SSH, private_key, known_hosts):
        if not required.exists():
            return 1
    command = core_command(python, values)
    api = _job_api()
    stop_event = None
    job = None
    relay = core = None
    status = 1
    previous_signals = {}
    try:
        stop_event = StopEvent()
        for named_signal in (signal.SIGINT, signal.SIGTERM):
            previous_signals[named_signal] = signal.signal(named_signal, lambda *_: stop_event.set())
        _operator_event("starting")
        job = api.create_job()
        relay = spawn_owned(api, job, [str(SSH), "-NT", "-F", "NUL", "-i", str(private_key),
            "-o", "BatchMode=yes", "-o", "UserKnownHostsFile=" + str(known_hosts),
            "-o", "StrictHostKeyChecking=yes", "-o", "IdentitiesOnly=yes",
            "-o", "KexAlgorithms=curve25519-sha256", "-o", "ExitOnForwardFailure=yes",
            "-o", "ServerAliveInterval=20", "-o", "ServerAliveCountMax=3",
            "-o", "ConnectTimeout=15", "-R", REVERSE_BINDING, RELAY_TARGET])
        if not stop_event.wait(2) and relay.poll() is None:
            core = spawn_owned(api, job, command)
            status = supervise(api, job, relay, core, stop_event)
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
            if child is not None:
                try:
                    close_owned(api, child)
                except Exception:
                    cleanup_ok = False
        if stop_event is not None:
            try:
                stop_event.close()
            except Exception:
                cleanup_ok = False
        for named_signal, handler in previous_signals.items():
            signal.signal(named_signal, handler)
        if not cleanup_ok:
            status = 1
        try:
            _operator_event("cleanup_failed" if not cleanup_ok else
                            ("stopped" if status == 0 else "runtime_failed"))
        except Exception:
            status = 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
