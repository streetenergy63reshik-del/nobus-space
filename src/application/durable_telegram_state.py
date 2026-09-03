"""Encrypted SQLite state for Telegram admission, capabilities and progress."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Mapping
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator
from uuid import UUID, uuid4

from src.contracts.models import canonical_json_digest
from src.security.dpapi import protect_current_user, unprotect_current_user


_ENTROPY = b"nobus-space:telegram-runtime:v1"
_JOB_KINDS = frozenset({"draft", "miniapp_draft", "patch", "effect"})
_JOB_STATUSES = frozenset({"pending", "leased", "failed"})
_CAPABILITY_KINDS = frozenset({"task", "patch", "action"})
_DPAPI_MAGIC = b"NBDP1"
_DPAPI_CHUNK_BYTES = 1024 * 1024
_MAX_PROTECTED_JSON_BYTES = 80 * 1024 * 1024
MAX_JOB_CLAIMS = 3


class DurableTelegramStateError(RuntimeError):
    """Stable storage failure without sensitive payload details."""


@dataclass(frozen=True, slots=True)
class DurableJob:
    job_id: UUID
    kind: str
    tenant_id: str
    task_id: UUID
    binding_digest: str
    payload: Mapping[str, Any]
    attempt_count: int
    lease_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ProgressMessageRef:
    tenant_id: str
    task_id: UUID
    chat_id: int
    message_id: int
    updated_at: datetime


class DpapiJsonCodec:
    """Canonical JSON protected by current-user Windows DPAPI."""

    def encode(self, value: Mapping[str, Any]) -> bytes:
        try:
            raw = json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            if not raw or len(raw) > _MAX_PROTECTED_JSON_BYTES:
                raise ValueError
            chunks = [
                protect_current_user(
                    raw[index : index + _DPAPI_CHUNK_BYTES],
                    entropy=_ENTROPY,
                )
                for index in range(0, len(raw), _DPAPI_CHUNK_BYTES)
            ]
            return _DPAPI_MAGIC + len(chunks).to_bytes(4, "big") + b"".join(
                len(chunk).to_bytes(4, "big") + chunk for chunk in chunks
            )
        except Exception:
            raise DurableTelegramStateError("runtime_payload_protection_failed") from None

    def decode(self, value: bytes) -> dict[str, Any]:
        try:
            if value.startswith(_DPAPI_MAGIC):
                count = int.from_bytes(value[5:9], "big")
                if not 1 <= count <= 80:
                    raise ValueError
                offset = 9
                raw_parts: list[bytes] = []
                for _ in range(count):
                    if offset + 4 > len(value):
                        raise ValueError
                    size = int.from_bytes(value[offset : offset + 4], "big")
                    offset += 4
                    if not 1 <= size <= 2 * 1024 * 1024 or offset + size > len(value):
                        raise ValueError
                    raw_parts.append(
                        unprotect_current_user(
                            value[offset : offset + size], entropy=_ENTROPY
                        )
                    )
                    offset += size
                if offset != len(value):
                    raise ValueError
                raw = b"".join(raw_parts)
            else:
                # Backward compatibility for pre-chunk runtime capabilities.
                raw = unprotect_current_user(value, entropy=_ENTROPY)
            if not raw or len(raw) > _MAX_PROTECTED_JSON_BYTES:
                raise ValueError
            decoded = json.loads(raw, object_pairs_hook=_unique_object)
            if not isinstance(decoded, dict):
                raise ValueError
            return decoded
        except Exception:
            raise DurableTelegramStateError("runtime_payload_protection_failed") from None


class SQLiteTelegramState:
    """One bounded local store; sensitive values are encrypted before SQLite."""

    def __init__(
        self,
        path: str | Path,
        *,
        encode: Callable[[Mapping[str, Any]], bytes] | None = None,
        decode: Callable[[bytes], dict[str, Any]] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        max_jobs: int = 40,
        max_capabilities: int = 2_000,
        busy_timeout_ms: int = 5_000,
    ) -> None:
        if (
            str(path) == ":memory:"
            or type(max_jobs) is not int
            or not 1 <= max_jobs <= 1_000
            or type(max_capabilities) is not int
            or not 1 <= max_capabilities <= 100_000
            or type(busy_timeout_ms) is not int
            or not 1 <= busy_timeout_ms <= 60_000
        ):
            raise ValueError("durable Telegram state configuration is invalid")
        codec = DpapiJsonCodec()
        self._path = Path(path)
        self._encode = encode or codec.encode
        self._decode = decode or codec.decode
        self._clock = clock
        self._max_jobs = max_jobs
        self._max_capabilities = max_capabilities
        self._timeout = busy_timeout_ms
        try:
            self._initialize()
        except (OSError, sqlite3.DatabaseError):
            raise DurableTelegramStateError("runtime_store_unavailable") from None

    @property
    def path(self) -> Path:
        return self._path

    def enqueue(
        self,
        *,
        kind: str,
        tenant_id: str,
        task_id: UUID,
        binding_digest: str,
        payload: Mapping[str, Any],
    ) -> DurableJob:
        kind, tenant_id, binding_digest = self._job_binding(
            kind, tenant_id, task_id, binding_digest
        )
        protected = self._encode(payload)
        payload_digest = canonical_json_digest(payload)
        now = self._now()
        try:
            with self._transaction() as connection:
                row = connection.execute(
                    """SELECT * FROM telegram_jobs
                       WHERE tenant_id=? AND task_id=? AND kind=?""",
                    (tenant_id, str(task_id), kind),
                ).fetchone()
                if row is not None:
                    job = self._job_from_row(row)
                    if (
                        job.binding_digest != binding_digest
                        or row["payload_digest"] != payload_digest
                    ):
                        raise DurableTelegramStateError("runtime_job_conflict")
                    if row["status"] == "failed":
                        raise DurableTelegramStateError("runtime_job_failed")
                    return job
                count = connection.execute(
                    "SELECT COUNT(*) FROM telegram_jobs"
                ).fetchone()[0]
                if count >= self._max_jobs:
                    raise DurableTelegramStateError("runtime_queue_full")
                job_id = uuid4()
                connection.execute(
                    """INSERT INTO telegram_jobs
                       (job_id,kind,tenant_id,task_id,binding_digest,payload_digest,
                        payload,status,attempt_count,lease_id,lease_owner,
                        lease_expires_at,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,'pending',0,NULL,NULL,NULL,?,?)""",
                    (
                        str(job_id), kind, tenant_id, str(task_id), binding_digest,
                        payload_digest, protected, now.isoformat(), now.isoformat(),
                    ),
                )
                return DurableJob(
                    job_id, kind, tenant_id, task_id, binding_digest, dict(payload), 0
                )
        except DurableTelegramStateError:
            raise
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise DurableTelegramStateError("runtime_store_unavailable") from None

    def claim(
        self, *, lease_owner: UUID, lease_seconds: int = 300
    ) -> DurableJob | None:
        if not isinstance(lease_owner, UUID) or type(lease_seconds) is not int or not 5 <= lease_seconds <= 14_400:
            raise ValueError("runtime job lease is invalid")
        now = self._now()
        expires = now + timedelta(seconds=lease_seconds)
        lease_id = uuid4()
        try:
            with self._transaction() as connection:
                # One recovery round protects an externally completed effect
                # after power loss. A second exhausted execution round, or an
                # exhausted delivery round, is dead-lettered instead of looping.
                connection.execute(
                    """UPDATE telegram_jobs
                       SET status='failed',
                           failure_code=CASE
                               WHEN kind='effect'
                               THEN 'runtime_effect_attempts_exhausted'
                               ELSE 'runtime_job_attempts_exhausted'
                           END,
                           lease_id=NULL,lease_owner=NULL,
                           lease_expires_at=NULL,updated_at=?
                       WHERE attempt_count>=? AND (
                           kind!='effect' OR
                           failure_code IN (
                               'runtime_effect_recovery',
                               'runtime_effect_delivery'
                           )
                       ) AND (
                           status='pending' OR
                           (status='leased' AND lease_expires_at<=?)
                       )""",
                    (now.isoformat(), MAX_JOB_CLAIMS, now.isoformat()),
                )
                connection.execute(
                    """UPDATE telegram_jobs
                       SET status='pending',attempt_count=0,
                           failure_code='runtime_effect_recovery',
                           lease_id=NULL,lease_owner=NULL,
                           lease_expires_at=NULL,updated_at=?
                       WHERE kind='effect' AND attempt_count>=?
                         AND failure_code IS NULL AND (
                           status='pending' OR
                           (status='leased' AND lease_expires_at<=?)
                       )""",
                    (now.isoformat(), MAX_JOB_CLAIMS, now.isoformat()),
                )
                connection.execute(
                    """UPDATE telegram_jobs
                       SET status='pending',lease_id=NULL,lease_owner=NULL,
                           lease_expires_at=NULL,updated_at=?
                       WHERE status='leased' AND lease_expires_at<=?
                         AND attempt_count<?""",
                    (now.isoformat(), now.isoformat(), MAX_JOB_CLAIMS),
                )
                row = connection.execute(
                    """SELECT * FROM telegram_jobs
                       WHERE status='pending' AND attempt_count<?
                       ORDER BY created_at,job_id LIMIT 1""",
                    (MAX_JOB_CLAIMS,),
                ).fetchone()
                if row is None:
                    return None
                cursor = connection.execute(
                    """UPDATE telegram_jobs SET status='leased',attempt_count=attempt_count+1,
                       lease_id=?,lease_owner=?,lease_expires_at=?,updated_at=?
                       WHERE job_id=? AND status='pending'
                         AND attempt_count<?""",
                    (
                        str(lease_id), str(lease_owner), expires.isoformat(),
                        now.isoformat(), row["job_id"], MAX_JOB_CLAIMS,
                    ),
                )
                if cursor.rowcount != 1:
                    raise DurableTelegramStateError("runtime_job_conflict")
                leased = connection.execute(
                    "SELECT * FROM telegram_jobs WHERE job_id=?", (row["job_id"],)
                ).fetchone()
                if leased is None:
                    raise DurableTelegramStateError("runtime_job_conflict")
                return self._job_from_row(leased)
        except DurableTelegramStateError:
            raise
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise DurableTelegramStateError("runtime_store_unavailable") from None

    def ack(self, job: DurableJob, *, lease_owner: UUID) -> None:
        job = self._validated_job(job, require_lease=True)
        now = self._now()
        try:
            with self._transaction() as connection:
                cursor = connection.execute(
                    """DELETE FROM telegram_jobs
                       WHERE job_id=? AND status='leased' AND lease_id=?
                         AND lease_owner=? AND lease_expires_at>?""",
                    (
                        str(job.job_id),
                        str(job.lease_id),
                        str(lease_owner),
                        now.isoformat(),
                    ),
                )
                if cursor.rowcount != 1:
                    raise DurableTelegramStateError("runtime_job_lease_lost")
        except DurableTelegramStateError:
            raise
        except (OSError, sqlite3.DatabaseError):
            raise DurableTelegramStateError("runtime_store_unavailable") from None

    def ack_effect_delivery(
        self,
        job: DurableJob,
        *,
        lease_owner: UUID,
        capability_token: str,
        tenant_id: str,
        user_id: int,
        chat_id: int,
    ) -> None:
        """Atomically remove a delivered effect job and its capability."""
        job = self._validated_job(job, require_lease=True)
        if (
            job.kind != "effect"
            or not _text(capability_token, 2_048)
            or not _text(tenant_id, 128)
            or type(user_id) is not int
            or type(chat_id) is not int
            or user_id <= 0
            or chat_id == 0
            or job.tenant_id != tenant_id.strip()
        ):
            raise ValueError("effect delivery acknowledgement is invalid")
        token_digest = (
            "sha256:"
            + hashlib.sha256(capability_token.encode("utf-8")).hexdigest()
        )
        now = self._now()
        try:
            with self._transaction() as connection:
                job_row = connection.execute(
                    """SELECT tenant_id,task_id,binding_digest,payload,
                              payload_digest
                       FROM telegram_jobs
                       WHERE job_id=? AND kind='effect' AND status='leased'
                         AND lease_id=? AND lease_owner=?
                         AND lease_expires_at>?""",
                    (
                        str(job.job_id),
                        str(job.lease_id),
                        str(lease_owner),
                        now.isoformat(),
                    ),
                ).fetchone()
                if job_row is None:
                    raise DurableTelegramStateError(
                        "runtime_job_lease_lost"
                    )
                job_payload = self._decode(bytes(job_row["payload"]))
                expected_task_id = UUID(
                    bytes=hashlib.sha256(
                        f"{tenant_id.strip()}:{capability_token}".encode()
                    ).digest()[:16],
                    version=4,
                )
                if (
                    not isinstance(job_payload, dict)
                    or canonical_json_digest(job_payload)
                    != job_row["payload_digest"]
                    or canonical_json_digest(job_payload)
                    != job_row["binding_digest"]
                    or job_payload.get("capability_token")
                    != capability_token
                    or job_row["tenant_id"] != tenant_id.strip()
                    or UUID(job_row["task_id"]) != expected_task_id
                    or job.task_id != expected_task_id
                    or job.binding_digest != job_row["binding_digest"]
                    or job.payload != job_payload
                ):
                    raise DurableTelegramStateError(
                        "runtime_effect_job_binding_invalid"
                    )
                row = connection.execute(
                    """SELECT payload,payload_digest
                       FROM telegram_capabilities
                       WHERE kind='action' AND token_digest=?
                         AND tenant_id=?""",
                    (token_digest, tenant_id.strip()),
                ).fetchone()
                if row is None:
                    raise DurableTelegramStateError(
                        "runtime_effect_capability_missing"
                    )
                payload = self._decode(bytes(row["payload"]))
                if (
                    not isinstance(payload, dict)
                    or canonical_json_digest(payload) != row["payload_digest"]
                    or payload.get("token") != capability_token
                    or payload.get("tenant_id") != tenant_id.strip()
                    or payload.get("user_id") != user_id
                    or payload.get("chat_id") != chat_id
                    or payload.get("state") != "delivered"
                ):
                    raise DurableTelegramStateError(
                        "runtime_effect_delivery_invalid"
                    )
                deleted_job = connection.execute(
                    """DELETE FROM telegram_jobs
                       WHERE job_id=? AND kind='effect' AND status='leased'
                         AND lease_id=? AND lease_owner=?
                         AND lease_expires_at>?""",
                    (
                        str(job.job_id),
                        str(job.lease_id),
                        str(lease_owner),
                        now.isoformat(),
                    ),
                )
                if deleted_job.rowcount != 1:
                    raise DurableTelegramStateError(
                        "runtime_job_lease_lost"
                    )
                deleted_capability = connection.execute(
                    """DELETE FROM telegram_capabilities
                       WHERE kind='action' AND token_digest=?
                         AND tenant_id=?""",
                    (token_digest, tenant_id.strip()),
                )
                if deleted_capability.rowcount != 1:
                    raise DurableTelegramStateError(
                        "runtime_effect_capability_missing"
                    )
        except DurableTelegramStateError:
            raise
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise DurableTelegramStateError(
                "runtime_store_unavailable"
            ) from None

    def release(self, job: DurableJob, *, lease_owner: UUID) -> None:
        job = self._validated_job(job, require_lease=True)
        now = self._now()
        try:
            with self._transaction() as connection:
                cursor = connection.execute(
                    """UPDATE telegram_jobs
                       SET status=CASE WHEN attempt_count>=? THEN 'failed'
                                       ELSE 'pending' END,
                           failure_code=CASE WHEN attempt_count>=?
                                       THEN 'runtime_job_attempts_exhausted'
                                       ELSE failure_code END,
                           lease_id=NULL,lease_owner=NULL,
                           lease_expires_at=NULL,updated_at=?
                       WHERE job_id=? AND status='leased'
                         AND lease_id=? AND lease_owner=?
                         AND lease_expires_at>?""",
                    (
                        MAX_JOB_CLAIMS,
                        MAX_JOB_CLAIMS,
                        now.isoformat(),
                        str(job.job_id),
                        str(job.lease_id),
                        str(lease_owner),
                        now.isoformat(),
                    ),
                )
                if cursor.rowcount != 1:
                    raise DurableTelegramStateError("runtime_job_lease_lost")
        except DurableTelegramStateError:
            raise
        except (OSError, sqlite3.DatabaseError):
            raise DurableTelegramStateError("runtime_store_unavailable") from None

    def retry_effect_delivery(
        self,
        job: DurableJob,
        *,
        lease_owner: UUID,
        delay_seconds: int = 30,
    ) -> None:
        """Persist a delayed retry for a completed effect delivery."""
        job = self._validated_job(job, require_lease=True)
        if (
            job.kind != "effect"
            or type(delay_seconds) is not int
            or not 5 <= delay_seconds <= 3_600
        ):
            raise ValueError("effect delivery retry is invalid")
        now = self._now()
        retry_at = now + timedelta(seconds=delay_seconds)
        try:
            with self._transaction() as connection:
                cursor = connection.execute(
                    """UPDATE telegram_jobs
                       SET status='leased',
                           attempt_count=CASE
                               WHEN failure_code='runtime_effect_delivery'
                               THEN attempt_count ELSE 0
                           END,
                           failure_code='runtime_effect_delivery',
                           lease_expires_at=?,updated_at=?
                       WHERE job_id=? AND status='leased'
                         AND lease_id=? AND lease_owner=?
                         AND lease_expires_at>?""",
                    (
                        retry_at.isoformat(),
                        now.isoformat(),
                        str(job.job_id),
                        str(job.lease_id),
                        str(lease_owner),
                        now.isoformat(),
                    ),
                )
                if cursor.rowcount != 1:
                    raise DurableTelegramStateError("runtime_job_lease_lost")
        except DurableTelegramStateError:
            raise
        except (OSError, sqlite3.DatabaseError):
            raise DurableTelegramStateError("runtime_store_unavailable") from None

    def fail(
        self,
        job: DurableJob,
        *,
        lease_owner: UUID,
        failure_code: str,
    ) -> None:
        job = self._validated_job(job, require_lease=True)
        if not _text(failure_code, 64):
            raise ValueError("runtime job failure code is invalid")
        now = self._now()
        try:
            with self._transaction() as connection:
                cursor = connection.execute(
                    """UPDATE telegram_jobs
                       SET status='failed',failure_code=?,lease_id=NULL,
                           lease_owner=NULL,lease_expires_at=NULL,updated_at=?
                       WHERE job_id=? AND status='leased' AND lease_id=?
                         AND lease_owner=? AND lease_expires_at>?""",
                    (
                        failure_code.strip(),
                        now.isoformat(),
                        str(job.job_id),
                        str(job.lease_id),
                        str(lease_owner),
                        now.isoformat(),
                    ),
                )
                if cursor.rowcount != 1:
                    raise DurableTelegramStateError("runtime_job_lease_lost")
        except DurableTelegramStateError:
            raise
        except (OSError, sqlite3.DatabaseError):
            raise DurableTelegramStateError("runtime_store_unavailable") from None

    def renew(
        self,
        job: DurableJob,
        *,
        lease_owner: UUID,
        lease_seconds: int = 300,
    ) -> DurableJob:
        job = self._validated_job(job, require_lease=True)
        if type(lease_seconds) is not int or not 5 <= lease_seconds <= 14_400:
            raise ValueError("runtime job lease is invalid")
        now = self._now()
        expires = now + timedelta(seconds=lease_seconds)
        try:
            with self._transaction() as connection:
                cursor = connection.execute(
                    """UPDATE telegram_jobs SET lease_expires_at=?,updated_at=?
                       WHERE job_id=? AND status='leased' AND lease_id=?
                       AND lease_owner=? AND lease_expires_at>?""",
                    (
                        expires.isoformat(), now.isoformat(), str(job.job_id),
                        str(job.lease_id), str(lease_owner), now.isoformat(),
                    ),
                )
                if cursor.rowcount != 1:
                    raise DurableTelegramStateError("runtime_job_lease_lost")
            return DurableJob(
                job.job_id, job.kind, job.tenant_id, job.task_id,
                job.binding_digest, job.payload, job.attempt_count,
                job.lease_id,
            )
        except DurableTelegramStateError:
            raise
        except (OSError, sqlite3.DatabaseError):
            raise DurableTelegramStateError("runtime_store_unavailable") from None

    def queue_counts(self) -> tuple[int, int]:
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    """SELECT
                       SUM(CASE WHEN status='leased' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END)
                       FROM telegram_jobs"""
                ).fetchone()
                return int(row[0] or 0), int(row[1] or 0)
        except (OSError, sqlite3.DatabaseError, TypeError, ValueError):
            raise DurableTelegramStateError("runtime_store_unavailable") from None

    def has_runnable_job(
        self,
        *,
        kind: str,
        tenant_id: str,
        task_id: UUID,
        binding_digest: str,
    ) -> bool:
        kind, tenant_id, binding_digest = self._job_binding(
            kind, tenant_id, task_id, binding_digest
        )
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    """SELECT binding_digest,status FROM telegram_jobs
                       WHERE tenant_id=? AND task_id=? AND kind=?""",
                    (tenant_id, str(task_id), kind),
                ).fetchone()
                if row is None:
                    return False
                if row["binding_digest"] != binding_digest:
                    raise DurableTelegramStateError("runtime_job_conflict")
                return row["status"] in {"pending", "leased"}
        except DurableTelegramStateError:
            raise
        except (OSError, sqlite3.DatabaseError, TypeError, ValueError):
            raise DurableTelegramStateError("runtime_store_unavailable") from None

    def dead_letter_count(self) -> int:
        try:
            with closing(self._connect()) as connection:
                return int(
                    connection.execute(
                        "SELECT COUNT(*) FROM telegram_jobs WHERE status='failed'"
                    ).fetchone()[0]
                )
        except (OSError, sqlite3.DatabaseError, TypeError, ValueError):
            raise DurableTelegramStateError("runtime_store_unavailable") from None

    def put_capability(
        self,
        *,
        kind: str,
        token_digest: str,
        tenant_id: str,
        payload: Mapping[str, Any],
        expires_at: datetime,
    ) -> None:
        if (
            kind not in _CAPABILITY_KINDS
            or not _is_digest(token_digest)
            or not _text(tenant_id, 128)
            or not _aware(expires_at)
        ):
            raise ValueError("runtime capability is invalid")
        protected = self._encode(payload)
        payload_digest = canonical_json_digest(payload)
        now = self._now()
        if expires_at.astimezone(UTC) <= now:
            raise ValueError("runtime capability expiry is invalid")
        try:
            with self._transaction() as connection:
                self._sweep_capabilities(connection, now)
                count = connection.execute(
                    "SELECT COUNT(*) FROM telegram_capabilities"
                ).fetchone()[0]
                if count >= self._max_capabilities:
                    raise DurableTelegramStateError("runtime_capability_full")
                connection.execute(
                    """INSERT INTO telegram_capabilities
                       (kind,token_digest,tenant_id,payload_digest,payload,
                        expires_at,created_at)
                       VALUES (?,?,?,?,?,?,?)""",
                    (
                        kind, token_digest, tenant_id.strip(), payload_digest,
                        protected, expires_at.astimezone(UTC).isoformat(),
                        now.isoformat(),
                    ),
                )
        except DurableTelegramStateError:
            raise
        except sqlite3.IntegrityError:
            raise DurableTelegramStateError("runtime_capability_conflict") from None
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise DurableTelegramStateError("runtime_store_unavailable") from None

    def replace_capability(
        self,
        *,
        kind: str,
        token_digest: str,
        tenant_id: str,
        expected_payload: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> bool:
        if (
            kind not in _CAPABILITY_KINDS
            or not _is_digest(token_digest)
            or not _text(tenant_id, 128)
        ):
            raise ValueError("runtime capability is invalid")
        expected_digest = canonical_json_digest(expected_payload)
        protected = self._encode(payload)
        payload_digest = canonical_json_digest(payload)
        now = self._now()
        try:
            with self._transaction() as connection:
                self._sweep_capabilities(connection, now)
                cursor = connection.execute(
                    """UPDATE telegram_capabilities
                       SET payload_digest=?,payload=?
                       WHERE kind=? AND token_digest=? AND tenant_id=?
                         AND payload_digest=?""",
                    (
                        payload_digest,
                        protected,
                        kind,
                        token_digest,
                        tenant_id.strip(),
                        expected_digest,
                    ),
                )
                return cursor.rowcount == 1
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise DurableTelegramStateError("runtime_store_unavailable") from None

    def read_capability(
        self, *, kind: str, token_digest: str, tenant_id: str
    ) -> dict[str, Any] | None:
        if kind not in _CAPABILITY_KINDS or not _is_digest(token_digest) or not _text(tenant_id, 128):
            return None
        now = self._now()
        try:
            with self._transaction() as connection:
                self._sweep_capabilities(connection, now)
                row = connection.execute(
                    """SELECT payload,payload_digest FROM telegram_capabilities
                       WHERE kind=? AND token_digest=? AND tenant_id=?""",
                    (kind, token_digest, tenant_id.strip()),
                ).fetchone()
                if row is None:
                    return None
                payload = self._decode(bytes(row["payload"]))
                if canonical_json_digest(payload) != row["payload_digest"]:
                    raise DurableTelegramStateError("runtime_payload_tampered")
                return payload
        except DurableTelegramStateError:
            raise
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise DurableTelegramStateError("runtime_store_unavailable") from None

    def delete_capability(
        self, *, kind: str, token_digest: str, tenant_id: str
    ) -> bool:
        if kind not in _CAPABILITY_KINDS or not _is_digest(token_digest) or not _text(tenant_id, 128):
            return False
        try:
            with self._transaction() as connection:
                cursor = connection.execute(
                    """DELETE FROM telegram_capabilities
                       WHERE kind=? AND token_digest=? AND tenant_id=?""",
                    (kind, token_digest, tenant_id.strip()),
                )
                return cursor.rowcount == 1
        except (OSError, sqlite3.DatabaseError):
            raise DurableTelegramStateError("runtime_store_unavailable") from None

    def put_semantic_clarification(
        self,
        *,
        owner_binding: str,
        tenant_id: str,
        tenant_binding: str,
        conversation_binding: str,
        answer_binding: str,
        envelope_revision: str,
        intake_revision: int,
        payload: Mapping[str, Any],
        expires_at: datetime,
    ) -> None:
        bindings = (
            owner_binding,
            tenant_binding,
            conversation_binding,
            answer_binding,
            envelope_revision,
        )
        if (
            not all(_is_digest(value) for value in bindings)
            or not _text(tenant_id, 128)
            or type(intake_revision) is not int
            or intake_revision < 1
            or not _aware(expires_at)
        ):
            raise ValueError("semantic clarification binding is invalid")
        protected = self._encode(payload)
        payload_digest = canonical_json_digest(payload)
        now = self._now()
        if not now < expires_at.astimezone(UTC) <= now + timedelta(minutes=30):
            raise ValueError("semantic clarification expiry is invalid")
        try:
            with self._transaction() as connection:
                self._sweep_semantic_clarifications(connection, now)
                connection.execute(
                    """INSERT INTO semantic_clarifications
                       (conversation_binding,owner_binding,tenant_id,tenant_binding,
                        answer_binding,envelope_revision,intake_revision,payload_digest,
                        payload,expires_at,created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(conversation_binding) DO UPDATE SET
                       owner_binding=excluded.owner_binding,
                       tenant_id=excluded.tenant_id,
                       tenant_binding=excluded.tenant_binding,
                       answer_binding=excluded.answer_binding,
                       envelope_revision=excluded.envelope_revision,
                       intake_revision=excluded.intake_revision,
                       payload_digest=excluded.payload_digest,
                       payload=excluded.payload,
                       expires_at=excluded.expires_at,
                       created_at=excluded.created_at""",
                    (
                        conversation_binding,
                        owner_binding,
                        tenant_id.strip(),
                        tenant_binding,
                        answer_binding,
                        envelope_revision,
                        intake_revision,
                        payload_digest,
                        protected,
                        expires_at.astimezone(UTC).isoformat(),
                        now.isoformat(),
                    ),
                )
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise DurableTelegramStateError("runtime_store_unavailable") from None

    def read_semantic_clarification(
        self,
        *,
        owner_binding: str,
        tenant_id: str,
        tenant_binding: str,
        conversation_binding: str,
        answer_binding: str,
        reply_envelope_revision: str,
    ) -> dict[str, Any] | None:
        bindings = (
            owner_binding,
            tenant_binding,
            conversation_binding,
            answer_binding,
            reply_envelope_revision,
        )
        if not all(_is_digest(value) for value in bindings) or not _text(
            tenant_id, 128
        ):
            return None
        now = self._now()
        try:
            with self._transaction() as connection:
                self._sweep_semantic_clarifications(connection, now)
                row = connection.execute(
                    """SELECT * FROM semantic_clarifications
                       WHERE conversation_binding=? AND owner_binding=?
                         AND tenant_id=? AND tenant_binding=?
                         AND answer_binding=?
                         AND envelope_revision<>?""",
                    (
                        conversation_binding,
                        owner_binding,
                        tenant_id.strip(),
                        tenant_binding,
                        answer_binding,
                        reply_envelope_revision,
                    ),
                ).fetchone()
                if row is None:
                    return None
                payload = self._decode(bytes(row["payload"]))
                if canonical_json_digest(payload) != row["payload_digest"]:
                    raise DurableTelegramStateError("runtime_payload_tampered")
                return payload
        except DurableTelegramStateError:
            raise
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise DurableTelegramStateError("runtime_store_unavailable") from None

    def delete_semantic_clarification(
        self,
        *,
        conversation_binding: str,
        tenant_id: str,
        payload_digest: str,
    ) -> bool:
        if (
            not _is_digest(conversation_binding)
            or not _is_digest(payload_digest)
            or not _text(tenant_id, 128)
        ):
            return False
        try:
            with self._transaction() as connection:
                cursor = connection.execute(
                    """DELETE FROM semantic_clarifications
                       WHERE conversation_binding=? AND tenant_id=?
                         AND payload_digest=?""",
                    (conversation_binding, tenant_id.strip(), payload_digest),
                )
                return cursor.rowcount == 1
        except (OSError, sqlite3.DatabaseError):
            raise DurableTelegramStateError("runtime_store_unavailable") from None

    def save_progress(
        self, *, tenant_id: str, task_id: UUID, chat_id: int, message_id: int
    ) -> ProgressMessageRef:
        if not _text(tenant_id, 128) or type(chat_id) is not int or type(message_id) is not int or chat_id == 0 or message_id <= 0:
            raise ValueError("progress message binding is invalid")
        now = self._now()
        try:
            with self._transaction() as connection:
                connection.execute(
                    """INSERT INTO telegram_progress
                       (tenant_id,task_id,chat_id,message_id,updated_at)
                       VALUES (?,?,?,?,?)
                       ON CONFLICT(tenant_id,task_id) DO UPDATE SET
                       chat_id=excluded.chat_id,message_id=excluded.message_id,
                       updated_at=excluded.updated_at""",
                    (tenant_id.strip(), str(task_id), chat_id, message_id, now.isoformat()),
                )
            return ProgressMessageRef(tenant_id.strip(), task_id, chat_id, message_id, now)
        except (OSError, sqlite3.DatabaseError):
            raise DurableTelegramStateError("runtime_store_unavailable") from None

    def read_progress(
        self, *, tenant_id: str, task_id: UUID
    ) -> ProgressMessageRef | None:
        if not _text(tenant_id, 128):
            return None
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    """SELECT * FROM telegram_progress
                       WHERE tenant_id=? AND task_id=?""",
                    (tenant_id.strip(), str(task_id)),
                ).fetchone()
                if row is None:
                    return None
                return ProgressMessageRef(
                    row["tenant_id"], UUID(row["task_id"]), row["chat_id"],
                    row["message_id"], datetime.fromisoformat(row["updated_at"]),
                )
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise DurableTelegramStateError("runtime_store_unavailable") from None

    def delete_progress(self, reference: ProgressMessageRef) -> bool:
        if not isinstance(reference, ProgressMessageRef):
            return False
        try:
            with self._transaction() as connection:
                cursor = connection.execute(
                    """DELETE FROM telegram_progress
                       WHERE tenant_id=? AND task_id=? AND chat_id=?
                         AND message_id=?""",
                    (
                        reference.tenant_id,
                        str(reference.task_id),
                        reference.chat_id,
                        reference.message_id,
                    ),
                )
                return cursor.rowcount == 1
        except (OSError, sqlite3.DatabaseError):
            raise DurableTelegramStateError("runtime_store_unavailable") from None

    def pop_progress(self, *, tenant_id: str, task_id: UUID) -> ProgressMessageRef | None:
        if not _text(tenant_id, 128):
            return None
        try:
            with self._transaction() as connection:
                row = connection.execute(
                    """SELECT * FROM telegram_progress
                       WHERE tenant_id=? AND task_id=?""",
                    (tenant_id.strip(), str(task_id)),
                ).fetchone()
                if row is None:
                    return None
                connection.execute(
                    "DELETE FROM telegram_progress WHERE tenant_id=? AND task_id=?",
                    (tenant_id.strip(), str(task_id)),
                )
                return ProgressMessageRef(
                    row["tenant_id"], UUID(row["task_id"]), row["chat_id"],
                    row["message_id"], datetime.fromisoformat(row["updated_at"]),
                )
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise DurableTelegramStateError("runtime_store_unavailable") from None

    def quick_check(self) -> bool:
        try:
            with closing(self._connect()) as connection:
                return connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        except (OSError, sqlite3.DatabaseError, TypeError):
            return False

    def backup(self, target: str | Path) -> Path:
        destination = Path(target)
        if destination == self._path or destination.exists():
            raise ValueError("backup target must be new")
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with closing(self._connect()) as source, closing(
                sqlite3.connect(destination)
            ) as output:
                source.backup(output)
            with closing(sqlite3.connect(destination)) as check:
                if check.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise sqlite3.DatabaseError
            return destination
        except (OSError, sqlite3.DatabaseError):
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                pass
            raise DurableTelegramStateError("runtime_backup_failed") from None

    def _job_from_row(self, row: sqlite3.Row) -> DurableJob:
        if row["kind"] not in _JOB_KINDS or row["status"] not in _JOB_STATUSES:
            raise DurableTelegramStateError("runtime_store_corrupt")
        payload = self._decode(bytes(row["payload"]))
        if canonical_json_digest(payload) != row["payload_digest"]:
            raise DurableTelegramStateError("runtime_payload_tampered")
        return DurableJob(
            UUID(row["job_id"]), row["kind"], row["tenant_id"],
            UUID(row["task_id"]), row["binding_digest"], payload,
            int(row["attempt_count"]),
            UUID(row["lease_id"]) if row["lease_id"] is not None else None,
        )

    @staticmethod
    def _validated_job(job: DurableJob, *, require_lease: bool) -> DurableJob:
        if not isinstance(job, DurableJob) or (require_lease and job.lease_id is None):
            raise ValueError("runtime job is invalid")
        return job

    @staticmethod
    def _job_binding(
        kind: str, tenant_id: str, task_id: UUID, binding_digest: str
    ) -> tuple[str, str, str]:
        if kind not in _JOB_KINDS or not _text(tenant_id, 128) or not isinstance(task_id, UUID) or not _is_digest(binding_digest):
            raise ValueError("runtime job binding is invalid")
        return kind, tenant_id.strip(), binding_digest

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self._path, isolation_level=None, timeout=self._timeout / 1_000
        )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout={self._timeout}")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        job_schema = """
            CREATE TABLE telegram_jobs (
                job_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL CHECK(
                    kind IN ('draft','miniapp_draft','patch','effect')
                ),
                tenant_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                binding_digest TEXT NOT NULL,
                payload_digest TEXT NOT NULL,
                payload BLOB NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','leased','failed')),
                attempt_count INTEGER NOT NULL CHECK(attempt_count>=0),
                failure_code TEXT,
                lease_id TEXT,
                lease_owner TEXT,
                lease_expires_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(tenant_id,task_id,kind)
            )
        """
        expected = {
            "job_id", "kind", "tenant_id", "task_id", "binding_digest",
            "payload_digest", "payload", "status", "attempt_count",
            "lease_id", "lease_owner", "lease_expires_at", "created_at",
            "updated_at",
        }
        with closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            row = connection.execute(
                """SELECT sql FROM sqlite_master
                   WHERE type='table' AND name='telegram_jobs'"""
            ).fetchone()
            if row is None:
                connection.execute(job_schema)
            else:
                columns = {
                    item["name"]
                    for item in connection.execute(
                        "PRAGMA table_info(telegram_jobs)"
                    )
                }
                sql = str(row["sql"] or "")
                current = (
                    expected | {"failure_code"} == columns
                    and "'effect'" in sql
                    and "'miniapp_draft'" in sql
                    and "'failed'" in sql
                )
                previous = (
                    expected | {"failure_code"} == columns
                    and "'effect'" in sql
                    and "'miniapp_draft'" not in sql
                    and "'failed'" in sql
                )
                legacy = columns == expected
                if not current and not previous and not legacy:
                    raise sqlite3.DatabaseError("unexpected telegram_jobs schema")
                if previous or legacy:
                    connection.execute("BEGIN IMMEDIATE")
                    try:
                        connection.execute(
                            "DROP INDEX IF EXISTS idx_telegram_jobs_ready"
                        )
                        connection.execute(
                            "ALTER TABLE telegram_jobs RENAME TO telegram_jobs_legacy"
                        )
                        connection.execute(job_schema)
                        failure_code = "failure_code" if previous else "NULL"
                        connection.execute(
                            f"""INSERT INTO telegram_jobs
                                (job_id,kind,tenant_id,task_id,binding_digest,
                                 payload_digest,payload,status,attempt_count,
                                 failure_code,lease_id,lease_owner,
                                 lease_expires_at,created_at,updated_at)
                                SELECT job_id,kind,tenant_id,task_id,binding_digest,
                                       payload_digest,payload,status,attempt_count,
                                       {failure_code},lease_id,lease_owner,
                                       lease_expires_at,created_at,updated_at
                                FROM telegram_jobs_legacy"""
                        )
                        connection.execute("DROP TABLE telegram_jobs_legacy")
                        connection.commit()
                    except BaseException:
                        connection.rollback()
                        raise
            connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_telegram_jobs_ready
                    ON telegram_jobs(status,created_at);
                CREATE TABLE IF NOT EXISTS telegram_capabilities (
                    kind TEXT NOT NULL CHECK(kind IN ('task','patch','action')),
                    token_digest TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    payload BLOB NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(kind,token_digest,tenant_id)
                );
                CREATE INDEX IF NOT EXISTS idx_telegram_capability_expiry
                    ON telegram_capabilities(expires_at);
                CREATE TABLE IF NOT EXISTS telegram_progress (
                    tenant_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL CHECK(message_id>0),
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(tenant_id,task_id)
                );
                CREATE TABLE IF NOT EXISTS semantic_clarifications (
                    conversation_binding TEXT PRIMARY KEY,
                    owner_binding TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    tenant_binding TEXT NOT NULL,
                    answer_binding TEXT NOT NULL,
                    envelope_revision TEXT NOT NULL,
                    intake_revision INTEGER NOT NULL CHECK(intake_revision>=1),
                    payload_digest TEXT NOT NULL,
                    payload BLOB NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_semantic_clarification_expiry
                    ON semantic_clarifications(expires_at);
                """
            )

    @staticmethod
    def _sweep_capabilities(connection: sqlite3.Connection, now: datetime) -> None:
        connection.execute(
            "DELETE FROM telegram_capabilities WHERE expires_at<=?",
            (now.isoformat(),),
        )

    @staticmethod
    def _sweep_semantic_clarifications(
        connection: sqlite3.Connection, now: datetime
    ) -> None:
        connection.execute(
            "DELETE FROM semantic_clarifications WHERE expires_at<=?",
            (now.isoformat(),),
        )

    def _now(self) -> datetime:
        value = self._clock()
        if type(value) is not datetime or not _aware(value):
            raise DurableTelegramStateError("runtime_clock_unavailable")
        return value.astimezone(UTC)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _text(value: object, limit: int) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit and "\x00" not in value


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )
