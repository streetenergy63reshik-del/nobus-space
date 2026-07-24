"""Encrypted owner-only index for Telegram business-note topics."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Callable, Mapping
from contextlib import closing
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.application.durable_telegram_state import DpapiJsonCodec
from src.transport.telegram import TextMessage


_MOSCOW = timezone(timedelta(hours=3), "MSK")
_MAX_NOTES = 50_000
_TASK_HINT = re.compile(
    r"\b(?:нужно|надо|сделать|позвон\w*|провер\w*|подготов\w*|"
    r"отправ\w*|созда\w*|перенес\w*|перенести|запис\w*|купить|"
    r"согласова\w*|задач\w*|срок\w*)\b",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"(?:^|(?<=[.!?]))\s+|\n+")


class BusinessNotesError(RuntimeError):
    """Stable Notes failure without note text or local paths."""


class BusinessNote(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    tenant_id: str = Field(min_length=1, max_length=128)
    chat_id: int = Field(lt=0)
    thread_id: int | None = Field(default=None, gt=0)
    message_id: int = Field(gt=0)
    update_id: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=4_096)
    created_at: datetime

    @field_validator("tenant_id", "text")
    @classmethod
    def canonical_text(cls, value: str) -> str:
        normalized = value.strip()
        if normalized != value or "\x00" in value:
            raise ValueError("note text is not canonical")
        return value

    @field_validator("created_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("note timestamp must be timezone-aware")
        return value.astimezone(UTC)


class SQLiteBusinessNotes:
    """Store encrypted note bodies with exact tenant/chat/topic binding."""

    def __init__(
        self,
        path: str | Path,
        *,
        encode: Callable[[Mapping[str, object]], bytes] | None = None,
        decode: Callable[[bytes], dict[str, object]] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        max_notes: int = _MAX_NOTES,
    ) -> None:
        if (
            str(path) == ":memory:"
            or type(max_notes) is not int
            or not 1 <= max_notes <= 100_000
        ):
            raise ValueError("business Notes configuration is invalid")
        codec = DpapiJsonCodec()
        self._path = Path(path)
        self._encode = encode or codec.encode
        self._decode = decode or codec.decode
        self._clock = clock
        self._max_notes = max_notes
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with closing(self._connect()) as connection:
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS business_notes(
                           tenant_id TEXT NOT NULL,
                           chat_id INTEGER NOT NULL,
                           thread_id INTEGER NOT NULL,
                           message_id INTEGER NOT NULL,
                           update_id INTEGER NOT NULL,
                           payload BLOB NOT NULL,
                           payload_digest TEXT NOT NULL,
                           created_at TEXT NOT NULL,
                           PRIMARY KEY(tenant_id,chat_id,message_id),
                           UNIQUE(tenant_id,chat_id,update_id)
                       ) WITHOUT ROWID"""
                )
                connection.execute(
                    """CREATE INDEX IF NOT EXISTS idx_business_notes_topic
                       ON business_notes(
                           tenant_id,chat_id,thread_id,created_at
                       )"""
                )
                _validate_schema(connection)
        except (OSError, sqlite3.DatabaseError):
            raise BusinessNotesError("business_notes_store_unavailable") from None

    @property
    def path(self) -> Path:
        return self._path

    def append(self, message: TextMessage) -> bool:
        if (
            not isinstance(message, TextMessage)
            or message.binding_purpose != "business_notes"
            or message.chat_id >= 0
        ):
            raise ValueError("business note binding is invalid")
        created_at = self._clock()
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("business note clock is invalid")
        note = BusinessNote(
            tenant_id=message.tenant_id,
            chat_id=message.chat_id,
            thread_id=message.message_thread_id,
            message_id=message.message_id,
            update_id=message.update_id,
            text=message.text,
            created_at=created_at,
        )
        payload = note.model_dump(mode="json")
        protected = self._encode(payload)
        digest = _protected_digest(protected)
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                count = connection.execute(
                    "SELECT COUNT(*) FROM business_notes"
                ).fetchone()[0]
                existing = connection.execute(
                    """SELECT tenant_id,chat_id,thread_id,message_id,
                              update_id,payload,payload_digest,created_at
                       FROM business_notes
                       WHERE tenant_id=? AND chat_id=?
                         AND (message_id=? OR update_id=?)""",
                    (
                        note.tenant_id,
                        note.chat_id,
                        note.message_id,
                        note.update_id,
                    ),
                ).fetchone()
                if existing is not None:
                    stored = self._decode_row(existing)
                    if stored.model_dump(
                        mode="json", exclude={"created_at"}
                    ) != note.model_dump(
                        mode="json", exclude={"created_at"}
                    ):
                        raise BusinessNotesError(
                            "business_notes_binding_conflict"
                        )
                    connection.commit()
                    return False
                if count >= self._max_notes:
                    raise BusinessNotesError("business_notes_capacity_exceeded")
                connection.execute(
                    """INSERT INTO business_notes(
                           tenant_id,chat_id,thread_id,message_id,update_id,
                           payload,payload_digest,created_at
                       ) VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        note.tenant_id,
                        note.chat_id,
                        note.thread_id or 0,
                        note.message_id,
                        note.update_id,
                        protected,
                        digest,
                        note.created_at.isoformat(),
                    ),
                )
                connection.commit()
            return True
        except BusinessNotesError:
            raise
        except (OSError, sqlite3.DatabaseError, TypeError, ValueError):
            raise BusinessNotesError("business_notes_store_unavailable") from None

    def recent(
        self,
        *,
        tenant_id: str,
        chat_id: int,
        thread_id: int | None,
        limit: int = 200,
        since: datetime | None = None,
    ) -> tuple[BusinessNote, ...]:
        if (
            not isinstance(tenant_id, str)
            or not tenant_id.strip()
            or type(chat_id) is not int
            or chat_id >= 0
            or (thread_id is not None and (
                type(thread_id) is not int or thread_id <= 0
            ))
            or type(limit) is not int
            or not 1 <= limit <= 500
            or (
                since is not None
                and (since.tzinfo is None or since.utcoffset() is None)
            )
        ):
            raise ValueError("business Notes query is invalid")
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    """SELECT tenant_id,chat_id,thread_id,message_id,
                              update_id,payload,payload_digest,created_at
                       FROM business_notes
                       WHERE tenant_id=? AND chat_id=? AND thread_id=?
                       ORDER BY created_at DESC, message_id DESC
                       LIMIT ?""",
                    (tenant_id.strip(), chat_id, thread_id or 0, limit),
                ).fetchall()
            notes = [self._decode_row(row) for row in rows]
            if since is not None:
                threshold = since.astimezone(UTC)
                notes = [
                    note for note in notes
                    if note.created_at >= threshold
                ]
            notes.sort(key=lambda note: (note.created_at, note.message_id))
            return tuple(notes)
        except BusinessNotesError:
            raise
        except (OSError, sqlite3.DatabaseError, TypeError, ValueError):
            raise BusinessNotesError("business_notes_store_unavailable") from None

    def _decode_row(self, row: sqlite3.Row) -> BusinessNote:
        try:
            protected = bytes(row["payload"])
            if _protected_digest(protected) != row["payload_digest"]:
                raise BusinessNotesError("business_notes_payload_tampered")
            payload = self._decode(protected)
            note = BusinessNote.model_validate_json(
                json.dumps(payload, ensure_ascii=False)
            )
            created_at = datetime.fromisoformat(row["created_at"])
            if (
                created_at.tzinfo is None
                or created_at.utcoffset() is None
                or note.tenant_id != row["tenant_id"]
                or note.chat_id != row["chat_id"]
                or (note.thread_id or 0) != row["thread_id"]
                or note.message_id != row["message_id"]
                or note.update_id != row["update_id"]
                or note.created_at != created_at.astimezone(UTC)
            ):
                raise BusinessNotesError("business_notes_binding_conflict")
            return note
        except BusinessNotesError:
            raise
        except (TypeError, ValueError):
            raise BusinessNotesError(
                "business_notes_payload_tampered"
            ) from None

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        return connection


def _protected_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _validate_schema(connection: sqlite3.Connection) -> None:
    from src.application.runtime_maintenance import EXPECTED_SCHEMA_DIGESTS

    actual = {
        f"{row['type']}:{row['name']}": _ddl_digest(str(row["sql"] or ""))
        for row in connection.execute(
            """SELECT type,name,sql FROM sqlite_master
               WHERE name NOT LIKE 'sqlite_%'"""
        )
    }
    if actual != EXPECTED_SCHEMA_DIGESTS["business-notes.sqlite3"]:
        raise BusinessNotesError("business_notes_store_unavailable")


def _ddl_digest(sql: str) -> str:
    normalized = re.sub(r"\s+", " ", sql.strip()).casefold()
    return hashlib.sha256(normalized.encode()).hexdigest()


class BusinessNotesService:
    """Index owner notes and prepare local extractive summaries."""

    def __init__(
        self,
        store: SQLiteBusinessNotes,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(_MOSCOW),
    ) -> None:
        if not isinstance(store, SQLiteBusinessNotes) or not callable(clock):
            raise ValueError("business Notes service is invalid")
        self._store = store
        self._clock = clock

    def handle_text(self, message: TextMessage) -> str | None:
        if (
            not isinstance(message, TextMessage)
            or message.binding_purpose != "business_notes"
        ):
            raise ValueError("business note message is invalid")
        intent = _notes_intent(message.text)
        if intent == "summary":
            return self._summary(message, tasks_only=False)
        if intent == "tasks":
            return self._summary(message, tasks_only=True)
        self._store.append(message)
        return None

    def _summary(self, message: TextMessage, *, tasks_only: bool) -> str:
        since: datetime | None = None
        if "сегодня" in message.text.casefold():
            now = self._clock()
            if now.tzinfo is None or now.utcoffset() is None:
                raise ValueError("business Notes clock is invalid")
            now = now.astimezone(_MOSCOW)
            since = now.replace(hour=0, minute=0, second=0, microsecond=0)
        notes = self._store.recent(
            tenant_id=message.tenant_id,
            chat_id=message.chat_id,
            thread_id=message.message_thread_id,
            since=since,
        )
        sentences = _unique_sentences(notes)
        if tasks_only:
            sentences = tuple(item for item in sentences if _TASK_HINT.search(item))
            title = "Задачи по теме"
            empty = "Явных задач в заметках темы не найдено."
        else:
            title = "Резюме темы"
            empty = "В этой теме пока нет заметок для резюме."
        if not sentences:
            return empty
        selected = sentences[-20:] if tasks_only else sentences[-12:]
        return _bounded_summary(title, selected)


def _notes_intent(text: str) -> str | None:
    normalized = " ".join(text.casefold().split())
    command = normalized.split(maxsplit=1)[0]
    if command == "/summary":
        return "summary"
    if command == "/tasks":
        return "tasks"
    explicitly_targets_notes = (
        "замет" in normalized or "из чата" in normalized
    )
    if (
        explicitly_targets_notes
        and normalized.startswith("собери")
        and "резюм" in normalized
    ):
        return "summary"
    if (
        explicitly_targets_notes
        and normalized.startswith("собери")
        and "задач" in normalized
    ):
        return "tasks"
    return None


def _bounded_summary(
    title: str,
    sentences: tuple[str, ...],
    *,
    limit: int = 3_500,
) -> str:
    lines: list[str] = []
    size = len(title) + 2
    for sentence in sentences:
        available = limit - size - (1 if lines else 0)
        if available <= 2:
            break
        line = f"• {sentence}"
        if len(line) > available:
            line = line[: available - 1].rstrip() + "…"
        lines.append(line)
        size += len(line) + (1 if len(lines) > 1 else 0)
    return f"{title}\n\n" + "\n".join(lines)


def _unique_sentences(notes: tuple[BusinessNote, ...]) -> tuple[str, ...]:
    values: list[str] = []
    seen: set[str] = set()
    for note in notes:
        for raw in _SENTENCE.split(note.text):
            value = raw.strip(" \t\r\n•-")
            key = value.casefold()
            if not value or key in seen:
                continue
            seen.add(key)
            values.append(value)
    return tuple(values)
