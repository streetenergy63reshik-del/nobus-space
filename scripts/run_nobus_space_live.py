"""Own one local Core/relay Job and bounded, evidence-gated recovery series."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.metadata
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
import urllib.error
import socket
from ctypes import wintypes
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

WORKTREE = Path(__file__).resolve().parents[1]
if str(WORKTREE) not in sys.path:
    sys.path.insert(0, str(WORKTREE))
from scripts.runtime_diagnostics import RelayCapture, RELAY_CAUSES, TRANSIENT_RELAY_CAUSES
from scripts.reboot_recovery import boot_identity
CANONICAL_REPOSITORY = next(
    (path for path in (WORKTREE, *WORKTREE.parents) if path.name == "nobus-orchestrator-dev"),
    WORKTREE.parents[1] / "nobus-orchestrator-dev",
)
CODE_ROOT = CANONICAL_REPOSITORY.parent
RUNNER = WORKTREE / "scripts" / "run_telegram_mvp1.py"
SSH = Path(os.environ["SYSTEMROOT"]) / "System32" / "OpenSSH" / "ssh.exe"
LOG_ROOT = CANONICAL_REPOSITORY / ".runtime" / "logs"
RECOVERY_DIRECTORY_NAME = "supervisor-control"
PUBLIC_ORIGIN = "https://app.nobusspace.com"
RELAY_TARGET = "nobus-relay@76.13.9.125"
REVERSE_BINDING = "127.0.0.1:18765:127.0.0.1:8765"
CREATE_NO_WINDOW = 0x08000000
STARTUP_SECONDS = 360
SHUTDOWN_SECONDS = 90
READINESS_INTERVAL_SECONDS = 10
READINESS_FAILURE_LIMIT = 3
CHILD_EXIT_SETTLE_SECONDS = 0.1
RECOVERY_RETRY_BUDGET = 10
RECOVERY_RETRY_INTERVAL_SECONDS = 60
CORE_OUTCOME_BYTES = 4096
RUNTIME_EVENT_LOG_NAME = "runner-supervisor-v3.jsonl"
RUNTIME_EVENT_LOG_BYTES = 1024 * 1024
RUNTIME_EVENT_LINE_BYTES = 2048
OPERATOR_EVENT_LOG_BYTES = 5 * 1024 * 1024
EXIT_STOP_CONTROL_CREATE_FAILED = 70
EXIT_STOP_CONTROL_SIGNAL_FAILED = 71
EXIT_STOP_CONTROL_CLOSE_FAILED = 72
EXIT_RUNTIME_EVIDENCE_FAILED = 73
EXIT_RUNTIME_COMPOSITION_INVALID = 74
EXIT_ACTIVATION_BINDING_INVALID = 75
EXIT_RECOVERY_CONTROL_BUSY = 76
EXIT_RECOVERY_RESET_REJECTED = 77
EXIT_RECOVERY_HISTORY_BLOCKED = 78
EXIT_SUPERVISOR_STARTUP_FAILED = 79
EXIT_RECOVERY_REBIND_REJECTED = 80
FALLBACK_EVENT_LOG_NAME = "runner-supervisor-fallback-v1.jsonl"
FALLBACK_EVENT_LOG_BYTES = 128 * 1024
FALLBACK_EVENT_LINE_BYTES = 2048
RECOVERY_LATCH_NAME = "runner-supervisor-evidence-latch-v1.json"
RECOVERY_LATCH_BYTES = 2048
_HISTORY_AUTHENTICATION_ENTROPY = b"nobus-space:supervisor-history:v3"
_FALLBACK_AUTHENTICATION_ENTROPY = b"nobus-space:supervisor-fallback:v1"
_LATCH_AUTHENTICATION_ENTROPY = b"nobus-space:supervisor-evidence-latch:v1"
RUNTIME_EVENT_KEYS = frozenset({
    "schema", "series_id", "run_id", "event", "stage", "error_class",
    "supervisor_exit_code", "core_exit_code", "relay_exit_code",
    "local_ready", "public_ready", "readiness_failures",
    "attempt", "retry_budget", "recovery_disposition", "core_outcome",
    "core_outcome_error", "cleanup_outcome", "activation_binding",
    "previous_event_digest", "reset_of_digest", "checkpoint_event",
    "anchor_of_digest",
})
RUNTIME_RECORDED_KEYS = RUNTIME_EVENT_KEYS | {"at", "authentication"}
RUNTIME_V4_KEYS = frozenset({"boot_id", "previous_boot_id", "relay_cause"})
RUNTIME_V5_KEYS = RUNTIME_V4_KEYS | {"power_evidence_digest"}
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
    "stop_control_create_failed", "stop_control_signal_failed",
    "stop_control_close_failed", "stop_control_callback_failed",
    "recovery_wait_event_write_failed",
})
_RECOVERY_DISPOSITIONS = frozenset({
    "pending", "complete", "retry", "stop_non_retryable",
    "stop_budget_exhausted", "stop_cleanup_failed", "stop_evidence_failed",
    "stop_planned", "reset", "initialized",
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
_EVENT_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_AUTHENTICATION = re.compile(r"[0-9a-f]{64,1536}")
_OPERATOR_EVENT = re.compile(
    rb"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z "
    rb"(?:starting|stopped|runtime_failed|cleanup_failed)\n"
)
_CORE_FAILURE_CODES = frozenset({
    "credential_configuration_invalid",
    "credential_unavailable",
    "telegram_binding_configuration_invalid",
    "telegram_binding_unavailable",
    "telegram_configuration_invalid",
    "telegram_unavailable",
    "telegram_protocol_error",
    "telegram_response_too_large",
    "telegram_download_too_large",
    "telegram_upload_too_large",
    "telegram_handler_failed",
    "telegram_checkpoint_failed",
    "telegram_consumer_busy",
    "telegram_artifact_projection_failed",
    "telegram_mvp1_failed",
    *{
        "telegram_mvp1_" + stage + "_failed"
        for stage in (
            "credentials", "local_preflight", "telegram_identity", "bindings",
            "runtime_stores", "core_runtime", "runtime_validation",
            "worker_probe", "voice_warmup", "rate_limit_provider",
            "control_construction", "control_start", "miniapp_core",
            "miniapp_server", "polling",
        )
    },
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
                or value["code"] not in _CORE_FAILURE_CODES):
            return None, "core_outcome_invalid"
    elif value["status"] in {"STOPPED", "ALREADY_RUNNING"}:
        if set(value) != {"status"}:
            return None, "core_outcome_invalid"
    else:
        return None, "core_outcome_invalid"
    return dict(value), None


def _core_outcome_matches_exit(exit_code, outcome) -> bool:
    """Reject a safe Core record that contradicts the observed process exit."""
    if exit_code is None or outcome is None:
        return True
    if outcome.get("status") == "FAIL":
        return exit_code != 0
    if outcome.get("status") in {"STOPPED", "ALREADY_RUNNING"}:
        return exit_code == 0
    return False


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


def _digest(value) -> bool:
    return type(value) is str and _EVENT_DIGEST.fullmatch(value) is not None


def _unique_json_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError
        value[key] = item
    return value


def _canonical_ascii(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii")


def _authentication(value, *, entropy: bytes) -> str:
    from src.security.dpapi import protect_current_user

    payload_digest = hashlib.sha256(_canonical_ascii(value)).digest()
    return protect_current_user(payload_digest, entropy=entropy).hex()


def _verify_authentication(value, authentication, *, entropy: bytes) -> None:
    from src.security.dpapi import unprotect_current_user

    if type(authentication) is not str or _AUTHENTICATION.fullmatch(authentication) is None:
        raise ValueError
    try:
        protected = bytes.fromhex(authentication)
        authenticated = unprotect_current_user(protected, entropy=entropy)
    except Exception:
        raise ValueError from None
    if authenticated != hashlib.sha256(_canonical_ascii(value)).digest():
        raise ValueError


def _single_link_file(path: Path) -> bool:
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError:
        return False
    return metadata.st_nlink == 1


def _validate_operator_segment(path: Path) -> None:
    if (_path_is_reparse(path) or not path.is_file() or not _single_link_file(path)
            or not 0 < path.stat().st_size <= OPERATOR_EVENT_LOG_BYTES):
        raise OSError
    content = path.read_bytes()
    if not content.endswith(b"\n"):
        raise OSError
    lines = content.splitlines(keepends=True)
    if not lines or any(_OPERATOR_EVENT.fullmatch(line) is None for line in lines):
        raise OSError


def _path_is_reparse(path: Path) -> bool:
    if path.is_symlink() or path.is_junction():
        return True
    attributes = getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0)
    return bool(attributes & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT


def _plain_root(root: Path, *, create: bool) -> tuple[int, int]:
    """Reject every reparse component and return the exact directory identity."""
    root = Path(root)
    if not root.is_absolute():
        raise OSError
    for candidate in (root, *root.parents):
        if candidate.exists() and _path_is_reparse(candidate):
            raise OSError
    if create:
        root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir() or _path_is_reparse(root):
        raise OSError
    for candidate in (root, *root.parents):
        if candidate.exists() and _path_is_reparse(candidate):
            raise OSError
    metadata = root.stat(follow_symlinks=False)
    return metadata.st_dev, metadata.st_ino


def _read_recovery_latch(root: Path):
    """Read the bounded owner-authenticated pre-control fail-stop latch."""
    path = Path(root) / RECOVERY_LATCH_NAME
    if not path.exists():
        return None, None
    identity = _plain_root(Path(root), create=False)
    if (_path_is_reparse(path) or not path.is_file() or not _single_link_file(path)
            or not 0 < path.stat().st_size <= RECOVERY_LATCH_BYTES):
        raise ValueError("runtime evidence latch is invalid")
    content = path.read_bytes()
    if not content.endswith(b"\n") or identity != _plain_root(Path(root), create=False):
        raise ValueError("runtime evidence latch is invalid")
    try:
        recorded = json.loads(
            content[:-1].decode("ascii"), object_pairs_hook=_unique_json_object
        )
        keys = {
            "schema", "status", "error_class", "activation_binding",
            "previous_event_digest", "series_id", "run_id", "attempt",
            "retry_budget", "at", "authentication",
        }
        if type(recorded) is not dict or set(recorded) != keys:
            raise ValueError
        authentication = recorded.pop("authentication")
        _verify_authentication(
            recorded, authentication, entropy=_LATCH_AUTHENTICATION_ENTROPY
        )
        if (recorded["schema"] != "nobus-recovery-evidence-latch-1"
                or recorded["status"] != "STOP"
                or recorded["error_class"] != "runtime_event_write_failed"
                or not _digest(recorded["activation_binding"])
                or not _digest(recorded["previous_event_digest"])
                or re.fullmatch(r"[0-9a-f]{32}", recorded["series_id"]) is None
                or re.fullmatch(r"[0-9a-f]{32}", recorded["run_id"]) is None
                or type(recorded["retry_budget"]) is not int
                or not 0 <= recorded["retry_budget"] <= RECOVERY_RETRY_BUDGET
                or type(recorded["attempt"]) is not int
                or not 1 <= recorded["attempt"] <= recorded["retry_budget"] + 1
                or re.fullmatch(
                    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
                    recorded["at"],
                ) is None):
            raise ValueError
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError, TypeError):
        raise ValueError("runtime evidence latch is invalid") from None
    return recorded, "sha256:" + hashlib.sha256(content).hexdigest()


def _write_recovery_latch(*, root: Path, activation_binding: str,
                          previous_event_digest: str, series_id: str,
                          run_id: str, attempt: int, retry_budget: int):
    payload = {
        "schema": "nobus-recovery-evidence-latch-1",
        "status": "STOP",
        "error_class": "runtime_event_write_failed",
        "activation_binding": activation_binding,
        "previous_event_digest": previous_event_digest,
        "series_id": series_id,
        "run_id": run_id,
        "attempt": attempt,
        "retry_budget": retry_budget,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    authentication = _authentication(
        payload, entropy=_LATCH_AUTHENTICATION_ENTROPY
    )
    content = _canonical_ascii({**payload, "authentication": authentication}) + b"\n"
    if len(content) > RECOVERY_LATCH_BYTES:
        raise OSError
    identity = _plain_root(Path(root), create=True)
    path = Path(root) / RECOVERY_LATCH_NAME
    if path.exists():
        raise OSError
    try:
        with path.open("xb") as stream:
            opened = os.fstat(stream.fileno())
            if opened.st_nlink != 1:
                raise OSError
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            current = path.stat(follow_symlinks=False)
            if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
                raise OSError
        if identity != _plain_root(Path(root), create=False):
            raise OSError
        _value, digest = _read_recovery_latch(Path(root))
        return digest
    except Exception:
        # A partial latch is intentionally retained: invalid control inventory
        # is itself a durable fail-closed condition for the next invocation.
        raise OSError from None


def _clear_recovery_latch(*, root: Path, expected_digest: str) -> None:
    identity = _plain_root(Path(root), create=False)
    _value, digest = _read_recovery_latch(Path(root))
    if digest != expected_digest:
        raise OSError
    path = Path(root) / RECOVERY_LATCH_NAME
    path.unlink()
    if path.exists() or identity != _plain_root(Path(root), create=False):
        raise OSError


def _latch_predecessor_matches(latch, event, predecessor=None,
                               predecessor_digest=None) -> bool:
    if event is None:
        return False
    if event["previous_event_digest"] == latch["previous_event_digest"]:
        return True
    return (
        predecessor is not None
        and predecessor["event"] == "history_checkpoint"
        and predecessor["anchor_of_digest"] == latch["previous_event_digest"]
        and predecessor_digest == event["previous_event_digest"]
    )


def _latch_matches_control_starting(latch, event, predecessor=None,
                                    predecessor_digest=None) -> bool:
    return (
        event is not None
        and event["event"] == "control_starting"
        and _latch_predecessor_matches(
            latch, event, predecessor, predecessor_digest
        )
        and event["activation_binding"] == latch["activation_binding"]
        and event["series_id"] == latch["series_id"]
        and event["run_id"] == latch["run_id"]
        and event["attempt"] == latch["attempt"]
        and event["retry_budget"] == latch["retry_budget"]
    )


def _latch_matches_control_failure(latch, event, predecessor=None,
                                   predecessor_digest=None) -> bool:
    return (
        event is not None
        and event["event"] == "control_failure"
        and _latch_predecessor_matches(
            latch, event, predecessor, predecessor_digest
        )
        and event["activation_binding"] == latch["activation_binding"]
        and event["series_id"] == latch["series_id"]
        and event["run_id"] == latch["run_id"]
        and event["attempt"] == latch["attempt"]
        and event["retry_budget"] == latch["retry_budget"]
        and event["error_class"] == "runtime_event_write_failed"
        and event["supervisor_exit_code"] == EXIT_RUNTIME_EVIDENCE_FAILED
    )


def _validate_recovery_inventory(root: Path, *, allow_compact=False) -> None:
    allowed = {
        RUNTIME_EVENT_LOG_NAME,
        RUNTIME_EVENT_LOG_NAME + ".previous",
        "runner-supervisor.log",
        "runner-supervisor.log.previous",
        RECOVERY_LATCH_NAME,
    }
    if allow_compact:
        allowed.add(RUNTIME_EVENT_LOG_NAME + ".compact")
    children = tuple(root.iterdir())
    if len(children) > len(allowed):
        raise OSError
    for child in children:
        if (child.name not in allowed or _path_is_reparse(child)
                or not child.is_file() or not _single_link_file(child)):
            raise OSError
        if child.name.startswith("runner-supervisor.log"):
            _validate_operator_segment(child)
        elif child.name == RECOVERY_LATCH_NAME:
            _read_recovery_latch(root)


def _terminal_state_valid(value) -> bool:
    """Enforce the exact combinations emitted by one supervised attempt."""
    status = value["supervisor_exit_code"]
    error = value["error_class"]
    stage = value["stage"]
    core_code = value["core_exit_code"]
    relay_code = value["relay_exit_code"]
    local = value["local_ready"]
    public = value["public_ready"]
    failures = value["readiness_failures"]
    outcome = value["core_outcome"]
    outcome_error = value["core_outcome_error"]
    cleanup = value["cleanup_outcome"]

    no_children = core_code is None and relay_code is None
    no_readiness = local is None and public is None and failures == 0
    no_core_evidence = outcome is None and outcome_error is None
    if status not in {0, 1} or cleanup not in {"proven", "failed"}:
        return False

    if error is None:
        return (
            stage == "complete" and status == 0 and cleanup == "proven"
            and no_children and no_readiness and outcome_error is None
            and outcome in (None, {"status": "STOPPED"})
        )
    early = {
        "runtime_input_missing": "input_validation",
        "supervisor_setup_failed": "setup",
        "job_setup_failed": "job_setup",
        "relay_launch_failed": "relay_start",
        "core_launch_failed": "core_start",
    }
    if error in early:
        return (
            stage == early[error] and status == 1 and no_children
            and no_readiness and no_core_evidence
        )
    if error == "runtime_event_write_failed":
        # A failed history append is represented by control_failure instead;
        # accepting a terminal row would falsely claim that append succeeded.
        return False
    if error == "operator_event_write_failed":
        if stage == "setup":
            return status == 1 and no_children and no_readiness and no_core_evidence
        if stage != "cleanup" or status != 1:
            return False
        if not no_children and not no_readiness:
            return False
        if no_children and (local is None) != (public is None):
            return False
        return no_readiness or (type(local) is bool and type(public) is bool)
    if error == "supervision_failed":
        return (
            stage == "startup" and status == 1 and no_children
            and no_readiness
        )
    if error in {"core_exit", "relay_exit", "core_and_relay_exit"}:
        expected_stages = {
            "core_exit": {"startup", "steady"},
            "relay_exit": {"relay_start", "startup", "steady"},
            "core_and_relay_exit": {"startup", "steady"},
        }
        codes_match = {
            "core_exit": core_code is not None and relay_code is None,
            "relay_exit": relay_code is not None and core_code is None,
            "core_and_relay_exit": core_code is not None and relay_code is not None,
        }[error]
        if not (
            stage in expected_stages[error] and status == 1 and codes_match
            and no_readiness
        ):
            return False
        if error == "relay_exit" and stage == "relay_start":
            return no_core_evidence
        return outcome is not None or outcome_error is not None
    if error == "startup_timeout":
        return (
            stage == "startup" and status == 1 and no_children
            and type(local) is bool and type(public) is bool and failures == 0
            and (outcome is not None or outcome_error is not None)
        )
    readiness = {
        "local_readiness_failed": (False, True),
        "public_readiness_failed": (True, False),
        "local_public_readiness_failed": (False, False),
    }
    if error in readiness:
        return (
            stage == "steady" and status == 1 and no_children
            and (local, public) == readiness[error]
            and failures == READINESS_FAILURE_LIMIT
            and (outcome is not None or outcome_error is not None)
        )
    if error == "planned_stop":
        return (
            stage in {"setup", "startup", "steady"}
            and status == (0 if cleanup == "proven" else 1)
            and no_children and local is None and public is None
            and 0 <= failures < READINESS_FAILURE_LIMIT
            and outcome_error is None
            and outcome in (None, {"status": "STOPPED"})
        )
    return False


def _validate_runtime_event(value, *, recorded: bool = False):
    keys = RUNTIME_EVENT_KEYS | ({"at"} if recorded else set())
    if type(value) is dict:
        if value.get("schema") == "nobus-runtime-event-4":
            keys |= RUNTIME_V4_KEYS
        elif value.get("schema") == "nobus-runtime-event-5":
            keys |= RUNTIME_V5_KEYS
    if type(value) is not dict or set(value) != keys:
        raise ValueError("runtime event fields are invalid")
    if (value["schema"] not in {"nobus-runtime-event-3", "nobus-runtime-event-4", "nobus-runtime-event-5"}
            or re.fullmatch(r"[0-9a-f]{32}", value["series_id"]) is None
            or re.fullmatch(r"[0-9a-f]{32}", value["run_id"]) is None
            or not _digest(value["activation_binding"])
            or (value["previous_event_digest"] is not None
                and not _digest(value["previous_event_digest"]))
            or (value["reset_of_digest"] is not None
                and not _digest(value["reset_of_digest"]))
            or (value["anchor_of_digest"] is not None
                and not _digest(value["anchor_of_digest"]))
            or value["event"] not in {
                "bootstrap", "control_starting", "control_ready",
                "control_closing", "control_closed", "control_failure",
                "starting", "terminal", "retry_waiting", "retry_elapsed",
                "recovery_wait_stopped", "recovery_reset", "activation_rebind",
                "history_checkpoint", "reboot_reconciled", "power_reconciled",
            }
            or value["stage"] not in _EVENT_STAGES
            or value["error_class"] not in _EVENT_ERRORS
            or value["recovery_disposition"] not in _RECOVERY_DISPOSITIONS
            or value["core_outcome_error"] not in _CORE_OUTCOME_ERRORS
            or value["cleanup_outcome"] not in {"not_started", "proven", "failed"}):
        raise ValueError("runtime event value is invalid")
    if value["schema"] in {"nobus-runtime-event-4", "nobus-runtime-event-5"}:
        for key in ("boot_id", "previous_boot_id"):
            if value[key] is not None and not _digest(value[key]):
                raise ValueError("boot identity invalid")
        if value["relay_cause"] is not None and value["relay_cause"] not in RELAY_CAUSES:
            raise ValueError("relay cause invalid")
        semantic_event = value["checkpoint_event"] or value["event"]
        if value["relay_cause"] is not None and (semantic_event != "terminal" or value["error_class"] not in {"relay_exit", "core_and_relay_exit"}):
            raise ValueError("relay cause misplaced")
        if value["previous_boot_id"] is not None and semantic_event not in {"reboot_reconciled", "power_reconciled"}:
            raise ValueError("previous boot misplaced")
        if value["boot_id"] is not None and semantic_event not in {"starting", "reboot_reconciled", "power_reconciled"}:
            raise ValueError("boot identity misplaced")
        if (value["schema"] == "nobus-runtime-event-5"
                and (semantic_event != "power_reconciled"
                     or not _digest(value["power_evidence_digest"]))):
            raise ValueError("power evidence misplaced")
    if recorded and re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
        value["at"],
    ) is None:
        raise ValueError("runtime event timestamp is invalid")
    for name in ("supervisor_exit_code", "core_exit_code", "relay_exit_code"):
        if (value[name] is not None
                and (type(value[name]) is not int
                     or not -(2 ** 31) <= value[name] <= 2 ** 32 - 1)):
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
            encoded = json.dumps(
                value["core_outcome"], ensure_ascii=True, separators=(",", ":")
            ).encode("ascii") + b"\n"
        except (TypeError, ValueError, UnicodeEncodeError):
            raise ValueError("runtime event Core outcome is invalid") from None
        parsed, error = _parse_core_outcome(encoded)
        if error is not None or parsed != value["core_outcome"]:
            raise ValueError("runtime event Core outcome is invalid")
    if value["core_outcome"] is not None and value["core_outcome_error"] is not None:
        raise ValueError("runtime event Core outcome is inconsistent")
    if not _core_outcome_matches_exit(
        value["core_exit_code"], value["core_outcome"]
    ):
        raise ValueError("runtime event Core outcome contradicts exit code")

    if value["event"] == "history_checkpoint":
        if (value["checkpoint_event"] not in {
                "control_starting", "control_ready", "control_closing",
                "control_closed", "control_failure", "starting", "terminal",
                "retry_waiting", "retry_elapsed", "recovery_wait_stopped",
                "recovery_reset", "activation_rebind", "reboot_reconciled", "power_reconciled",
            } or not _digest(value["anchor_of_digest"])):
            raise ValueError("runtime history checkpoint is invalid")
        semantic = dict(value)
        semantic["event"] = value["checkpoint_event"]
        semantic["checkpoint_event"] = None
        semantic["anchor_of_digest"] = None
        _validate_runtime_event(semantic, recorded=recorded)
        return
    if value["checkpoint_event"] is not None or value["anchor_of_digest"] is not None:
        raise ValueError("runtime event checkpoint fields are invalid")

    empty_process_fields = (
        value["core_exit_code"] is None
        and value["relay_exit_code"] is None
        and value["local_ready"] is None
        and value["public_ready"] is None
        and value["readiness_failures"] == 0
        and value["core_outcome"] is None
        and value["core_outcome_error"] is None
    )
    event = value["event"]
    if event == "bootstrap":
        valid = (
            value["stage"] == "recovery_control"
            and value["error_class"] is None
            and value["supervisor_exit_code"] == 0
            and value["recovery_disposition"] == "initialized"
            and value["cleanup_outcome"] == "proven"
            and value["previous_event_digest"] is None
            and value["reset_of_digest"] is None
            and empty_process_fields
        )
    elif event in {"control_starting", "control_ready"}:
        valid = (
            value["stage"] == "recovery_control"
            and value["error_class"] is None
            and value["supervisor_exit_code"] == (0 if event == "control_ready" else None)
            and value["recovery_disposition"] == "pending"
            and value["cleanup_outcome"] == "not_started"
            and value["reset_of_digest"] is None
            and empty_process_fields
        )
    elif event in {"control_closing", "control_closed"}:
        disposition = value["recovery_disposition"]
        valid = (
            value["stage"] == "recovery_control"
            and value["error_class"] is None
            and (
                (value["supervisor_exit_code"] == 0
                 and disposition in {"complete", "stop_planned"})
                or (value["supervisor_exit_code"] == 1
                    and disposition in {
                        "stop_non_retryable", "stop_budget_exhausted",
                        "stop_cleanup_failed", "stop_evidence_failed",
                    })
            )
            and value["cleanup_outcome"] == "proven"
            and value["reset_of_digest"] is None
            and empty_process_fields
        )
    elif event == "control_failure":
        expected_exit = {
            "stop_control_create_failed": EXIT_STOP_CONTROL_CREATE_FAILED,
            "stop_control_signal_failed": EXIT_STOP_CONTROL_SIGNAL_FAILED,
            "stop_control_close_failed": EXIT_STOP_CONTROL_CLOSE_FAILED,
            "stop_control_callback_failed": EXIT_RUNTIME_EVIDENCE_FAILED,
            "runtime_event_write_failed": EXIT_RUNTIME_EVIDENCE_FAILED,
            "recovery_wait_event_write_failed": EXIT_RUNTIME_EVIDENCE_FAILED,
        }
        valid = (
            value["stage"] == "recovery_control"
            and value["error_class"] in expected_exit
            and value["supervisor_exit_code"] == expected_exit.get(value["error_class"])
            and value["recovery_disposition"] == "stop_evidence_failed"
            and value["cleanup_outcome"] == "proven"
            and value["reset_of_digest"] is None
            and empty_process_fields
        )
    elif event == "starting":
        valid = (
            value["stage"] == "setup"
            and value["error_class"] is None
            and value["supervisor_exit_code"] is None
            and value["recovery_disposition"] == "pending"
            and value["cleanup_outcome"] == "not_started"
            and value["reset_of_digest"] is None
            and empty_process_fields
        )
    elif event in {"retry_waiting", "retry_elapsed"}:
        valid = (
            value["stage"] == "recovery_wait"
            and value["error_class"] is None
            and value["supervisor_exit_code"] is None
            and value["attempt"] <= value["retry_budget"]
            and value["recovery_disposition"] == "retry"
            and value["cleanup_outcome"] == "proven"
            and value["reset_of_digest"] is None
            and empty_process_fields
        )
    elif event == "recovery_wait_stopped":
        valid = (
            value["stage"] == "recovery_wait"
            and value["error_class"] == "planned_stop"
            and value["supervisor_exit_code"] == 0
            and value["attempt"] <= value["retry_budget"]
            and value["recovery_disposition"] == "stop_planned"
            and value["cleanup_outcome"] == "proven"
            and value["reset_of_digest"] is None
            and empty_process_fields
        )
    elif event in {"reboot_reconciled", "power_reconciled"}:
        valid = (
            value["schema"] == ("nobus-runtime-event-4" if event == "reboot_reconciled" else "nobus-runtime-event-5")
            and _digest(value.get("boot_id")) and _digest(value.get("previous_boot_id"))
            and ((value["boot_id"] != value["previous_boot_id"]) == (event == "reboot_reconciled"))
            and value["stage"] == "recovery_control" and value["error_class"] is None
            and value["supervisor_exit_code"] == 0 and value["cleanup_outcome"] == "proven"
            and value["recovery_disposition"] == "retry" and value["attempt"] <= value["retry_budget"]
            and _digest(value["reset_of_digest"]) and empty_process_fields
        )
    elif event == "recovery_reset":
        valid = (
            value["stage"] == "recovery_control"
            and value["error_class"] is None
            and value["supervisor_exit_code"] == 0
            and value["recovery_disposition"] == "reset"
            and value["cleanup_outcome"] == "proven"
            and _digest(value["reset_of_digest"])
            and empty_process_fields
        )
    elif event == "activation_rebind":
        valid = (
            value["stage"] == "recovery_control"
            and value["error_class"] is None
            and value["supervisor_exit_code"] == 0
            and value["attempt"] == 1
            and value["recovery_disposition"] == "initialized"
            and value["cleanup_outcome"] == "proven"
            and _digest(value["reset_of_digest"])
            and empty_process_fields
        )
    else:
        valid = (
            value["recovery_disposition"] in _ATTEMPT_DISPOSITIONS
            and value["reset_of_digest"] is None
            and _terminal_state_valid(value)
        )
        if valid:
            expected = _recovery_disposition(
                status=value["supervisor_exit_code"], terminal=value,
                core_outcome=value["core_outcome"],
                core_outcome_error=value["core_outcome_error"],
                cleanup_ok=value["cleanup_outcome"] == "proven",
                attempt=value["attempt"], retry_budget=value["retry_budget"],
            )
            valid = value["recovery_disposition"] == expected
    if not valid:
        raise ValueError("runtime event state is inconsistent")


def _effective_event(value):
    if value["event"] != "history_checkpoint":
        return value
    semantic = dict(value)
    semantic["event"] = value["checkpoint_event"]
    semantic["checkpoint_event"] = None
    semantic["anchor_of_digest"] = None
    return semantic


def _validate_transition(previous, current, previous_digest):
    previous = _effective_event(previous)
    current = _effective_event(current)
    if current["previous_event_digest"] != previous_digest:
        raise ValueError("runtime history digest chain is invalid")
    prior, event = previous["event"], current["event"]
    same_series_attempt = (
        current["series_id"] == previous["series_id"]
        and current["attempt"] == previous["attempt"]
        and current["retry_budget"] == previous["retry_budget"]
        and current["activation_binding"] == previous["activation_binding"]
    )
    if event == "activation_rebind":
        clean_prior = (
            prior in {"bootstrap", "recovery_reset", "activation_rebind"}
            or (
                prior == "control_closed"
                and previous["recovery_disposition"] in {"complete", "stop_planned"}
            )
        )
        valid = (
            clean_prior
            and current["reset_of_digest"] == previous_digest
            and current["activation_binding"] != previous["activation_binding"]
            and current["series_id"] != previous["series_id"]
            and current["attempt"] == 1
            and current["retry_budget"] == previous["retry_budget"]
        )
        if not valid:
            raise ValueError("runtime activation rebind transition is invalid")
        return
    if current["activation_binding"] != previous["activation_binding"]:
        raise ValueError("runtime history activation binding is invalid")
    if event in {"reboot_reconciled", "power_reconciled"}:
        if not (prior == "starting" and same_series_attempt
                and _digest(previous.get("boot_id"))
                and current["previous_boot_id"] == previous["boot_id"]
                and current["reset_of_digest"] == previous_digest):
            raise ValueError("reboot reconciliation transition invalid")
        return
    if event == "recovery_reset":
        resettable = prior in {
            "control_starting", "control_ready", "starting", "terminal",
            "retry_waiting", "recovery_wait_stopped", "control_closing",
            "control_failure",
        } or (
            prior == "control_closed"
            and previous["recovery_disposition"] not in {"complete", "stop_planned"}
        )
        if not (
            resettable and same_series_attempt
            and current["reset_of_digest"] == previous_digest
        ):
            raise ValueError("runtime recovery reset transition is invalid")
        return
    if event == "control_failure":
        same_attempt_prior = prior in {
            "control_starting", "control_ready", "control_closing", "starting",
            "control_closed", "terminal", "retry_waiting",
            "recovery_wait_stopped",
        } and same_series_attempt
        next_attempt_after_wait = (
            prior in {"retry_elapsed", "reboot_reconciled", "power_reconciled"}
            and current["series_id"] == previous["series_id"]
            and current["attempt"] == previous["attempt"] + 1
            and current["retry_budget"] == previous["retry_budget"]
        )
        clean_prior = (
            prior in {"bootstrap", "recovery_reset", "activation_rebind"}
            or (
                prior == "control_closed"
                and previous["recovery_disposition"] in {"complete", "stop_planned"}
            )
        )
        failed_before_control_start = (
            current["error_class"] == "runtime_event_write_failed"
            and clean_prior
            and current["series_id"] != previous["series_id"]
            and current["attempt"] == 1
            and current["retry_budget"] == previous["retry_budget"]
        )
        if not (same_attempt_prior or next_attempt_after_wait
                or failed_before_control_start):
            raise ValueError("runtime control failure transition is invalid")
        return
    if prior == "bootstrap":
        valid = (
            event == "control_starting"
            and current["attempt"] == 1
            and current["retry_budget"] == previous["retry_budget"]
            and current["series_id"] != previous["series_id"]
        )
    elif prior in {"recovery_reset", "activation_rebind"}:
        valid = (
            event == "control_starting"
            and current["attempt"] == 1
            and current["retry_budget"] == previous["retry_budget"]
            and current["series_id"] != previous["series_id"]
        )
    elif prior == "control_starting":
        valid = (
            event == "control_ready" and same_series_attempt
            and current["run_id"] == previous["run_id"]
        )
    elif prior == "control_ready":
        valid = event == "starting" and same_series_attempt
    elif prior == "starting":
        valid = (
            event == "terminal" and same_series_attempt
            and current["run_id"] == previous["run_id"]
        )
    elif prior == "terminal" and previous["recovery_disposition"] == "retry":
        valid = event == "retry_waiting" and same_series_attempt
    elif prior == "retry_waiting":
        valid = event in {"retry_elapsed", "recovery_wait_stopped"} and same_series_attempt
    elif prior in {"retry_elapsed", "reboot_reconciled", "power_reconciled"}:
        valid = (
            event in {"starting", "control_starting"}
            and current["series_id"] == previous["series_id"]
            and current["attempt"] == previous["attempt"] + 1
            and current["retry_budget"] == previous["retry_budget"]
        )
    elif prior in {"terminal", "recovery_wait_stopped"}:
        valid = (
            event == "control_closing" and same_series_attempt
            and current["recovery_disposition"] == previous["recovery_disposition"]
        )
    elif prior == "control_closing":
        valid = (
            event == "control_closed" and same_series_attempt
            and current["run_id"] == previous["run_id"]
            and current["recovery_disposition"] == previous["recovery_disposition"]
            and current["supervisor_exit_code"] == previous["supervisor_exit_code"]
        )
    elif prior == "control_closed":
        if previous["recovery_disposition"] in {"complete", "stop_planned"}:
            valid = (
                event == "control_starting"
                and current["attempt"] == 1
                and current["retry_budget"] == previous["retry_budget"]
                and current["series_id"] != previous["series_id"]
            )
        else:
            valid = False
    elif prior == "control_failure":
        valid = False
    else:
        valid = False
    if not valid:
        raise ValueError("runtime history transition is invalid")


def _decode_runtime_event(line: bytes):
    if not line.endswith(b"\n") or len(line) > RUNTIME_EVENT_LINE_BYTES:
        raise ValueError("runtime history is invalid")

    try:
        recorded = json.loads(
            line[:-1].decode("ascii"), object_pairs_hook=_unique_json_object
        )
        if type(recorded) is not dict:
            raise ValueError
        extra = (RUNTIME_V4_KEYS if recorded.get("schema") == "nobus-runtime-event-4"
                 else RUNTIME_V5_KEYS if recorded.get("schema") == "nobus-runtime-event-5" else set())
        if set(recorded) != (RUNTIME_RECORDED_KEYS | extra):
            raise ValueError
        authentication = recorded.pop("authentication")
        _verify_authentication(
            recorded, authentication, entropy=_HISTORY_AUTHENTICATION_ENTROPY
        )
        value = recorded
        _validate_runtime_event(value, recorded=True)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError, TypeError):
        raise ValueError("runtime history is invalid") from None
    return value


def _read_runtime_segment(path: Path, *, root: Path, identity):
    if (_path_is_reparse(path) or not path.is_file()
            or not _single_link_file(path)):
        raise OSError
    if not 0 < path.stat().st_size <= RUNTIME_EVENT_LOG_BYTES:
        raise OSError
    content = path.read_bytes()
    if not content.endswith(b"\n") or identity != _plain_root(root, create=False):
        raise OSError
    metadata = path.stat(follow_symlinks=False)
    before = (
        metadata.st_dev, metadata.st_ino, metadata.st_size,
        metadata.st_mtime_ns,
    )
    if _path_is_reparse(path) or not path.is_file():
        raise OSError
    rows = []
    digests = []
    for line in content.splitlines(keepends=True):
        rows.append(_decode_runtime_event(line))
        digests.append("sha256:" + hashlib.sha256(line).hexdigest())
    metadata = path.stat(follow_symlinks=False)
    after = (
        metadata.st_dev, metadata.st_ino, metadata.st_size,
        metadata.st_mtime_ns,
    )
    if before != after:
        raise OSError
    return rows, digests


def _validate_runtime_rows(rows, digests, origins, *, previous_name,
                           activation_binding):
    if not rows:
        return
    if rows[0]["event"] != "bootstrap" or rows[0]["previous_event_digest"] is not None:
        raise ValueError("runtime history bootstrap is invalid")
    if any(not _digest(row["activation_binding"]) for row in rows):
        raise ValueError("runtime history activation binding is invalid")
    checkpoint_seen = False
    for index in range(1, len(rows)):
        if rows[index]["previous_event_digest"] != digests[index - 1]:
            raise ValueError("runtime history digest chain is invalid")
        if rows[index]["event"] == "history_checkpoint":
            previous_rows = origins.count(previous_name)
            if (checkpoint_seen or index != 1
                    or origins[index] != previous_name
                    or previous_rows != 2):
                raise ValueError("runtime history checkpoint placement is invalid")
            checkpoint_seen = True
            continue
        _validate_transition(rows[index - 1], rows[index], digests[index - 1])
    if (activation_binding is not None
            and _effective_event(rows[-1])["activation_binding"] != activation_binding):
        raise ValueError("runtime history activation binding is invalid")


def _validate_runtime_continuation(rows, digests, *, activation_binding):
    """Validate one authenticated segment whose predecessor was compacted."""
    if not rows or not _digest(rows[0]["previous_event_digest"]):
        raise ValueError("runtime history continuation is invalid")
    if any(row["event"] == "history_checkpoint" for row in rows):
        raise ValueError("runtime history checkpoint placement is invalid")
    if any(not _digest(row["activation_binding"]) for row in rows):
        raise ValueError("runtime history activation binding is invalid")
    for index in range(1, len(rows)):
        if rows[index]["previous_event_digest"] != digests[index - 1]:
            raise ValueError("runtime history digest chain is invalid")
        _validate_transition(rows[index - 1], rows[index], digests[index - 1])
    if (activation_binding is not None
            and _effective_event(rows[-1])["activation_binding"] != activation_binding):
        raise ValueError("runtime history activation binding is invalid")


def _runtime_history(*, root: Path, activation_binding: str | None = None,
                     allow_compact=False):
    try:
        identity = _plain_root(root, create=False) if root.exists() else None
        if identity is not None:
            _validate_recovery_inventory(root, allow_compact=allow_compact)
        current = root / RUNTIME_EVENT_LOG_NAME
        previous = root / (RUNTIME_EVENT_LOG_NAME + ".previous")
        # Without an authenticated recovery latch, an incomplete two-segment
        # rotation remains an invalid history rather than exposing an older head.
        if previous.exists() and not current.exists():
            raise OSError
        rows = []
        digests = []
        origins = []
        for path in (previous, current):
            if not path.exists():
                continue
            segment_rows, segment_digests = _read_runtime_segment(
                path, root=root, identity=identity
            )
            rows.extend(segment_rows)
            digests.extend(segment_digests)
            origins.extend([path.name] * len(segment_rows))
        _validate_runtime_rows(
            rows, digests, origins, previous_name=previous.name,
            activation_binding=activation_binding,
        )
        return rows, digests
    except OSError:
        raise RuntimeError("runtime history unavailable") from None


def _same_checkpoint_semantics(first, second) -> bool:
    left = dict(_effective_event(first))
    right = dict(_effective_event(second))
    for name in ("at", "previous_event_digest"):
        left.pop(name, None)
        right.pop(name, None)
    return left == right


def _bounded_staging_bytes(path: Path, *, root: Path, limit: int) -> bytes:
    identity = _plain_root(root, create=False)
    if (_path_is_reparse(path) or not path.is_file() or not _single_link_file(path)):
        raise OSError
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        if before.st_nlink != 1 or not 0 <= before.st_size <= limit:
            raise OSError
        content = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    current = path.stat(follow_symlinks=False)
    fields = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
    if (len(content) != before.st_size or fields(before) != fields(after)
            or fields(before) != fields(current) or _path_is_reparse(path)
            or identity != _plain_root(root, create=False)):
        raise OSError
    return content


def _validate_latched_compact(root: Path, rows, digests, latch):
    if not rows or digests[-1] != latch["previous_event_digest"]:
        raise OSError
    content = _bounded_staging_bytes(
        root / (RUNTIME_EVENT_LOG_NAME + ".compact"), root=root,
        limit=min(RUNTIME_EVENT_LOG_BYTES, 2 * RUNTIME_EVENT_LINE_BYTES),
    )
    lines = content.splitlines(keepends=True)
    if len(lines) > 2 or any(len(line) > RUNTIME_EVENT_LINE_BYTES for line in lines):
        raise OSError
    for index, line in enumerate(lines):
        if not line.endswith(b"\n"):
            if index != len(lines) - 1:
                raise OSError
            continue  # Never history: interrupted bytes remain latched until ack.
        record = _decode_runtime_event(line)
        if index == 0:
            if record != rows[0]:
                raise OSError
        elif (record["event"] != "history_checkpoint"
                or record["anchor_of_digest"] != digests[-1]
                or record["previous_event_digest"] != "sha256:" + hashlib.sha256(lines[0]).hexdigest()
                or not _same_checkpoint_semantics(record, rows[-1])):
            raise OSError
    return content


def _latched_runtime_history(*, root: Path, latch,
                             activation_binding: str | None = None):
    """Recognize only exact authenticated interruption states of rotation."""
    try:
        rows, digests = _runtime_history(
            root=root, activation_binding=activation_binding
        )
        return rows, digests, None
    except (RuntimeError, ValueError):
        pass
    try:
        if (latch is None or latch["activation_binding"] != activation_binding):
            raise OSError
        identity = _plain_root(root, create=False)
        compact = root / (RUNTIME_EVENT_LOG_NAME + ".compact")
        if compact.exists():
            rows, digests = _runtime_history(
                root=root, activation_binding=activation_binding, allow_compact=True
            )
            _validate_latched_compact(root, rows, digests, latch)
            return rows, digests, "compact_pending"
        _validate_recovery_inventory(root)
        previous = root / (RUNTIME_EVENT_LOG_NAME + ".previous")
        current = root / RUNTIME_EVENT_LOG_NAME
        if not previous.exists():
            raise OSError
        previous_rows, previous_digests = _read_runtime_segment(
            previous, root=root, identity=identity
        )
        _validate_runtime_rows(
            previous_rows, previous_digests,
            [previous.name] * len(previous_rows), previous_name=previous.name,
            activation_binding=activation_binding,
        )
        prior = previous_rows[-1]
        prior_is_anchor = (
            previous_digests[-1] == latch["previous_event_digest"]
            or (
                prior["event"] == "history_checkpoint"
                and prior["anchor_of_digest"] == latch["previous_event_digest"]
            )
        )
        if not current.exists():
            if not prior_is_anchor:
                raise OSError
            return previous_rows, previous_digests, "previous_only"
        if current.stat().st_size <= RUNTIME_EVENT_LINE_BYTES:
            fragment = _bounded_staging_bytes(
                current, root=root, limit=RUNTIME_EVENT_LINE_BYTES
            )
            if b"\n" not in fragment and prior_is_anchor:
                return previous_rows, previous_digests, "incomplete_current"
        current_rows, current_digests = _read_runtime_segment(
            current, root=root, identity=identity
        )
        _validate_runtime_continuation(
            current_rows, current_digests,
            activation_binding=activation_binding,
        )
        if not (
            prior["event"] == "history_checkpoint"
            and prior["anchor_of_digest"] == latch["previous_event_digest"]
            and current_digests[-1] == latch["previous_event_digest"]
            and _same_checkpoint_semantics(prior, current_rows[-1])
        ):
            raise OSError
        return previous_rows, previous_digests, "stale_current"
    except (IndexError, OSError, RuntimeError, ValueError):
        raise RuntimeError("runtime history unavailable") from None


def _encoded_record(record):
    if type(record) is not dict or "authentication" in record:
        raise ValueError("runtime event authentication is invalid")
    authenticated = {
        **record,
        "authentication": _authentication(
            record, entropy=_HISTORY_AUTHENTICATION_ENTROPY
        ),
    }
    line = _canonical_ascii(authenticated) + b"\n"
    if len(line) > RUNTIME_EVENT_LINE_BYTES:
        raise ValueError("runtime event line is too large")
    return line


def _write_compacted_previous(root, bootstrap, last, last_digest):
    bootstrap_line = _encoded_record(bootstrap)
    semantic = dict(_effective_event(last))
    semantic["event"] = "history_checkpoint"
    semantic["checkpoint_event"] = _effective_event(last)["event"]
    semantic["anchor_of_digest"] = last_digest
    semantic["previous_event_digest"] = "sha256:" + hashlib.sha256(bootstrap_line).hexdigest()
    semantic["at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _validate_runtime_event(semantic, recorded=True)
    checkpoint_line = _encoded_record(semantic)
    content = bootstrap_line + checkpoint_line
    if len(content) > RUNTIME_EVENT_LOG_BYTES:
        raise OSError
    temporary = root / (RUNTIME_EVENT_LOG_NAME + ".compact")
    previous = root / (RUNTIME_EVENT_LOG_NAME + ".previous")
    if (temporary.exists()
            or (previous.exists()
                and (_path_is_reparse(previous) or not _single_link_file(previous)))):
        raise OSError
    with temporary.open("xb") as stream:
        if os.fstat(stream.fileno()).st_nlink != 1:
            raise OSError
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, previous)
    return semantic, "sha256:" + hashlib.sha256(checkpoint_line).hexdigest()


def _write_runtime_event(value, *, root: Path = LOG_ROOT):
    """Append one linked safe event; compact only this owned bounded history."""
    if type(value) is not dict or value.get("previous_event_digest") is not None:
        raise ValueError("runtime event previous digest is caller-controlled")
    try:
        identity = _plain_root(root, create=True)
        rows, digests = _runtime_history(root=root)
        if not rows and value.get("event") != "bootstrap":
            raise ValueError("runtime event requires explicit bootstrap")
        if rows and value.get("event") == "bootstrap":
            raise ValueError("runtime bootstrap already exists")
        record = dict(value)
        previous_digest = digests[-1] if digests else None
        record["previous_event_digest"] = previous_digest
        if rows:
            _validate_transition(rows[-1], record, previous_digest)
        _validate_runtime_event(record)
        recorded = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **record}
        line = _encoded_record(recorded)
        path = root / RUNTIME_EVENT_LOG_NAME
        previous = root / (RUNTIME_EVENT_LOG_NAME + ".previous")
        for candidate in (path, previous):
            if (candidate.exists()
                    and (_path_is_reparse(candidate) or not candidate.is_file()
                         or not _single_link_file(candidate))):
                raise OSError
        if path.exists() and path.stat().st_size + len(line) > RUNTIME_EVENT_LOG_BYTES:
            if not previous.exists():
                os.replace(path, previous)
            else:
                checkpoint, previous_digest = _write_compacted_previous(
                    root, rows[0], rows[-1], digests[-1]
                )
                path.unlink()
                record["previous_event_digest"] = previous_digest
                _validate_transition(checkpoint, record, previous_digest)
                _validate_runtime_event(record)
                recorded = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **record}
                line = _encoded_record(recorded)
        if identity != _plain_root(root, create=False):
            raise OSError
        with path.open("ab") as stream:
            opened = os.fstat(stream.fileno())
            if opened.st_nlink != 1:
                raise OSError
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())
            if (opened.st_dev, opened.st_ino) != (
                path.stat(follow_symlinks=False).st_dev,
                path.stat(follow_symlinks=False).st_ino,
            ):
                raise OSError
        if (_path_is_reparse(path) or not _single_link_file(path)
                or path.stat().st_size > RUNTIME_EVENT_LOG_BYTES
                or identity != _plain_root(root, create=False)):
            raise OSError
    except (OSError, RuntimeError):
        raise RuntimeError("runtime event write failed") from None
    return "sha256:" + hashlib.sha256(line).hexdigest()


def _runtime_record(series_id: str, run_id: str, event: str, *,
                    activation_binding: str, attempt: int, retry_budget: int,
                    recovery_disposition: str, stage: str, error_class=None,
                    supervisor_exit_code=None, core_exit_code=None, relay_exit_code=None,
                    local_ready=None, public_ready=None, readiness_failures=0,
                    core_outcome=None, core_outcome_error=None,
                    cleanup_outcome="not_started", reset_of_digest=None,
                    boot_id=None, previous_boot_id=None, relay_cause=None,
                    power_evidence_digest=None):
    result = {
        "schema": "nobus-runtime-event-3", "series_id": series_id,
        "run_id": run_id, "event": event, "activation_binding": activation_binding,
        "previous_event_digest": None, "reset_of_digest": reset_of_digest,
        "checkpoint_event": None, "anchor_of_digest": None,
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
    if power_evidence_digest is not None:
        result.update(schema="nobus-runtime-event-5", boot_id=boot_id,
                      previous_boot_id=previous_boot_id, relay_cause=relay_cause,
                      power_evidence_digest=power_evidence_digest)
    elif any(item is not None for item in (boot_id, previous_boot_id, relay_cause)):
        result.update(schema="nobus-runtime-event-4", boot_id=boot_id,
                      previous_boot_id=previous_boot_id, relay_cause=relay_cause)
    return result


def _materialize_latched_control_failure(*, root: Path, latch,
                                         latch_digest: str,
                                         activation_binding: str,
                                         rotation_kind: str):
    """Finish only an exact latched rotation as a durable safe STOP."""
    if rotation_kind not in {"previous_only", "stale_current", "incomplete_current"}:
        raise RuntimeError("runtime evidence repair precondition failed")
    temporary = root.parent / (
        "." + RUNTIME_EVENT_LOG_NAME + "." + uuid4().hex + ".repair"
    )
    created = False
    try:
        identity = _plain_root(root, create=False)
        rows, digests, observed_kind = _latched_runtime_history(
            root=root, latch=latch, activation_binding=activation_binding
        )
        current_latch, current_latch_digest = _read_recovery_latch(root)
        if (observed_kind != rotation_kind or not rows
                or current_latch != latch
                or current_latch_digest != latch_digest):
            raise OSError
        predecessor = rows[-1]
        predecessor_digest = digests[-1]
        record = _runtime_record(
            latch["series_id"], latch["run_id"], "control_failure",
            activation_binding=latch["activation_binding"],
            attempt=latch["attempt"], retry_budget=latch["retry_budget"],
            recovery_disposition="stop_evidence_failed",
            stage="recovery_control", error_class="runtime_event_write_failed",
            supervisor_exit_code=EXIT_RUNTIME_EVIDENCE_FAILED,
            cleanup_outcome="proven",
        )
        record["previous_event_digest"] = predecessor_digest
        _validate_transition(predecessor, record, predecessor_digest)
        _validate_runtime_event(record)
        recorded = {
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **record,
        }
        line = _encoded_record(recorded)
        if len(line) > RUNTIME_EVENT_LOG_BYTES:
            raise OSError

        with temporary.open("xb") as stream:
            created = True
            opened = os.fstat(stream.fileno())
            if opened.st_nlink != 1:
                raise OSError
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())
            saved = temporary.stat(follow_symlinks=False)
            if (opened.st_dev, opened.st_ino) != (saved.st_dev, saved.st_ino):
                raise OSError

        # Reconcile again immediately before the one mutation.  The public CLI
        # holds the production supervisor mutex across this operation.
        check_rows, check_digests, check_kind = _latched_runtime_history(
            root=root, latch=latch, activation_binding=activation_binding
        )
        if (check_kind != rotation_kind or check_digests != digests
                or identity != _plain_root(root, create=False)):
            raise OSError
        current = root / RUNTIME_EVENT_LOG_NAME
        if rotation_kind in {"stale_current", "incomplete_current"}:
            if (_path_is_reparse(current) or not current.is_file()
                    or not _single_link_file(current)):
                raise OSError
            current.unlink()
        if current.exists() or identity != _plain_root(root, create=False):
            raise OSError
        os.replace(temporary, current)
        created = False
        final_rows, final_digests = _runtime_history(
            root=root, activation_binding=activation_binding
        )
        event = final_rows[-1]
        predecessor = final_rows[-2] if len(final_rows) > 1 else None
        predecessor_digest = final_digests[-2] if len(final_digests) > 1 else None
        if (final_digests[-1] != "sha256:" + hashlib.sha256(line).hexdigest()
                or not _latch_matches_control_failure(
                    latch, event, predecessor, predecessor_digest
                )):
            raise OSError
        return event, final_digests[-1]
    except (OSError, RuntimeError, ValueError):
        raise RuntimeError("runtime evidence repair failed") from None
    finally:
        if created and temporary.exists():
            try:
                if (not _path_is_reparse(temporary) and temporary.is_file()
                        and _single_link_file(temporary)):
                    temporary.unlink()
            except OSError:
                pass


def _recovery_disposition(*, status, terminal, core_outcome, core_outcome_error,
                          cleanup_ok, attempt, retry_budget):
    """Classify only explicitly safe transient failures as retryable."""
    if not cleanup_ok:
        return "stop_cleanup_failed"
    if terminal["error_class"] in _EVIDENCE_ERRORS:
        return "stop_evidence_failed"
    if core_outcome_error is not None:
        return "stop_evidence_failed"
    if not _core_outcome_matches_exit(
        terminal.get("core_exit_code"), core_outcome
    ):
        return "stop_evidence_failed"
    if terminal["error_class"] == "planned_stop":
        safe = core_outcome in (None, {"status": "STOPPED"})
        return "stop_planned" if status == 0 and safe else "stop_non_retryable"
    if status == 0:
        return "complete" if core_outcome in (None, {"status": "STOPPED"}) else "stop_non_retryable"
    if core_outcome is not None and core_outcome.get("status") == "FAIL":
        transient = (
            terminal["error_class"] == "core_exit"
            and core_outcome == {"status": "FAIL", "code": "telegram_unavailable"}
        )
        if not transient:
            return "stop_non_retryable"
        return "retry" if attempt <= retry_budget else "stop_budget_exhausted"
    transient = (
        (
            terminal["error_class"] == "relay_exit"
            and (
                # Preserve the interpretation of authenticated historical v3 rows.
                ("relay_cause" not in terminal and terminal.get("stage") == "steady"
                 and core_outcome == {"status": "STOPPED"})
                or (terminal.get("relay_cause") in TRANSIENT_RELAY_CAUSES
                    and terminal.get("stage") in {"relay_start", "startup", "steady"}
                    and (core_outcome == {"status": "STOPPED"}
                         or (terminal.get("stage") == "relay_start" and core_outcome is None)))
            )
        )
        or (
            terminal["error_class"] in {"public_readiness_failed", "startup_timeout"}
            and terminal["local_ready"] is True
            and terminal["public_ready"] is False
            and core_outcome == {"status": "STOPPED"}
        )
    )
    if not transient:
        return "stop_non_retryable"
    return "retry" if attempt <= retry_budget else "stop_budget_exhausted"


def _run_bounded_recovery(run_attempt, *, stop_event, first_attempt,
                          retry_budget, retry_interval, on_wait_start=None,
                          on_wait_complete=None, on_wait_stop=None):
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
        if on_wait_start is not None:
            on_wait_start(attempt)
        if stop_event.wait(retry_interval):
            if on_wait_stop is not None:
                on_wait_stop(attempt)
            return 0
        if on_wait_complete is not None:
            on_wait_complete(attempt)
    return 1


def _last_runtime_event(*, root: Path = LOG_ROOT, activation_binding=None):
    """Return the newest bounded event and a digest suitable for exact reset."""
    try:
        rows, digests = _runtime_history(
            root=root, activation_binding=activation_binding
        )
        if not rows:
            return None, None
        return rows[-1], digests[-1]
    except (OSError, ValueError):
        raise RuntimeError("runtime history unavailable") from None


def _recovery_state(*, root: Path = LOG_ROOT, activation_binding=None):
    """Resume a proven retry, or fail closed on STOP/UNKNOWN history."""
    try:
        latch, latch_digest = _read_recovery_latch(root)
        if latch is None:
            rows, digests = _runtime_history(
                root=root, activation_binding=activation_binding
            )
            rotation_kind = None
        else:
            rows, digests, rotation_kind = _latched_runtime_history(
                root=root, latch=latch,
                activation_binding=activation_binding,
            )
        event = rows[-1] if rows else None
        digest = digests[-1] if digests else None
    except (OSError, RuntimeError, ValueError):
        return {"state": "blocked", "reason": "runtime_history_invalid",
                "series_id": None, "next_attempt": None, "last_digest": None}
    if event is None:
        return {"state": "blocked", "reason": "runtime_history_missing",
                "series_id": None, "next_attempt": None, "last_digest": None}
    if latch is not None:
        if latch["activation_binding"] != activation_binding:
            return {"state": "blocked", "reason": "runtime_history_invalid",
                    "series_id": None, "next_attempt": None, "last_digest": None}
        if rotation_kind in {"previous_only", "stale_current", "incomplete_current", "compact_pending"}:
            return {
                "state": "blocked", "reason": "runtime_event_write_failed",
                "series_id": latch["series_id"], "next_attempt": None,
                "last_digest": latch_digest,
            }
        predecessor = rows[-2] if len(rows) > 1 else None
        predecessor_digest = digests[-2] if len(digests) > 1 else None
        if digest == latch["previous_event_digest"]:
            return {
                "state": "blocked", "reason": "runtime_event_write_failed",
                "series_id": latch["series_id"], "next_attempt": None,
                "last_digest": latch_digest,
            }
        if not (
            _latch_matches_control_starting(
                latch, event, predecessor, predecessor_digest
            )
            or _latch_matches_control_failure(
                latch, event, predecessor, predecessor_digest
            )
        ):
            return {"state": "blocked", "reason": "runtime_history_invalid",
                    "series_id": None, "next_attempt": None, "last_digest": None}
    event = _effective_event(event)
    if event["event"] in {"bootstrap", "recovery_reset", "activation_rebind"}:
        return {"state": "new", "reason": None, "series_id": None,
                "next_attempt": 1, "last_digest": digest}
    if event["event"] == "starting":
        return {"state": "blocked", "reason": "previous_attempt_unknown",
                "series_id": event["series_id"], "next_attempt": None,
                "last_digest": digest}
    disposition = event["recovery_disposition"]
    if event["event"] in {"retry_elapsed", "reboot_reconciled", "power_reconciled"} and event["attempt"] <= event["retry_budget"]:
        return {"state": "resume", "reason": None,
                "series_id": event["series_id"],
                "next_attempt": event["attempt"] + 1, "last_digest": digest}
    if event["event"] == "control_closed":
        if disposition in {"complete", "stop_planned"}:
            return {"state": "new", "reason": None, "series_id": None,
                    "next_attempt": 1, "last_digest": digest}
        return {"state": "blocked", "reason": disposition,
                "series_id": event["series_id"], "next_attempt": None,
                "last_digest": digest}
    reasons = {
        "control_starting": "previous_control_setup_unknown",
        "control_ready": "previous_control_callback_unknown",
        "control_closing": "previous_control_close_unknown",
        "control_failure": event["error_class"],
        "terminal": "retry_transition_missing" if disposition == "retry" else "previous_control_close_unknown",
        "retry_waiting": "recovery_wait_unknown",
        "recovery_wait_stopped": "previous_control_close_unknown",
    }
    return {"state": "blocked", "reason": reasons.get(event["event"], "runtime_history_invalid"),
            "series_id": event["series_id"], "next_attempt": None,
            "last_digest": digest}


def _inspect_recovery(*, root: Path = LOG_ROOT, activation_binding=None):
    state = _recovery_state(root=root, activation_binding=activation_binding)
    return {
        "schema": "nobus-recovery-control-1",
        "status": "PASS" if state["state"] != "blocked" else "STOP",
        **state,
    }


def _initialize_recovery(*, root: Path, activation_binding: str):
    if not _digest(activation_binding):
        raise ValueError("recovery activation binding is invalid")
    try:
        latch, _latch_digest = _read_recovery_latch(root)
        if latch is not None:
            raise RuntimeError
        event, digest = _last_runtime_event(root=root)
    except (RuntimeError, ValueError):
        if root.exists() and any(root.iterdir()):
            raise
        event = digest = None
    if event is not None:
        if _effective_event(event)["activation_binding"] != activation_binding:
            raise RuntimeError("recovery activation rebind required")
        return {
            "schema": "nobus-recovery-control-2", "status": "ALREADY_INITIALIZED",
            "activation_binding": activation_binding, "event_digest": digest,
        }
    event_digest = _write_runtime_event(_runtime_record(
        uuid4().hex, uuid4().hex, "bootstrap",
        activation_binding=activation_binding, attempt=1,
        retry_budget=RECOVERY_RETRY_BUDGET, recovery_disposition="initialized",
        stage="recovery_control", supervisor_exit_code=0,
        cleanup_outcome="proven",
    ), root=root)
    return {
        "schema": "nobus-recovery-control-2", "status": "INITIALIZED",
        "activation_binding": activation_binding, "event_digest": event_digest,
    }


def _rebind_recovery(expected_digest: str, *, root: Path,
                     activation_binding: str):
    """Move a clean preserved history to one exact new activation binding."""
    if (not _digest(expected_digest) or not _digest(activation_binding)):
        raise ValueError("recovery rebind digest is invalid")
    latch, _latch_digest = _read_recovery_latch(root)
    if latch is not None:
        raise RuntimeError("recovery rebind precondition failed")
    event, digest = _last_runtime_event(root=root)
    if event is None or digest != expected_digest:
        raise RuntimeError("recovery rebind precondition failed")
    semantic = _effective_event(event)
    old_binding = semantic["activation_binding"]
    if (old_binding == activation_binding
            or _recovery_state(root=root, activation_binding=old_binding)["state"] != "new"):
        raise RuntimeError("recovery rebind precondition failed")
    rebind_digest = _write_runtime_event(_runtime_record(
        uuid4().hex, uuid4().hex, "activation_rebind",
        activation_binding=activation_binding,
        attempt=1, retry_budget=semantic["retry_budget"],
        recovery_disposition="initialized", stage="recovery_control",
        supervisor_exit_code=0, cleanup_outcome="proven",
        reset_of_digest=expected_digest,
    ), root=root)
    return {
        "schema": "nobus-recovery-control-2", "status": "REBOUND",
        "activation_binding": activation_binding,
        "rebind_of_digest": expected_digest,
        "event_digest": rebind_digest,
    }


def _acknowledge_recovery_stop(expected_digest: str, *, root: Path = LOG_ROOT,
                               activation_binding=None):
    if re.fullmatch(r"sha256:[0-9a-f]{64}", expected_digest) is None:
        raise ValueError("recovery reset digest is invalid")
    try:
        latch, latch_digest = _read_recovery_latch(root)
    except (OSError, ValueError):
        raise RuntimeError("recovery reset precondition failed") from None
    state = _recovery_state(root=root, activation_binding=activation_binding)
    try:
        if latch is None:
            rows, digests = _runtime_history(
                root=root, activation_binding=activation_binding
            )
            rotation_kind = None
        else:
            rows, digests, rotation_kind = _latched_runtime_history(
                root=root, latch=latch,
                activation_binding=activation_binding,
            )
        event = rows[-1] if rows else None
        digest = digests[-1] if digests else None
    except (OSError, RuntimeError, ValueError):
        raise RuntimeError("recovery reset precondition failed") from None
    acknowledged_latch = None
    if latch is not None:
        if (latch["activation_binding"] != activation_binding
                or state["state"] != "blocked"):
            raise RuntimeError("recovery reset precondition failed")
        repaired_from_latch = False
        if rotation_kind == "compact_pending":
            if expected_digest != latch_digest or state["last_digest"] != latch_digest:
                raise RuntimeError("recovery reset precondition failed")
            content = _validate_latched_compact(root, rows, digests, latch)
            check_rows, check_digests, check_kind = _latched_runtime_history(
                root=root, latch=latch, activation_binding=activation_binding
            )
            if (check_kind != rotation_kind or check_digests != digests
                    or _validate_latched_compact(root, check_rows, check_digests, latch) != content):
                raise RuntimeError("recovery reset precondition failed")
            (root / (RUNTIME_EVENT_LOG_NAME + ".compact")).unlink()
            rows, digests = _runtime_history(root=root, activation_binding=activation_binding)
            event, digest = rows[-1], digests[-1]
            rotation_kind = None
        if rotation_kind in {"previous_only", "stale_current", "incomplete_current"}:
            if expected_digest != latch_digest or state["last_digest"] != latch_digest:
                raise RuntimeError("recovery reset precondition failed")
            event, digest = _materialize_latched_control_failure(
                root=root, latch=latch, latch_digest=latch_digest,
                activation_binding=activation_binding,
                rotation_kind=rotation_kind,
            )
            rows, digests = _runtime_history(
                root=root, activation_binding=activation_binding
            )
            repaired_from_latch = True
        elif digest == latch["previous_event_digest"]:
            if expected_digest != latch_digest or state["last_digest"] != latch_digest:
                raise RuntimeError("recovery reset precondition failed")
            digest = _write_runtime_event(_runtime_record(
                latch["series_id"], latch["run_id"], "control_failure",
                activation_binding=latch["activation_binding"],
                attempt=latch["attempt"], retry_budget=latch["retry_budget"],
                recovery_disposition="stop_evidence_failed",
                stage="recovery_control", error_class="runtime_event_write_failed",
                supervisor_exit_code=EXIT_RUNTIME_EVIDENCE_FAILED,
                cleanup_outcome="proven",
            ), root=root)
            event, _current = _last_runtime_event(
                root=root, activation_binding=activation_binding
            )
            rows, digests = _runtime_history(
                root=root, activation_binding=activation_binding
            )
            predecessor = rows[-2] if len(rows) > 1 else None
            predecessor_digest = digests[-2] if len(digests) > 1 else None
            if (_current != digest or not _latch_matches_control_failure(
                    latch, event, predecessor, predecessor_digest)):
                raise RuntimeError("recovery reset precondition failed")
            repaired_from_latch = True
        predecessor = rows[-2] if len(rows) > 1 else None
        predecessor_digest = digests[-2] if len(digests) > 1 else None
        if (_latch_matches_control_starting(
                latch, event, predecessor, predecessor_digest)
                or _latch_matches_control_failure(
                    latch, event, predecessor, predecessor_digest)):
            if (not repaired_from_latch
                    and (expected_digest != digest
                         or state["last_digest"] != digest)):
                raise RuntimeError("recovery reset precondition failed")
            acknowledged_latch = latch_digest
            _clear_recovery_latch(root=root, expected_digest=latch_digest)
        else:
            raise RuntimeError("recovery reset precondition failed")
        state = _recovery_state(root=root, activation_binding=activation_binding)
        event, digest = _last_runtime_event(
            root=root, activation_binding=activation_binding
        )
    if (state["state"] != "blocked" or event is None
            or state["last_digest"] != digest):
        raise RuntimeError("recovery reset precondition failed")
    if acknowledged_latch is None and digest != expected_digest:
        raise RuntimeError("recovery reset precondition failed")
    semantic = _effective_event(event)
    reset_digest = _write_runtime_event(_runtime_record(
        semantic["series_id"], uuid4().hex, "recovery_reset",
        activation_binding=semantic["activation_binding"],
        attempt=semantic["attempt"], retry_budget=semantic["retry_budget"],
        recovery_disposition="reset", stage="recovery_control",
        supervisor_exit_code=0, cleanup_outcome="proven",
        reset_of_digest=digest,
    ), root=root)
    result = {
        "schema": "nobus-recovery-control-1",
        "status": "RESET",
        "reset_of_digest": digest,
        "reset_event_digest": reset_digest,
    }
    if acknowledged_latch is not None:
        result["evidence_latch_digest"] = acknowledged_latch
    return result


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


def _operator_event(code, *, root: Path = LOG_ROOT):
    if code not in {"starting", "stopped", "runtime_failed", "cleanup_failed"}:
        raise ValueError("runtime event is invalid")
    line = (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            + " " + code + "\n").encode("ascii")
    try:
        identity = _plain_root(root, create=True)
        path = root / "runner-supervisor.log"
        previous = root / "runner-supervisor.log.previous"
        for candidate in (path, previous):
            if (candidate.exists()
                    and (_path_is_reparse(candidate) or not candidate.is_file()
                         or not _single_link_file(candidate))):
                raise OSError
            if candidate.exists():
                _validate_operator_segment(candidate)
        if path.exists() and path.stat().st_size + len(line) > OPERATOR_EVENT_LOG_BYTES:
            os.replace(path, previous)
        if identity != _plain_root(root, create=False):
            raise OSError
        with path.open("ab") as stream:
            opened = os.fstat(stream.fileno())
            if opened.st_nlink != 1:
                raise OSError
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())
            current = path.stat(follow_symlinks=False)
            if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
                raise OSError
        if (_path_is_reparse(path) or not _single_link_file(path)
                or path.stat().st_size > OPERATOR_EVENT_LOG_BYTES
                or identity != _plain_root(root, create=False)):
            raise OSError
    except OSError:
        raise RuntimeError("runtime operator event write failed") from None


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


def spawn_owned(api, job: int, command: list[str], *, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL):
    gate, name = api.create_gate()
    process = None
    try:
        process = subprocess.Popen(
            [str(Path(sys._base_executable).with_name("python.exe")), "-I", "-S", str(Path(__file__).resolve()),
             "--gated-child", name, "--", *command],
            cwd=WORKTREE, stdin=subprocess.PIPE, stdout=stdout,
            stderr=stderr, creationflags=CREATE_NO_WINDOW,
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


def stop_process(process, *, graceful: bool = False, on_preexisting_exit=None) -> bool:
    if process is None:
        return True
    code = process.poll()
    if code is not None:
        if on_preexisting_exit is not None:
            on_preexisting_exit(code)
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
        self.last = None
        self.reason = None

    def run(self, read, *, seconds, stop_event=None):
        deadline = time.monotonic() + seconds
        self.reason = None
        if stop_event is not None and stop_event.is_set():
            self.reason = "cancelled"
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
                self.reason = "probe_busy"
                return False
            worker = threading.Thread(target=work, name="nobus-readiness", daemon=True)
            self._thread = worker
            worker.start()
        while True:
            if stop_event is not None and stop_event.is_set():
                self.reason = "cancelled"
                return False
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.reason = "deadline"
                return False
            if done.wait(min(.05, remaining)):
                worker.join(timeout=max(0.0, deadline - time.monotonic()))
                # Never consume a late PASS or carry it into another request.
                return (not worker.is_alive() and time.monotonic() < deadline
                        and (stop_event is None or not stop_event.is_set())
                        and result[0])


_LOCAL_READINESS_PROBE = _ReadinessProbe()
_PUBLIC_READINESS_PROBE = _ReadinessProbe()


def _ready_request(url, *, seconds, probe, headers=None, stop_event=None):
    started = time.monotonic()
    detail = {"http_status": None, "body_matches": False, "error_class": None}
    def read():
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "NobusSpace-Health/1.0", **(headers or {})})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
            with opener.open(request, timeout=seconds) as response:
                detail["http_status"] = response.status
                detail["body_matches"] = response.read(256) == b'{"status":"ready"}'
                detail["error_class"] = None if response.status == 200 and detail["body_matches"] else "response_mismatch"
                return detail["error_class"] is None
        except urllib.error.HTTPError as error:
            detail.update(http_status=error.code, error_class="http_error")
        except (TimeoutError, socket.timeout):
            detail["error_class"] = "deadline"
        except urllib.error.URLError as error:
            detail["error_class"] = "deadline" if isinstance(error.reason, TimeoutError) else "transport_error"
        except Exception:
            detail["error_class"] = "probe_error"
        return False
    result = probe.run(read, seconds=seconds, stop_event=stop_event)
    elapsed = round((time.monotonic() - started) * 1000)
    if probe.reason is not None or elapsed >= seconds * 1000:
        detail = {"http_status": None, "body_matches": False,
                  "error_class": probe.reason or "deadline"}
    probe.last = {**detail, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  "elapsed_ms": elapsed, "deadline_ms": int(seconds * 1000),
                  "status": "PASS" if result else "FAIL"}
    return result


def ready(*, stop_event=None) -> bool:
    return _ready_request("http://127.0.0.1:8765/readyz", seconds=2,
                          probe=_LOCAL_READINESS_PROBE,
                          headers={"Host": "app.nobusspace.com"}, stop_event=stop_event)


def public_ready(*, stop_event=None) -> bool:
    return _ready_request(
        PUBLIC_ORIGIN + "/readyz", seconds=5,
        probe=_PUBLIC_READINESS_PROBE, stop_event=stop_event,
    )


def _readiness_pair(stop_event):
    local = ready(stop_event=stop_event)
    public = public_ready(stop_event=stop_event)
    return local, public


def readiness_details():
    return [{"boundary": boundary, **(probe.last or {"status": "NOT CHECKED", "error_class": "not_run"})}
            for boundary, probe in (("local", _LOCAL_READINESS_PROBE), ("public", _PUBLIC_READINESS_PROBE))]


def _write_probe_diagnostic(root, run_id, attempt, stage):
    from scripts.runtime_diagnostics import write_diagnostic
    write_diagnostic(root.parent / "supervisor-diagnostics", "readiness", {
        "run_id": run_id, "attempt": attempt, "stage": stage, "checks": readiness_details(),
    })


def _readiness_error(local: bool, public: bool) -> str:
    if not local and not public:
        return "local_public_readiness_failed"
    return "local_readiness_failed" if not local else "public_readiness_failed"


def supervise(api, job, relay, core, stop_event, *, clock=time.monotonic, probe=None,
              report=None, settle=time.sleep, diagnostic=None) -> int:
    if probe is None:
        probe = lambda: _readiness_pair(stop_event)
    if report is None:
        report = lambda _value: None

    def readiness(stage):
        result = probe()
        if diagnostic is not None:
            diagnostic(stage)
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

    def planned_or_child(stage, failures=0):
        if child_exit(stage):
            return 1
        report({"stage": stage, "error_class": "planned_stop",
                "core_exit_code": None, "relay_exit_code": None,
                "local_ready": None, "public_ready": None,
                "readiness_failures": failures})
        return 0

    deadline = clock() + STARTUP_SECONDS
    last_local = last_public = None
    startup_ready = False
    while clock() < deadline:
        if child_exit("startup"):
            return 1
        if stop_event.is_set():
            return planned_or_child("startup")
        local, public = readiness("startup")
        if child_exit("startup"):
            return 1
        if stop_event.is_set():
            return planned_or_child("startup")
        last_local, last_public = local, public
        if local and public:
            startup_ready = True
            break
        if stop_event.wait(1):
            return planned_or_child("startup")
    if not startup_ready:
        if child_exit("startup"):
            return 1
        if stop_event.is_set():
            return planned_or_child("startup")
        report({"stage": "startup", "error_class": "startup_timeout",
                "core_exit_code": None, "relay_exit_code": None,
                "local_ready": last_local, "public_ready": last_public,
                "readiness_failures": 0})
        return 1
    failures = 0
    while True:
        stopped = stop_event.wait(READINESS_INTERVAL_SECONDS)
        if child_exit("steady"):
            return 1
        if stopped:
            return planned_or_child("steady", failures)
        local, public = readiness("steady")
        if child_exit("steady"):
            return 1
        if stop_event.is_set():
            return planned_or_child("steady", failures)
        failures = 0 if local and public else failures + 1
        if failures >= READINESS_FAILURE_LIMIT:
            settle(CHILD_EXIT_SETTLE_SECONDS)
            if child_exit("steady"):
                return 1
            report({"stage": "steady", "error_class": _readiness_error(local, public),
                    "core_exit_code": None, "relay_exit_code": None,
                    "local_ready": local, "public_ready": public,
                    "readiness_failures": failures})
            return 1


def _arguments(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, _message):
            raise _CliFailure(
                "runtime_arguments_invalid", EXIT_RUNTIME_COMPOSITION_INVALID
            )

    parser = Parser()
    commands = parser.add_mutually_exclusive_group()
    commands.add_argument("--stop", action="store_true")
    commands.add_argument("--check-ready", action="store_true")
    parser.add_argument("--diagnostic-details", action="store_true")
    parser.add_argument("--verify-production-identity", action="store_true")
    commands.add_argument("--inspect-recovery", action="store_true")
    commands.add_argument("--initialize-recovery", action="store_true")
    commands.add_argument("--acknowledge-recovery-stop")
    commands.add_argument("--rebind-recovery-from")
    parser.add_argument("--semantic-admission", action="store_true")
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--voice-model-directory", type=Path)
    parser.add_argument("--backup-root", type=Path)
    parser.add_argument("--backup-ownership")
    parser.add_argument("--health-launcher", type=Path)
    parser.add_argument("--scheduler-task-name", default="NobusSpaceBot")
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


def _bounded_directory_evidence(root: Path) -> dict[str, object]:
    from src.application.runtime_maintenance import checked_path
    from src.contracts.models import canonical_json_digest

    root = checked_path(root)
    _plain_root(root, create=False)
    if not root.is_dir():
        raise ValueError("activation directory is invalid")
    rows = []
    total = 0
    for path in sorted(root.rglob("*")):
        checked_path(path, root=root)
        if _path_is_reparse(path):
            raise ValueError("activation directory is invalid")
        if path.is_dir():
            continue
        if (not path.is_file() or not _single_link_file(path)
                or len(rows) >= 64):
            raise ValueError("activation directory is invalid")
        size = path.stat().st_size
        total += size
        if size <= 0 or total > 1024 * 1024 * 1024:
            raise ValueError("activation directory is invalid")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        rows.append({
            "name": path.relative_to(root).as_posix(),
            "bytes": size,
            "sha256": digest,
        })
    if not rows:
        raise ValueError("activation directory is invalid")
    return {
        "count": len(rows),
        "bytes": total,
        "digest": canonical_json_digest(rows),
    }


def _installed_distribution_identity() -> dict[str, object]:
    from src.contracts.models import canonical_json_digest

    inventory = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        version = distribution.version
        if type(name) is not str or type(version) is not str:
            raise ValueError("installed distribution identity is invalid")
        normalized = re.sub(r"[-_.]+", "-", name).lower()
        if (re.fullmatch(r"[a-z0-9][a-z0-9-]{0,127}", normalized) is None
                or not version or len(version) > 128
                or normalized in inventory):
            raise ValueError("installed distribution identity is invalid")
        inventory[normalized] = version
    rows = [
        {"name": name, "version": inventory[name]}
        for name in sorted(inventory)
    ]
    if not rows or len(rows) > 512:
        raise ValueError("installed distribution identity is invalid")
    return {"count": len(rows), "digest": canonical_json_digest(rows)}


def _scheduler_task_signature(task_name: str):
    """Read one bounded Task Scheduler snapshot through the trusted helper."""
    if re.fullmatch(r"NobusSpace[A-Za-z0-9-]{1,64}", task_name) is None:
        raise ValueError("scheduler task name is invalid")
    helper = WORKTREE / "ops" / "windows" / "Invoke-NobusSpaceTask.ps1"
    powershell = (
        Path(os.environ["SYSTEMROOT"])
        / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    )
    result = subprocess.run(
        [
            str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(helper),
            "-Operation", "Inspect", "-TaskName", task_name,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=30,
        check=False,
        creationflags=CREATE_NO_WINDOW,
    )
    if result.returncode != 0 or not 0 < len(result.stdout) <= 64 * 1024:
        raise RuntimeError("scheduler signature unavailable")
    try:
        value = json.loads(
            result.stdout.decode("utf-8-sig"), object_pairs_hook=_unique_json_object
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        raise RuntimeError("scheduler signature unavailable") from None
    if (type(value) is not dict
            or set(value) != {
                "name", "state", "enabled", "last_result", "current_principal",
                "signature",
            }
            or value["name"] != task_name
            or type(value["signature"]) is not dict):
        raise RuntimeError("scheduler signature unavailable")
    return value


def _validate_scheduler_task_snapshot(value, *, role: str, task_name: str,
                                      expected_action: dict[str, object],
                                      allow_disabled_health: bool = False,
                                      allow_disabled_staging: bool = False,
                                      now: datetime | None = None):
    """Reject unsafe Scheduler composition before hashing its exact identity."""
    from src.contracts.models import canonical_json_digest

    top_keys = {
        "name", "state", "enabled", "last_result", "current_principal",
        "signature",
    }
    signature_keys = {
        "principal", "logon_type", "run_level", "actions", "triggers",
        "start_when_available", "disallow_battery", "stop_on_battery",
        "wake_to_run", "restart_count", "restart_interval",
        "execution_limit", "multiple_instances", "compatibility",
        "allow_demand_start", "allow_hard_terminate",
        "delete_expired_task_after", "hidden", "priority",
        "run_only_if_idle", "idle_duration", "idle_wait_timeout",
        "stop_on_idle_end", "restart_on_idle", "run_only_if_network",
        "network_id", "network_name", "disallow_remote_app_session",
        "unified_scheduling_engine", "volatile",
        "maintenance_settings_present",
    }
    trigger_keys = {
        "type", "enabled", "start", "end", "user", "days_interval",
        "interval", "duration", "stop_at_end", "execution_limit", "id",
        "delay", "random_delay",
    }
    disabled_task = (
        (allow_disabled_staging or (allow_disabled_health and role == "health"))
        and type(value) is dict and value.get("enabled") is False
        and value.get("state") == "Disabled"
    )
    if (role not in {"main", "health", "backup"}
            or type(value) is not dict or set(value) != top_keys
            or value["name"] != task_name
            or (value["enabled"] is not True and not disabled_task)
            or type(value["state"]) is not str
            or type(value["last_result"]) is not int
            or type(value["current_principal"]) is not str
            or re.fullmatch(r"S-[0-9-]{5,184}", value["current_principal"]) is None
            or type(value["signature"]) is not dict
            or set(value["signature"]) != signature_keys):
        raise ValueError("scheduler task profile is invalid")
    signature = value["signature"]
    if (signature["principal"] != value["current_principal"]
            or signature["logon_type"] != 3
            or signature["run_level"] != 0
            or signature["actions"] != [expected_action]
            or type(signature["triggers"]) is not list
            or len(signature["triggers"]) != 1
            or signature["start_when_available"] is not True
            or signature["disallow_battery"] is not False
            or signature["stop_on_battery"] is not False
            or signature["wake_to_run"] is not False
            or signature["restart_count"] != 0
            or signature["restart_interval"] not in {None, ""}
            or signature["multiple_instances"] != 2
            or signature["compatibility"] != 3
            or signature["allow_demand_start"] is not True
            or signature["allow_hard_terminate"] is not True
            or signature["delete_expired_task_after"] != ""
            or signature["hidden"] is not False
            or signature["priority"] != 7
            or signature["run_only_if_idle"] is not False
            or signature["idle_duration"] != "PT10M"
            or signature["idle_wait_timeout"] != "PT1H"
            or signature["stop_on_idle_end"] is not True
            or signature["restart_on_idle"] is not False
            or signature["run_only_if_network"] is not False
            or signature["network_id"] != ""
            or signature["network_name"] != ""
            or signature["disallow_remote_app_session"] is not False
            or signature["unified_scheduling_engine"] is not True
            or signature["volatile"] is not False
            or signature["maintenance_settings_present"] is not False):
        raise ValueError("scheduler task profile is invalid")
    trigger = signature["triggers"][0]
    if (type(trigger) is not dict or set(trigger) != trigger_keys
            or trigger["enabled"] is not True
            or trigger["execution_limit"] != ""
            or trigger["id"] != ""
            or trigger["delay"] != ""
            or trigger["random_delay"] != ""):
        raise ValueError("scheduler task profile is invalid")
    common_trigger = trigger["end"] is None
    if role == "main":
        valid_trigger = (
            common_trigger and trigger["type"] == "MSFT_TaskLogonTrigger"
            and trigger["start"] is None
            and trigger["user"] == value["current_principal"]
            and trigger["days_interval"] is None
            and trigger["interval"] is None and trigger["duration"] is None
            and trigger["stop_at_end"] is False
            and signature["execution_limit"] == "PT0S"
        )
    else:
        try:
            start = datetime.fromisoformat(trigger["start"])
        except (TypeError, ValueError):
            start = None
        aware_start = start is not None and start.tzinfo is not None
        reference = now or datetime.now().astimezone()
        reference_is_aware = reference.tzinfo is not None
        if role == "health":
            valid_trigger = (
                common_trigger and aware_start and reference_is_aware
                and trigger["type"] == "MSFT_TaskTimeTrigger"
                and trigger["user"] is None and trigger["days_interval"] is None
                and trigger["interval"] == "PT1M" and trigger["duration"] == "P3650D"
                and trigger["stop_at_end"] is True
                and signature["execution_limit"] == "PT2M"
                and start <= reference + timedelta(minutes=5)
                and start + timedelta(days=3650) > reference
            )
        else:
            local_start = start.astimezone() if aware_start else None
            local_reference = reference.astimezone() if reference_is_aware else None
            next_daily_start = (
                local_reference.replace(
                    hour=3, minute=30, second=0, microsecond=0
                ) if local_reference is not None else None
            )
            if (next_daily_start is not None
                    and next_daily_start < local_reference):
                next_daily_start += timedelta(days=1)
            valid_trigger = (
                common_trigger and aware_start and reference_is_aware
                and local_start.hour == 3 and local_start.minute == 30
                and local_start.second == 0 and local_start.microsecond == 0
                and local_start <= next_daily_start
                and trigger["type"] == "MSFT_TaskDailyTrigger"
                and trigger["user"] is None and trigger["days_interval"] == 1
                and trigger["interval"] is None and trigger["duration"] is None
                and trigger["stop_at_end"] is False
                and signature["execution_limit"] == "PT20M"
            )
    if not valid_trigger:
        raise ValueError("scheduler task profile is invalid")
    return {"name": task_name, "signature": canonical_json_digest(signature)}


def _resolved_path_text(path: Path) -> str:
    return os.path.normcase(str(Path(path).resolve(strict=True)))


def _task_path_matches(value, expected: Path) -> bool:
    try:
        return type(value) is str and _resolved_path_text(Path(value)) == _resolved_path_text(expected)
    except (OSError, ValueError):
        return False


def _main_scheduler_action(values, runtime: Path, pythonw: Path,
                           health_launcher: Path, task_name: str):
    arguments = [f'"{WORKTREE / "scripts" / "run_nobus_space_live.py"}"']
    if bool(getattr(values, "semantic_admission", False)):
        arguments.append("--semantic-admission")
    arguments.extend([
        "--runtime-root", f'"{runtime}"',
        "--voice-model-directory", f'"{Path(values.voice_model_directory).resolve(strict=True)}"',
        "--backup-root", f'"{Path(values.backup_root).resolve(strict=True)}"',
        "--backup-ownership", values.backup_ownership,
        "--health-launcher", f'"{health_launcher}"',
        "--scheduler-task-name", task_name,
    ])
    return {
        "execute": str(pythonw), "arguments": " ".join(arguments),
        "working_directory": str(WORKTREE),
    }


def _health_scheduler_action(health_launcher: Path):
    return {
        "execute": "powershell.exe",
        "arguments": (
            "-WindowStyle Hidden -NoLogo -NoProfile -NonInteractive "
            f'-ExecutionPolicy Bypass -File "{health_launcher}"'
        ),
        "working_directory": None,
    }


def _backup_action_binding(snapshot, pythonw: Path):
    try:
        action = snapshot["signature"]["actions"]
        if type(action) is not list or len(action) != 1 or type(action[0]) is not dict:
            raise ValueError
        action = action[0]
        if set(action) != {"execute", "arguments", "working_directory"}:
            raise ValueError
        match = re.fullmatch(
            r'"([^"\r\n]{1,2048})" --config "([^"\r\n]{1,2048})" '
            r'--config-digest (sha256:[0-9a-f]{64})',
            str(action["arguments"]),
        )
        if (match is None or not _task_path_matches(action["execute"], pythonw)
                or not _task_path_matches(action["working_directory"], WORKTREE)
                or not _task_path_matches(
                    match.group(1), WORKTREE / "scripts" / "run_telegram_backup_cycle.py"
                )):
            raise ValueError
        config_path = Path(match.group(2))
        if not config_path.is_absolute():
            raise ValueError
        from src.application.runtime_maintenance import checked_path
        config_path = checked_path(config_path, root=WORKTREE)
        return dict(action), config_path, match.group(3)
    except (KeyError, OSError, TypeError, ValueError):
        raise ValueError("scheduler task profile is invalid") from None


def _backup_restart_authorized(config_path: Path, config_digest: str) -> bool:
    """Allow the one health-disabled instant created by the bound backup cycle."""
    try:
        from src.application import managed_backups
        from src.application.runtime_maintenance import checked_path

        journal = checked_path(
            config_path.with_name("backup-cycle-state.dpapi"),
            root=config_path.parent,
        )
        if (_path_is_reparse(journal) or not journal.is_file()
                or not _single_link_file(journal)
                or not 0 < journal.stat().st_size <= 64 * 1024):
            return False
        value = managed_backups._certificate(journal)
        allowed = {
                "schema", "config_digest", "phase", "at", "attempt_id",
                "generation",
            }
        if (type(value) is not dict or set(value) not in (allowed, allowed | {"backup_status"})
                or ("backup_status" in value and value["backup_status"] != "VERIFIED")
                or value["schema"] != "c6-backup-cycle-state-1"
                or value["config_digest"] != config_digest
                or value["phase"] not in {"restart_permitted", "starting"}
                or re.fullmatch(r"[0-9a-f]{32}", value["attempt_id"]) is None
                or managed_backups.GENERATION.fullmatch(value["generation"]) is None):
            return False
        stamp = datetime.fromisoformat(value["at"])
        current = datetime.now().astimezone()
        if stamp.tzinfo is None:
            return False
        age = current - stamp
        # New cycles may follow authenticated retry progress, bounded by the
        # existing 20-minute Scheduler limit with one minute reserved for cleanup.
        return -timedelta(minutes=1) <= age <= timedelta(minutes=19 if "backup_status" in value else 10)
    except (KeyError, OSError, RuntimeError, TypeError, ValueError):
        return False


def _validate_backup_activation_config(path: Path, digest: str, *, application,
                                       runtime: Path, backup: Path, ownership: str,
                                       task_name: str, snapshots):
    from src.application.runtime_maintenance import checked_path, file_evidence
    from src.contracts.models import canonical_json_digest

    path = checked_path(path, root=WORKTREE)
    if (_path_is_reparse(path) or not path.is_file() or not _single_link_file(path)
            or not 0 < path.stat().st_size <= 64 * 1024):
        raise ValueError("backup activation configuration is invalid")
    try:
        value = json.loads(
            path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_json_object
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        raise ValueError("backup activation configuration is invalid") from None
    if (type(value) is not dict
            or set(value) != {
                "schema", "application", "runtime", "backup_root", "ownership",
                "tasks", "inputs",
            }
            or canonical_json_digest(value) != digest
            or value["schema"] != "c6-backup-cycle-1"
            or value["application"] != application
            or not _task_path_matches(value["runtime"], runtime)
            or not _task_path_matches(value["backup_root"], backup)
            or value["ownership"] != ownership
            or type(value["tasks"]) is not dict
            or set(value["tasks"]) != {"main", "health"}
            or type(value["inputs"]) is not dict
            or not 3 <= len(value["inputs"]) <= 64):
        raise ValueError("backup activation configuration is invalid")
    for role, name in (("main", task_name), ("health", task_name + "-Health")):
        item = value["tasks"][role]
        if (type(item) is not dict or set(item) != {"name", "signature"}
                or item["name"] != name
                or item["signature"] != snapshots[role]["signature"]):
            raise ValueError("backup activation configuration is invalid")
    required = {
        "ops/windows/Invoke-NobusSpaceTask.ps1",
        "docs/11-Контекст-продукта.md",
        "codex-runtime.local.json",
    }
    if not required.issubset(value["inputs"]):
        raise ValueError("backup activation configuration is invalid")
    for relative, evidence in value["inputs"].items():
        candidate = Path(relative) if type(relative) is str else Path("/")
        if (candidate.is_absolute() or ".." in candidate.parts
                or file_evidence(checked_path(WORKTREE / candidate, root=WORKTREE)) != evidence):
            raise ValueError("backup activation configuration is invalid")
    result = file_evidence(path)
    if result is None:
        raise ValueError("backup activation configuration is invalid")
    return {"path": path.relative_to(WORKTREE).as_posix(), **result}


def _scheduler_activation(values, runtime: Path, *, application,
                          pythonw: Path, health_launcher: Path,
                          allow_disabled_staging: bool = False):
    task_name = getattr(values, "scheduler_task_name", "NobusSpaceBot")
    if re.fullmatch(r"NobusSpace[A-Za-z0-9-]{1,64}", task_name) is None:
        raise ValueError("scheduler task name is invalid")
    names = {
        "main": task_name,
        "health": task_name + "-Health",
        "backup": task_name + "-Backup",
    }
    snapshots = {role: _scheduler_task_signature(name) for role, name in names.items()}
    staged_disabled = all(
        snapshot["enabled"] is False and snapshot["state"] == "Disabled"
        for snapshot in snapshots.values()
    )
    staging_mode = allow_disabled_staging and staged_disabled
    actions = {
        "main": _main_scheduler_action(values, runtime, pythonw, health_launcher, task_name),
        "health": _health_scheduler_action(health_launcher),
    }
    backup_action, config_path, config_digest = _backup_action_binding(
        snapshots["backup"], pythonw
    )
    actions["backup"] = backup_action
    backup_restart = (
        snapshots["health"]["enabled"] is False
        and _backup_restart_authorized(config_path, config_digest)
    )
    bindings = {
        role: _validate_scheduler_task_snapshot(
            snapshots[role], role=role, task_name=names[role],
            expected_action=actions[role],
            allow_disabled_health=(role == "health" and backup_restart),
            allow_disabled_staging=staging_mode,
        )
        for role in ("main", "health", "backup")
    }
    config = _validate_backup_activation_config(
        config_path, config_digest, application=application, runtime=runtime,
        backup=Path(values.backup_root), ownership=values.backup_ownership,
        task_name=task_name, snapshots=snapshots,
    )
    return {"tasks": bindings, "backup_config": config}


def _activation_manifest(values, runtime: Path, *,
                         allow_disabled_staging: bool = False) -> dict[str, object]:
    from src.application.runtime_maintenance import (
        application_binding,
        file_evidence,
        runtime_target_binding,
    )
    from src.contracts.models import canonical_json_digest

    runtime = Path(runtime).resolve(strict=True)
    voice = getattr(values, "voice_model_directory", None)
    backup = getattr(values, "backup_root", None)
    backup_owner = getattr(values, "backup_ownership", None)
    health_launcher = getattr(values, "health_launcher", None)
    task_name = getattr(values, "scheduler_task_name", "NobusSpaceBot")
    if (voice is None or backup is None or health_launcher is None
            or type(backup_owner) is not str
            or _EVENT_DIGEST.fullmatch(backup_owner) is None):
        raise ValueError("activation inputs are incomplete")
    for directory in (voice, backup):
        if not Path(directory).is_absolute() or not Path(directory).is_dir():
            raise ValueError("activation directory is invalid")
        _plain_root(Path(directory), create=False)
    if (not Path(health_launcher).is_absolute()
            or file_evidence(Path(health_launcher)) is None):
        raise ValueError("health launcher is invalid")

    voice = Path(voice).resolve(strict=True)
    backup = Path(backup).resolve(strict=True)
    health_launcher = Path(health_launcher).resolve(strict=True)
    application = application_binding()
    inputs = {}
    for relative in (
        "docs/11-Контекст-продукта.md",
        "telegram-bindings.local.json",
        "codex-runtime.local.json",
        "src/transport/miniapp_static/app.js",
        "src/transport/miniapp_static/index.html",
        "src/transport/miniapp_static/styles.css",
        "ops/windows/Invoke-NobusSpaceTask.ps1",
        "requirements.txt",
    ):
        evidence = file_evidence(WORKTREE / relative)
        if evidence is None:
            raise ValueError("activation input is unavailable")
        inputs[relative] = evidence

    python = Path(sys.executable).with_name("python.exe").resolve(strict=True)
    pythonw = Path(sys.executable).with_name("pythonw.exe").resolve(strict=True)
    base_python = Path(sys._base_executable).resolve(strict=True)
    runtime_identity = {
        "python_version": list(sys.version_info[:5]),
        "python": file_evidence(python),
        "pythonw": file_evidence(pythonw),
        "base_python": file_evidence(base_python),
        "distributions": _installed_distribution_identity(),
    }
    if any(value is None for key, value in runtime_identity.items() if key != "python_version"):
        raise ValueError("installed runtime identity is invalid")

    scheduler = _scheduler_activation(
        values, runtime, application=application,
        pythonw=pythonw, health_launcher=health_launcher,
        allow_disabled_staging=allow_disabled_staging,
    )

    return {
        "schema": "nobus-supervisor-activation-3",
        "application": application,
        "runtime_binding": runtime_target_binding(runtime),
        "semantic_admission": bool(getattr(values, "semantic_admission", False)),
        "runtime_inputs": inputs,
        "voice": {
            "root_binding": runtime_target_binding(voice),
            "inventory": _bounded_directory_evidence(voice),
        },
        "backup": {
            "root_binding": runtime_target_binding(backup),
            "ownership": backup_owner,
        },
        "health_launcher": file_evidence(health_launcher),
        "installed_runtime": runtime_identity,
        "scheduler_signatures": scheduler["tasks"],
        "backup_config": scheduler["backup_config"],
    }


def _runtime_recovery_context(values):
    runtime = getattr(values, "runtime_root", None)
    try:
        if runtime is None or not runtime.is_absolute() or not runtime.is_dir():
            raise OSError
        _plain_root(runtime, create=False)
    except (OSError, ValueError):
        raise _CliFailure(
            "runtime_composition_invalid", EXIT_RUNTIME_COMPOSITION_INVALID
        ) from None
    try:
        from src.contracts.models import canonical_json_digest

        if getattr(values, "verify_production_identity", False):
            require_production_identity()

        staging_control = any((
            bool(getattr(values, "initialize_recovery", False)),
            getattr(values, "rebind_recovery_from", None) is not None,
            bool(getattr(values, "inspect_recovery", False)),
            getattr(values, "acknowledge_recovery_stop", None) is not None,
        ))
        activation_binding = canonical_json_digest(_activation_manifest(
            values, runtime, allow_disabled_staging=staging_control
        ))
    except Exception:
        raise _CliFailure(
            "activation_binding_invalid", EXIT_ACTIVATION_BINDING_INVALID
        ) from None
    return runtime / RECOVERY_DIRECTORY_NAME, activation_binding


def require_production_identity():
    # Verification uses the same identity as production, never changes its digest.
    if any(Path(item).name.lower() != "pythonw.exe" for item in (sys.executable, sys._base_executable)):
        raise ValueError("production windowed Python identity required")


def _run_owned_recovery(values, *, mutex_name=r"Global\NobusSpaceBotSupervisor",
                        root=None, activation_binding=None, run_attempt=None) -> int:
    from src.application.windows_singleton import WindowsNamedMutex
    if root is None or activation_binding is None:
        root, activation_binding = _runtime_recovery_context(values)
    with WindowsNamedMutex(mutex_name):
        if run_attempt is None:
            from scripts.reboot_recovery import reconcile
            reconcile(sys.modules[__name__], values, root=root, binding=activation_binding)
        return _recover(
            values, root=root, activation_binding=activation_binding,
            run_attempt=run_attempt,
        )


class _CliFailure(RuntimeError):
    def __init__(self, error_class: str, exit_code: int):
        self.error_class = error_class
        self.exit_code = exit_code
        super().__init__(error_class)


def _cli_command(values=None) -> str:
    commands = (
        ("inspect_recovery", "inspect_recovery"),
        ("initialize_recovery", "initialize_recovery"),
        ("rebind_recovery_from", "rebind_recovery"),
        ("acknowledge_recovery_stop", "acknowledge_recovery_stop"),
        ("check_ready", "check_ready"),
        ("stop", "stop"),
    )
    if values is not None:
        for attribute, name in commands:
            item = getattr(values, attribute, False)
            if item is True or (item is not None and item is not False):
                return name
        return "run"
    arguments = set(sys.argv[1:])
    for attribute, name in commands:
        if "--" + attribute.replace("_", "-") in arguments:
            return name
    return "arguments"


_FALLBACK_FAILURE_MATRIX = {
    "arguments": {"runtime_arguments_invalid": EXIT_RUNTIME_COMPOSITION_INVALID},
    "check_ready": {"supervisor_startup_failed": EXIT_SUPERVISOR_STARTUP_FAILED},
    "inspect_recovery": {
        "runtime_composition_invalid": EXIT_RUNTIME_COMPOSITION_INVALID,
        "activation_binding_invalid": EXIT_ACTIVATION_BINDING_INVALID,
        "supervisor_startup_failed": EXIT_SUPERVISOR_STARTUP_FAILED,
    },
    "initialize_recovery": {
        "runtime_composition_invalid": EXIT_RUNTIME_COMPOSITION_INVALID,
        "activation_binding_invalid": EXIT_ACTIVATION_BINDING_INVALID,
        "recovery_control_busy": EXIT_RECOVERY_CONTROL_BUSY,
        "recovery_history_blocked": EXIT_RECOVERY_HISTORY_BLOCKED,
        "supervisor_startup_failed": EXIT_SUPERVISOR_STARTUP_FAILED,
    },
    "rebind_recovery": {
        "runtime_composition_invalid": EXIT_RUNTIME_COMPOSITION_INVALID,
        "activation_binding_invalid": EXIT_ACTIVATION_BINDING_INVALID,
        "recovery_control_busy": EXIT_RECOVERY_CONTROL_BUSY,
        "recovery_rebind_rejected": EXIT_RECOVERY_REBIND_REJECTED,
        "supervisor_startup_failed": EXIT_SUPERVISOR_STARTUP_FAILED,
    },
    "acknowledge_recovery_stop": {
        "runtime_composition_invalid": EXIT_RUNTIME_COMPOSITION_INVALID,
        "activation_binding_invalid": EXIT_ACTIVATION_BINDING_INVALID,
        "recovery_control_busy": EXIT_RECOVERY_CONTROL_BUSY,
        "recovery_reset_rejected": EXIT_RECOVERY_RESET_REJECTED,
        "supervisor_startup_failed": EXIT_SUPERVISOR_STARTUP_FAILED,
    },
    "stop": {
        "stop_control_create_failed": EXIT_STOP_CONTROL_CREATE_FAILED,
        "stop_control_signal_failed": EXIT_STOP_CONTROL_SIGNAL_FAILED,
        "stop_control_close_failed": EXIT_STOP_CONTROL_CLOSE_FAILED,
        "supervisor_startup_failed": EXIT_SUPERVISOR_STARTUP_FAILED,
    },
    "run": {
        "runtime_composition_invalid": EXIT_RUNTIME_COMPOSITION_INVALID,
        "activation_binding_invalid": EXIT_ACTIVATION_BINDING_INVALID,
        "recovery_control_busy": EXIT_RECOVERY_CONTROL_BUSY,
        "recovery_history_blocked": EXIT_RECOVERY_HISTORY_BLOCKED,
        "runtime_event_write_failed": EXIT_RUNTIME_EVIDENCE_FAILED,
        "recovery_wait_event_write_failed": EXIT_RUNTIME_EVIDENCE_FAILED,
        "stop_control_create_failed": EXIT_STOP_CONTROL_CREATE_FAILED,
        "stop_control_signal_failed": EXIT_STOP_CONTROL_SIGNAL_FAILED,
        "stop_control_close_failed": EXIT_STOP_CONTROL_CLOSE_FAILED,
        "stop_control_callback_failed": EXIT_RUNTIME_EVIDENCE_FAILED,
        "supervisor_startup_failed": EXIT_SUPERVISOR_STARTUP_FAILED,
    },
}


def _validate_fallback_failure(command: str, error_class: str, exit_code: int) -> None:
    if _FALLBACK_FAILURE_MATRIX.get(command, {}).get(error_class) != exit_code:
        raise ValueError("fallback failure combination is invalid")


def _decode_fallback_event(line: bytes) -> dict[str, object]:
    if not line.endswith(b"\n") or len(line) > FALLBACK_EVENT_LINE_BYTES:
        raise ValueError
    try:
        value = json.loads(
            line[:-1].decode("ascii"), object_pairs_hook=_unique_json_object
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        raise ValueError from None
    keys = {
        "schema", "status", "command", "error_class", "exit_code",
        "run_id", "at", "authentication",
    }
    if type(value) is not dict or set(value) != keys:
        raise ValueError
    authentication = value.pop("authentication")
    if (value["schema"] != "nobus-supervisor-cli-failure-1"
            or value["status"] != "STOP"
            or type(value["exit_code"]) is not int
            or re.fullmatch(r"[0-9a-f]{32}", value["run_id"]) is None
            or re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
                value["at"],
            ) is None):
        raise ValueError
    _validate_fallback_failure(
        value["command"], value["error_class"], value["exit_code"]
    )
    _verify_authentication(
        value, authentication, entropy=_FALLBACK_AUTHENTICATION_ENTROPY
    )
    return value


def _write_fallback_failure(command: str, error_class: str, exit_code: int) -> None:
    _validate_fallback_failure(command, error_class, exit_code)
    payload = {
        "schema": "nobus-supervisor-cli-failure-1",
        "status": "STOP",
        "command": command,
        "error_class": error_class,
        "exit_code": exit_code,
        "run_id": uuid4().hex,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    authentication = _authentication(
        payload, entropy=_FALLBACK_AUTHENTICATION_ENTROPY
    )
    line = _canonical_ascii({**payload, "authentication": authentication}) + b"\n"
    if len(line) > FALLBACK_EVENT_LINE_BYTES:
        raise OSError
    identity = _plain_root(LOG_ROOT, create=True)
    path = LOG_ROOT / FALLBACK_EVENT_LOG_NAME
    previous = LOG_ROOT / (FALLBACK_EVENT_LOG_NAME + ".previous")
    for candidate in (previous, path):
        if not candidate.exists():
            continue
        if (_path_is_reparse(candidate) or not candidate.is_file()
                or not _single_link_file(candidate)
                or not 0 < candidate.stat().st_size <= FALLBACK_EVENT_LOG_BYTES):
            raise OSError
        content = candidate.read_bytes()
        if not content.endswith(b"\n"):
            raise OSError
        for existing in content.splitlines(keepends=True):
            _decode_fallback_event(existing)
    if path.exists() and path.stat().st_size + len(line) > FALLBACK_EVENT_LOG_BYTES:
        if previous.exists():
            previous.unlink()
        os.replace(path, previous)
    if identity != _plain_root(LOG_ROOT, create=False):
        raise OSError
    with path.open("ab") as stream:
        opened = os.fstat(stream.fileno())
        if opened.st_nlink != 1:
            raise OSError
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())
        current = path.stat(follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise OSError
    if (_path_is_reparse(path) or not _single_link_file(path)
            or path.stat().st_size > FALLBACK_EVENT_LOG_BYTES
            or identity != _plain_root(LOG_ROOT, create=False)):
        raise OSError


def _emit_cli_failure(command: str, error_class: str, exit_code: int) -> int:
    try:
        _write_fallback_failure(command, error_class, exit_code)
    except Exception:
        error_class = "fallback_event_write_failed"
        exit_code = EXIT_RUNTIME_EVIDENCE_FAILED
    print(json.dumps({
        "schema": "nobus-supervisor-cli-failure-1",
        "status": "STOP",
        "command": command,
        "error_class": error_class,
        "exit_code": exit_code,
    }, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
    return exit_code


def _control_failure_for_status(root: Path, activation_binding: str,
                                status: int) -> str:
    fallback = {
        EXIT_STOP_CONTROL_CREATE_FAILED: "stop_control_create_failed",
        EXIT_STOP_CONTROL_SIGNAL_FAILED: "stop_control_signal_failed",
        EXIT_STOP_CONTROL_CLOSE_FAILED: "stop_control_close_failed",
        EXIT_RUNTIME_EVIDENCE_FAILED: "runtime_event_write_failed",
    }[status]
    try:
        event, _digest_value = _last_runtime_event(
            root=root, activation_binding=activation_binding
        )
        event = _effective_event(event) if event is not None else None
        if (event is not None and event["event"] == "control_failure"
                and event["supervisor_exit_code"] == status
                and _FALLBACK_FAILURE_MATRIX["run"].get(event["error_class"]) == status):
            return event["error_class"]
    except (RuntimeError, ValueError):
        pass
    return fallback


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--gated-child":
        return _gated_child(sys.argv[2:])
    if str(WORKTREE) not in sys.path:
        sys.path.insert(0, str(WORKTREE))
    from src.application.windows_singleton import WindowsNamedMutex, RunnerAlreadyActive
    values = None
    try:
        values = _arguments()
        if values.check_ready:
            local = ready()
            public = public_ready()
            healthy = local and public
            result = {
                "status": "PASS" if healthy else "FAIL",
                "local_ready": local, "public_ready": public,
            }
            if values.diagnostic_details:
                result["checks"] = readiness_details()
            print(json.dumps(result, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
            return 0 if healthy else 1
        if values.inspect_recovery:
            root, activation_binding = _runtime_recovery_context(values)
            print(json.dumps(
                _inspect_recovery(root=root, activation_binding=activation_binding),
                ensure_ascii=True,
                separators=(",", ":"), sort_keys=True,
            ))
            return 0
        if values.stop:
            event = None
            failure = None
            try:
                event = StopEvent(request=True)
            except Exception:
                raise _CliFailure(
                    "stop_control_create_failed", EXIT_STOP_CONTROL_CREATE_FAILED
                ) from None
            try:
                event.set()
            except Exception:
                failure = _CliFailure(
                    "stop_control_signal_failed", EXIT_STOP_CONTROL_SIGNAL_FAILED
                )
            try:
                event.close()
            except Exception:
                if failure is None:
                    failure = _CliFailure(
                        "stop_control_close_failed", EXIT_STOP_CONTROL_CLOSE_FAILED
                    )
            if failure is not None:
                raise failure
            print('{"status":"stop_requested"}')
            return 0
        if values.initialize_recovery:
            root, activation_binding = _runtime_recovery_context(values)
            try:
                with WindowsNamedMutex(r"Global\NobusSpaceBotSupervisor"):
                    try:
                        result = _initialize_recovery(
                            root=root, activation_binding=activation_binding
                        )
                    except (RuntimeError, ValueError):
                        raise _CliFailure(
                            "recovery_history_blocked",
                            EXIT_RECOVERY_HISTORY_BLOCKED,
                        ) from None
            except RunnerAlreadyActive:
                raise _CliFailure(
                    "recovery_control_busy", EXIT_RECOVERY_CONTROL_BUSY
                ) from None
            print(json.dumps(
                result, ensure_ascii=True, separators=(",", ":"), sort_keys=True
            ))
            return 0
        if values.rebind_recovery_from is not None:
            root, activation_binding = _runtime_recovery_context(values)
            try:
                with WindowsNamedMutex(r"Global\NobusSpaceBotSupervisor"):
                    try:
                        result = _rebind_recovery(
                            values.rebind_recovery_from, root=root,
                            activation_binding=activation_binding,
                        )
                    except (RuntimeError, ValueError):
                        raise _CliFailure(
                            "recovery_rebind_rejected",
                            EXIT_RECOVERY_REBIND_REJECTED,
                        ) from None
            except RunnerAlreadyActive:
                raise _CliFailure(
                    "recovery_control_busy", EXIT_RECOVERY_CONTROL_BUSY
                ) from None
            print(json.dumps(
                result, ensure_ascii=True, separators=(",", ":"), sort_keys=True
            ))
            return 0
        if values.acknowledge_recovery_stop is not None:
            root, activation_binding = _runtime_recovery_context(values)
            try:
                with WindowsNamedMutex(r"Global\NobusSpaceBotSupervisor"):
                    try:
                        result = _acknowledge_recovery_stop(
                            values.acknowledge_recovery_stop, root=root,
                            activation_binding=activation_binding,
                        )
                    except (RuntimeError, ValueError):
                        raise _CliFailure(
                            "recovery_reset_rejected", EXIT_RECOVERY_RESET_REJECTED
                        ) from None
            except RunnerAlreadyActive:
                raise _CliFailure(
                    "recovery_control_busy", EXIT_RECOVERY_CONTROL_BUSY
                ) from None
            print(json.dumps(
                result, ensure_ascii=True, separators=(",", ":"), sort_keys=True
            ))
            return 0
        root, activation_binding = _runtime_recovery_context(values)
        status = _run_owned_recovery(
            values, root=root, activation_binding=activation_binding
        )
        if status in {
            EXIT_STOP_CONTROL_CREATE_FAILED, EXIT_STOP_CONTROL_SIGNAL_FAILED,
            EXIT_STOP_CONTROL_CLOSE_FAILED, EXIT_RUNTIME_EVIDENCE_FAILED,
        }:
            return _emit_cli_failure(
                "run", _control_failure_for_status(root, activation_binding, status),
                status,
            )
        return status
    except _CliFailure as error:
        return _emit_cli_failure(
            ("arguments" if error.error_class == "runtime_arguments_invalid"
             else _cli_command(values)),
            error.error_class,
            error.exit_code,
        )
    except RunnerAlreadyActive:
        return _emit_cli_failure(
            _cli_command(values), "recovery_control_busy",
            EXIT_RECOVERY_CONTROL_BUSY,
        )
    except Exception:
        return _emit_cli_failure(
            _cli_command(values), "supervisor_startup_failed",
            EXIT_SUPERVISOR_STARTUP_FAILED,
        )


class _RecoveryControlFailure(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _with_stop_control(callback, *, on_ready=None, on_closing=None,
                       on_closed=None, on_failure=None) -> int:
    stop_event = None
    previous_signals = {}
    status = 1
    failure = None
    callback_completed = False
    signal_failed = [False]
    try:
        try:
            stop_event = StopEvent()
        except Exception:
            failure = "stop_control_create_failed"
            status = EXIT_STOP_CONTROL_CREATE_FAILED
            return status

        def request_stop(*_ignored):
            try:
                stop_event.set()
            except Exception:
                signal_failed[0] = True
                raise

        for named_signal in (signal.SIGINT, signal.SIGTERM):
            previous_signals[named_signal] = signal.signal(
                named_signal, request_stop
            )
        if on_ready is not None:
            on_ready()
        status = callback(stop_event)
        callback_completed = True
        if signal_failed[0]:
            failure = "stop_control_signal_failed"
            status = EXIT_STOP_CONTROL_SIGNAL_FAILED
        elif on_closing is not None:
            on_closing(status)
    except _RecoveryControlFailure as error:
        failure = error.code
        status = EXIT_RUNTIME_EVIDENCE_FAILED
    except Exception:
        failure = (
            "stop_control_signal_failed" if signal_failed[0]
            else "stop_control_callback_failed"
        )
        status = (
            EXIT_STOP_CONTROL_SIGNAL_FAILED if signal_failed[0]
            else EXIT_RUNTIME_EVIDENCE_FAILED
        )
    finally:
        if stop_event is not None:
            try:
                stop_event.close()
            except Exception:
                failure = "stop_control_close_failed"
                status = EXIT_STOP_CONTROL_CLOSE_FAILED
            else:
                if failure is None and callback_completed and on_closed is not None:
                    try:
                        on_closed(status)
                    except _RecoveryControlFailure as error:
                        failure = error.code
                        status = EXIT_RUNTIME_EVIDENCE_FAILED
                    except Exception:
                        failure = "stop_control_callback_failed"
                        status = EXIT_RUNTIME_EVIDENCE_FAILED
        for named_signal, handler in previous_signals.items():
            try:
                signal.signal(named_signal, handler)
            except Exception:
                if failure is None:
                    failure = "stop_control_callback_failed"
                    status = EXIT_RUNTIME_EVIDENCE_FAILED
        if failure is not None and on_failure is not None:
            try:
                on_failure(failure)
            except Exception:
                status = EXIT_RUNTIME_EVIDENCE_FAILED
    return status


def _recover(values, *, root=None, activation_binding=None, run_attempt=None) -> int:
    if root is None or activation_binding is None:
        root, activation_binding = _runtime_recovery_context(values)
    state = _recovery_state(root=root, activation_binding=activation_binding)
    if state["state"] == "blocked":
        raise _CliFailure(
            "recovery_history_blocked", EXIT_RECOVERY_HISTORY_BLOCKED
        )
    series_id = state["series_id"] or uuid4().hex
    control_run_id = uuid4().hex
    context = {
        "attempt": state["next_attempt"], "disposition": "stop_evidence_failed",
        "status": 1, "closing_run_id": None,
    }

    try:
        latch_digest = _write_recovery_latch(
            root=root, activation_binding=activation_binding,
            previous_event_digest=state["last_digest"], series_id=series_id,
            run_id=control_run_id, attempt=context["attempt"],
            retry_budget=RECOVERY_RETRY_BUDGET,
        )
    except Exception:
        try:
            _write_runtime_event(_runtime_record(
                series_id, control_run_id, "control_failure",
                activation_binding=activation_binding,
                attempt=context["attempt"], retry_budget=RECOVERY_RETRY_BUDGET,
                recovery_disposition="stop_evidence_failed",
                stage="recovery_control", error_class="runtime_event_write_failed",
                supervisor_exit_code=EXIT_RUNTIME_EVIDENCE_FAILED,
                cleanup_outcome="proven",
            ), root=root)
        except Exception:
            pass
        raise _CliFailure(
            "runtime_event_write_failed", EXIT_RUNTIME_EVIDENCE_FAILED
        ) from None

    try:
        _write_runtime_event(_runtime_record(
            series_id, control_run_id, "control_starting",
            activation_binding=activation_binding,
            attempt=context["attempt"], retry_budget=RECOVERY_RETRY_BUDGET,
            recovery_disposition="pending", stage="recovery_control",
        ), root=root)
    except Exception:
        raise _CliFailure(
            "runtime_event_write_failed", EXIT_RUNTIME_EVIDENCE_FAILED
        ) from None
    try:
        _clear_recovery_latch(root=root, expected_digest=latch_digest)
    except Exception:
        raise _CliFailure(
            "runtime_event_write_failed", EXIT_RUNTIME_EVIDENCE_FAILED
        ) from None

    def control_event(event, *, error_class=None, exit_code=None):
        run_id = context["closing_run_id"] or control_run_id
        disposition = (
            "stop_evidence_failed" if event == "control_failure"
            else (context["disposition"] if event in {"control_closing", "control_closed"}
                  else "pending")
        )
        try:
            return _write_runtime_event(_runtime_record(
                series_id, run_id, event, activation_binding=activation_binding,
                attempt=context["attempt"], retry_budget=RECOVERY_RETRY_BUDGET,
                recovery_disposition=disposition, stage="recovery_control",
                error_class=error_class, supervisor_exit_code=exit_code,
                cleanup_outcome=("proven" if event in {
                    "control_closing", "control_closed", "control_failure"
                } else "not_started"),
            ), root=root)
        except Exception:
            raise _RecoveryControlFailure("runtime_event_write_failed") from None

    def write_wait_event(event, number, *, stopped=False):
        try:
            _write_runtime_event(_runtime_record(
                series_id, uuid4().hex, event,
                activation_binding=activation_binding,
                attempt=number, retry_budget=RECOVERY_RETRY_BUDGET,
                recovery_disposition="stop_planned" if stopped else "retry",
                stage="recovery_wait", error_class="planned_stop" if stopped else None,
                supervisor_exit_code=0 if stopped else None,
                cleanup_outcome="proven",
            ), root=root)
            if stopped:
                context.update(
                    attempt=number, disposition="stop_planned", status=0
                )
        except Exception:
            raise _RecoveryControlFailure(
                "recovery_wait_event_write_failed"
            ) from None

    def controlled(stop_event):
        def attempt(number):
            context["attempt"] = number
            implementation = run_attempt or _run_attempt
            outcome = implementation(
                values,
                stop_event=stop_event,
                series_id=series_id,
                attempt=number,
                retry_budget=RECOVERY_RETRY_BUDGET,
                root=root,
                activation_binding=activation_binding,
            )
            context.update(
                disposition=outcome["recovery_disposition"],
                status=outcome["status"],
            )
            return outcome

        status = _run_bounded_recovery(
            attempt,
            stop_event=stop_event,
            first_attempt=state["next_attempt"],
            retry_budget=RECOVERY_RETRY_BUDGET,
            retry_interval=RECOVERY_RETRY_INTERVAL_SECONDS,
            on_wait_start=lambda number: write_wait_event("retry_waiting", number),
            on_wait_complete=lambda number: write_wait_event("retry_elapsed", number),
            on_wait_stop=lambda number: write_wait_event(
                "recovery_wait_stopped", number, stopped=True
            ),
        )
        context["status"] = status
        return status

    def closing(status):
        context["closing_run_id"] = uuid4().hex
        control_event("control_closing", exit_code=0 if status == 0 else 1)

    def closed(status):
        control_event("control_closed", exit_code=0 if status == 0 else 1)

    def failed(code):
        exit_code = {
            "stop_control_create_failed": EXIT_STOP_CONTROL_CREATE_FAILED,
            "stop_control_signal_failed": EXIT_STOP_CONTROL_SIGNAL_FAILED,
            "stop_control_close_failed": EXIT_STOP_CONTROL_CLOSE_FAILED,
            "runtime_event_write_failed": EXIT_RUNTIME_EVIDENCE_FAILED,
            "recovery_wait_event_write_failed": EXIT_RUNTIME_EVIDENCE_FAILED,
            "stop_control_callback_failed": EXIT_RUNTIME_EVIDENCE_FAILED,
        }.get(code, EXIT_RUNTIME_EVIDENCE_FAILED)
        try:
            control_event("control_failure", error_class=code, exit_code=exit_code)
        except Exception:
            pass

    return _with_stop_control(
        controlled,
        on_ready=lambda: control_event("control_ready", exit_code=0),
        on_closing=closing, on_closed=closed, on_failure=failed,
    )


def _main(values) -> int:
    """Run one attempt for deterministic drills; production uses _recover."""
    return _with_stop_control(
        lambda stop_event: _run_attempt(
            values,
            stop_event=stop_event,
            series_id=uuid4().hex,
            attempt=1,
            retry_budget=RECOVERY_RETRY_BUDGET,
            root=LOG_ROOT,
            activation_binding="sha256:" + "0" * 64,
        )["status"]
    )


def _run_attempt(values, *, stop_event, series_id, attempt, retry_budget,
                 root, activation_binding, relay_command=None,
                 core_command_override=None, probe=None, required_paths=None,
                 relay_settle_seconds=2, children_started=None):
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
    relay_capture = None
    status = 1
    try:
        _write_runtime_event(_runtime_record(
            series_id, run_id, "starting", attempt=attempt,
            activation_binding=activation_binding,
            retry_budget=retry_budget, recovery_disposition="pending",
            stage="setup",
            boot_id=boot_identity() if required_paths is None else None,
        ), root=root)
    except Exception:
        raise _RecoveryControlFailure("runtime_event_write_failed") from None
    try:
        required_inputs = required_paths or (
            WORKTREE, CANONICAL_REPOSITORY, python, RUNNER, SSH,
            private_key, known_hosts,
        )
        for required in required_inputs:
            if not required.exists():
                raise RuntimeError("runtime input unavailable")
        command = core_command_override or core_command(python, values)
        relay_values = relay_command or [
            str(SSH), "-NT", "-F", "NUL", "-i", str(private_key),
            "-o", "BatchMode=yes", "-o", "UserKnownHostsFile=" + str(known_hosts),
            "-o", "StrictHostKeyChecking=yes", "-o", "IdentitiesOnly=yes",
            "-o", "KexAlgorithms=curve25519-sha256", "-o", "ExitOnForwardFailure=yes",
            "-o", "ServerAliveInterval=20", "-o", "ServerAliveCountMax=3",
            "-o", "ConnectTimeout=15", "-R", REVERSE_BINDING, RELAY_TARGET,
        ]
        terminal.update(stage="setup", error_class="supervisor_setup_failed")
        api = _job_api()
        terminal.update(error_class="operator_event_write_failed")
        _operator_event("starting", root=root)
        terminal.update(stage="job_setup", error_class="job_setup_failed")
        job = api.create_job()
        terminal.update(stage="relay_start", error_class="relay_launch_failed")
        relay = spawn_owned(api, job, relay_values, stderr=subprocess.PIPE)
        if getattr(relay, "stderr", None) is not None:
            relay_capture = RelayCapture(relay.stderr)
        stopped_before_core = stop_event.wait(relay_settle_seconds)
        relay_before_core = relay.poll()
        if relay_before_core is not None:
            terminal.update(stage="relay_start", error_class="relay_exit",
                            relay_exit_code=relay_before_core)
        elif stopped_before_core or stop_event.is_set():
            terminal.update(stage="setup", error_class="planned_stop")
            status = 0
        else:
            terminal.update(stage="core_start", error_class="core_launch_failed")
            core = spawn_owned(api, job, command, stdout=subprocess.PIPE)
            if getattr(core, "stdout", None) is not None:
                core_capture = _CoreOutcomeCapture(core.stdout)
            if children_started is not None:
                children_started(relay, core)
            terminal.update(stage="startup", error_class="supervision_failed")
            status = supervise(api, job, relay, core, stop_event,
                               probe=probe,
                               diagnostic=(lambda stage: _write_probe_diagnostic(root, run_id, attempt, stage)) if probe is None else None,
                               report=lambda value: terminal.update(value))
    except Exception:
        status = 1
    finally:
        # Snapshot both children immediately before the first supervisor-owned
        # stop.  A child that exited after supervise() made its decision must
        # remain the causal outcome, not be relabelled as readiness/planned stop.
        relay_before_cleanup = relay.poll() if relay is not None else None
        core_before_cleanup = core.poll() if core is not None else None
        pre_signal_core_exits = []
        cleanup_ok = True
        try:
            cleanup_ok = stop_process(
                core, graceful=True, on_preexisting_exit=pre_signal_core_exits.append
            )
        except Exception:
            cleanup_ok = False
        if pre_signal_core_exits:
            core_before_cleanup = pre_signal_core_exits[-1]
        relay_before_terminate = relay.poll() if relay is not None else None
        if relay_before_cleanup is None:
            relay_before_cleanup = relay_before_terminate
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
        core_code = core.poll() if core is not None else None
        if not _core_outcome_matches_exit(core_code, core_outcome):
            core_outcome = None
            core_outcome_error = "core_outcome_invalid"
        planned_core_failed = core is not None and (
            core_code not in {None, 0}
            or core_outcome != {"status": "STOPPED"}
            or core_outcome_error is not None
        )
        prior_child_error = terminal["error_class"] in {
            "core_exit", "relay_exit", "core_and_relay_exit",
        }
        causal_core_exit = (
            core_before_cleanup is not None
            or (prior_child_error and terminal.get("core_exit_code") is not None)
            or (terminal["error_class"] == "planned_stop" and planned_core_failed)
        )
        causal_relay_exit = (
            relay_before_cleanup is not None
            or (prior_child_error and terminal.get("relay_exit_code") is not None)
        )
        # A failed cleanup is already the fail-closed disposition.  Preserve
        # the primary observation in that case; late child sampling is used to
        # prevent a successful cleanup from authorising the wrong retry.
        if cleanup_ok and (causal_core_exit or causal_relay_exit):
            corrected_error = (
                "core_and_relay_exit" if causal_core_exit and causal_relay_exit
                else ("core_exit" if causal_core_exit else "relay_exit")
            )
            terminal.update(
                stage=("relay_start" if corrected_error == "relay_exit" and core is None
                       else terminal["stage"]),
                error_class=corrected_error,
                core_exit_code=core_code if causal_core_exit else None,
                relay_exit_code=(
                    relay_before_cleanup if causal_relay_exit else None
                ),
                local_ready=None, public_ready=None, readiness_failures=0,
            )
            status = 1
        if not cleanup_ok:
            status = 1
        relay_cause = relay_capture.finish() if relay_capture is not None else "unknown"
        if terminal["error_class"] in {"relay_exit", "core_and_relay_exit"}:
            terminal["relay_cause"] = relay_cause
        try:
            _operator_event(
                "cleanup_failed" if not cleanup_ok else
                ("stopped" if status == 0 else "runtime_failed"),
                root=root,
            )
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
                activation_binding=activation_binding,
                retry_budget=retry_budget, recovery_disposition=disposition,
                stage=terminal["stage"],
                error_class=terminal["error_class"], supervisor_exit_code=status,
                core_exit_code=terminal["core_exit_code"],
                relay_exit_code=terminal["relay_exit_code"],
                local_ready=terminal["local_ready"],
                public_ready=terminal["public_ready"],
                readiness_failures=terminal["readiness_failures"],
                core_outcome=core_outcome, core_outcome_error=core_outcome_error,
                relay_cause=terminal.get("relay_cause"),
                cleanup_outcome="proven" if cleanup_ok else "failed",
            ), root=root)
        except Exception:
            raise _RecoveryControlFailure("runtime_event_write_failed") from None
    return {"status": status, "recovery_disposition": disposition}


if __name__ == "__main__":
    raise SystemExit(main())
