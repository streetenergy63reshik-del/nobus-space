"""Crash-recoverable maintenance primitives for the local Telegram runtime."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shutil
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID


JOURNAL_NAME = "restore-journal.json"
RUNTIME_DATABASE_NAMES = frozenset(
    {
        "telegram-checkpoint.sqlite3",
        "task-runtime.sqlite3",
        "telegram-state.sqlite3",
    }
)
EXPECTED_SCHEMA_DIGESTS: dict[str, dict[str, str]] = {
    "telegram-checkpoint.sqlite3": {
        "table:telegram_polling_checkpoints":
            "49efdc53c50e91d899b3ee17f48e3f33f1deeb149c9e55ab6060e5184f3e1393",
    },
    "task-runtime.sqlite3": {
        "index:idx_outbox_expired":
            "3cff5fc64008af56366bbcdda2bbeba1db4e553ec11d2cb2fbcb3de2a90d8469",
        "index:idx_outbox_pending":
            "0224720ab167d2e5e701f0561b80bbf4e81a84da4af7d66f4e31450b098c53c5",
        "index:idx_outbox_receipts":
            "24d1e682c3898994bad1e9f7ee258fa0c25b716a8a1ef9364e9767efccb69ba7",
        "table:audit_events":
            "07571fac9c3caf4d5b709f61817d624d24758c9ffacece6a4c1df606fa7dff2d",
        "table:ingress_claims":
            "b3b537e0a787c8d3baca03a6f1f583892dc90e7a0e30c1b21a8d7ed6ca8d554f",
        "table:outbox_messages":
            "39174bc3721c2f0b4315be0efb3b224d9935a555c29d6e52cb1488bc5f0fb40d",
        "table:outbox_receipts":
            "6713069ee549076aa984fc8d0d72d834f0ba9c3e2f68f6453be0a8f48938e693",
        "table:task_snapshots":
            "e5ec08239422f6d4c587d1840072b377d55aa152207f4ed7232657f3a4c84fc6",
    },
    "telegram-state.sqlite3": {
        "index:idx_telegram_capability_expiry":
            "ddbbca4c024c9c1b4e84e7e05293586fd880825d7a9a2f81433e6b7fa0e307df",
        "index:idx_telegram_jobs_ready":
            "d11e18b3e3149bf94ce68aee06049de67106b46fadda83df8d97af4817d4f645",
        "table:telegram_capabilities":
            "647d83bf9edb15eb15feb109871151e9412e4b573d6c01a94d7a882248329190",
        "table:telegram_jobs":
            "e2c9eb3c33b012a7c822e9d734fb5e0ce0a5d0eaea227ede5365bf446883a8cb",
        "table:telegram_progress":
            "93178455126f5edaeaa6ed3af42141e688b34d9d481bfa205900d4e9127e434b",
    },
}


def quick_check(path: Path) -> None:
    with closing(sqlite3.connect(path)) as connection:
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("runtime database verification failed")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeError("runtime database foreign key mismatch")


def validate_runtime_database(path: Path) -> None:
    """Validate exact DDL plus every stored application digest."""
    path = Path(path)
    expected = EXPECTED_SCHEMA_DIGESTS.get(path.name)
    if expected is None:
        raise ValueError("unknown runtime database")
    quick_check(path)
    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        actual = {
            f"{row['type']}:{row['name']}": _ddl_digest(str(row["sql"] or ""))
            for row in connection.execute(
                """SELECT type,name,sql FROM sqlite_master
                   WHERE name NOT LIKE 'sqlite_%'"""
            )
        }
    if actual != expected:
        raise RuntimeError("runtime database schema mismatch")
    if path.name == "telegram-checkpoint.sqlite3":
        _validate_checkpoint_rows(path)
    elif path.name == "task-runtime.sqlite3":
        _validate_task_runtime_rows(path)
    else:
        _validate_telegram_state_rows(path)


def dead_letter_count(path: Path) -> int:
    if Path(path).name != "telegram-state.sqlite3":
        return 0
    with closing(sqlite3.connect(path)) as connection:
        value = connection.execute(
            "SELECT COUNT(*) FROM telegram_jobs WHERE status='failed'"
        ).fetchone()[0]
    return int(value)


def _ddl_digest(sql: str) -> str:
    normalized = re.sub(r"\s+", " ", sql.strip()).casefold()
    return hashlib.sha256(normalized.encode()).hexdigest()


def _validate_checkpoint_rows(path: Path) -> None:
    from src.transport.telegram.bot_api import PollingLease
    from src.transport.telegram.sqlite_checkpoint import _state_digest

    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """SELECT consumer_id,offset,lease_id,lease_owner,lease_expires_at,
                      revision,updated_at,state_digest
               FROM telegram_polling_checkpoints"""
        )
        for row in rows:
            updated = _aware(row["updated_at"])
            lease_values = (
                row["lease_id"],
                row["lease_owner"],
                row["lease_expires_at"],
            )
            lease = None
            if all(value is not None for value in lease_values):
                lease = PollingLease(
                    lease_id=UUID(lease_values[0]),
                    owner_id=UUID(lease_values[1]),
                    expires_at=_aware(lease_values[2]),
                )
                seconds = (lease.expires_at - updated).total_seconds()
                if not 0 < seconds <= 300:
                    raise RuntimeError("polling checkpoint lease is invalid")
            elif any(value is not None for value in lease_values):
                raise RuntimeError("polling checkpoint lease is invalid")
            if (
                not isinstance(row["consumer_id"], str)
                or not row["consumer_id"]
                or (
                    row["offset"] is not None
                    and (type(row["offset"]) is not int or row["offset"] < 0)
                )
                or type(row["revision"]) is not int
                or row["revision"] < 1
                or row["state_digest"]
                != _state_digest(
                    row["consumer_id"],
                    row["offset"],
                    lease,
                    row["revision"],
                    updated,
                )
            ):
                raise RuntimeError("polling checkpoint digest mismatch")


def _read_only_store(path: Path):
    from src.storage.sqlite_store import SQLiteStore

    store = object.__new__(SQLiteStore)
    store._path = path
    store._verifier_registry = None
    store._busy_timeout_ms = 5_000
    return store


def _validate_task_runtime_rows(path: Path) -> None:
    from src.storage.sqlite_store import _claim_binding_digest, _is_digest

    store = _read_only_store(path)
    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        tasks = connection.execute(
            "SELECT tenant_id,task_id FROM task_snapshots"
        ).fetchall()
        claims = connection.execute(
            """SELECT tenant_id,idempotency_key,ingress_id,ingress_fingerprint,
                      task_id,claim_binding_digest,claimed_at
               FROM ingress_claims"""
        ).fetchall()
        attempts = connection.execute(
            "SELECT DISTINCT tenant_id,task_id,attempt_id FROM audit_events"
        ).fetchall()
        messages = connection.execute(
            "SELECT tenant_id,message_id FROM outbox_messages"
        ).fetchall()
    for row in tasks:
        if store.read_task(row["tenant_id"], UUID(row["task_id"])) is None:
            raise RuntimeError("task snapshot is missing")
    for row in claims:
        task_id = UUID(row["task_id"])
        UUID(row["ingress_id"])
        _aware(row["claimed_at"])
        snapshot = store.read_task(row["tenant_id"], task_id)
        if (
            snapshot is None
            or not _is_digest(row["ingress_fingerprint"])
            or row["claim_binding_digest"]
            != _claim_binding_digest(
                row["ingress_fingerprint"],
                tenant_id=row["tenant_id"],
                idempotency_key=row["idempotency_key"],
                task_id=task_id,
                contract_digest=snapshot.projection.contract_digest,
            )
        ):
            raise RuntimeError("ingress claim binding mismatch")
    for row in attempts:
        store.read_events(
            row["tenant_id"],
            UUID(row["task_id"]),
            UUID(row["attempt_id"]),
        )
    for row in messages:
        message_id = UUID(row["message_id"])
        if store.read_outbox_message(row["tenant_id"], message_id) is None:
            raise RuntimeError("outbox message is missing")
        store.read_outbox_receipts(row["tenant_id"], message_id)


def _validate_telegram_state_rows(path: Path) -> None:
    from src.application.durable_telegram_state import DpapiJsonCodec
    from src.contracts.models import canonical_json_digest

    codec = DpapiJsonCodec()
    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        jobs = connection.execute("SELECT * FROM telegram_jobs").fetchall()
        capabilities = connection.execute(
            "SELECT * FROM telegram_capabilities"
        ).fetchall()
        progress = connection.execute(
            """SELECT tenant_id,task_id,chat_id,message_id,updated_at
               FROM telegram_progress"""
        ).fetchall()
    for row in jobs:
        created = _aware(row["created_at"])
        updated = _aware(row["updated_at"])
        attempts = row["attempt_count"]
        status = row["status"]
        lease_values = (
            row["lease_id"],
            row["lease_owner"],
            row["lease_expires_at"],
        )
        payload = codec.decode(bytes(row["payload"]))
        if (
            not _runtime_text(row["tenant_id"], 128)
            or row["kind"] not in {"draft", "patch", "effect"}
            or row["status"] not in {"pending", "leased", "failed"}
            or not _runtime_digest(row["binding_digest"])
            or not _runtime_digest(row["payload_digest"])
            or canonical_json_digest(payload) != row["payload_digest"]
            or type(attempts) is not int
            or not 0 <= attempts <= 3
            or updated < created
        ):
            raise RuntimeError("runtime job row is invalid")
        UUID(row["job_id"])
        UUID(row["task_id"])
        if status == "leased":
            if not all(value is not None for value in lease_values):
                raise RuntimeError("runtime job lease is invalid")
            UUID(row["lease_id"])
            UUID(row["lease_owner"])
            lease_expires = _aware(row["lease_expires_at"])
            if (
                not 1 <= attempts <= 3
                or lease_expires <= updated
                or lease_expires - updated > timedelta(hours=4)
            ):
                raise RuntimeError("runtime job lease is invalid")
        elif any(value is not None for value in lease_values):
            raise RuntimeError("runtime job lease is invalid")
        if status == "pending" and attempts >= 3:
            raise RuntimeError("runtime job attempts are invalid")
        if status == "failed":
            if (
                not 1 <= attempts <= 3
                or not _runtime_text(row["failure_code"], 64)
            ):
                raise RuntimeError("runtime job failure is invalid")
        elif row["failure_code"] is not None:
            raise RuntimeError("runtime job failure is invalid")
    for row in capabilities:
        created = _aware(row["created_at"])
        expires = _aware(row["expires_at"])
        payload = codec.decode(bytes(row["payload"]))
        if (
            row["kind"] not in {"task", "patch", "action"}
            or not _runtime_text(row["tenant_id"], 128)
            or not _runtime_digest(row["token_digest"])
            or not _runtime_digest(row["payload_digest"])
            or canonical_json_digest(payload) != row["payload_digest"]
            or expires <= created
        ):
            raise RuntimeError("runtime capability row is invalid")
    for row in progress:
        UUID(row["task_id"])
        _aware(row["updated_at"])
        if (
            not _runtime_text(row["tenant_id"], 128)
            or type(row["chat_id"]) is not int
            or row["chat_id"] == 0
            or type(row["message_id"]) is not int
            or row["message_id"] <= 0
        ):
            raise RuntimeError("progress binding is invalid")


def _runtime_text(value: object, limit: int) -> bool:
    return (
        isinstance(value, str)
        and value == value.strip()
        and bool(value)
        and len(value) <= limit
        and "\x00" not in value
    )


def _runtime_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None
    )


def _aware(value: object) -> datetime:
    if not isinstance(value, str):
        raise RuntimeError("runtime timestamp is invalid")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuntimeError("runtime timestamp is invalid")
    return parsed.astimezone(UTC)

def checkpoint(path: Path) -> None:
    if not path.exists():
        return
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connection.commit()
    validate_runtime_database(path)


def fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def replace_durable(source: Path, target: Path) -> None:
    source = Path(source)
    target = Path(target)
    if os.name == "nt":
        flags = 0x1 | 0x8  # MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH
        move = ctypes.windll.kernel32.MoveFileExW
        move.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32)
        move.restype = ctypes.c_int
        if not move(str(source), str(target), flags):
            raise OSError(ctypes.get_last_error(), "durable replace failed")
    else:
        os.replace(source, target)
        fsync_directory(target.parent)


def copy_durable(source: Path, target: Path) -> None:
    with Path(source).open("rb") as current, Path(target).open("wb") as output:
        shutil.copyfileobj(current, output)
        output.flush()
        os.fsync(output.fileno())
    fsync_directory(Path(target).parent)


def write_bytes_durable(path: Path, content: bytes) -> None:
    with Path(path).open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    fsync_directory(Path(path).parent)


def unlink_durable(path: Path) -> None:
    Path(path).unlink(missing_ok=True)
    fsync_directory(Path(path).parent)


def write_journal(runtime: Path, values: dict[str, object]) -> Path:
    runtime.mkdir(parents=True, exist_ok=True)
    journal = runtime / JOURNAL_NAME
    temporary = runtime / f".{JOURNAL_NAME}.tmp"
    unlink_durable(temporary)
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(values, stream, ensure_ascii=True, separators=(",", ":"))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    replace_durable(temporary, journal)
    fsync_directory(runtime)
    return journal


def recover_interrupted_restore(runtime: Path) -> bool:
    """Roll back an interrupted multi-database replacement before startup."""
    runtime = runtime.resolve()
    journal = runtime / JOURNAL_NAME
    if not journal.is_file():
        return False
    try:
        values = json.loads(journal.read_text(encoding="utf-8"))
        if (
            not isinstance(values, dict)
            or set(values) != {"schema_version", "staging", "names"}
            or type(values.get("schema_version")) is not int
            or values["schema_version"] != 1
        ):
            raise ValueError
        staging = Path(values["staging"]).resolve(strict=True)
        if (
            not staging.is_dir()
            or staging.parent != runtime
            or not staging.name.startswith("restore-")
        ):
            raise ValueError
        names = values["names"]
        if (
            not isinstance(names, list)
            or len(names) != len(RUNTIME_DATABASE_NAMES)
            or set(names) != RUNTIME_DATABASE_NAMES
        ):
            raise ValueError
        for name in reversed(names):
            target = runtime / name
            previous = staging / f"{name}.previous"
            if previous.is_file():
                rollback = staging / f"{name}.rollback"
                copy_durable(previous, rollback)
                replace_durable(rollback, target)
            else:
                unlink_durable(target)
            unlink_durable(runtime / f"{name}-wal")
            unlink_durable(runtime / f"{name}-shm")
        unlink_durable(journal)
        shutil.rmtree(staging)
        fsync_directory(runtime)
        return True
    except Exception:
        raise RuntimeError("interrupted restore recovery failed") from None
