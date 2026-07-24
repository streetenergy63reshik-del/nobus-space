"""Owner-bound Google Tasks adapter using existing OAuth authority."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GoogleTaskActionKind(str, Enum):
    NONE = "none"
    LIST = "list"
    CREATE = "create"
    UPDATE = "update"
    COMPLETE = "complete"
    DELETE = "delete"


class GoogleTaskAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: GoogleTaskActionKind
    title: str | None = Field(default=None, max_length=1_024)
    target: str | None = Field(default=None, max_length=1_024)
    list_name: str | None = Field(default=None, max_length=1_024)
    notes: str | None = Field(default=None, max_length=8_000)
    due: date | None = None

    @model_validator(mode="after")
    def validate_action(self) -> "GoogleTaskAction":
        for value in (self.title, self.target, self.list_name, self.notes):
            if value is not None and (not value.strip() or "\x00" in value):
                raise ValueError("task text is invalid")
        if self.kind is GoogleTaskActionKind.NONE:
            if any(
                value is not None
                for value in (
                    self.title,
                    self.target,
                    self.list_name,
                    self.notes,
                    self.due,
                )
            ):
                raise ValueError("none task action must be empty")
        elif self.kind is GoogleTaskActionKind.CREATE and self.title is None:
            raise ValueError("task title is missing")
        elif self.kind in {
            GoogleTaskActionKind.UPDATE,
            GoogleTaskActionKind.COMPLETE,
            GoogleTaskActionKind.DELETE,
        } and self.target is None:
            raise ValueError("task target is missing")
        elif self.kind is GoogleTaskActionKind.UPDATE and all(
            value is None for value in (self.title, self.notes, self.due)
        ):
            raise ValueError("task update is empty")
        return self


class GoogleTaskItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    task_id: str = Field(min_length=1, max_length=2_048)
    tasklist_id: str = Field(min_length=1, max_length=2_048)
    tasklist_title: str = Field(min_length=1, max_length=1_024)
    title: str = Field(min_length=1, max_length=1_024)
    status: str = Field(pattern=r"^(needsAction|completed)$")
    due: date | None = None
    notes: str | None = Field(default=None, max_length=8_000)


class GoogleTaskResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    message: str = Field(min_length=1, max_length=3_400)
    item: GoogleTaskItem | None = None


class GoogleTaskPlanner(Protocol):
    async def plan_google_task_action(
        self, instruction: str, envelope: object
    ) -> GoogleTaskAction: ...


class GoogleTasksClient:
    def __init__(
        self,
        token_path: str | Path,
        *,
        service_factory: Callable[[], Any] | None = None,
    ) -> None:
        path = Path(token_path).resolve(strict=False)
        if not path.is_absolute():
            raise ValueError("Google Tasks configuration is invalid")
        self._token_path = path
        self._service_factory = service_factory
        self._service_instance: Any | None = None

    async def execute(
        self, action: GoogleTaskAction, *, idempotency_key: str
    ) -> GoogleTaskResult:
        action = GoogleTaskAction.model_validate(action.model_dump())
        _validate_key(idempotency_key)
        return await asyncio.to_thread(self._execute_sync, action, idempotency_key)

    async def resolve_delete(self, action: GoogleTaskAction) -> GoogleTaskItem:
        action = GoogleTaskAction.model_validate(action.model_dump())
        if action.kind is not GoogleTaskActionKind.DELETE:
            raise ValueError("Google Task delete action is invalid")
        return await asyncio.to_thread(self._resolve_unique_sync, action)

    async def delete_task(self, tasklist_id: str, task_id: str) -> None:
        if not _safe_text(tasklist_id, 2_048) or not _safe_text(task_id, 2_048):
            raise ValueError("Google Task binding is invalid")
        await asyncio.to_thread(self._delete_sync, tasklist_id, task_id)

    def _service(self) -> Any:
        if self._service_instance is not None:
            return self._service_instance
        if self._service_factory is not None:
            self._service_instance = self._service_factory()
            return self._service_instance
        if not self._token_path.is_file():
            raise RuntimeError("google_tasks_credentials_unavailable")
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            scopes = ("https://www.googleapis.com/auth/tasks",)
            credentials = Credentials.from_authorized_user_file(
                str(self._token_path)
            )
            if not credentials.has_scopes(scopes):
                raise RuntimeError
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            if not credentials.valid:
                raise RuntimeError
            self._service_instance = build(
                "tasks", "v1", credentials=credentials, cache_discovery=False
            )
            return self._service_instance
        except ImportError:
            raise RuntimeError("google_tasks_dependency_unavailable") from None
        except RuntimeError:
            raise RuntimeError("google_tasks_credentials_unavailable") from None
        except Exception:
            raise RuntimeError("google_tasks_unavailable") from None

    def _execute_sync(
        self, action: GoogleTaskAction, idempotency_key: str
    ) -> GoogleTaskResult:
        tasklist_id, tasklist_title = self._tasklist_sync(action.list_name)
        if action.kind is GoogleTaskActionKind.LIST:
            items = self._items_sync(tasklist_id, tasklist_title)
            active = [item for item in items if item.status == "needsAction"]
            if not active:
                return GoogleTaskResult(message="Активных задач нет.")
            lines = [
                f"• {item.title}"
                + (f" — до {item.due:%d.%m.%Y}" if item.due else "")
                for item in active[:30]
            ]
            return GoogleTaskResult(
                message=f"Задачи · {tasklist_title}:\n\n" + "\n".join(lines)
            )
        key_marker = _marker(idempotency_key)
        action_digest = hashlib.sha256(
            json.dumps(
                action.model_dump(mode="json"),
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        marker = f"{key_marker}[nobus-action:{action_digest}]"
        replay = self._find_marker_sync(
            tasklist_id,
            tasklist_title,
            key_marker,
            marker,
        )
        if replay is not None:
            return self._result(action.kind, replay)
        if action.kind is GoogleTaskActionKind.CREATE:
            body = {
                "title": action.title,
                "notes": _notes(action.notes, marker),
            }
            if action.due is not None:
                body["due"] = f"{action.due.isoformat()}T00:00:00.000Z"
            try:
                raw = self._service().tasks().insert(
                    tasklist=tasklist_id, body=body
                ).execute()
            except Exception:
                raise RuntimeError("google_tasks_write_failed") from None
            return self._result(
                action.kind,
                self._item(raw, tasklist_id, tasklist_title),
            )
        current = self._resolve_unique_sync(action)
        body: dict[str, object] = {
            "notes": _notes(action.notes if action.notes is not None else current.notes, marker)
        }
        if action.kind is GoogleTaskActionKind.UPDATE:
            if action.title is not None:
                body["title"] = action.title
            if action.due is not None:
                body["due"] = f"{action.due.isoformat()}T00:00:00.000Z"
        elif action.kind is GoogleTaskActionKind.COMPLETE:
            body["status"] = "completed"
        else:
            raise ValueError("Google Task action requires another boundary")
        try:
            raw = self._service().tasks().patch(
                tasklist=current.tasklist_id,
                task=current.task_id,
                body=body,
            ).execute()
        except Exception:
            raise RuntimeError("google_tasks_write_failed") from None
        return self._result(
            action.kind,
            self._item(raw, current.tasklist_id, current.tasklist_title),
        )

    def _tasklist_sync(self, name: str | None) -> tuple[str, str]:
        try:
            values = self._service().tasklists().list(maxResults=100).execute()
            items = values.get("items", [])
            if not isinstance(items, list) or not items:
                raise RuntimeError("google_tasklist_not_found")
            candidates = [
                item
                for item in items
                if isinstance(item, dict)
                and _safe_text(item.get("id"), 2_048)
                and _safe_text(item.get("title"), 1_024)
            ]
            if name is None:
                selected = candidates[:1]
            else:
                selected = [
                    item
                    for item in candidates
                    if item["title"].casefold() == name.strip().casefold()
                ]
            if len(selected) != 1:
                raise RuntimeError(
                    "google_tasklist_not_found"
                    if not selected
                    else "google_tasklist_ambiguous"
                )
            return selected[0]["id"], selected[0]["title"]
        except RuntimeError:
            raise
        except Exception:
            raise RuntimeError("google_tasks_read_failed") from None

    def _items_sync(
        self, tasklist_id: str, tasklist_title: str
    ) -> tuple[GoogleTaskItem, ...]:
        try:
            values = self._service().tasks().list(
                tasklist=tasklist_id,
                maxResults=100,
                showCompleted=True,
                showHidden=True,
            ).execute()
            items = values.get("items", [])
            if not isinstance(items, list):
                raise ValueError
            return tuple(
                self._item(item, tasklist_id, tasklist_title) for item in items
            )
        except (RuntimeError, ValueError):
            raise
        except Exception:
            raise RuntimeError("google_tasks_read_failed") from None

    def _resolve_unique_sync(self, action: GoogleTaskAction) -> GoogleTaskItem:
        tasklist_id, title = self._tasklist_sync(action.list_name)
        target = (action.target or "").strip()
        selected = [
            item
            for item in self._items_sync(tasklist_id, title)
            if item.title.casefold() == target.casefold()
        ]
        if not selected:
            raise RuntimeError("google_task_not_found")
        if len(selected) != 1:
            raise RuntimeError("google_task_ambiguous")
        return selected[0]

    def _find_marker_sync(
        self,
        tasklist_id: str,
        tasklist_title: str,
        key_marker: str,
        exact_marker: str,
    ) -> GoogleTaskItem | None:
        try:
            values = self._service().tasks().list(
                tasklist=tasklist_id,
                maxResults=100,
                showCompleted=True,
                showHidden=True,
            ).execute()
            raw_items = values.get("items", [])
            if not isinstance(raw_items, list):
                raise ValueError
            matched = [
                item
                for item in raw_items
                if isinstance(item, dict)
                and key_marker in str(item.get("notes", ""))
            ]
            if len(matched) > 1:
                raise RuntimeError("google_tasks_idempotency_conflict")
            if not matched:
                return None
            if exact_marker not in str(matched[0].get("notes", "")):
                raise RuntimeError("google_tasks_idempotency_conflict")
            return self._item(matched[0], tasklist_id, tasklist_title)
        except (RuntimeError, ValueError):
            raise
        except Exception:
            raise RuntimeError("google_tasks_read_failed") from None

    def _delete_sync(self, tasklist_id: str, task_id: str) -> None:
        try:
            self._service().tasks().delete(
                tasklist=tasklist_id, task=task_id
            ).execute()
        except Exception as error:
            if getattr(getattr(error, "resp", None), "status", None) != 404:
                raise RuntimeError("google_tasks_delete_failed") from None

    @staticmethod
    def _item(
        raw: object, tasklist_id: str, tasklist_title: str
    ) -> GoogleTaskItem:
        if not isinstance(raw, dict):
            raise RuntimeError("google_tasks_response_invalid")
        try:
            due = raw.get("due")
            return GoogleTaskItem(
                task_id=raw["id"],
                tasklist_id=tasklist_id,
                tasklist_title=tasklist_title,
                title=raw["title"],
                status=raw.get("status", "needsAction"),
                due=None if not due else date.fromisoformat(str(due)[:10]),
                notes=raw.get("notes"),
            )
        except Exception:
            raise RuntimeError("google_tasks_response_invalid") from None

    @staticmethod
    def _result(
        kind: GoogleTaskActionKind, item: GoogleTaskItem
    ) -> GoogleTaskResult:
        verb = {
            GoogleTaskActionKind.CREATE: "создана",
            GoogleTaskActionKind.UPDATE: "обновлена",
            GoogleTaskActionKind.COMPLETE: "выполнена",
        }.get(kind, "готова")
        return GoogleTaskResult(
            message=f"Задача «{item.title}» {verb}.",
            item=item,
        )


def _validate_key(value: str) -> None:
    if (
        not isinstance(value, str)
        or not value.startswith("sha256:")
        or len(value) != 71
    ):
        raise ValueError("Google Tasks idempotency key is invalid")


def _marker(key: str) -> str:
    return f"[nobus-id:{hashlib.sha256(key.encode()).hexdigest()}]"


def _notes(value: str | None, marker: str) -> str:
    return f"{(value or '').strip()}\n\n{marker}".strip()


def _safe_text(value: object, limit: int) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and "\x00" not in value
        and len(value) <= limit
    )
