"""Evidence-gated boot reconciliation; never resets history or business state."""
from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime
import hashlib
import ctypes
import os
from pathlib import Path
import socket
import subprocess
from uuid import UUID, uuid4


def boot_identity():
    # SYSTEM_BOOT_ENVIRONMENT_INFORMATION (class 90): boot GUID, not wall time.
    # Unsupported OS/API fails closed; never substitute uptime or a random UUID.
    query = ctypes.WinDLL("ntdll").NtQuerySystemInformation
    query.argtypes = (ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong))
    query.restype = ctypes.c_long
    buffer = ctypes.create_string_buffer(32)
    returned = ctypes.c_ulong()
    if query(90, buffer, len(buffer), ctypes.byref(returned)) != 0 or returned.value != 32:
        raise ValueError("boot identity unavailable")
    identifier = buffer.raw[:16]
    if identifier == bytes(16):
        raise ValueError("boot identity unavailable")
    return "sha256:" + hashlib.sha256(identifier).hexdigest()


def children_absent(worktree, reverse_binding):
    # No process details are emitted. Unknown inspection outcome is never absence.
    script = """& { param($root,$binding)
$ErrorActionPreference='Stop'
$items=@(Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -in @('python.exe','pythonw.exe','ssh.exe') -and -not $_.CommandLine) -or
    ($_.Name -in @('python.exe','pythonw.exe') -and $_.CommandLine -and $_.CommandLine.Contains($root) -and
        ($_.CommandLine.Contains('run_telegram_mvp1.py') -or $_.CommandLine.Contains('--gated-child'))) -or
    ($_.Name -eq 'ssh.exe' -and $_.CommandLine -and $_.CommandLine.Contains($binding))
})
$items.Count
} """ + "'" + str(worktree).replace("'", "''") + "' '" + reverse_binding.replace("'", "''") + "'"
    result = subprocess.run([str(Path(os.environ["SYSTEMROOT"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"),
                             "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW, check=True)
    if result.stdout.strip() != b"0":
        return False
    with socket.socket() as sock:
        sock.settimeout(1)
        # Connection refused is evidence of no listener; timeout/access error is not.
        return sock.connect_ex(("127.0.0.1", 8765)) in {10061, 111}


def validate_effects(runtime):
    from src.application import runtime_maintenance as m
    m.validate_runtime_set(runtime)
    store = m._read_only_store(runtime / "task-runtime.sqlite3")
    if store.restore_reconciliation_required():
        raise ValueError("reconciliation required")
    with closing(m._read_connection(runtime / "telegram-checkpoint.sqlite3")) as con:
        for (expires,) in con.execute("SELECT lease_expires_at FROM telegram_polling_checkpoints"):
            if expires is not None and datetime.fromisoformat(expires) > datetime.now(UTC):
                raise ValueError("polling lease active")
    with closing(m._read_connection(runtime / "telegram-state.sqlite3")) as con:
        if con.execute("SELECT COUNT(*) FROM telegram_jobs WHERE status NOT IN ('finished','failed') OR kind='effect'").fetchone()[0]:
            raise ValueError("unfinished task requires reconciliation")
        if con.execute("SELECT COUNT(*) FROM telegram_capabilities WHERE kind='action'").fetchone()[0]:
            raise ValueError("effect capability requires reconciliation")
    with closing(m._read_connection(runtime / "task-runtime.sqlite3")) as con:
        rows = con.execute("SELECT tenant_id,task_id FROM task_snapshots").fetchall()
        for tenant in {row[0] for row in rows}:
            counts = store.delivery_counts(tenant)
            if any(counts.get(key, 0) for key in ("pending", "leased", "unknown", "failed")):
                raise ValueError("delivery requires reconciliation")
        # Verify each projection through its existing authenticated parser.
        for tenant, task_id in rows:
            task = store.read_task(tenant, UUID(task_id))
            if task is None or task.projection.status.value not in {"answered", "completed", "failed", "rejected", "waiting_input", "waiting_human", "deferred", "escalate"}:
                raise ValueError("task requires reconciliation")


def reconcile(s, values, *, root, binding, current_boot=None, validate=None, absent=None):
    """Caller owns the supervisor mutex. Hold Core + backup exclusion to commit."""
    from src.application.windows_singleton import WindowsNamedMutex
    state = s._recovery_state(root=root, activation_binding=binding)
    if state["reason"] != "previous_attempt_unknown":
        return False
    event, digest = s._last_runtime_event(root=root, activation_binding=binding)
    event = s._effective_event(event)
    boot = current_boot if current_boot is not None else boot_identity()
    if (not s._digest(event.get("boot_id")) or not s._digest(boot)
            or event["boot_id"] == boot or event["attempt"] > event["retry_budget"]):
        return False
    with WindowsNamedMutex(r"Global\NobusSpaceBackupCycle"), WindowsNamedMutex():
        if not (absent or (lambda: children_absent(s.WORKTREE, s.REVERSE_BINDING)))():
            return False
        (validate or (lambda: validate_effects(values.runtime_root)))()
        again, head = s._last_runtime_event(root=root, activation_binding=binding)
        if head != digest or s._effective_event(again) != event:
            raise ValueError("recovery history changed")
        s._write_runtime_event(s._runtime_record(
            event["series_id"], uuid4().hex, "reboot_reconciled", activation_binding=binding,
            attempt=event["attempt"], retry_budget=event["retry_budget"],
            recovery_disposition="retry", stage="recovery_control", supervisor_exit_code=0,
            cleanup_outcome="proven", reset_of_digest=digest,
            boot_id=boot, previous_boot_id=event["boot_id"],
        ), root=root)
    return True
