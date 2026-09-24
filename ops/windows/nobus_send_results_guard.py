"""Fail-closed ownership check for the existing nobus-send-results sender.

The sender runs inside a Codex turn.  Bridge turns belong to the Telegram
bridge and must not invoke the global skill as a second delivery path.  This
module reads only the already configured notifier's bridge-state pointer and
the existing SQLite request table; it never sends or edits anything.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID


_OWNED_STATUSES = (
    "received", "dispatching", "running", "waiting_author", "waiting_owner",
    "waiting_pc", "execution_completed", "delivering", "delivery_partial",
    "delivery_unknown", "unknown_dispatch",
)


class DeliveryOwnerGuardError(RuntimeError):
    """A send cannot be safely attributed to the independent skill."""


def assert_skill_delivery_allowed(
    *, settings_path: Path, codex_thread_id: str | None,
) -> None:
    """Reject an active bridge turn or an unbound create bootstrap.

    Absent bridge configuration leaves the legacy skill unchanged.  Once a
    bridge-state pointer is configured, unreadable or malformed state blocks
    sends instead of guessing that no bridge owns the turn.
    """
    try:
        settings = json.loads(Path(settings_path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DeliveryOwnerGuardError("bridge_owner_settings_unavailable") from exc
    if not isinstance(settings, dict):
        raise DeliveryOwnerGuardError("bridge_owner_settings_invalid")
    raw_path = settings.get("bridge_state_path")
    if raw_path is None:
        return
    if codex_thread_id is None:
        raise DeliveryOwnerGuardError("codex_thread_identity_missing")
    try:
        thread_id = str(UUID(codex_thread_id))
    except (TypeError, ValueError) as exc:
        raise DeliveryOwnerGuardError("codex_thread_identity_invalid") from exc
    if not isinstance(raw_path, str):
        raise DeliveryOwnerGuardError("bridge_owner_state_invalid")
    state = Path(raw_path)
    if not state.is_absolute() or state.is_symlink() or not state.is_file():
        raise DeliveryOwnerGuardError("bridge_owner_state_unavailable")
    statuses = ",".join("?" for _ in _OWNED_STATUSES)
    try:
        with closing(sqlite3.connect(state.as_uri() + "?mode=ro", uri=True, timeout=1)) as connection:
            connection.execute("PRAGMA query_only=ON")
            owned = connection.execute(
                "SELECT 1 FROM desktop_bridge_requests "
                f"WHERE status IN ({statuses}) AND "
                "(desktop_thread_id=? OR "
                "(operation='create' AND status='dispatching' "
                "AND desktop_thread_id IS NULL AND updated_at>=?)) "
                "LIMIT 1",
                (*_OWNED_STATUSES, thread_id,
                 (datetime.now(UTC) - timedelta(seconds=120)).isoformat()),
            ).fetchone()
    except (OSError, sqlite3.Error) as exc:
        raise DeliveryOwnerGuardError("bridge_owner_state_unavailable") from exc
    if owned is not None:
        raise DeliveryOwnerGuardError("bridge_delivery_owned")
