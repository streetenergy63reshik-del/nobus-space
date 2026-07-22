"""Durable SQLite implementation of the Telegram polling checkpoint contract."""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing, contextmanager
from functools import wraps
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterator, ParamSpec, TypeVar
from uuid import UUID, uuid4

from src.contracts.models import canonical_json_digest
from src.transport.telegram.bot_api import PollingLease


_P = ParamSpec("_P")
_R = TypeVar("_R")


_CONSUMER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


class SQLitePollingCheckpointError(RuntimeError):
    """The durable polling checkpoint is unavailable or corrupt."""


def _stable_errors(operation: Callable[_P, _R]) -> Callable[_P, _R]:
    """Remove nested exception details from the public persistence boundary."""

    @wraps(operation)
    def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        failed = False
        try:
            return operation(*args, **kwargs)
        except (
            SQLitePollingCheckpointError,
            OSError,
            sqlite3.DatabaseError,
            TypeError,
            ValueError,
        ):
            failed = True
        if failed:
            raise SQLitePollingCheckpointError(
                "polling checkpoint is invalid"
            )
        raise AssertionError("unreachable")

    return wrapped


class SQLitePollingCheckpointStore:
    """One generation-bound polling lease and monotonic offset per consumer."""

    @_stable_errors
    def __init__(
        self,
        path: str | Path,
        *,
        consumer_id: str,
        lease_duration_seconds: int = 60,
        busy_timeout_ms: int = 5_000,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._path = Path(path)
        self._consumer_id = consumer_id
        self._lease_duration = lease_duration_seconds
        self._busy_timeout_ms = busy_timeout_ms
        self._clock = clock or _utc_now
        valid = (
            str(path) != ":memory:"
            and isinstance(consumer_id, str)
            and _CONSUMER_RE.fullmatch(consumer_id) is not None
            and type(lease_duration_seconds) is int
            and 1 <= lease_duration_seconds <= 300
            and type(busy_timeout_ms) is int
            and 1 <= busy_timeout_ms <= 60_000
            and callable(self._clock)
        )
        if not valid:
            raise SQLitePollingCheckpointError("polling checkpoint is invalid")
        try:
            self._initialize()
        except (OSError, sqlite3.DatabaseError):
            raise SQLitePollingCheckpointError(
                "polling checkpoint is invalid"
            ) from None

    @_stable_errors
    def acquire(
        self, owner_id: UUID, acquired_at: datetime
    ) -> PollingLease | None:
        if not isinstance(owner_id, UUID):
            raise SQLitePollingCheckpointError("polling checkpoint is invalid")
        try:
            _aware_utc(acquired_at)
            with self._transaction() as connection:
                row = self._select(connection)
                if row is None:
                    now = _aware_utc(self._clock())
                    offset = None
                    revision = 1
                else:
                    state = self._validate_row(row)
                    now = self._now_after(state.updated_at)
                    if state.lease is not None and state.lease.expires_at > now:
                        return None
                    offset = state.offset
                    revision = state.revision + 1
                lease = PollingLease(
                    lease_id=uuid4(),
                    owner_id=owner_id,
                    expires_at=now + timedelta(seconds=self._lease_duration),
                )
                self._write(
                    connection,
                    offset=offset,
                    lease=lease,
                    revision=revision,
                    updated_at=now,
                    insert=row is None,
                )
                return lease
        except SQLitePollingCheckpointError:
            raise
        except (OSError, sqlite3.DatabaseError, TypeError, ValueError):
            raise SQLitePollingCheckpointError(
                "polling checkpoint is invalid"
            ) from None

    @_stable_errors
    def load(self, lease: PollingLease) -> int | None:
        validated = _valid_lease(lease)
        try:
            with closing(self._connect()) as connection:
                row = self._select(connection)
                state = self._validate_row(row)
                now = self._now_after(state.updated_at)
                if state.lease != validated or now >= validated.expires_at:
                    raise ValueError("stale polling lease")
                return state.offset
        except (OSError, sqlite3.DatabaseError, TypeError, ValueError):
            raise SQLitePollingCheckpointError(
                "polling checkpoint is invalid"
            ) from None

    @_stable_errors
    def advance(
        self,
        *,
        lease: PollingLease,
        expected: int | None,
        next_offset: int,
    ) -> bool:
        validated = _valid_lease(lease)
        if (
            (expected is not None and not _non_negative_int(expected))
            or not _non_negative_int(next_offset)
            or (expected is not None and next_offset <= expected)
        ):
            raise SQLitePollingCheckpointError("polling checkpoint is invalid")
        try:
            with self._transaction() as connection:
                state = self._validate_row(self._select(connection))
                if state.lease != validated or state.offset != expected:
                    return False
                now = self._now_after(state.updated_at)
                if now >= validated.expires_at:
                    return False
                self._write(
                    connection,
                    offset=next_offset,
                    lease=validated,
                    revision=state.revision + 1,
                    updated_at=now,
                    insert=False,
                )
                return True
        except SQLitePollingCheckpointError:
            raise
        except (OSError, sqlite3.DatabaseError, TypeError, ValueError):
            raise SQLitePollingCheckpointError(
                "polling checkpoint is invalid"
            ) from None

    @_stable_errors
    def release(self, lease: PollingLease) -> bool:
        validated = _valid_lease(lease)
        try:
            with self._transaction() as connection:
                state = self._validate_row(self._select(connection))
                if state.lease != validated:
                    return False
                now = self._now_after(state.updated_at)
                self._write(
                    connection,
                    offset=state.offset,
                    lease=None,
                    revision=state.revision + 1,
                    updated_at=now,
                    insert=False,
                )
                return True
        except SQLitePollingCheckpointError:
            raise
        except (OSError, sqlite3.DatabaseError, TypeError, ValueError):
            raise SQLitePollingCheckpointError(
                "polling checkpoint is invalid"
            ) from None

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self._path,
            isolation_level=None,
            timeout=self._busy_timeout_ms / 1_000,
        )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
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
        with closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS telegram_polling_checkpoints (
                       consumer_id TEXT PRIMARY KEY,
                       offset INTEGER CHECK (offset IS NULL OR offset >= 0),
                       lease_id TEXT,
                       lease_owner TEXT,
                       lease_expires_at TEXT,
                       revision INTEGER NOT NULL CHECK (revision >= 1),
                       updated_at TEXT NOT NULL,
                       state_digest TEXT NOT NULL,
                       CHECK (
                           (lease_id IS NULL AND lease_owner IS NULL
                            AND lease_expires_at IS NULL)
                           OR
                           (lease_id IS NOT NULL AND lease_owner IS NOT NULL
                            AND lease_expires_at IS NOT NULL)
                       )
                   )"""
            )

    def _select(self, connection: sqlite3.Connection) -> sqlite3.Row | None:
        return connection.execute(
            """SELECT consumer_id, offset, lease_id, lease_owner,
                      lease_expires_at, revision, updated_at, state_digest
               FROM telegram_polling_checkpoints WHERE consumer_id = ?""",
            (self._consumer_id,),
        ).fetchone()

    def _validate_row(self, row: sqlite3.Row | None) -> "_PollingState":
        if row is None or row["consumer_id"] != self._consumer_id:
            raise ValueError("polling checkpoint is missing")
        offset = row["offset"]
        revision = row["revision"]
        if (
            (offset is not None and not _non_negative_int(offset))
            or type(revision) is not int
            or revision < 1
        ):
            raise ValueError("invalid polling checkpoint values")
        updated_at = _aware_utc(datetime.fromisoformat(row["updated_at"]))
        lease_values = (
            row["lease_id"],
            row["lease_owner"],
            row["lease_expires_at"],
        )
        if all(value is None for value in lease_values):
            lease = None
        elif all(isinstance(value, str) for value in lease_values):
            lease = PollingLease(
                lease_id=UUID(lease_values[0]),
                owner_id=UUID(lease_values[1]),
                expires_at=_aware_utc(datetime.fromisoformat(lease_values[2])),
            )
            lease_seconds = (lease.expires_at - updated_at).total_seconds()
            if not 0 < lease_seconds <= 300:
                raise ValueError("polling lease duration is invalid")
        else:
            raise ValueError("partial polling lease")
        expected = _state_digest(
            self._consumer_id, offset, lease, revision, updated_at
        )
        if row["state_digest"] != expected:
            raise ValueError("polling checkpoint digest mismatch")
        return _PollingState(offset, lease, revision, updated_at)

    def _write(
        self,
        connection: sqlite3.Connection,
        *,
        offset: int | None,
        lease: PollingLease | None,
        revision: int,
        updated_at: datetime,
        insert: bool,
    ) -> None:
        values = (
            offset,
            str(lease.lease_id) if lease else None,
            str(lease.owner_id) if lease else None,
            lease.expires_at.isoformat() if lease else None,
            revision,
            updated_at.isoformat(),
            _state_digest(self._consumer_id, offset, lease, revision, updated_at),
        )
        if insert:
            connection.execute(
                """INSERT INTO telegram_polling_checkpoints
                   (consumer_id, offset, lease_id, lease_owner,
                    lease_expires_at, revision, updated_at, state_digest)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (self._consumer_id, *values),
            )
        else:
            cursor = connection.execute(
                """UPDATE telegram_polling_checkpoints
                   SET offset = ?, lease_id = ?, lease_owner = ?,
                       lease_expires_at = ?, revision = ?, updated_at = ?,
                       state_digest = ?
                   WHERE consumer_id = ?""",
                (*values, self._consumer_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("polling checkpoint update failed")

    def _now_after(self, prior: datetime) -> datetime:
        try:
            now = _aware_utc(self._clock())
        except (TypeError, ValueError):
            raise SQLitePollingCheckpointError(
                "polling checkpoint is invalid"
            ) from None
        if now < prior:
            raise SQLitePollingCheckpointError(
                "polling checkpoint is invalid"
            )
        return now


class _PollingState:
    __slots__ = ("offset", "lease", "revision", "updated_at")

    def __init__(
        self,
        offset: int | None,
        lease: PollingLease | None,
        revision: int,
        updated_at: datetime,
    ) -> None:
        self.offset = offset
        self.lease = lease
        self.revision = revision
        self.updated_at = updated_at


def _valid_lease(value: object) -> PollingLease:
    if (
        not isinstance(value, PollingLease)
        or not isinstance(value.lease_id, UUID)
        or not isinstance(value.owner_id, UUID)
    ):
        raise SQLitePollingCheckpointError("polling checkpoint is invalid")
    try:
        expires_at = _aware_utc(value.expires_at)
    except (TypeError, ValueError):
        raise SQLitePollingCheckpointError(
            "polling checkpoint is invalid"
        ) from None
    return PollingLease(value.lease_id, value.owner_id, expires_at)


def _aware_utc(value: object) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _non_negative_int(value: object) -> bool:
    return type(value) is int and value >= 0


def _state_digest(
    consumer_id: str,
    offset: int | None,
    lease: PollingLease | None,
    revision: int,
    updated_at: datetime,
) -> str:
    return canonical_json_digest(
        {
            "consumer_id": consumer_id,
            "lease_expires_at": (
                lease.expires_at.isoformat() if lease else None
            ),
            "lease_id": str(lease.lease_id) if lease else None,
            "lease_owner": str(lease.owner_id) if lease else None,
            "offset": offset,
            "revision": revision,
            "updated_at": updated_at.isoformat(),
        }
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)
