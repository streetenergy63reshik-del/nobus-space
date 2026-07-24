"""Typed external-service adapters with no embedded credentials."""

from .google_calendar import (
    CalendarAction,
    CalendarActionKind,
    CalendarEvent,
    CalendarService,
    CalendarResult,
    GoogleCalendarClient,
)
from .google_drive import (
    GoogleDriveAction,
    GoogleDriveActionKind,
    GoogleDriveClient,
    GoogleDriveFile,
    GoogleDriveResult,
)
from .google_tasks import (
    GoogleTaskAction,
    GoogleTaskActionKind,
    GoogleTaskItem,
    GoogleTaskResult,
    GoogleTasksClient,
)

__all__ = [
    "CalendarAction",
    "CalendarActionKind",
    "CalendarEvent",
    "CalendarResult",
    "CalendarService",
    "GoogleCalendarClient",
    "GoogleDriveAction",
    "GoogleDriveActionKind",
    "GoogleDriveClient",
    "GoogleDriveFile",
    "GoogleDriveResult",
    "GoogleTaskAction",
    "GoogleTaskActionKind",
    "GoogleTaskItem",
    "GoogleTaskResult",
    "GoogleTasksClient",
]
