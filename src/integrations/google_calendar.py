"""Owner-bound Google Calendar adapter using an existing OAuth token."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


MOSCOW = timezone(timedelta(hours=3), "MSK")
_CALENDAR_WRITE_SCOPES = frozenset(
    {
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/calendar.events.owned",
    }
)


class CalendarActionKind(str, Enum):
    NONE = "none"
    LIST = "list"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class CalendarAction(BaseModel):
    """Closed action schema produced by the read-only intent planner."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: CalendarActionKind
    title: str | None = Field(default=None, max_length=300)
    target: str | None = Field(default=None, max_length=300)
    start: datetime | None = None
    end: datetime | None = None
    description: str | None = Field(default=None, max_length=4_000)

    @model_validator(mode="after")
    def validate_action(self) -> "CalendarAction":
        for value in (self.title, self.target, self.description):
            if value is not None and (not value.strip() or "\x00" in value):
                raise ValueError("calendar text is invalid")
        for value in (self.start, self.end):
            if value is not None and value.tzinfo is None:
                raise ValueError("calendar datetime must be timezone-aware")
        if self.kind is CalendarActionKind.NONE:
            if any(
                value is not None
                for value in (
                    self.title,
                    self.target,
                    self.start,
                    self.end,
                    self.description,
                )
            ):
                raise ValueError("none calendar action must be empty")
        elif self.kind is CalendarActionKind.LIST:
            if self.start is None or self.end is None or self.end <= self.start:
                raise ValueError("calendar list range is invalid")
        elif self.kind is CalendarActionKind.CREATE:
            if (
                self.title is None
                or self.start is None
                or self.end is None
                or self.end <= self.start
            ):
                raise ValueError("calendar create action is invalid")
        elif self.kind is CalendarActionKind.UPDATE:
            if self.target is None or (
                self.title is None
                and self.start is None
                and self.end is None
                and self.description is None
            ):
                raise ValueError("calendar update action is invalid")
            if (self.start is None) != (self.end is None):
                raise ValueError("calendar update time range is incomplete")
            if self.start is not None and self.end <= self.start:
                raise ValueError("calendar update time range is invalid")
        elif self.kind is CalendarActionKind.DELETE and self.target is None:
            raise ValueError("calendar delete target is missing")
        return self


class CalendarEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    event_id: str = Field(min_length=1, max_length=1_024)
    title: str = Field(min_length=1, max_length=300)
    start: datetime
    end: datetime
    html_link: str | None = Field(default=None, max_length=2_048)

    @model_validator(mode="after")
    def validate_event(self) -> "CalendarEvent":
        if self.start.tzinfo is None or self.end.tzinfo is None or self.end <= self.start:
            raise ValueError("calendar event range is invalid")
        return self


class CalendarResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    message: str = Field(min_length=1, max_length=3_400)
    event: CalendarEvent | None = None


class CalendarPlanner(Protocol):
    async def plan_calendar_action(
        self, instruction: str, envelope: object
    ) -> CalendarAction: ...


class CalendarService(Protocol):
    async def execute(
        self, action: CalendarAction, *, idempotency_key: str
    ) -> CalendarResult: ...

    async def resolve_delete(self, action: CalendarAction) -> CalendarEvent: ...

    async def delete_event(self, event_id: str) -> None: ...


class GoogleCalendarClient:
    """Minimal Calendar v3 boundary; it never logs or returns OAuth material."""

    def __init__(
        self,
        token_path: str | Path,
        *,
        calendar_id: str = "primary",
        tz: timezone = MOSCOW,
        service_factory: Callable[[], Any] | None = None,
    ) -> None:
        path = Path(token_path).resolve(strict=False)
        if (
            not path.is_absolute()
            or not isinstance(calendar_id, str)
            or not calendar_id.strip()
            or not isinstance(tz, timezone)
        ):
            raise ValueError("Google Calendar configuration is invalid")
        self._token_path = path
        self._calendar_id = calendar_id.strip()
        self._timezone = tz
        self._service_factory = service_factory
        self._service_instance: Any | None = None

    async def execute(
        self, action: CalendarAction, *, idempotency_key: str
    ) -> CalendarResult:
        action = CalendarAction.model_validate(action.model_dump())
        if (
            not isinstance(idempotency_key, str)
            or not idempotency_key.startswith("sha256:")
            or len(idempotency_key) != 71
        ):
            raise ValueError("calendar idempotency key is invalid")
        return await asyncio.to_thread(self._execute_sync, action, idempotency_key)

    async def resolve_delete(self, action: CalendarAction) -> CalendarEvent:
        action = CalendarAction.model_validate(action.model_dump())
        if action.kind is not CalendarActionKind.DELETE:
            raise ValueError("calendar delete action is invalid")
        return await asyncio.to_thread(self._resolve_unique_sync, action.target or "")

    async def delete_event(self, event_id: str) -> None:
        if not isinstance(event_id, str) or not event_id.strip() or "\x00" in event_id:
            raise ValueError("calendar event id is invalid")
        await asyncio.to_thread(self._delete_sync, event_id.strip())

    def _service(self) -> Any:
        if self._service_instance is not None:
            return self._service_instance
        if self._service_factory is not None:
            self._service_instance = self._service_factory()
            return self._service_instance
        if not self._token_path.is_file():
            raise RuntimeError("google_calendar_credentials_unavailable")
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build

            credentials = Credentials.from_authorized_user_file(
                str(self._token_path)
            )
            if not _has_any_scope(credentials, _CALENDAR_WRITE_SCOPES):
                raise RuntimeError
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            if not credentials.valid:
                raise RuntimeError
            self._service_instance = build(
                "calendar",
                "v3",
                credentials=credentials,
                cache_discovery=False,
            )
            return self._service_instance
        except ImportError:
            raise RuntimeError("google_calendar_dependency_unavailable") from None
        except RuntimeError:
            raise RuntimeError("google_calendar_credentials_unavailable") from None
        except Exception:
            raise RuntimeError("google_calendar_unavailable") from None

    def _execute_sync(
        self, action: CalendarAction, idempotency_key: str
    ) -> CalendarResult:
        if action.kind is CalendarActionKind.LIST:
            events = self._list_sync(action.start, action.end)
            if not events:
                return CalendarResult(message="На выбранный период событий нет.")
            lines = [
                f"• {event.start.astimezone(self._timezone):%d.%m %H:%M} — {event.title}"
                for event in events[:20]
            ]
            return CalendarResult(message="Календарь:\n\n" + "\n".join(lines))
        if action.kind is CalendarActionKind.CREATE:
            event_id = "nobus" + hashlib.sha256(
                idempotency_key.encode()
            ).hexdigest()[:32]
            body = {
                "id": event_id,
                "summary": action.title,
                "description": action.description or "",
                "start": {
                    "dateTime": action.start.isoformat(),
                },
                "end": {
                    "dateTime": action.end.isoformat(),
                },
            }
            service = self._service()
            try:
                raw = service.events().insert(
                    calendarId=self._calendar_id,
                    body=body,
                    sendUpdates="none",
                ).execute()
            except Exception as error:
                if getattr(getattr(error, "resp", None), "status", None) != 409:
                    raise RuntimeError("google_calendar_write_failed") from None
                raw = service.events().get(
                    calendarId=self._calendar_id, eventId=event_id
                ).execute()
                if not self._matches_create(raw, action):
                    raise RuntimeError("google_calendar_idempotency_conflict")
            event = self._event(raw)
            return CalendarResult(
                message=(
                    f"Событие «{event.title}» записано на "
                    f"{event.start.astimezone(self._timezone):%d.%m.%Y %H:%M}."
                ),
                event=event,
            )
        if action.kind is CalendarActionKind.UPDATE:
            marker = hashlib.sha256(idempotency_key.encode()).hexdigest()
            action_digest = hashlib.sha256(
                json.dumps(
                    action.model_dump(mode="json"),
                    allow_nan=False,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            replay = self._find_marker_sync(marker, action_digest)
            if replay is not None:
                return CalendarResult(
                    message=(
                        f"Событие «{replay.title}» обновлено: "
                        f"{replay.start.astimezone(self._timezone):%d.%m.%Y %H:%M}."
                    ),
                    event=replay,
                )
            current = self._resolve_unique_sync(action.target or "")
            body: dict[str, object] = {
                "extendedProperties": {
                    "private": {
                        "nobusKey": marker,
                        "nobusActionDigest": action_digest,
                    }
                }
            }
            if action.title is not None:
                body["summary"] = action.title
            if action.description is not None:
                body["description"] = action.description
            if action.start is not None:
                body["start"] = {
                    "dateTime": action.start.isoformat(),
                }
                body["end"] = {
                    "dateTime": action.end.isoformat(),
                }
            try:
                raw = self._service().events().patch(
                    calendarId=self._calendar_id,
                    eventId=current.event_id,
                    body=body,
                    sendUpdates="none",
                ).execute()
            except Exception:
                raise RuntimeError("google_calendar_write_failed") from None
            event = self._event(raw)
            return CalendarResult(
                message=(
                    f"Событие «{event.title}» обновлено: "
                    f"{event.start.astimezone(self._timezone):%d.%m.%Y %H:%M}."
                ),
                event=event,
            )
        raise ValueError("calendar action requires another boundary")

    def _find_marker_sync(
        self, marker: str, action_digest: str
    ) -> CalendarEvent | None:
        try:
            values = self._service().events().list(
                calendarId=self._calendar_id,
                privateExtendedProperty=f"nobusKey={marker}",
                singleEvents=True,
                maxResults=2,
            ).execute()
            items = values.get("items", [])
            if not isinstance(items, list):
                raise ValueError
            matched = [
                item
                for item in items
                if isinstance(item, dict)
                and item.get("extendedProperties", {})
                .get("private", {})
                .get("nobusKey")
                == marker
            ]
            if len(matched) > 1:
                raise ValueError
            if not matched:
                return None
            stored_digest = (
                matched[0].get("extendedProperties", {})
                .get("private", {})
                .get("nobusActionDigest")
            )
            if stored_digest != action_digest:
                raise RuntimeError("google_calendar_idempotency_conflict")
            return self._event(matched[0])
        except (RuntimeError, ValueError):
            raise
        except Exception:
            raise RuntimeError("google_calendar_read_failed") from None

    def _resolve_unique_sync(self, target: str) -> CalendarEvent:
        normalized = target.strip()
        if not normalized:
            raise ValueError("calendar target is empty")
        now = datetime.now(self._timezone)
        events = self._list_sync(
            now - timedelta(days=30),
            now + timedelta(days=366),
            query=normalized,
        )
        exact = [
            event
            for event in events
            if event.title.casefold() == normalized.casefold()
        ]
        selected = exact or events
        if not selected:
            raise RuntimeError("calendar_event_not_found")
        if len(selected) != 1:
            raise RuntimeError("calendar_event_ambiguous")
        return selected[0]

    def _list_sync(
        self,
        start: datetime | None,
        end: datetime | None,
        *,
        query: str | None = None,
    ) -> tuple[CalendarEvent, ...]:
        if start is None or end is None or start.tzinfo is None or end.tzinfo is None:
            raise ValueError("calendar range is invalid")
        options: dict[str, object] = {
            "calendarId": self._calendar_id,
            "timeMin": start.astimezone(UTC).isoformat(),
            "timeMax": end.astimezone(UTC).isoformat(),
            "singleEvents": True,
            "orderBy": "startTime",
            "maxResults": 100,
        }
        if query:
            options["q"] = query
        try:
            values = self._service().events().list(**options).execute()
            items = values.get("items", [])
            if not isinstance(items, list):
                raise ValueError
            return tuple(self._event(item) for item in items)
        except (RuntimeError, ValueError):
            raise
        except Exception:
            raise RuntimeError("google_calendar_read_failed") from None

    def _delete_sync(self, event_id: str) -> None:
        try:
            self._service().events().delete(
                calendarId=self._calendar_id,
                eventId=event_id,
                sendUpdates="none",
            ).execute()
        except Exception as error:
            if getattr(getattr(error, "resp", None), "status", None) != 404:
                raise RuntimeError("google_calendar_delete_failed") from None

    def _event(self, raw: object) -> CalendarEvent:
        if not isinstance(raw, dict):
            raise RuntimeError("google_calendar_response_invalid")
        try:
            start = self._event_time(raw["start"])
            end = self._event_time(raw["end"])
            return CalendarEvent(
                event_id=raw["id"],
                title=raw.get("summary") or "Без названия",
                start=start,
                end=end,
                html_link=raw.get("htmlLink"),
            )
        except Exception:
            raise RuntimeError("google_calendar_response_invalid") from None

    def _event_time(self, value: object) -> datetime:
        if not isinstance(value, dict):
            raise ValueError
        if isinstance(value.get("dateTime"), str):
            parsed = datetime.fromisoformat(value["dateTime"].replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError
            return parsed
        if isinstance(value.get("date"), str):
            parsed_date = date.fromisoformat(value["date"])
            return datetime.combine(parsed_date, time.min, self._timezone)
        raise ValueError

    def _matches_create(self, raw: object, action: CalendarAction) -> bool:
        if not isinstance(raw, dict):
            return False
        try:
            return (
                raw.get("summary") == action.title
                and (raw.get("description") or "") == (action.description or "")
                and self._event_time(raw["start"]).astimezone(UTC)
                == action.start.astimezone(UTC)
                and self._event_time(raw["end"]).astimezone(UTC)
                == action.end.astimezone(UTC)
            )
        except (KeyError, TypeError, ValueError):
            return False


def _has_any_scope(
    credentials: object, accepted: frozenset[str]
) -> bool:
    """Accept a least-privilege scope or an explicitly broader one."""
    has_scopes = getattr(credentials, "has_scopes", None)
    return callable(has_scopes) and any(
        bool(has_scopes((scope,))) for scope in accepted
    )
