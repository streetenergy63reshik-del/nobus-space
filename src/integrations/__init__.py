"""Typed external-service adapters with no embedded credentials."""

from .google_calendar import (
    CalendarAction,
    CalendarActionKind,
    CalendarEvent,
    CalendarService,
    CalendarResult,
    GoogleCalendarClient,
)

__all__ = [
    "CalendarAction",
    "CalendarActionKind",
    "CalendarEvent",
    "CalendarResult",
    "CalendarService",
    "GoogleCalendarClient",
]
