"""C5 bounded process/singleton drills, with synthetic owned fixtures only."""
from __future__ import annotations

import asyncio
import ctypes
import io
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from scripts import run_nobus_space_live as supervisor
from scripts import run_telegram_mvp1 as runner
from src.application.windows_singleton import WindowsNamedMutex, RunnerAlreadyActive
from src.transport.telegram.sqlite_checkpoint import SQLitePollingCheckpointStore, SQLitePollingCheckpointError


def test_c5_semantic_composition_is_explicit_and_default_off(tmp_path):
    default = runner._arguments(["--serve"])
    candidate = runner._arguments(["--serve", "--semantic-admission", "--runtime-root", str(tmp_path)])
    assert runner._GATE_C1_SEMANTIC_ADMISSION_ENABLED is False
    assert runner._semantic_enabled(default) is False
    assert runner._semantic_enabled(candidate) is True
    assert candidate.runtime_root == tmp_path.resolve()
    command = supervisor.core_command(Path(sys.executable), supervisor._arguments([
        "--semantic-admission", "--runtime-root", str(tmp_path)]))
    assert command.count("--semantic-admission") == 1
    assert "--shutdown-stdin" in command
    assert "--announce" not in command  # Restarts cannot flood the owner chat.
    assert "--semantic-admission" not in supervisor.core_command(Path(sys.executable), supervisor._arguments([]))
    with pytest.raises(ValueError):
        runner._semantic_enabled(SimpleNamespace(semantic_admission="true"))


def test_c5_voice_failed_child_is_unavailable_and_idle_is_distinct():
    runner._assert_voice_available(SimpleNamespace(_closed=False, _process=None))
    runner._assert_voice_available(SimpleNamespace(_closed=False, _process=SimpleNamespace(returncode=None)))
    with pytest.raises(RuntimeError, match="voice dependency unavailable"):
        runner._assert_voice_available(SimpleNamespace(_closed=False, _process=SimpleNamespace(returncode=1)))
    with pytest.raises(RuntimeError, match="voice dependency unavailable"):
        runner._assert_voice_available(SimpleNamespace(_closed=True, _process=None))


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_bytes", [b"stop\n", b""])
async def test_c5_shutdown_private_pipe_and_parent_eof_close_admission(monkeypatch, stop_bytes):
    started, closed = asyncio.Event(), asyncio.Event()

    async def run(values, *, report_stage):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            closed.set()

    monkeypatch.setattr(runner, "_run", run)
    monkeypatch.setattr(runner.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(stop_bytes)))
    result = await asyncio.wait_for(runner._run_with_shutdown(
        SimpleNamespace(shutdown_stdin=True), report_stage=lambda _: None), 3)
    assert result == {"status": "STOPPED"}
    assert started.is_set() and closed.is_set()


def test_c5_supervisor_failures_are_bounded_and_never_restart_a_process():
    class Event:
        waits = 0
        def is_set(self):
            return False
        def wait(self, seconds):
            self.waits += 1
            assert self.waits <= 3
            return False
    replies = iter([True, False, False, False])
    process = SimpleNamespace(poll=lambda: None)
    event = Event()
    assert supervisor.supervise(None, None, process, process, event, probe=lambda: next(replies)) == 1
    assert event.waits == 3


def test_c5_stale_polling_lease_cannot_replay_checkpoint(tmp_path):
    clock = [datetime.now(UTC)]
    path = tmp_path / "telegram-checkpoint.sqlite3"
    first = SQLitePollingCheckpointStore(path, consumer_id="c5-fixture", lease_duration_seconds=1, clock=lambda: clock[0])
    second = SQLitePollingCheckpointStore(path, consumer_id="c5-fixture", lease_duration_seconds=1, clock=lambda: clock[0])
    old = first.acquire(uuid4(), clock[0])
    assert old is not None and second.acquire(uuid4(), clock[0]) is None
    assert first.advance(lease=old, expected=None, next_offset=7)
    clock[0] += timedelta(seconds=2)
    current = second.acquire(uuid4(), clock[0])
    assert current is not None and second.load(current) == 7
    assert not first.advance(lease=old, expected=7, next_offset=8)
    with pytest.raises(SQLitePollingCheckpointError):
        first.load(old)
    assert second.advance(lease=current, expected=7, next_offset=8)
    assert second.release(current)


def _wait_marker(path):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        time.sleep(.02)
    pytest.fail("owned process marker was not produced")


def _process_handles(pids):
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    api.OpenProcess.restype = ctypes.c_void_p
    api.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    api.WaitForSingleObject.restype = ctypes.c_uint32
    api.CloseHandle.argtypes = (ctypes.c_void_p,)
    api.CloseHandle.restype = ctypes.c_int
    handles = [api.OpenProcess(0x00101000, False, pid) for pid in pids]
    assert all(handles)
    api.GetProcessTimes.argtypes = (ctypes.c_void_p, *([ctypes.c_void_p] * 4))
    api.GetProcessTimes.restype = ctypes.c_int
    identities = []
    for pid, handle in zip(pids, handles):
        times = [ctypes.c_uint64() for _ in range(4)]
        assert api.GetProcessTimes(handle, *(ctypes.byref(value) for value in times))
        api.QueryFullProcessImageNameW.argtypes = (ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p, ctypes.c_void_p)
        api.QueryFullProcessImageNameW.restype = ctypes.c_int
        buffer = ctypes.create_unicode_buffer(4096)
        size = ctypes.c_uint32(len(buffer))
        assert api.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size))
        identities.append({"pid": pid, "created_filetime": times[0].value,
                           "executable_name": Path(buffer.value).name})
    return api, handles, identities


def _job_pids(job):
    class ProcessList(ctypes.Structure):
        _fields_ = [("assigned", ctypes.c_uint32), ("count", ctypes.c_uint32),
                    ("pids", ctypes.c_size_t * 32)]
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.QueryInformationJobObject.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p)
    api.QueryInformationJobObject.restype = ctypes.c_int
    result = ProcessList()
    assert api.QueryInformationJobObject(job, 3, ctypes.byref(result), ctypes.sizeof(result), None)
    assert result.assigned == result.count and result.count <= 32
    return list(result.pids[:result.count])


def _job_active(job):
    class Accounting(ctypes.Structure):
        _fields_ = [(name, ctypes.c_int64) for name in ("user", "kernel", "period_user", "period_kernel")] + [
            (name, ctypes.c_uint32) for name in ("faults", "total", "active", "terminated")]
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.QueryInformationJobObject.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p)
    api.QueryInformationJobObject.restype = ctypes.c_int
    result = Accounting()
    assert api.QueryInformationJobObject(job, 1, ctypes.byref(result), ctypes.sizeof(result), None)
    return result.active


def _receipt(name, data):
    if os.environ.get("NOBUS_C5_RUNTIME_RECEIPTS") != "1":
        return
    root = Path(__file__).parents[1]
    directory = root / ".runtime" / "c5" / "runtime"
    directory.mkdir(parents=True, exist_ok=True)
    record = {"status": "PASS", "scope": "synthetic disposable owned Windows processes",
              "recorded_at": datetime.now(UTC).isoformat(), **data,
              "source_files_sha256": {path: hashlib.sha256((root/path).read_bytes()).hexdigest() for path in
                 ("scripts/run_nobus_space_live.py", "scripts/run_telegram_mvp1.py",
                  "src/application/windows_singleton.py", "tests/test_c5_runtime_operations.py")}}
    (directory / (name + ".json")).write_text(json.dumps(record, indent=2), encoding="utf-8")


@pytest.mark.skipif(os.name != "nt", reason="real Windows Job proof")
@pytest.mark.parametrize("shutdown", ["close", "terminate"])
def test_c5_real_job_assignment_precedes_child_and_close_removes_descendants(tmp_path, shutdown):
    marker = tmp_path / "owned-processes.json"
    api = supervisor._job_api()
    job = api.create_job()
    observations = []

    class CheckedApi:
        create_gate = api.create_gate
        close = api.close
        def assign(self, value, pid):
            assert not marker.exists()
            api.assign(value, pid)
            observations.append("assigned")
        def signal(self, gate):
            assert observations == ["assigned"] and not marker.exists()
            api.signal(gate)
            observations.append("released")

    code = ("import os,sys,subprocess,json,time; from pathlib import Path; "
            "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],creationflags=0x08000000); "
            f"Path({str(marker)!r}).write_text(json.dumps([os.getpid(),child.pid]),encoding='utf-8'); "
            "time.sleep(30)")
    process = None
    handles = []
    try:
        process = supervisor.spawn_owned(CheckedApi(), job, [sys._base_executable, "-c", code])
        pids = _wait_marker(marker)
        members = _job_pids(job)
        assert set([process.pid, *pids]).issubset(members)
        native, handles, identities = _process_handles(members)
        assert observations == ["assigned", "released"]
        started = time.monotonic()
        assert _job_active(job) == len(members)
        if shutdown == "terminate":
            api.terminate(job)
            assert all(native.WaitForSingleObject(handle, 5000) == 0 for handle in handles)
            active = _job_active(job)
            assert active == 0
        else:
            active = None
        api.close(job)
        job = None
        assert all(native.WaitForSingleObject(handle, 5000) == 0 for handle in handles)
        process.wait(timeout=5)
        _receipt("job-" + shutdown, {"identities": identities, "job_active_before": len(members),
                 "job_active_after": active, "all_exact_process_handles_signaled": True,
                 "cleanup_seconds": time.monotonic() - started,
                 "gate_order": observations, "external_processes_touched": 0})
    finally:
        if job is not None:
            api.terminate(job)
            api.close(job)
        for handle in handles:
            native.CloseHandle(handle)
        if process is not None:
            supervisor.close_owned(api, process)


@pytest.mark.skipif(os.name != "nt", reason="real Windows singleton proof")
def test_c5_real_duplicate_singleton_and_graceful_owned_stop(tmp_path):
    name = "Global\\NobusSpaceBotC5-" + uuid4().hex
    marker = tmp_path / "singleton.json"
    code = ("import sys,json; from pathlib import Path; "
            f"sys.path.insert(0,{str(Path(__file__).parents[1])!r}); "
            "from src.application.windows_singleton import WindowsNamedMutex; "
            f"mutex=WindowsNamedMutex({name!r}); mutex.__enter__(); "
            f"Path({str(marker)!r}).write_text(json.dumps({{'owned': True}}),encoding='utf-8'); "
            "sys.stdin.buffer.readline(); mutex.__exit__()")
    api = supervisor._job_api()
    job = api.create_job()
    process = None
    try:
        process = supervisor.spawn_owned(api, job, [sys._base_executable, "-c", code])
        assert _wait_marker(marker) == {"owned": True}
        members = _job_pids(job)
        native, handles, identities = _process_handles(members)
        with pytest.raises(RunnerAlreadyActive):
            with WindowsNamedMutex(name):
                pytest.fail("duplicate runtime acquired live singleton")
        started = time.monotonic()
        assert supervisor.stop_process(process, graceful=True)
        api.terminate(job)
        assert supervisor.wait_job_empty(job)
        assert all(native.WaitForSingleObject(handle, 1000) == 0 for handle in handles)
        for handle in handles:
            native.CloseHandle(handle)
        assert _job_active(job) == 0
        with WindowsNamedMutex(name):
            pass
        _receipt("singleton-graceful-stop", {"identities": identities, "job_active_after": 0,
                 "duplicate_rejected": True, "reacquire_after_exit": True,
                 "cleanup_seconds": time.monotonic() - started, "external_processes_touched": 0})
    finally:
        api.terminate(job)
        api.close(job)
        if process is not None:
            supervisor.close_owned(api, process)


@pytest.mark.skipif(os.name != "nt", reason="real Windows named stop proof")
def test_c5_stop_signal_is_bound_to_exact_runtime_name():
    name = "Local\\NobusSpaceBotC5Stop-" + uuid4().hex
    event = supervisor.StopEvent(name)
    requester = supervisor.StopEvent(name, request=True)
    try:
        assert not event.is_set()
        requester.set()
        assert event.wait(.2)
        with pytest.raises(RuntimeError, match="unavailable"):
            supervisor.StopEvent(name + "-foreign", request=True)
    finally:
        requester.close()
        event.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled,fail_store,restore_hold", [(False, False, False), (True, False, False), (True, True, False), (True, False, True)])
async def test_c5_real_runner_wires_isolated_semantic_profile_once(tmp_path, monkeypatch, enabled, fail_store, restore_hold):
    events, stores, controls, semantic = [], {}, [], []
    from src.transport.telegram.bot_api import TelegramBotApi as RealApi
    class Api(RealApi):
        def __init__(self):
            pass  # No transport/network; real Sender still validates the real API type.
        async def get_me(self):
            return SimpleNamespace(bot_id=1, username="Nobusspacebot")
        async def aclose(self):
            events.append("api_closed")
    class Runtime:
        async def probe_worker(self):
            assert (tmp_path / "artifacts").is_dir()
            events.append("synthetic_worker_probe")
        async def close(self):
            events.append("runtime_closed")
    class Voice:
        async def warmup(self):
            events.append("synthetic_voice_warmup")
        async def close(self):
            events.append("voice_closed")
    class Control:
        async def start(self):
            events.append("control_started")
        async def close(self):
            events.append("control_closed")
        def assert_healthy(self):
            pass
    runtime, state = Runtime(), object()
    def build_runtime(**values):
        stores["core"] = values["sqlite_path"]
        stores["compute_temp"] = values["temp_root"]
        return runtime
    def state_store(path):
        stores["telegram"] = path
        return state
    def checkpoint_store(path, **values):
        stores["checkpoint"] = path
        return object()
    def compile_service(actual_runtime):
        assert actual_runtime is runtime
        result = object()
        semantic.append(result)
        return result
    def control_factory(*args, **values):
        controls.append(values)
        return Control()
    async def poll(*args, **values):
        events.append("synthetic_poll")
        return 1
    binding = tmp_path / "synthetic-bindings.json"
    binding.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(runner, "_BINDING_PATH", binding)
    monkeypatch.setattr(runner, "read_generic_credential", lambda _: SimpleNamespace(
        username="@Nobusspacebot", secret=SimpleNamespace(get_secret_value=lambda: "synthetic-only")))
    monkeypatch.setattr(runner, "_required_codex_executable", lambda: Path(sys.executable))
    monkeypatch.setattr(runner, "_required_executable", lambda _: Path(sys.executable))
    monkeypatch.setattr(runner, "_validated_worktree", lambda: tmp_path)
    monkeypatch.setattr(runner, "_load_project_context", lambda: "synthetic context")
    monkeypatch.setattr(runner, "NobusMemory", lambda _: object())
    monkeypatch.setattr(runner, "TelegramBotApi", lambda **_: Api())
    monkeypatch.setattr(runner, "TelegramBindingConfig", SimpleNamespace(model_validate=lambda _: SimpleNamespace(
        bindings=[SimpleNamespace(purpose="owner_private")])))
    monkeypatch.setattr(runner, "load_telegram_bindings", lambda *a, **k: {})
    monkeypatch.setattr(runner, "_task_destinations", lambda _: ({"owner": "sha256:" + "a" * 64}, {"owner": ("sha256:" + "a" * 64, 1)}))
    monkeypatch.setattr(runner, "SQLitePollingCheckpointStore", checkpoint_store)
    monkeypatch.setattr(runner, "SQLiteTelegramState", state_store)
    monkeypatch.setattr(runner, "TelegramGateway", lambda **_: object())
    monkeypatch.setattr(runner, "build_gate5a4_runtime", build_runtime)
    def validate(path):
        events.append("synthetic_store_validation")
        if fail_store:
            raise RuntimeError("synthetic invalid store")
    monkeypatch.setattr(runner, "validate_runtime_set", validate)
    def admission_ready(path):
        events.append("synthetic_restore_fence_check")
        if restore_hold:
            raise RuntimeError("synthetic restore hold")
    monkeypatch.setattr(runner, "assert_runtime_admission_ready", admission_ready)
    monkeypatch.setattr(runner, "_build_voice_transcriber", lambda _: Voice())
    monkeypatch.setattr(runner, "build_codex_rate_limit_client", lambda **_: object())
    monkeypatch.setattr(runner, "SemanticAdmissionService", compile_service)
    for name in ("DurableTaskConfirmationStore", "DurablePatchConfirmationStore",
                 "DurableTelegramActionStore", "DurableSemanticClarificationStore"):
        monkeypatch.setattr(runner, name, lambda state: object())
    monkeypatch.setattr(runner, "DurableProductTelegramControlPlane", control_factory)
    monkeypatch.setattr(runner, "TelegramPollingBoundary", lambda *a, **k: object())
    monkeypatch.setattr(runner, "_poll_once_and_announce", poll)
    values = runner._arguments(["--once", "--runtime-root", str(tmp_path)] + (["--semantic-admission"] if enabled else []))
    if fail_store or restore_hold:
        with pytest.raises(RuntimeError, match="synthetic invalid store|synthetic restore hold"):
            await runner._run(values)
        assert not controls and not semantic
        assert "synthetic_worker_probe" not in events and "synthetic_voice_warmup" not in events
        assert events[-2:] == ["runtime_closed", "api_closed"]
        return
    result = await runner._run(values)
    assert result["status"] == "PASS" and result["acknowledged"] == 1
    assert len(controls) == 1 and controls[0]["task_runtime"] is runtime
    assert isinstance(controls[0]["task_status_sender"], runner.TelegramStatusSender)
    assert (tmp_path / "artifacts").is_dir()
    assert controls[0]["telegram_state"] is state
    assert controls[0]["enable_semantic_admission"] is enabled
    assert controls[0]["semantic_admission"] is (semantic[0] if enabled else None)
    assert len(semantic) == int(enabled)
    assert all(path.parent == tmp_path for path in stores.values())
    assert events.index("synthetic_store_validation") < events.index("synthetic_worker_probe")
    assert events[-4:] == ["control_closed", "runtime_closed", "voice_closed", "api_closed"]


@pytest.mark.parametrize("failure", ["event", "log", "job", "core_spawn", "stop", "terminate", "close", "empty"])
def test_c5_setup_failure_closes_acquired_handles_and_cannot_pass(monkeypatch, failure):
    seen = []
    class Event:
        def __init__(self):
            if failure == "event":
                raise RuntimeError("synthetic setup failure")
            seen.append("event_acquired")
        def wait(self, timeout):
            return False
        def set(self):
            pass
        def close(self):
            seen.append("event_closed")
    class Api:
        def create_job(self):
            if failure == "job":
                raise RuntimeError("synthetic setup failure")
            seen.append("job_acquired")
            return 77
        def terminate(self, job):
            seen.append("job_terminate_attempted")
            if failure == "terminate":
                raise RuntimeError("synthetic cleanup failure")
        def close(self, job):
            seen.append("job_close_attempted")
            if failure == "close":
                raise RuntimeError("synthetic cleanup failure")
    def log(code):
        if code == "starting" and failure == "log":
            raise RuntimeError("synthetic log failure")
        seen.append(code)
    def spawn(*args):
        count = seen.count("spawn")
        seen.append("spawn")
        if count == 1 and failure == "core_spawn":
            raise RuntimeError("synthetic launch failure")
        return SimpleNamespace(poll=lambda: None)
    monkeypatch.setattr(supervisor.Path, "exists", lambda _: True)
    monkeypatch.setattr(supervisor, "StopEvent", Event)
    monkeypatch.setattr(supervisor, "_job_api", Api)
    monkeypatch.setattr(supervisor, "_operator_event", log)
    monkeypatch.setattr(supervisor, "spawn_owned", spawn)
    monkeypatch.setattr(supervisor, "supervise", lambda *a, **k: 0)
    monkeypatch.setattr(supervisor, "stop_process", lambda *a, **k: failure != "stop")
    monkeypatch.setattr(supervisor, "close_owned", lambda *a: seen.append("process_closed"))
    monkeypatch.setattr(supervisor, "wait_job_empty", lambda job: failure != "empty")
    assert supervisor._main(supervisor._arguments([])) == 1
    if "event_acquired" in seen:
        assert "event_closed" in seen
    if "job_acquired" in seen:
        assert "job_terminate_attempted" in seen and "job_close_attempted" in seen
    assert "stopped" not in seen


def test_c5_supervisor_children_receive_only_sanitized_environment(monkeypatch):
    observed = {}
    def spawn(*args, **values):
        observed.update(values)
        return SimpleNamespace(pid=42)
    api = SimpleNamespace(create_gate=lambda: (11, "synthetic-gate"),
                          assign=lambda *a: None, signal=lambda *a: None, close=lambda *a: None)
    monkeypatch.setenv("NOBUS_PRIVATE_SENTINEL", "must-not-inherit")
    monkeypatch.setenv("PYTHONPATH", "must-not-inherit")
    monkeypatch.setattr(supervisor.subprocess, "Popen", spawn)
    process = supervisor.spawn_owned(api, 7, [sys.executable])
    assert process._nobus_gate == 11
    assert "NOBUS_PRIVATE_SENTINEL" not in observed["env"]
    assert "PYTHONPATH" not in observed["env"]
    assert observed["stderr"] == subprocess.DEVNULL
    assert observed["creationflags"] == 0x08000000


@pytest.mark.asyncio
async def test_c5_caller_cancellation_waits_for_owned_runtime_cleanup(monkeypatch):
    import threading
    pipe_released = threading.Event()
    started, closed = asyncio.Event(), asyncio.Event()
    class Pipe:
        def readline(self, limit):
            pipe_released.wait(3)
            return b""
    async def run(values, *, report_stage):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(.01)
            closed.set()
    monkeypatch.setattr(runner, "_run", run)
    monkeypatch.setattr(runner.sys, "stdin", SimpleNamespace(buffer=Pipe()))
    outer = asyncio.create_task(runner._run_with_shutdown(SimpleNamespace(shutdown_stdin=True), report_stage=lambda _: None))
    try:
        await started.wait()
        outer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(outer, 2)
        assert closed.is_set()
    finally:
        pipe_released.set()


@pytest.mark.parametrize("body,status,expected", [(b'{"status":"ready"}', 200, True),
    (b'{"status":"ready"}', 403, False), (b'not-the-core', 200, False)])
def test_c5_public_ingress_requires_exact_core_readiness(monkeypatch, body, status, expected):
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, size):
            assert size == 256
            return body
    response = Response()
    response.status = status
    def request(request, *, timeout):
        assert request.full_url == supervisor.PUBLIC_ORIGIN + "/readyz"
        assert timeout == 5
        return response
    def opener(handler, redirect):
        assert handler.proxies == {}
        assert isinstance(redirect, __import__("urllib.request", fromlist=["HTTPRedirectHandler"]).HTTPRedirectHandler)
        return SimpleNamespace(open=request)
    monkeypatch.setattr(supervisor.urllib.request, "build_opener", opener)
    assert supervisor.public_ready() is expected


@pytest.mark.asyncio
async def test_c5_repeated_caller_cancellation_does_not_cut_short_cleanup(monkeypatch):
    import threading
    release_pipe = threading.Event()
    started, cleanup_started, cleanup_release, cleanup_done = (asyncio.Event() for _ in range(4))
    class Pipe:
        def readline(self, limit):
            release_pipe.wait(3)
            return b""
    async def run(values, *, report_stage):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup_started.set()
            await cleanup_release.wait()
            cleanup_done.set()
    monkeypatch.setattr(runner, "_run", run)
    monkeypatch.setattr(runner.sys, "stdin", SimpleNamespace(buffer=Pipe()))
    outer = asyncio.create_task(runner._run_with_shutdown(SimpleNamespace(shutdown_stdin=True), report_stage=lambda _: None))
    try:
        await started.wait()
        outer.cancel()
        await cleanup_started.wait()
        outer.cancel()
        await asyncio.sleep(0)
        assert not outer.done() and not cleanup_done.is_set()
        cleanup_release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(outer, 2)
        assert cleanup_done.is_set()
    finally:
        cleanup_release.set()
        release_pipe.set()


@pytest.mark.parametrize("argument", ["--runtime-root", "--voice-model-directory"])
@pytest.mark.parametrize("reparse_at_parent", [False, True])
def test_c5_supervisor_rejects_original_reparse_path_before_resolving(tmp_path, monkeypatch, argument, reparse_at_parent):
    directory = tmp_path / "state"
    directory.mkdir()
    original = directory.parent if reparse_at_parent else directory
    native_check = Path.is_junction
    monkeypatch.setattr(Path, "is_junction", lambda path: path == original or native_check(path))
    with pytest.raises(ValueError, match="runtime composition is invalid"):
        supervisor.core_command(Path(sys.executable), supervisor._arguments([argument, str(directory)]))


def test_c5_installer_health_delegates_exact_bounded_probe_and_has_total_task_limit():
    installer = (Path(__file__).parents[1] / "ops/windows/Install-NobusSpaceBot.ps1").read_text(encoding="utf-8")
    body = installer.split('$healthBody = @"', 1)[1].split('"@', 1)[0]
    assert "Invoke-WebRequest" not in body
    assert "--check-ready *>> `$log" in body
    assert "if (`$LASTEXITCODE -ne 0)" in body
    assert "Start-ScheduledTask" not in body
    assert "-ExecutionTimeLimit (New-TimeSpan -Minutes 2)" in installer


@pytest.mark.parametrize("outcomes, expected", [((True, True),0),((True,False),1),((False,True),1)])
def test_c5_readiness_cli_safe_json_and_never_starts_runtime(monkeypatch,capsys,outcomes,expected):
    monkeypatch.setattr(supervisor.sys,"argv",["runner","--check-ready"])
    monkeypatch.setattr(supervisor,"ready",lambda:outcomes[0])
    monkeypatch.setattr(supervisor,"public_ready",lambda:outcomes[1])
    monkeypatch.setattr(supervisor,"_main",lambda *_:pytest.fail("read-only probe started runtime"))
    assert supervisor.main()==expected
    assert json.loads(capsys.readouterr().out)=={"status":"PASS" if expected==0 else "FAIL"}


def test_c5_probe_deadline_dns_stall_has_one_inflight_and_discards_late_pass():
    import threading
    probe=supervisor._ReadinessProbe()
    entered,release=threading.Event(),threading.Event()
    calls=[]
    def stalled_dns():
        calls.append(1);entered.set();release.wait(2);return True
    start=time.monotonic()
    try:
        assert not probe.run(stalled_dns,seconds=.08)
        assert entered.is_set() and time.monotonic()-start<.5
        original=probe._thread
        for _ in range(20):
            assert not probe.run(stalled_dns,seconds=.08)
            assert probe._thread is original
        assert len(calls)==1 and original.daemon
    finally:
        release.set();probe._thread.join(2)
    assert not probe._thread.is_alive()
    assert not probe.run(lambda:False,seconds=.5)  # Late True cannot become next result.
    for _ in range(10):
        assert probe.run(lambda:True,seconds=.5)  # Completed local->public never races thread exit.


def test_c5_probe_stop_during_dns_is_prompt_and_late_pass_is_discarded():
    import threading
    probe=supervisor._ReadinessProbe();stopped=threading.Event();release=threading.Event()
    timer=threading.Timer(.08,stopped.set);timer.daemon=True;timer.start()
    start=time.monotonic()
    try:
        assert not probe.run(lambda:release.wait(2),seconds=5,stop_event=stopped)
        assert time.monotonic()-start<.5
    finally:
        release.set();timer.cancel();timer.join(1);probe._thread.join(2)
    assert not probe.run(lambda:True,seconds=5,stop_event=stopped)


@pytest.fixture
def probe_server():
    from contextlib import contextmanager
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    import threading
    @contextmanager
    def serve(reply):
        stopping=threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):reply(self,stopping)
        server=ThreadingHTTPServer(("127.0.0.1",0),Handler);server.daemon_threads=True
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:yield f"http://127.0.0.1:{server.server_port}",stopping
        finally:
            stopping.set();server.shutdown();server.server_close();worker.join(2)
    return serve


def test_c5_real_redirect_never_reaches_other_origin(monkeypatch,probe_server):
    foreign_hits=[]
    def foreign(handler,stop):
        foreign_hits.append(handler.path);body=b'{"status":"ready"}'
        handler.send_response(200);handler.send_header("Content-Length",str(len(body)));handler.end_headers();handler.wfile.write(body)
    with probe_server(foreign) as (foreign_url,_):
        def redirect(handler,stop):
            handler.send_response(302);handler.send_header("Location",foreign_url+'/foreign');handler.send_header("Content-Length","0");handler.end_headers()
        with probe_server(redirect) as (origin,_):
            monkeypatch.setattr(supervisor,"_READINESS_PROBE",supervisor._ReadinessProbe())
            monkeypatch.setattr(supervisor,"PUBLIC_ORIGIN",origin)
            assert supervisor.public_ready() is False
            assert supervisor._ready_request(origin+'/readyz',seconds=2,headers={"Host":"app.nobusspace.com"}) is False
    assert foreign_hits==[]


@pytest.mark.parametrize("stop_early",[False,True])
def test_c5_real_chunked_body_has_total_deadline_and_supervisor_stop(monkeypatch,probe_server,stop_early):
    import threading
    progress=[]
    def slow(handler,stopping):
        handler.send_response(200);handler.send_header("Transfer-Encoding","chunked");handler.end_headers()
        for byte in b'{"status":"ready"}':
            if stopping.wait(.36):return
            try:handler.wfile.write(b'1\r\n'+bytes([byte])+b'\r\n');handler.wfile.flush();progress.append(time.monotonic())
            except OSError:return
        try:handler.wfile.write(b'0\r\n\r\n');handler.wfile.flush()
        except OSError:pass
    probe=supervisor._ReadinessProbe();monkeypatch.setattr(supervisor,"_READINESS_PROBE",probe)
    with probe_server(slow) as (origin,server_stop):
        monkeypatch.setattr(supervisor,"PUBLIC_ORIGIN",origin)
        stopped=threading.Event();timer=None;start=time.monotonic()
        try:
            if stop_early:
                monkeypatch.setattr(supervisor,"ready",lambda **_:True)
                process=SimpleNamespace(poll=lambda:None)
                timer=threading.Timer(.2,stopped.set);timer.daemon=True;timer.start()
                assert supervisor.supervise(None,None,process,process,stopped)==0
                assert time.monotonic()-start<.7
            else:
                assert supervisor.public_ready() is False
                assert 4.7<=time.monotonic()-start<5.7
                assert len(progress)>=10  # Valid chunks keep defeating an inactivity-only timeout.
        finally:
            server_stop.set()
            if timer is not None:timer.cancel();timer.join(1)
    probe._thread.join(2)
    assert not probe._thread.is_alive()
