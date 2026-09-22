"""Durable Telegram-to-Desktop correlation in the existing runtime database."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable, Mapping
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterator
from uuid import UUID

from src.application.durable_telegram_state import DpapiJsonCodec
from src.contracts.models import canonical_json_digest


class DesktopBridgeStateError(RuntimeError):
    """Stable bridge storage error without user content or local paths."""


class BridgeRequestStatus(str, Enum):
    RECEIVED = "received"
    NEEDS_TARGET = "needs_target"
    NEEDS_VOICE_CONFIRMATION = "needs_voice_confirmation"
    DISPATCHING = "dispatching"
    RUNNING = "running"
    WAITING_AUTHOR = "waiting_author"
    WAITING_OWNER = "waiting_owner"
    EXECUTION_COMPLETED = "execution_completed"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    WAITING_PC = "waiting_pc"
    UNKNOWN_DISPATCH = "unknown_dispatch"
    DELIVERY_PARTIAL = "delivery_partial"
    DELIVERY_UNKNOWN = "delivery_unknown"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InteractionKind(str, Enum):
    VOICE_CONFIRMATION = "voice_confirmation"
    QUESTION = "question"
    COMMAND_APPROVAL = "command_approval"
    FILE_APPROVAL = "file_approval"
    PERMISSIONS_APPROVAL = "permissions_approval"
    MCP_ELICITATION = "mcp_elicitation"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class BridgeRequest:
    request_id: UUID
    ingress_key: str
    tenant_id: str
    author_user_id: int
    author_identity: str
    chat_id: int
    topic_id: int | None
    source_message_id: int
    operation: str
    project_name: str | None
    desktop_thread_id: str | None
    desktop_turn_id: str | None
    client_message_id: str | None
    status: BridgeRequestStatus
    payload: Mapping[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PendingDesktopInteraction:
    interaction_id: str
    request_id: UUID
    kind: InteractionKind
    desktop_request_id: str
    desktop_turn_id: str
    target_user_id: int
    telegram_chat_id: int | None
    telegram_message_id: int | None
    generation: int
    payload: Mapping[str, Any]
    payload_digest: str
    expires_at: datetime
    status: str


@dataclass(frozen=True, slots=True)
class DeliveryClaim:
    operation_key: str
    request_id: UUID
    kind: str
    ordinal: int
    source_digest: str
    status: str
    telegram_message_id: int | None


_REQUEST_STATUSES = frozenset(item.value for item in BridgeRequestStatus)
_TERMINAL_REQUEST_STATUSES = frozenset(
    {
        BridgeRequestStatus.DELIVERED.value,
        BridgeRequestStatus.DELIVERY_PARTIAL.value,
        BridgeRequestStatus.FAILED.value,
        BridgeRequestStatus.CANCELLED.value,
    }
)
_OPERATIONS = frozenset({"create", "continue", "redeliver"})
_DELIVERY_KINDS = frozenset({"text", "artifact", "manifest"})
_INTERACTION_STATUSES = frozenset(
    {"pending", "answered", "expired", "superseded", "unknown"}
)
_THREAD_BLOCKING_STATUSES = (
    "received",
    "needs_voice_confirmation",
    "dispatching",
    "running",
    "waiting_author",
    "waiting_owner",
    "waiting_pc",
    "unknown_dispatch",
)


class SQLiteDesktopBridgeState:
    """Fail-closed M2 state sharing the established encrypted SQLite runtime."""

    def __init__(
        self,
        path: str | Path,
        *,
        encode: Callable[[Mapping[str, Any]], bytes] | None = None,
        decode: Callable[[bytes], dict[str, Any]] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        max_active_requests: int = 1_000,
        max_pending_interactions: int = 64,
        busy_timeout_ms: int = 5_000,
    ) -> None:
        if (
            str(path) == ":memory:"
            or type(max_active_requests) is not int
            or not 1 <= max_active_requests <= 100_000
            or type(max_pending_interactions) is not int
            or not 1 <= max_pending_interactions <= 1_024
            or type(busy_timeout_ms) is not int
            or not 1 <= busy_timeout_ms <= 60_000
        ):
            raise ValueError("desktop bridge state configuration is invalid")
        codec = DpapiJsonCodec()
        self._path = Path(path)
        self._encode = encode or codec.encode
        self._decode = decode or codec.decode
        self._clock = clock
        self._max_active_requests = max_active_requests
        self._max_pending_interactions = max_pending_interactions
        self._timeout = busy_timeout_ms
        try:
            self._initialize()
        except (OSError, sqlite3.DatabaseError):
            raise DesktopBridgeStateError("desktop_bridge_store_unavailable") from None

    def create_request(
        self,
        *,
        request_id: UUID,
        ingress_key: str,
        tenant_id: str,
        author_user_id: int,
        author_identity: str,
        chat_id: int,
        topic_id: int | None,
        source_message_id: int,
        operation: str,
        project_name: str | None,
        payload: Mapping[str, Any],
    ) -> BridgeRequest:
        values = {
            "request_id": str(request_id),
            "ingress_key": _digest(ingress_key),
            "tenant_id": _text(tenant_id, 128),
            "author_user_id": _positive_int(author_user_id),
            "author_identity": _text(author_identity, 256),
            "chat_id": _nonzero_int(chat_id),
            "topic_id": _optional_positive_int(topic_id),
            "source_message_id": _positive_int(source_message_id),
            "operation": operation,
            "project_name": _optional_text(project_name, 256),
        }
        if operation not in _OPERATIONS or not isinstance(payload, Mapping):
            raise ValueError("desktop bridge request is invalid")
        protected_payload = dict(payload)
        payload_digest = canonical_json_digest(protected_payload)
        encoded = self._encode(protected_payload)
        now = self._now()
        try:
            with self._transaction() as connection:
                row = connection.execute(
                    "SELECT * FROM desktop_bridge_requests WHERE ingress_key=?",
                    (values["ingress_key"],),
                ).fetchone()
                if row is None:
                    active = connection.execute(
                        """SELECT COUNT(*) FROM desktop_bridge_requests
                           WHERE status NOT IN (
                               'delivered','delivery_partial','failed','cancelled'
                           )"""
                    ).fetchone()[0]
                    if active >= self._max_active_requests:
                        raise DesktopBridgeStateError("desktop_bridge_queue_full")
                    connection.execute(
                        """INSERT INTO desktop_bridge_requests
                           (request_id,ingress_key,tenant_id,author_user_id,
                            author_identity,chat_id,topic_id,source_message_id,
                            operation,project_name,desktop_thread_id,desktop_turn_id,
                            client_message_id,status,payload_digest,payload,created_at,updated_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,NULL,NULL,NULL,?,?,?,?,?)""",
                        (
                            values["request_id"], values["ingress_key"], values["tenant_id"],
                            values["author_user_id"], values["author_identity"], values["chat_id"],
                            values["topic_id"], values["source_message_id"], values["operation"],
                            values["project_name"], BridgeRequestStatus.RECEIVED.value,
                            payload_digest, encoded, now.isoformat(), now.isoformat(),
                        ),
                    )
                    row = connection.execute(
                        "SELECT * FROM desktop_bridge_requests WHERE request_id=?",
                        (values["request_id"],),
                    ).fetchone()
                request = self._request_from_row(row)
                if (
                    request.request_id != request_id
                    or request.tenant_id != values["tenant_id"]
                    or request.author_user_id != author_user_id
                    or request.author_identity != values["author_identity"]
                    or request.chat_id != chat_id
                    or request.topic_id != topic_id
                    or request.source_message_id != source_message_id
                    or request.operation != operation
                    or request.project_name != values["project_name"]
                    or canonical_json_digest(request.payload) != payload_digest
                ):
                    raise DesktopBridgeStateError("desktop_bridge_ingress_conflict")
                return request
        except DesktopBridgeStateError:
            raise
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise DesktopBridgeStateError("desktop_bridge_store_unavailable") from None

    def read_request(self, request_id: UUID) -> BridgeRequest | None:
        if not isinstance(request_id, UUID):
            return None
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    "SELECT * FROM desktop_bridge_requests WHERE request_id=?",
                    (str(request_id),),
                ).fetchone()
                return None if row is None else self._request_from_row(row)
        except DesktopBridgeStateError:
            raise
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise DesktopBridgeStateError("desktop_bridge_store_unavailable") from None

    def list_requests(
        self, *, statuses: frozenset[BridgeRequestStatus]
    ) -> tuple[BridgeRequest, ...]:
        if not statuses:
            return ()
        placeholders = ",".join("?" for _ in statuses)
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    f"""SELECT * FROM desktop_bridge_requests
                        WHERE status IN ({placeholders}) ORDER BY created_at""",
                    tuple(item.value for item in statuses),
                ).fetchall()
                return tuple(self._request_from_row(row) for row in rows)
        except DesktopBridgeStateError:
            raise
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise DesktopBridgeStateError("desktop_bridge_store_unavailable") from None

    def latest_topic_request(
        self, *, chat_id: int, topic_id: int | None
    ) -> BridgeRequest | None:
        _nonzero_int(chat_id)
        _optional_positive_int(topic_id)
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    """SELECT * FROM desktop_bridge_requests
                       WHERE chat_id=? AND topic_id IS ? AND desktop_thread_id IS NOT NULL
                         AND status NOT IN ('failed','cancelled','unknown_dispatch')
                       ORDER BY created_at DESC LIMIT 1""",
                    (chat_id, topic_id),
                ).fetchone()
                return None if row is None else self._request_from_row(row)
        except DesktopBridgeStateError:
            raise
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise DesktopBridgeStateError("desktop_bridge_store_unavailable") from None

    def recent_author_request_count(
        self, *, author_user_id: int, since: datetime
    ) -> int:
        author = _positive_int(author_user_id)
        if not _aware(since):
            raise ValueError("desktop bridge request window is invalid")
        try:
            with closing(self._connect()) as connection:
                value = connection.execute(
                    """SELECT COUNT(*) FROM desktop_bridge_requests
                       WHERE author_user_id=? AND created_at>=?""",
                    (author, since.astimezone(UTC).isoformat()),
                ).fetchone()[0]
                return int(value)
        except (OSError, sqlite3.DatabaseError, TypeError, ValueError):
            raise DesktopBridgeStateError("desktop_bridge_store_unavailable") from None

    def has_prior_thread_request(self, request: BridgeRequest) -> bool:
        """Return whether an older request still owns this Desktop thread."""
        if not isinstance(request, BridgeRequest) or request.desktop_thread_id is None:
            return False
        placeholders = ",".join("?" for _ in _THREAD_BLOCKING_STATUSES)
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    f"""SELECT 1 FROM desktop_bridge_requests
                        WHERE desktop_thread_id=? AND request_id!=?
                          AND status IN ({placeholders})
                          AND (created_at<? OR (created_at=? AND request_id<?))
                        LIMIT 1""",
                    (
                        request.desktop_thread_id,
                        str(request.request_id),
                        *_THREAD_BLOCKING_STATUSES,
                        request.created_at.isoformat(),
                        request.created_at.isoformat(),
                        str(request.request_id),
                    ),
                ).fetchone()
                return row is not None
        except (OSError, sqlite3.DatabaseError):
            raise DesktopBridgeStateError("desktop_bridge_store_unavailable") from None

    def next_received_for_thread(self, thread_id: str) -> BridgeRequest | None:
        thread = _text(thread_id, 256)
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    """SELECT * FROM desktop_bridge_requests
                       WHERE desktop_thread_id=? AND status='received'
                       ORDER BY created_at,request_id LIMIT 1""",
                    (thread,),
                ).fetchone()
                return None if row is None else self._request_from_row(row)
        except DesktopBridgeStateError:
            raise
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise DesktopBridgeStateError("desktop_bridge_store_unavailable") from None

    def bind_desktop(
        self,
        request_id: UUID,
        *,
        thread_id: str,
        turn_id: str | None,
        client_message_id: str,
        status: BridgeRequestStatus,
    ) -> BridgeRequest:
        if not isinstance(request_id, UUID) or status.value not in _REQUEST_STATUSES:
            raise ValueError("desktop bridge binding is invalid")
        thread = _text(thread_id, 256)
        turn = _optional_text(turn_id, 256)
        message = _text(client_message_id, 256)
        now = self._now()
        try:
            with self._transaction() as connection:
                row = connection.execute(
                    "SELECT * FROM desktop_bridge_requests WHERE request_id=?",
                    (str(request_id),),
                ).fetchone()
                if row is None:
                    raise DesktopBridgeStateError("desktop_bridge_request_missing")
                current = self._request_from_row(row)
                if current.status.value in _TERMINAL_REQUEST_STATUSES:
                    raise DesktopBridgeStateError("desktop_bridge_request_terminal")
                if current.desktop_thread_id not in {None, thread}:
                    raise DesktopBridgeStateError("desktop_bridge_thread_conflict")
                if current.desktop_turn_id not in {None, turn}:
                    raise DesktopBridgeStateError("desktop_bridge_turn_conflict")
                if current.client_message_id not in {None, message}:
                    raise DesktopBridgeStateError("desktop_bridge_message_conflict")
                connection.execute(
                    """UPDATE desktop_bridge_requests
                       SET desktop_thread_id=?,desktop_turn_id=?,client_message_id=?,
                           status=?,updated_at=? WHERE request_id=?""",
                    (thread, turn, message, status.value, now.isoformat(), str(request_id)),
                )
                updated = connection.execute(
                    "SELECT * FROM desktop_bridge_requests WHERE request_id=?",
                    (str(request_id),),
                ).fetchone()
                return self._request_from_row(updated)
        except DesktopBridgeStateError:
            raise
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise DesktopBridgeStateError("desktop_bridge_store_unavailable") from None

    def transition(
        self,
        request_id: UUID,
        *,
        expected: frozenset[BridgeRequestStatus],
        status: BridgeRequestStatus,
    ) -> bool:
        if not isinstance(request_id, UUID) or not expected:
            return False
        now = self._now().isoformat()
        placeholders = ",".join("?" for _ in expected)
        try:
            with self._transaction() as connection:
                cursor = connection.execute(
                    f"""UPDATE desktop_bridge_requests SET status=?,updated_at=?
                        WHERE request_id=? AND status IN ({placeholders})""",
                    (status.value, now, str(request_id), *(item.value for item in expected)),
                )
                return cursor.rowcount == 1
        except (OSError, sqlite3.DatabaseError):
            raise DesktopBridgeStateError("desktop_bridge_store_unavailable") from None

    def put_interaction(
        self,
        *,
        interaction_id: str,
        request_id: UUID,
        kind: InteractionKind,
        desktop_request_id: str | int,
        desktop_turn_id: str,
        target_user_id: int,
        generation: int,
        payload: Mapping[str, Any],
        expires_at: datetime,
    ) -> PendingDesktopInteraction:
        identifier = _text(interaction_id, 256)
        desktop_identifier = _text(str(desktop_request_id), 256)
        turn = _text(desktop_turn_id, 256)
        target = _positive_int(target_user_id)
        if (
            not isinstance(request_id, UUID)
            or not isinstance(kind, InteractionKind)
            or type(generation) is not int
            or generation < 1
            or not isinstance(payload, Mapping)
            or not _aware(expires_at)
            or expires_at <= self._now()
        ):
            raise ValueError("desktop interaction is invalid")
        protected = dict(payload)
        digest = canonical_json_digest(protected)
        encoded = self._encode(protected)
        now = self._now().isoformat()
        try:
            with self._transaction() as connection:
                row = connection.execute(
                    "SELECT * FROM desktop_bridge_interactions WHERE interaction_id=?",
                    (identifier,),
                ).fetchone()
                if row is None:
                    pending = connection.execute(
                        """SELECT COUNT(*) FROM desktop_bridge_interactions
                           WHERE request_id=? AND status='pending'""",
                        (str(request_id),),
                    ).fetchone()[0]
                    if pending >= self._max_pending_interactions:
                        raise DesktopBridgeStateError(
                            "desktop_bridge_interaction_capacity"
                        )
                    connection.execute(
                        """INSERT INTO desktop_bridge_interactions
                       (interaction_id,request_id,kind,desktop_request_id,
                        desktop_turn_id,target_user_id,telegram_message_id,
                        connection_generation,payload_digest,payload,expires_at,
                        status,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,NULL,?,?,?,?,?,?,?)""",
                        (
                            identifier, str(request_id), kind.value,
                            desktop_identifier, turn, target, generation, digest,
                            encoded, expires_at.astimezone(UTC).isoformat(),
                            "pending", now, now,
                        ),
                    )
                    row = connection.execute(
                        """SELECT * FROM desktop_bridge_interactions
                           WHERE interaction_id=?""",
                        (identifier,),
                    ).fetchone()
                interaction = self._interaction_from_row(row)
                if (
                    interaction.request_id != request_id
                    or interaction.kind is not kind
                    or interaction.desktop_request_id != desktop_identifier
                    or interaction.desktop_turn_id != turn
                    or interaction.target_user_id != target
                    or interaction.generation != generation
                    or interaction.payload_digest != digest
                ):
                    raise DesktopBridgeStateError("desktop_bridge_interaction_conflict")
                return interaction
        except DesktopBridgeStateError:
            raise
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise DesktopBridgeStateError("desktop_bridge_store_unavailable") from None

    def bind_interaction_message(
        self,
        interaction_id: str,
        *,
        telegram_chat_id: int,
        telegram_message_id: int,
    ) -> bool:
        identifier = _text(interaction_id, 256)
        chat_id = _nonzero_int(telegram_chat_id)
        message_id = _positive_int(telegram_message_id)
        try:
            with self._transaction() as connection:
                row = connection.execute(
                    """SELECT telegram_chat_id,telegram_message_id,status
                       FROM desktop_bridge_interactions WHERE interaction_id=?""",
                    (identifier,),
                ).fetchone()
                if row is None or row["status"] != "pending":
                    return False
                if (
                    row["telegram_chat_id"] not in {None, chat_id}
                    or row["telegram_message_id"] not in {None, message_id}
                ):
                    raise DesktopBridgeStateError("desktop_bridge_interaction_conflict")
                connection.execute(
                    """UPDATE desktop_bridge_interactions
                       SET telegram_chat_id=?,telegram_message_id=?,updated_at=?
                       WHERE interaction_id=?""",
                    (chat_id, message_id, self._now().isoformat(), identifier),
                )
                return True
        except DesktopBridgeStateError:
            raise
        except (OSError, sqlite3.DatabaseError):
            raise DesktopBridgeStateError("desktop_bridge_store_unavailable") from None

    def pending_interaction_for_reply(
        self, *, chat_id: int, telegram_message_id: int
    ) -> PendingDesktopInteraction | None:
        _nonzero_int(chat_id)
        _positive_int(telegram_message_id)
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    """SELECT * FROM desktop_bridge_interactions
                       WHERE telegram_chat_id=? AND telegram_message_id=?
                         AND status='pending'""",
                    (chat_id, telegram_message_id),
                ).fetchone()
                if row is None:
                    return None
                interaction = self._interaction_from_row(row)
                if interaction.expires_at <= self._now():
                    return None
                return interaction
        except DesktopBridgeStateError:
            raise
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise DesktopBridgeStateError("desktop_bridge_store_unavailable") from None

    def resolve_interaction(
        self, interaction_id: str, *, responder_user_id: int
    ) -> bool:
        identifier = _text(interaction_id, 256)
        responder = _positive_int(responder_user_id)
        now = self._now().isoformat()
        try:
            with self._transaction() as connection:
                cursor = connection.execute(
                    """UPDATE desktop_bridge_interactions SET status='answered',updated_at=?
                       WHERE interaction_id=? AND target_user_id=? AND status='pending'
                         AND expires_at>?""",
                    (now, identifier, responder, now),
                )
                return cursor.rowcount == 1
        except (OSError, sqlite3.DatabaseError):
            raise DesktopBridgeStateError("desktop_bridge_store_unavailable") from None

    def close_interaction(self, interaction_id: str, *, status: str) -> bool:
        identifier = _text(interaction_id, 256)
        if status not in {"expired", "superseded", "unknown"}:
            raise ValueError("desktop interaction close status is invalid")
        try:
            with self._transaction() as connection:
                cursor = connection.execute(
                    """UPDATE desktop_bridge_interactions SET status=?,updated_at=?
                       WHERE interaction_id=? AND status='pending'""",
                    (status, self._now().isoformat(), identifier),
                )
                return cursor.rowcount == 1
        except (OSError, sqlite3.DatabaseError):
            raise DesktopBridgeStateError("desktop_bridge_store_unavailable") from None

    def expire_interactions(self) -> tuple[PendingDesktopInteraction, ...]:
        """Atomically close overdue prompts and stop their bridge requests.

        The corresponding Desktop turn is deliberately not cancelled or answered:
        it remains visible to the owner in Desktop.  Marking the bridge request as
        failed prevents a late Telegram reply or a restart from making an approval
        decision after its validity window.
        """
        now = self._now().isoformat()
        try:
            with self._transaction() as connection:
                rows = connection.execute(
                    """SELECT * FROM desktop_bridge_interactions
                       WHERE status='pending' AND expires_at<=?
                       ORDER BY created_at,interaction_id""",
                    (now,),
                ).fetchall()
                if not rows:
                    return ()
                interactions = tuple(self._interaction_from_row(row) for row in rows)
                identifiers = tuple(item.interaction_id for item in interactions)
                placeholders = ",".join("?" for _ in identifiers)
                connection.execute(
                    f"""UPDATE desktop_bridge_interactions
                        SET status='expired',updated_at=?
                        WHERE interaction_id IN ({placeholders}) AND status='pending'""",
                    (now, *identifiers),
                )
                request_ids = tuple(dict.fromkeys(str(item.request_id) for item in interactions))
                request_placeholders = ",".join("?" for _ in request_ids)
                connection.execute(
                    f"""UPDATE desktop_bridge_requests
                        SET status='failed',updated_at=?
                        WHERE request_id IN ({request_placeholders})
                          AND status IN ('needs_voice_confirmation','waiting_author','waiting_owner')""",
                    (now, *request_ids),
                )
                return interactions
        except DesktopBridgeStateError:
            raise
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise DesktopBridgeStateError("desktop_bridge_store_unavailable") from None

    def claim_delivery(
        self,
        *,
        request_id: UUID,
        kind: str,
        ordinal: int,
        source_digest: str,
        destination_ref: str,
        payload: Mapping[str, Any],
    ) -> DeliveryClaim:
        if (
            not isinstance(request_id, UUID)
            or kind not in _DELIVERY_KINDS
            or type(ordinal) is not int
            or ordinal < 0
            or not isinstance(payload, Mapping)
        ):
            raise ValueError("desktop delivery is invalid")
        digest = _digest(source_digest)
        destination = _text(destination_ref, 512)
        operation_key = canonical_json_digest(
            {
                "schema": "nobus-desktop-delivery-v1",
                "request_id": str(request_id),
                "kind": kind,
                "ordinal": ordinal,
                "source_digest": digest,
                "destination_ref": destination,
            }
        )
        protected = dict(payload)
        payload_digest = canonical_json_digest(protected)
        encoded = self._encode(protected)
        now = self._now().isoformat()
        try:
            with self._transaction() as connection:
                inserted = connection.execute(
                    """INSERT INTO desktop_bridge_deliveries
                       (operation_key,request_id,kind,ordinal,source_digest,
                        destination_ref,payload_digest,payload,status,
                        telegram_message_id,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,NULL,?,?)
                       ON CONFLICT(operation_key) DO NOTHING""",
                    (
                        operation_key, str(request_id), kind, ordinal, digest,
                        destination, payload_digest, encoded, "claimed", now, now,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM desktop_bridge_deliveries WHERE operation_key=?",
                    (operation_key,),
                ).fetchone()
                if row["payload_digest"] != payload_digest:
                    raise DesktopBridgeStateError("desktop_bridge_delivery_conflict")
                if inserted.rowcount == 0 and row["status"] == "claimed":
                    connection.execute(
                        """UPDATE desktop_bridge_deliveries
                           SET status='unknown',updated_at=?
                           WHERE operation_key=? AND status='claimed'""",
                        (now, operation_key),
                    )
                    row = connection.execute(
                        "SELECT * FROM desktop_bridge_deliveries WHERE operation_key=?",
                        (operation_key,),
                    ).fetchone()
                elif inserted.rowcount == 0 and row["status"] == "failed":
                    connection.execute(
                        """UPDATE desktop_bridge_deliveries
                           SET status='claimed',updated_at=?
                           WHERE operation_key=? AND status='failed'""",
                        (now, operation_key),
                    )
                    row = connection.execute(
                        "SELECT * FROM desktop_bridge_deliveries WHERE operation_key=?",
                        (operation_key,),
                    ).fetchone()
                return self._delivery_from_row(row)
        except DesktopBridgeStateError:
            raise
        except (OSError, sqlite3.DatabaseError, ValueError, TypeError):
            raise DesktopBridgeStateError("desktop_bridge_store_unavailable") from None

    def finish_delivery(
        self,
        operation_key: str,
        *,
        telegram_message_id: int | None,
        status: str,
    ) -> bool:
        key = _digest(operation_key)
        if status not in {"sent", "unknown", "failed"}:
            raise ValueError("desktop delivery status is invalid")
        if status == "sent":
            message_id = _positive_int(telegram_message_id)
        elif telegram_message_id is not None:
            raise ValueError("non-sent delivery cannot have a Telegram receipt")
        else:
            message_id = None
        try:
            with self._transaction() as connection:
                cursor = connection.execute(
                    """UPDATE desktop_bridge_deliveries
                       SET status=?,telegram_message_id=?,updated_at=?
                       WHERE operation_key=? AND status='claimed'""",
                    (status, message_id, self._now().isoformat(), key),
                )
                if cursor.rowcount == 1:
                    return True
                row = connection.execute(
                    "SELECT status,telegram_message_id FROM desktop_bridge_deliveries WHERE operation_key=?",
                    (key,),
                ).fetchone()
                return bool(row is not None and row["status"] == status and row["telegram_message_id"] == message_id)
        except (OSError, sqlite3.DatabaseError):
            raise DesktopBridgeStateError("desktop_bridge_store_unavailable") from None

    def _request_from_row(self, row: sqlite3.Row) -> BridgeRequest:
        payload = self._decode(bytes(row["payload"]))
        if canonical_json_digest(payload) != row["payload_digest"]:
            raise DesktopBridgeStateError("desktop_bridge_payload_tampered")
        return BridgeRequest(
            request_id=UUID(row["request_id"]), ingress_key=row["ingress_key"],
            tenant_id=row["tenant_id"], author_user_id=row["author_user_id"],
            author_identity=row["author_identity"], chat_id=row["chat_id"],
            topic_id=row["topic_id"], source_message_id=row["source_message_id"],
            operation=row["operation"], project_name=row["project_name"],
            desktop_thread_id=row["desktop_thread_id"], desktop_turn_id=row["desktop_turn_id"],
            client_message_id=row["client_message_id"], status=BridgeRequestStatus(row["status"]),
            payload=payload, created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _interaction_from_row(self, row: sqlite3.Row) -> PendingDesktopInteraction:
        payload = self._decode(bytes(row["payload"]))
        if canonical_json_digest(payload) != row["payload_digest"]:
            raise DesktopBridgeStateError("desktop_bridge_payload_tampered")
        return PendingDesktopInteraction(
            interaction_id=row["interaction_id"], request_id=UUID(row["request_id"]),
            kind=InteractionKind(row["kind"]), desktop_request_id=row["desktop_request_id"],
            desktop_turn_id=row["desktop_turn_id"], target_user_id=row["target_user_id"],
            telegram_chat_id=row["telegram_chat_id"],
            telegram_message_id=row["telegram_message_id"], generation=row["connection_generation"],
            payload=payload, payload_digest=row["payload_digest"],
            expires_at=datetime.fromisoformat(row["expires_at"]), status=row["status"],
        )

    @staticmethod
    def _delivery_from_row(row: sqlite3.Row) -> DeliveryClaim:
        return DeliveryClaim(
            operation_key=row["operation_key"], request_id=UUID(row["request_id"]),
            kind=row["kind"], ordinal=row["ordinal"], source_digest=row["source_digest"],
            status=row["status"], telegram_message_id=row["telegram_message_id"],
        )

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

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, isolation_level=None, timeout=self._timeout / 1_000)
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout={self._timeout}")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA secure_delete=ON")
        return connection

    def _initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS desktop_bridge_requests (
                    request_id TEXT PRIMARY KEY,
                    ingress_key TEXT NOT NULL UNIQUE,
                    tenant_id TEXT NOT NULL,
                    author_user_id INTEGER NOT NULL CHECK(author_user_id>0),
                    author_identity TEXT NOT NULL,
                    chat_id INTEGER NOT NULL CHECK(chat_id!=0),
                    topic_id INTEGER CHECK(topic_id>0),
                    source_message_id INTEGER NOT NULL CHECK(source_message_id>0),
                    operation TEXT NOT NULL CHECK(operation IN ('create','continue','redeliver')),
                    project_name TEXT,
                    desktop_thread_id TEXT,
                    desktop_turn_id TEXT,
                    client_message_id TEXT,
                    status TEXT NOT NULL CHECK(status IN (
                        'received','needs_target','needs_voice_confirmation','dispatching','running',
                        'waiting_author','waiting_owner','execution_completed','delivering','delivered',
                        'waiting_pc','unknown_dispatch','delivery_partial','delivery_unknown','failed','cancelled'
                    )),
                    payload_digest TEXT NOT NULL,
                    payload BLOB NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_desktop_bridge_requests_status
                    ON desktop_bridge_requests(status,created_at);
                CREATE INDEX IF NOT EXISTS idx_desktop_bridge_requests_topic
                    ON desktop_bridge_requests(chat_id,topic_id,created_at);
                CREATE TABLE IF NOT EXISTS desktop_bridge_interactions (
                    interaction_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL REFERENCES desktop_bridge_requests(request_id),
                    kind TEXT NOT NULL CHECK(kind IN (
                        'voice_confirmation','question','command_approval','file_approval','permissions_approval','mcp_elicitation','unknown'
                    )),
                    desktop_request_id TEXT NOT NULL,
                    desktop_turn_id TEXT NOT NULL,
                    target_user_id INTEGER NOT NULL CHECK(target_user_id>0),
                    telegram_chat_id INTEGER CHECK(telegram_chat_id!=0),
                    telegram_message_id INTEGER CHECK(telegram_message_id>0),
                    connection_generation INTEGER NOT NULL CHECK(connection_generation>0),
                    payload_digest TEXT NOT NULL,
                    payload BLOB NOT NULL,
                    expires_at TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending','answered','expired','superseded','unknown')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_desktop_bridge_interaction_pending
                    ON desktop_bridge_interactions(status,expires_at);
                CREATE TABLE IF NOT EXISTS desktop_bridge_deliveries (
                    operation_key TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL REFERENCES desktop_bridge_requests(request_id),
                    kind TEXT NOT NULL CHECK(kind IN ('text','artifact','manifest')),
                    ordinal INTEGER NOT NULL CHECK(ordinal>=0),
                    source_digest TEXT NOT NULL,
                    destination_ref TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    payload BLOB NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('claimed','sent','unknown','failed')),
                    telegram_message_id INTEGER CHECK(telegram_message_id>0),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(request_id,kind,ordinal)
                );
                CREATE INDEX IF NOT EXISTS idx_desktop_bridge_delivery_status
                    ON desktop_bridge_deliveries(status,created_at);
                """
            )
            columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(desktop_bridge_interactions)"
                )
            }
            if "telegram_chat_id" not in columns:
                connection.execute(
                    """ALTER TABLE desktop_bridge_interactions
                       ADD COLUMN telegram_chat_id INTEGER
                       CHECK(telegram_chat_id!=0)"""
                )
            connection.execute(
                "DROP INDEX IF EXISTS idx_desktop_bridge_interaction_message"
            )
            connection.execute(
                """CREATE UNIQUE INDEX idx_desktop_bridge_interaction_message
                   ON desktop_bridge_interactions(
                       telegram_chat_id,telegram_message_id
                   )
                   WHERE telegram_chat_id IS NOT NULL
                     AND telegram_message_id IS NOT NULL"""
            )

    def _now(self) -> datetime:
        value = self._clock()
        if not _aware(value):
            raise DesktopBridgeStateError("desktop_bridge_clock_unavailable")
        return value.astimezone(UTC)


def _text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid text")
    normalized = value.strip()
    if not normalized or len(normalized) > limit or "\x00" in normalized:
        raise ValueError("invalid text")
    return normalized


def _optional_text(value: object, limit: int) -> str | None:
    return None if value is None else _text(value, limit)


def _digest(value: object) -> str:
    normalized = _text(value, 71)
    if len(normalized) != 71 or not normalized.startswith("sha256:") or any(
        character not in "0123456789abcdef" for character in normalized[7:]
    ):
        raise ValueError("invalid digest")
    return normalized


def _positive_int(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError("invalid positive integer")
    return value


def _nonzero_int(value: object) -> int:
    if type(value) is not int or value == 0:
        raise ValueError("invalid non-zero integer")
    return value


def _optional_positive_int(value: object) -> int | None:
    return None if value is None else _positive_int(value)


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None
