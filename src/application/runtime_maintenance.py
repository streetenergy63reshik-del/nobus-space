"""Crash-recoverable maintenance primitives for the local Telegram runtime."""

from __future__ import annotations

import ctypes
import base64
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
from contextlib import closing, contextmanager, ExitStack
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID


JOURNAL_NAME = "restore-journal.json"
RUNTIME_DATABASE_NAMES = frozenset(
    {
        "telegram-checkpoint.sqlite3",
        "task-runtime.sqlite3",
        "telegram-state.sqlite3",
        "business-notes.sqlite3",
    }
)
REQUIRED_RUNTIME_DATABASE_NAMES = RUNTIME_DATABASE_NAMES - {"business-notes.sqlite3"}
# Local MVP bound: DPAPI JSON adds base64 and uses the existing 80 MiB codec.
MAX_BACKUP_DATABASE_BYTES = 48 * 1024 * 1024
BACKUP_SCHEMA_VERSION = 3
EXPECTED_SCHEMA_DIGESTS: dict[str, dict[str, str]] = {
    "business-notes.sqlite3": {
        "index:idx_business_notes_topic":
            "05fcb014bb5a54c2220f990ce2c1b211c2dc6d3e7f5e0b490defb656b74307fc",
        "table:business_notes":
            "6bf62f047ad4465c6420ee5538b46eeab3e3854ff523741d9991684f93542b21",
    },
    "telegram-checkpoint.sqlite3": {
        "table:telegram_polling_checkpoints":
            "49efdc53c50e91d899b3ee17f48e3f33f1deeb149c9e55ab6060e5184f3e1393",
    },
    "task-runtime.sqlite3": {
        "table:runtime_reconciliations": "a5388c00aa769418ff70ba4baac4b139559c641c5870480c40627e0109676283",
        "index:idx_miniapp_auth_replays_expiry":
            "9468112a0c4b4afbb54dfc0ab5c8984d41a8070cce1a209c61229e518d8ab280",
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
        "table:miniapp_restore_fence": "8038aed0628b69b62db2dbfb831790f9e29088f1704814c0426b51fb199b47b4",
        "table:miniapp_auth_replays":
            "457452b833664f228838673ed77b76f2819b42e332fbac61695e30a759ba1c72",
        "table:miniapp_session_recovery":
            "340b4e0ca0c53c69c9b60bbabafa575ca9f52ea1b0ca1ae19b2c23a3f0f2fc89",
        "table:miniapp_requests":
            "35c345972544e90e012e107f9a1395f32a5b851499b7ffa59e192b8f0c798d9e",
        "table:outbox_messages":
            "39174bc3721c2f0b4315be0efb3b224d9935a555c29d6e52cb1488bc5f0fb40d",
        "table:outbox_receipts":
            "6713069ee549076aa984fc8d0d72d834f0ba9c3e2f68f6453be0a8f48938e693",
        "table:outbox_delivery_parts":
            "ccdc5edb86902a6dcd2b1f2d77af8b2db5b54eef78f7c2e52c234ba6783c6b11",
        "table:sealed_answers":
            "23012de2a0736440d826a5e40c85d04997c48c62f82c8de669fb6ed90a982495",
        "table:task_snapshots":
            "b1f338e3deff32d9507eda30384864f4a1baabce6b56d7f59cfdeffe65b5aef4",
    },
    "telegram-state.sqlite3": {
        "index:idx_semantic_clarification_expiry":
            "39cb81c8d32e7ca047b8a0f738441ec28cea8aeaa391ba242d2894e161310719",
        "index:idx_telegram_capability_expiry":
            "ddbbca4c024c9c1b4e84e7e05293586fd880825d7a9a2f81433e6b7fa0e307df",
        "index:idx_telegram_jobs_ready":
            "d11e18b3e3149bf94ce68aee06049de67106b46fadda83df8d97af4817d4f645",
        "table:telegram_capabilities":
            "647d83bf9edb15eb15feb109871151e9412e4b573d6c01a94d7a882248329190",
        "table:semantic_clarifications":
            "d3f9ae1e18148dd71d0645af7059ee1dc30a89b6eb7f8ea745ec0966349234fb",
        "table:telegram_jobs":
            "ce29f038e79e8b2c0e27fbd313a1f60e1a5a4277eba8d2d641cf20d90a0949e7",
        "table:telegram_progress":
            "93178455126f5edaeaa6ed3af42141e688b34d9d481bfa205900d4e9127e434b",
    },
}


def checked_path(path: Path, *, root: Path | None = None) -> Path:
    """Reject traversal, links and Windows reparse points before maintenance I/O."""
    path = Path(path)
    if ".." in path.parts:
        raise ValueError("unsafe maintenance path")
    path = path.absolute()
    if root is not None and not path.is_relative_to(Path(root).absolute()):
        raise ValueError("unsafe maintenance path")
    for component in (*reversed(path.parents), path):
        try:
            metadata = component.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(metadata.st_mode)
                or getattr(metadata, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
                or (stat.S_ISREG(metadata.st_mode) and metadata.st_nlink != 1)):
            raise ValueError("unsafe maintenance path")
    return path


def runtime_database_paths(root: Path) -> tuple[Path, ...]:
    root = checked_path(root)
    names = set(REQUIRED_RUNTIME_DATABASE_NAMES)
    if (root / "business-notes.sqlite3").exists():
        names.add("business-notes.sqlite3")
    return tuple(checked_path(root / name, root=root) for name in sorted(names))


def runtime_target_binding(root: Path) -> str:
    from src.contracts.models import canonical_json_digest
    return canonical_json_digest({"runtime_root": os.path.normcase(str(checked_path(root)))})


def application_binding() -> dict[str, object]:
    """Bind installed source bytes separately from Git HEAD (which may be WIP)."""
    root = Path(__file__).resolve().parents[2]
    digest = hashlib.sha256()
    paths = list((root / "src").rglob("*.py"))
    paths += list((root / "scripts").glob("*.py"))
    paths.append(root / "requirements.txt")
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode() + b"\x00")
        # Python sources and requirements are text; Git may check them out CRLF.
        digest.update(hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).digest())
    revision = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True,
        timeout=10, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ).stdout.decode("ascii").strip()
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise RuntimeError("application revision unavailable")
    from src.contracts.models import canonical_json_digest
    return {"source_commit": revision, "code_digest": "sha256:" + digest.hexdigest(),
            "schema_digest": canonical_json_digest(EXPECTED_SCHEMA_DIGESTS),
            "protection": "current-user-dpapi", "database_limit_bytes": MAX_BACKUP_DATABASE_BYTES}


def _read_connection(path: Path) -> sqlite3.Connection:
    path = checked_path(path)
    if not path.is_file():
        raise RuntimeError("runtime database missing")
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1)
    if not hasattr(connection, "setconfig"):
        connection.close()
        raise RuntimeError("SQLite defensive configuration unavailable")
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_TRUSTED_SCHEMA, False)
    return connection


def file_evidence(path: Path) -> dict[str, object] | None:
    path = checked_path(path)
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError("maintenance file invalid")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def database_state_digest(path: Path, *, exclude_reconciliation: bool = False) -> str:
    """Logical state includes WAL commits and every authority/replay row."""
    digest = hashlib.sha256()
    with closing(_read_connection(path)) as connection:
        tables = sorted(row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
        for name in tables:
            if exclude_reconciliation and name == "runtime_reconciliations":
                continue
            if not re.fullmatch(r"[a-z_]+", name):
                raise RuntimeError("runtime table invalid")
            digest.update(name.encode() + b"\x00")
            columns = len(connection.execute(f'SELECT * FROM "{name}" LIMIT 0').description)
            order = ",".join(str(index + 1) for index in range(columns))
            for row in connection.execute(f'SELECT * FROM "{name}" ORDER BY {order}'):
                safe = [{"blob_digest": hashlib.sha256(item).hexdigest()} if isinstance(item, bytes)
                        else item for item in row]
                digest.update(json.dumps(safe, ensure_ascii=True, separators=(",", ":")).encode() + b"\n")
    return "sha256:" + digest.hexdigest()


@contextmanager
def lock_runtime_databases(paths: tuple[Path, ...]):
    """Reserve every writer before reading any snapshot; bounded SQLITE_BUSY."""
    with ExitStack() as stack:
        for path in sorted(paths):
            checked_path(path)
            connection = stack.enter_context(closing(sqlite3.connect(
                path.as_uri() + "?mode=rw", uri=True, isolation_level=None, timeout=1)))
            connection.execute("BEGIN IMMEDIATE")
        yield


def protect_backup(content: bytes) -> bytes:
    from src.application.durable_telegram_state import DpapiJsonCodec
    if not 0 < len(content) <= MAX_BACKUP_DATABASE_BYTES:
        raise RuntimeError("backup database size limit exceeded")
    return DpapiJsonCodec().encode({"sqlite_backup_v3": base64.b64encode(content).decode("ascii")})


def unprotect_backup(content: bytes) -> bytes:
    from src.application.durable_telegram_state import DpapiJsonCodec
    if not 0 < len(content) <= 72 * 1024 * 1024:
        raise RuntimeError("backup encrypted size limit exceeded")
    value = DpapiJsonCodec().decode(content)
    if set(value) != {"sqlite_backup_v3"} or not isinstance(value["sqlite_backup_v3"], str):
        raise RuntimeError("backup encrypted format invalid")
    result = base64.b64decode(value["sqlite_backup_v3"], validate=True)
    if not 0 < len(result) <= MAX_BACKUP_DATABASE_BYTES:
        raise RuntimeError("backup database size limit exceeded")
    return result


def require_free_space(root: Path, required: int) -> None:
    if shutil.disk_usage(checked_path(root)).free < required + 16 * 1024 * 1024:
        raise RuntimeError("runtime disk space insufficient")


def validate_runtime_set(root: Path) -> None:
    """Check installed schemas and C4 request→Core bindings without emitting payload."""
    paths = runtime_database_paths(root)
    for path in paths:
        validate_runtime_database(path)
    store = _read_only_store(Path(root) / "task-runtime.sqlite3")
    from src.storage.sqlite_store import MiniAppCancelledRequest
    with closing(_read_connection(Path(root) / "task-runtime.sqlite3")) as connection:
        connection.row_factory = sqlite3.Row
        for row in connection.execute("SELECT * FROM miniapp_requests"):
            record = store._miniapp_request_from_row(row)
            claim = connection.execute("SELECT task_id FROM ingress_claims WHERE tenant_id=? AND idempotency_key=?",
                                       (row["tenant_id"], row["idempotency_key"])).fetchone()
            if isinstance(record, MiniAppCancelledRequest):
                if claim is not None:
                    raise RuntimeError("cancelled request has accepted ingress")
            elif claim is not None:
                if record.state == "not_accepted" or store.read_ingress_claim(record.envelope) is None:
                    raise RuntimeError("request ingress binding mismatch")
    store.miniapp_restore_cutoff()
    store.restore_reconciliation_required()


def assert_runtime_admission_ready(root: Path) -> None:
    if _read_only_store(Path(root) / "task-runtime.sqlite3").restore_reconciliation_required():
        raise RuntimeError("restored runtime requires owner reconciliation")


def invalidate_restored_authority(root: Path) -> None:
    """Revoke transient authority and quarantine pending effects; preserve receipts."""
    from src.application.durable_telegram_state import DpapiJsonCodec
    from src.contracts.models import canonical_json_digest
    codec = DpapiJsonCodec()
    with closing(sqlite3.connect(root / "task-runtime.sqlite3")) as connection:
        connection.execute("PRAGMA secure_delete=ON")
        connection.execute("DELETE FROM miniapp_session_recovery")
        connection.execute("INSERT INTO miniapp_restore_fence VALUES (1, ?, 1) ON CONFLICT(singleton) DO UPDATE SET auth_not_before=excluded.auth_not_before, reconciliation_required=1",
                           (datetime.now(UTC).isoformat(),))
        connection.commit()
    with closing(sqlite3.connect(root / "telegram-state.sqlite3")) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA secure_delete=ON")
        for row in connection.execute("SELECT * FROM telegram_capabilities").fetchall():
            payload = codec.decode(bytes(row["payload"]))
            if row["kind"] == "action" and "effect_digest" in payload:
                # A pending side effect may have happened after the snapshot. It
                # becomes UNKNOWN; completed/delivered receipts remain intact.
                if payload.get("state") == "pending":
                    payload = dict(payload, state="unknown")
                    connection.execute("UPDATE telegram_capabilities SET payload=?, payload_digest=? WHERE kind=? AND tenant_id=? AND token_digest=?",
                                       (codec.encode(payload), canonical_json_digest(payload), row["kind"], row["tenant_id"], row["token_digest"]))
            else:
                connection.execute("DELETE FROM telegram_capabilities WHERE kind=? AND tenant_id=? AND token_digest=?",
                                   (row["kind"], row["tenant_id"], row["token_digest"]))
        connection.execute("DELETE FROM semantic_clarifications")
        connection.commit()


def quick_check(path: Path) -> None:
    with closing(_read_connection(path)) as connection:
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("runtime database verification failed")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeError("runtime database foreign key mismatch")


def validate_runtime_database(path: Path, *, content: bool = True) -> None:
    """Validate exact DDL plus every stored application digest."""
    path = Path(path)
    expected = EXPECTED_SCHEMA_DIGESTS.get(path.name)
    if expected is None:
        raise ValueError("unknown runtime database")
    with closing(_read_connection(path)) as connection:
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
    quick_check(path)
    if not content:
        return
    if path.name == "telegram-checkpoint.sqlite3":
        _validate_checkpoint_rows(path)
    elif path.name == "task-runtime.sqlite3":
        _validate_task_runtime_rows(path)
    elif path.name == "telegram-state.sqlite3":
        _validate_telegram_state_rows(path)
    else:
        _validate_business_notes_rows(path)


def expire_runtime_voice(path: Path, *, require_quiescent: bool = False) -> None:
    """Maintenance-only expiry before content validation; never mutate backup originals."""
    if path.name != 'telegram-state.sqlite3':
        return
    validate_runtime_database(path, content=False)
    from src.application.durable_telegram_state import DpapiJsonCodec, purge_voice_rows
    from src.application.durable_telegram_state import require_voice_quiescent
    with closing(sqlite3.connect(path, isolation_level=None)) as connection:
        connection.execute('PRAGMA secure_delete=ON')
        connection.execute('BEGIN IMMEDIATE')
        try:
            purge_voice_rows(connection, now=datetime.now(UTC), encode=DpapiJsonCodec().encode)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        if connection.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0] != 0:
            raise RuntimeError('runtime voice cleanup busy')
        if require_quiescent:
            require_voice_quiescent(connection)


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

    with closing(_read_connection(path)) as connection:
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
    from src.storage.sqlite_store import MiniAppCancelledRequest, _claim_binding_digest, _is_digest

    store = _read_only_store(path)
    store.miniapp_restore_cutoff()
    store.restore_reconciliation_required()
    with closing(_read_connection(path)) as connection:
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
        replays = connection.execute(
            """SELECT tenant_id,replay_digest,auth_expires_at,claimed_at
               FROM miniapp_auth_replays"""
        ).fetchall()
        recoveries = connection.execute("SELECT * FROM miniapp_session_recovery").fetchall()
        requests = connection.execute("SELECT * FROM miniapp_requests").fetchall()
    from src.application.runtime_reconciliation import validate_records
    with closing(_read_connection(path)) as connection:
        validate_records(connection)
    for row in tasks:
        if store.read_task(row["tenant_id"], UUID(row["task_id"])) is None:
            raise RuntimeError("task snapshot is missing")
        store.read_sealed_answer(row["tenant_id"], UUID(row["task_id"]))
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
        store.read_delivery_parts(row["tenant_id"], message_id)
    for row in replays:
        claimed = _aware(row["claimed_at"])
        expires = _aware(row["auth_expires_at"])
        tenant_id = row["tenant_id"]
        if (
            not isinstance(tenant_id, str)
            or tenant_id != tenant_id.strip()
            or not tenant_id
            or len(tenant_id) > 128
            or not _is_digest(row["replay_digest"])
            or claimed.utcoffset() != timedelta(0)
            or expires.utcoffset() != timedelta(0)
            or not 0 < (expires - claimed).total_seconds() <= 1_020
        ):
            raise RuntimeError("miniapp auth replay binding mismatch")
    for row in recoveries:
        if (not isinstance(row["tenant_id"], str) or not row["tenant_id"].strip()
                or len(row["tenant_id"]) > 128
                or row["tenant_id"] != row["tenant_id"].strip()
                or not _is_digest(row["auth_context_ref"])
                or not _is_digest(row["credential_digest"])
                or _aware(row["expires_at"]).utcoffset() != timedelta(0)):
            raise RuntimeError("miniapp recovery binding mismatch")
    for row in requests:
        record = store._miniapp_request_from_row(row)
        if isinstance(record, MiniAppCancelledRequest):
            continue  # The closed tombstone schema and exact row binding were validated above.
        if (re.fullmatch(r"[A-Za-z0-9._~-]{16,128}", row["idempotency_key"]) is None
                or record.envelope.source.value != "api"
                or record.envelope.kind.value != "text"
                or record.envelope.actor_identity != "telegram:owner"
                or record.envelope.external_message_id != "miniapp:task.create:" + row["idempotency_key"]):
            raise RuntimeError("miniapp request binding mismatch")


def _validate_telegram_state_rows(path: Path) -> None:
    from src.application.durable_telegram_state import DpapiJsonCodec
    from src.contracts.models import canonical_json_digest

    codec = DpapiJsonCodec()
    with closing(_read_connection(path)) as connection:
        connection.row_factory = sqlite3.Row
        jobs = connection.execute("SELECT * FROM telegram_jobs").fetchall()
        capabilities = connection.execute(
            "SELECT * FROM telegram_capabilities"
        ).fetchall()
        progress = connection.execute(
            """SELECT tenant_id,task_id,chat_id,message_id,updated_at
               FROM telegram_progress"""
        ).fetchall()
        clarifications = connection.execute(
            "SELECT * FROM semantic_clarifications"
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
        if (row['kind']=='voice' and row['payload_digest'] != canonical_json_digest({})
            and created+timedelta(hours=1) <= datetime.now(UTC)):
            raise RuntimeError('runtime voice retention maintenance required')
        payload = codec.decode(bytes(row["payload"]))
        if (
            not _runtime_text(row["tenant_id"], 128)
            or row["kind"] not in {"draft", "miniapp_draft", "patch", "effect", "voice"}
            or row["status"] not in {"pending", "leased", "failed", "waiting", "finished"}
            or (row["status"] in {"waiting", "finished"} and row["kind"] != "voice")
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
    for row in clarifications:
        created = _aware(row["created_at"])
        expires = _aware(row["expires_at"])
        payload = codec.decode(bytes(row["payload"]))
        if (
            not _runtime_digest(row["conversation_binding"])
            or not _runtime_digest(row["owner_binding"])
            or not _runtime_text(row["tenant_id"], 128)
            or not _runtime_digest(row["tenant_binding"])
            or not _runtime_digest(row["answer_binding"])
            or not _runtime_digest(row["envelope_revision"])
            or type(row["intake_revision"]) is not int
            or row["intake_revision"] < 1
            or not _runtime_digest(row["payload_digest"])
            or canonical_json_digest(payload) != row["payload_digest"]
            or not created < expires <= created + timedelta(minutes=30)
        ):
            raise RuntimeError("semantic clarification row is invalid")



def _validate_business_notes_rows(path: Path) -> None:
    from src.application.business_notes import BusinessNote
    from src.application.durable_telegram_state import DpapiJsonCodec

    codec = DpapiJsonCodec()
    with closing(_read_connection(path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """SELECT tenant_id,chat_id,thread_id,message_id,update_id,
                      payload,payload_digest,created_at
               FROM business_notes"""
        )
        for row in rows:
            payload = codec.decode(bytes(row["payload"]))
            note = BusinessNote.model_validate_json(
                json.dumps(payload, ensure_ascii=False)
            )
            if (
                "sha256:" + hashlib.sha256(bytes(row["payload"])).hexdigest()
                != row["payload_digest"]
                or note.tenant_id != row["tenant_id"]
                or note.chat_id != row["chat_id"]
                or (note.thread_id or 0) != row["thread_id"]
                or note.message_id != row["message_id"]
                or note.update_id != row["update_id"]
                or note.created_at != _aware(row["created_at"])
            ):
                raise RuntimeError("business Notes row is invalid")

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
        if connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] != 0:
            raise RuntimeError("runtime checkpoint busy")
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


def cleanup_staging(root: Path, staging: Path, identity: tuple[int, int], names: set[str]) -> None:
    """Delete only enumerated files in the directory created by this operation."""
    staging = checked_path(staging, root=root)
    metadata = staging.stat()
    if staging.parent != checked_path(root) or (metadata.st_dev, metadata.st_ino) != identity:
        raise RuntimeError("staging ownership mismatch")
    allowed = {name + suffix for name in names for suffix in ("", "-wal", "-shm", ".previous", ".rollback")}
    targets = tuple(staging.iterdir())
    for target in targets:
        checked_path(target, root=staging)
        if target.name not in allowed or not target.is_file():
            raise RuntimeError("staging cleanup scope mismatch")
    for target in targets:
        checked_path(target, root=staging)
        target.unlink()
    checked_path(staging, root=root).rmdir()
    fsync_directory(root)


def restore_journal_values(runtime: Path, staging: Path, names: set[str]) -> dict[str, object]:
    metadata = staging.stat()
    return {
        "schema_version": 2, "runtime_binding": runtime_target_binding(runtime),
        "staging": staging.name, "staging_identity": [metadata.st_dev, metadata.st_ino],
        "files": [{"name": name,
                   "previous": file_evidence(staging / (name + ".previous")),
                   "candidate": file_evidence(staging / name),
                   "sidecars": {suffix: file_evidence(runtime / (name + suffix)) for suffix in ("-wal", "-shm")}}
                  for name in sorted(names)],
    }


def write_journal(runtime: Path, values: dict[str, object]) -> Path:
    from src.contracts.models import canonical_json_digest
    from src.security.dpapi import protect_current_user
    runtime = checked_path(runtime)
    runtime.mkdir(parents=True, exist_ok=True)
    journal = checked_path(runtime / JOURNAL_NAME, root=runtime)
    if journal.exists():
        raise RuntimeError("restore journal already exists")
    protected = protect_current_user(canonical_json_digest(values).encode("ascii"),
                                     entropy=b"nobus-space:restore-journal:v2")
    write_bytes_durable(journal, json.dumps({"payload": values, "authentication": protected.hex()},
                                          ensure_ascii=True, separators=(",", ":")).encode())
    return journal


def recover_interrupted_restore(runtime: Path) -> bool:
    """Authenticated, identity-bound rollback; refuse any unplanned target change."""
    from src.contracts.models import canonical_json_digest
    from src.security.dpapi import unprotect_current_user
    runtime = checked_path(runtime)
    journal = checked_path(runtime / JOURNAL_NAME, root=runtime)
    if not journal.exists():
        return False
    try:
        if not journal.is_file() or journal.stat().st_size > 64 * 1024:
            raise ValueError
        envelope = json.loads(journal.read_text(encoding="utf-8"))
        if not isinstance(envelope, dict) or set(envelope) != {"payload", "authentication"}:
            raise ValueError
        values = envelope["payload"]
        authenticated = unprotect_current_user(bytes.fromhex(envelope["authentication"]),
                                               entropy=b"nobus-space:restore-journal:v2").decode("ascii")
        if authenticated != canonical_json_digest(values):
            raise ValueError
        if (not isinstance(values, dict)
                or set(values) != {"schema_version", "runtime_binding", "staging", "staging_identity", "files"}
                or type(values["schema_version"]) is not int or values["schema_version"] != 2
                or values["runtime_binding"] != runtime_target_binding(runtime)
                or not isinstance(values["staging"], str)
                or re.fullmatch(r"restore-[a-zA-Z0-9_-]+", values["staging"]) is None):
            raise ValueError
        staging = checked_path(runtime / values["staging"], root=runtime)
        metadata = staging.stat()
        identity = (metadata.st_dev, metadata.st_ino)
        if not staging.is_dir() or values["staging_identity"] != list(identity):
            raise ValueError
        files = values["files"]
        if not isinstance(files, list) or not 3 <= len(files) <= 4:
            raise ValueError
        names = {item["name"] for item in files}
        if not REQUIRED_RUNTIME_DATABASE_NAMES <= names <= RUNTIME_DATABASE_NAMES or len(names) != len(files):
            raise ValueError
        for item in files:
            if set(item) != {"name", "previous", "candidate", "sidecars"}:
                raise ValueError
            name = item["name"]
            if file_evidence(staging / (name + ".previous")) != item["previous"]:
                raise ValueError
            current = file_evidence(runtime / name)
            if current != item["candidate"] and current != item["previous"]:
                raise ValueError
            if set(item["sidecars"]) != {"-wal", "-shm"}:
                raise ValueError
            for suffix, expected in item["sidecars"].items():
                actual = file_evidence(runtime / (name + suffix))
                if actual is not None and actual != expected:
                    raise ValueError
        for item in reversed(files):
            name = item["name"]
            target = checked_path(runtime / name, root=runtime)
            if item["previous"] is not None:
                rollback = checked_path(staging / (name + ".rollback"), root=staging)
                copy_durable(staging / (name + ".previous"), rollback)
                replace_durable(rollback, target)
            elif target.exists():
                unlink_durable(target)
            for suffix in ("-wal", "-shm"):
                unlink_durable(checked_path(runtime / (name + suffix), root=runtime))
        for item in files:
            if file_evidence(runtime / item["name"]) != item["previous"]:
                raise RuntimeError("rollback verification failed")
        unlink_durable(journal)
        cleanup_staging(runtime, staging, identity, names)
        return True
    except Exception:
        raise RuntimeError("interrupted restore recovery failed") from None
