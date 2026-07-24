from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.application.business_notes import (
    BusinessNotesError,
    BusinessNotesService,
    SQLiteBusinessNotes,
)
from src.transport.telegram import TextMessage


AUTH = "sha256:" + "a" * 64


def _encode(value: dict[str, object]) -> bytes:
    return b"encrypted:" + json.dumps(
        value, ensure_ascii=False, sort_keys=True
    ).encode("utf-8")[::-1]


def _decode(value: bytes) -> dict[str, object]:
    assert value.startswith(b"encrypted:")
    result = json.loads(value[len(b"encrypted:") :][::-1])
    assert isinstance(result, dict)
    return result


def _message(
    text: str,
    *,
    message_id: int,
    update_id: int | None = None,
    thread_id: int = 10,
    tenant_id: str = "owner",
) -> TextMessage:
    return TextMessage(
        update_id=update_id if update_id is not None else message_id,
        tenant_id=tenant_id,
        actor_identity="telegram:owner",
        actor_role="owner",
        auth_context_ref=AUTH,
        user_id=7,
        chat_id=-100123,
        message_thread_id=thread_id,
        binding_purpose="business_notes",
        message_id=message_id,
        text=text,
    )


def _store(
    tmp_path: Path,
    *,
    clock=lambda: datetime(2026, 7, 24, 10, 0, tzinfo=UTC),
    max_notes: int = 50_000,
) -> SQLiteBusinessNotes:
    return SQLiteBusinessNotes(
        tmp_path / "notes.sqlite3",
        encode=_encode,
        decode=_decode,
        clock=clock,
        max_notes=max_notes,
    )


def test_note_is_encrypted_durable_and_idempotent(tmp_path: Path) -> None:
    store = _store(tmp_path)
    message = _message(
        "Позвонить поставщику завтра.",
        message_id=1,
    )

    assert store.append(message) is True
    assert store.append(message) is False
    reopened = _store(tmp_path)
    notes = reopened.recent(
        tenant_id="owner",
        chat_id=-100123,
        thread_id=10,
    )

    assert [item.text for item in notes] == [
        "Позвонить поставщику завтра."
    ]
    assert "Позвонить".encode("utf-8") not in (
        tmp_path / "notes.sqlite3"
    ).read_bytes()
    with closing(sqlite3.connect(store.path)) as connection:
        stored_digest = connection.execute(
            "SELECT payload_digest FROM business_notes"
        ).fetchone()[0]
    assert stored_digest != AUTH


def test_replay_keeps_original_server_timestamp(tmp_path: Path) -> None:
    current = [datetime(2026, 7, 24, 10, 0, tzinfo=UTC)]
    store = _store(tmp_path, clock=lambda: current[0])
    message = _message("Повтор.", message_id=1)
    assert store.append(message) is True
    current[0] += timedelta(hours=2)

    assert store.append(message) is False
    notes = store.recent(
        tenant_id="owner",
        chat_id=-100123,
        thread_id=10,
    )
    assert notes[0].created_at == datetime(
        2026, 7, 24, 10, 0, tzinfo=UTC
    )


def test_note_binding_conflict_and_tamper_fail_closed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.append(_message("Первая версия.", message_id=1))
    with pytest.raises(BusinessNotesError, match="binding_conflict"):
        store.append(_message("Подмена.", message_id=1))
    with pytest.raises(BusinessNotesError, match="binding_conflict"):
        store.append(
            _message("Другой message.", message_id=2, update_id=1)
        )

    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE business_notes SET payload_digest=?",
            ("sha256:" + "f" * 64,),
        )
    with pytest.raises(BusinessNotesError, match="payload_tampered"):
        store.recent(
            tenant_id="owner",
            chat_id=-100123,
            thread_id=10,
        )


def test_existing_schema_and_plaintext_row_tamper_fail_closed(
    tmp_path: Path,
) -> None:
    malformed = tmp_path / "notes.sqlite3"
    with closing(sqlite3.connect(malformed)) as connection:
        connection.execute("CREATE TABLE business_notes(value TEXT)")
    with pytest.raises(BusinessNotesError, match="store_unavailable"):
        _store(tmp_path)

    malformed.unlink()
    store = _store(tmp_path)
    store.append(_message("Сегодня.", message_id=1))
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE business_notes SET created_at=?",
            ("2020-01-01T00:00:00+00:00",),
        )
    with pytest.raises(BusinessNotesError, match="binding_conflict"):
        store.recent(
            tenant_id="owner",
            chat_id=-100123,
            thread_id=10,
            since=datetime(2026, 7, 24, tzinfo=UTC),
        )


def test_topics_and_tenants_are_isolated(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.append(_message("Тема один.", message_id=1, thread_id=10))
    store.append(_message("Тема два.", message_id=2, thread_id=20))
    store.append(
        _message(
            "Другой tenant.",
            message_id=3,
            thread_id=10,
            tenant_id="tenant-b",
        )
    )

    values = store.recent(
        tenant_id="owner",
        chat_id=-100123,
        thread_id=10,
    )
    assert [item.text for item in values] == ["Тема один."]


def test_local_summary_and_task_extraction_do_not_index_commands(
    tmp_path: Path,
) -> None:
    service = BusinessNotesService(_store(tmp_path))
    assert service.handle_text(
        _message("Идея новой услуги.", message_id=1)
    ) is None
    assert service.handle_text(
        _message("Нужно позвонить клиенту завтра.", message_id=2)
    ) is None

    summary = service.handle_text(
        _message("Собери резюме заметок.", message_id=3)
    )
    tasks = service.handle_text(
        _message("/tasks", message_id=4)
    )

    assert summary is not None and "Идея новой услуги" in summary
    assert summary is not None and "Нужно позвонить" in summary
    assert tasks is not None and "Нужно позвонить" in tasks
    assert tasks is not None and "Идея новой услуги" not in tasks
    notes = service._store.recent(
        tenant_id="owner",
        chat_id=-100123,
        thread_id=10,
    )
    assert len(notes) == 2


def test_command_like_notes_are_not_silently_consumed(
    tmp_path: Path,
) -> None:
    service = BusinessNotesService(_store(tmp_path))
    for message_id, text in enumerate(
        (
            "Собери резюме встречи для клиента к пятнице.",
            "/summarydraft",
        ),
        start=1,
    ):
        assert service.handle_text(
            _message(text, message_id=message_id)
        ) is None
    notes = service._store.recent(
        tenant_id="owner",
        chat_id=-100123,
        thread_id=10,
    )
    assert [note.text for note in notes] == [
        "Собери резюме встречи для клиента к пятнице.",
        "/summarydraft",
    ]


def test_today_and_telegram_output_are_bounded(tmp_path: Path) -> None:
    current = [datetime(2026, 7, 23, 20, 0, tzinfo=UTC)]
    store = _store(tmp_path, clock=lambda: current[0])
    store.append(_message("Вчера.", message_id=1))
    current[0] = datetime(2026, 7, 24, 10, 0, tzinfo=UTC)
    store.append(_message("Сегодня " + "я" * 4_000, message_id=2))
    service = BusinessNotesService(
        store,
        clock=lambda: datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
    )

    result = service.handle_text(
        _message("/summary сегодня", message_id=3)
    )

    assert result is not None
    assert "Вчера" not in result
    assert len(result) <= 3_500
    assert result.endswith("…")


def test_recent_decrypts_only_the_bounded_candidate_set(tmp_path: Path) -> None:
    store = _store(tmp_path, max_notes=1_000)
    for message_id in range(1, 101):
        store.append(_message(f"note {message_id}", message_id=message_id))

    original_decode = store._decode
    decode_calls = 0

    def counting_decode(value: bytes) -> dict[str, object]:
        nonlocal decode_calls
        decode_calls += 1
        return original_decode(value)

    store._decode = counting_decode
    result = store.recent(
        tenant_id="owner",
        chat_id=-100123,
        thread_id=10,
        limit=1,
    )

    assert [note.message_id for note in result] == [100]
    assert decode_calls == 1


def test_since_filter_and_capacity_are_bounded(tmp_path: Path) -> None:
    current = [datetime(2026, 7, 23, 10, 0, tzinfo=UTC)]
    store = _store(tmp_path, clock=lambda: current[0], max_notes=2)
    store.append(_message("Вчера.", message_id=1))
    current[0] += timedelta(days=1)
    store.append(_message("Сегодня.", message_id=2))

    values = store.recent(
        tenant_id="owner",
        chat_id=-100123,
        thread_id=10,
        since=datetime(2026, 7, 24, 0, 0, tzinfo=UTC),
    )
    assert [item.text for item in values] == ["Сегодня."]
    with pytest.raises(BusinessNotesError, match="capacity_exceeded"):
        store.append(_message("Лишняя.", message_id=3))
