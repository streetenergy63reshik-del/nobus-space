from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import pytest

from src.integrations import CalendarAction, CalendarActionKind, GoogleCalendarClient
from src.integrations.google_calendar import (
    _CALENDAR_WRITE_SCOPES,
    _has_any_scope,
)


MSK = timezone(timedelta(hours=3), "MSK")
KEY = "sha256:" + "a" * 64


class _Response:
    def __init__(self, status: int) -> None:
        self.status = status


class _HttpError(Exception):
    def __init__(self, status: int) -> None:
        self.resp = _Response(status)


class _Request:
    def __init__(self, operation: Callable[[], object]) -> None:
        self._operation = operation

    def execute(self) -> object:
        return self._operation()


class _Events:
    def __init__(self) -> None:
        self.values: dict[str, dict[str, Any]] = {}
        self.insert_calls = 0
        self.delete_calls = 0

    def insert(self, *, body: dict[str, Any], **_: object) -> _Request:
        def operation() -> object:
            self.insert_calls += 1
            event_id = body["id"]
            if event_id in self.values:
                raise _HttpError(409)
            value = {
                **body,
                "id": event_id,
                "htmlLink": f"https://calendar.invalid/{event_id}",
            }
            self.values[event_id] = value
            return value

        return _Request(operation)

    def get(self, *, eventId: str, **_: object) -> _Request:
        return _Request(lambda: self.values[eventId])

    def list(self, *, q: str | None = None, **_: object) -> _Request:
        def operation() -> object:
            values = list(self.values.values())
            if q is not None:
                values = [
                    value
                    for value in values
                    if q.casefold() in str(value.get("summary", "")).casefold()
                ]
            return {"items": values}

        return _Request(operation)

    def patch(
        self, *, eventId: str, body: dict[str, Any], **_: object
    ) -> _Request:
        def operation() -> object:
            self.values[eventId] = {**self.values[eventId], **body}
            return self.values[eventId]

        return _Request(operation)

    def delete(self, *, eventId: str, **_: object) -> _Request:
        def operation() -> object:
            self.delete_calls += 1
            if eventId not in self.values:
                raise _HttpError(404)
            self.values.pop(eventId)
            return {}

        return _Request(operation)


class _Service:
    def __init__(self) -> None:
        self.boundary = _Events()

    def events(self) -> _Events:
        return self.boundary


def _client(service: _Service) -> GoogleCalendarClient:
    return GoogleCalendarClient(
        Path("C:/not-read-by-fake/token.json"),
        service_factory=lambda: service,
    )


def _create(title: str = "Планёрка") -> CalendarAction:
    start = datetime(2026, 7, 27, 10, 0, tzinfo=MSK)
    return CalendarAction(
        kind=CalendarActionKind.CREATE,
        title=title,
        start=start,
        end=start + timedelta(hours=1),
    )


def test_action_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        CalendarAction(
            kind=CalendarActionKind.CREATE,
            title="Планёрка",
            start=datetime(2026, 7, 27, 10, 0),
            end=datetime(2026, 7, 27, 11, 0),
        )


def test_create_is_idempotent_for_same_key() -> None:
    service = _Service()
    client = _client(service)

    first = asyncio.run(client.execute(_create(), idempotency_key=KEY))
    second = asyncio.run(client.execute(_create(), idempotency_key=KEY))

    assert first.event == second.event
    assert len(service.boundary.values) == 1
    assert service.boundary.insert_calls == 2
    assert first.message.startswith("Событие «Планёрка» записано")


def test_create_rejects_same_key_with_different_payload() -> None:
    service = _Service()
    client = _client(service)
    asyncio.run(client.execute(_create("Планёрка"), idempotency_key=KEY))

    with pytest.raises(RuntimeError, match="idempotency_conflict"):
        asyncio.run(
            client.execute(_create("Другая встреча"), idempotency_key=KEY)
        )

    assert len(service.boundary.values) == 1


def test_list_and_update_unique_event() -> None:
    service = _Service()
    client = _client(service)
    created = asyncio.run(client.execute(_create(), idempotency_key=KEY))
    assert created.event is not None
    start = datetime(2026, 7, 27, 12, 0, tzinfo=MSK)

    updated = asyncio.run(
        client.execute(
            CalendarAction(
                kind=CalendarActionKind.UPDATE,
                target="Планёрка",
                title="Планёрка команды",
                start=start,
                end=start + timedelta(minutes=30),
            ),
            idempotency_key="sha256:" + "b" * 64,
        )
    )
    replayed = asyncio.run(
        client.execute(
            CalendarAction(
                kind=CalendarActionKind.UPDATE,
                target="Планёрка",
                title="Планёрка команды",
                start=start,
                end=start + timedelta(minutes=30),
            ),
            idempotency_key="sha256:" + "b" * 64,
        )
    )
    assert replayed.event is not None
    assert replayed.event.event_id == updated.event.event_id
    listed = asyncio.run(
        client.execute(
            CalendarAction(
                kind=CalendarActionKind.LIST,
                start=start - timedelta(days=1),
                end=start + timedelta(days=1),
            ),
            idempotency_key="sha256:" + "c" * 64,
        )
    )

    assert updated.event is not None
    assert updated.event.title == "Планёрка команды"
    assert "Планёрка команды" in listed.message


def test_update_rejects_same_key_with_different_payload() -> None:
    service = _Service()
    client = _client(service)
    asyncio.run(client.execute(_create(), idempotency_key=KEY))
    start = datetime(2026, 7, 27, 12, 0, tzinfo=MSK)
    key = "sha256:" + "b" * 64
    asyncio.run(
        client.execute(
            CalendarAction(
                kind=CalendarActionKind.UPDATE,
                target="Планёрка",
                title="Планёрка команды",
                start=start,
                end=start + timedelta(minutes=30),
            ),
            idempotency_key=key,
        )
    )

    with pytest.raises(RuntimeError, match="idempotency_conflict"):
        asyncio.run(
            client.execute(
                CalendarAction(
                    kind=CalendarActionKind.UPDATE,
                    target="Планёрка",
                    title="Другое название",
                    start=start,
                    end=start + timedelta(minutes=30),
                ),
                idempotency_key=key,
            )
        )



def test_resolve_delete_rejects_ambiguous_and_delete_is_idempotent() -> None:
    service = _Service()
    client = _client(service)
    asyncio.run(client.execute(_create("Созвон"), idempotency_key=KEY))
    asyncio.run(
        client.execute(
            _create("Созвон второй"),
            idempotency_key="sha256:" + "d" * 64,
        )
    )
    action = CalendarAction(kind=CalendarActionKind.DELETE, target="Созвон")

    event = asyncio.run(client.resolve_delete(action))
    asyncio.run(client.delete_event(event.event_id))
    asyncio.run(client.delete_event(event.event_id))

    assert service.boundary.delete_calls == 2
    assert event.event_id not in service.boundary.values


def test_resolve_delete_rejects_multiple_partial_matches() -> None:
    service = _Service()
    client = _client(service)
    asyncio.run(client.execute(_create("Созвон один"), idempotency_key=KEY))
    asyncio.run(
        client.execute(
            _create("Созвон два"),
            idempotency_key="sha256:" + "e" * 64,
        )
    )

    with pytest.raises(RuntimeError, match="calendar_event_ambiguous"):
        asyncio.run(
            client.resolve_delete(
                CalendarAction(
                    kind=CalendarActionKind.DELETE,
                    target="Созвон",
                )
            )
        )


@pytest.mark.parametrize(
    "granted_scope",
    [
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/calendar.events.owned",
    ],
)
def test_calendar_accepts_compatible_write_scopes(granted_scope: str) -> None:
    class _Credentials:
        @staticmethod
        def has_scopes(scopes: tuple[str, ...]) -> bool:
            return set(scopes).issubset({granted_scope})

    assert _has_any_scope(_Credentials(), _CALENDAR_WRITE_SCOPES)


def test_calendar_rejects_read_only_or_unrelated_scopes() -> None:
    class _Credentials:
        @staticmethod
        def has_scopes(scopes: tuple[str, ...]) -> bool:
            return set(scopes).issubset(
                {"https://www.googleapis.com/auth/calendar.readonly"}
            )

    assert not _has_any_scope(_Credentials(), _CALENDAR_WRITE_SCOPES)
