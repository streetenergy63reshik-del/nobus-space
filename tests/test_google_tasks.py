from __future__ import annotations

from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.integrations.google_tasks import (
    GoogleTaskAction,
    GoogleTaskActionKind,
    GoogleTasksClient,
)


class _Request:
    def __init__(self, value: object) -> None:
        self._value = value

    def execute(self) -> object:
        return deepcopy(self._value)


class _TaskLists:
    def list(self, **_: object) -> _Request:
        return _Request({"items": [{"id": "list-1", "title": "Основные"}]})


class _Tasks:
    def __init__(self) -> None:
        self.items: list[dict[str, object]] = []
        self.insert_calls = 0
        self.patch_calls = 0
        self.delete_calls = 0

    def list(self, **_: object) -> _Request:
        return _Request({"items": self.items})

    def insert(self, *, tasklist: str, body: dict[str, object]) -> _Request:
        assert tasklist == "list-1"
        self.insert_calls += 1
        item = {
            "id": f"task-{self.insert_calls}",
            "title": body["title"],
            "status": "needsAction",
            **body,
        }
        self.items.append(item)
        return _Request(item)

    def patch(
        self, *, tasklist: str, task: str, body: dict[str, object]
    ) -> _Request:
        assert tasklist == "list-1"
        self.patch_calls += 1
        selected = next(item for item in self.items if item["id"] == task)
        selected.update(body)
        return _Request(selected)

    def delete(self, *, tasklist: str, task: str) -> _Request:
        assert tasklist == "list-1"
        self.delete_calls += 1
        self.items = [item for item in self.items if item["id"] != task]
        return _Request({})


class _Service:
    def __init__(self) -> None:
        self.task_lists = _TaskLists()
        self.task_items = _Tasks()

    def tasklists(self) -> _TaskLists:
        return self.task_lists

    def tasks(self) -> _Tasks:
        return self.task_items


def _client(service: _Service) -> GoogleTasksClient:
    return GoogleTasksClient(
        Path("C:/unused/google-token.json"),
        service_factory=lambda: service,
    )


def _key(label: str) -> str:
    return "sha256:" + label.ljust(64, "0")[:64]


@pytest.mark.asyncio
async def test_create_is_idempotent_after_result_delivery_failure() -> None:
    service = _Service()
    client = _client(service)
    action = GoogleTaskAction(
        kind=GoogleTaskActionKind.CREATE,
        title="Подготовить отчёт",
        notes="К пятнице",
        due=date(2026, 7, 31),
    )

    first = await client.execute(action, idempotency_key=_key("a"))
    replay = await client.execute(action, idempotency_key=_key("a"))

    assert first.item == replay.item
    assert service.task_items.insert_calls == 1
    assert first.item is not None
    assert first.item.notes is not None
    assert "К пятнице" in first.item.notes


@pytest.mark.asyncio
async def test_update_preserves_notes_and_replay_does_not_patch_twice() -> None:
    service = _Service()
    service.task_items.items.append(
        {
            "id": "task-existing",
            "title": "Старое имя",
            "status": "needsAction",
            "notes": "Важный контекст",
        }
    )
    client = _client(service)
    action = GoogleTaskAction(
        kind=GoogleTaskActionKind.UPDATE,
        target="Старое имя",
        title="Новое имя",
    )

    first = await client.execute(action, idempotency_key=_key("b"))
    replay = await client.execute(action, idempotency_key=_key("b"))

    assert first.item == replay.item
    assert service.task_items.patch_calls == 1
    assert first.item is not None
    assert first.item.title == "Новое имя"
    assert first.item.notes is not None
    assert "Важный контекст" in first.item.notes


@pytest.mark.asyncio
async def test_complete_preserves_notes() -> None:
    service = _Service()
    service.task_items.items.append(
        {
            "id": "task-existing",
            "title": "Позвонить",
            "status": "needsAction",
            "notes": "Клиент А",
        }
    )
    client = _client(service)

    result = await client.execute(
        GoogleTaskAction(
            kind=GoogleTaskActionKind.COMPLETE,
            target="Позвонить",
        ),
        idempotency_key=_key("c"),
    )

    assert result.item is not None
    assert result.item.status == "completed"
    assert result.item.notes is not None
    assert "Клиент А" in result.item.notes


@pytest.mark.asyncio
async def test_delete_requires_separate_boundary() -> None:
    service = _Service()
    service.task_items.items.append(
        {
            "id": "task-existing",
            "title": "Удалить меня",
            "status": "needsAction",
        }
    )
    client = _client(service)
    action = GoogleTaskAction(
        kind=GoogleTaskActionKind.DELETE,
        target="Удалить меня",
    )

    with pytest.raises(ValueError, match="another boundary"):
        await client.execute(action, idempotency_key=_key("d"))

    item = await client.resolve_delete(action)
    await client.delete_task(item.tasklist_id, item.task_id)

    assert service.task_items.delete_calls == 1
    assert not service.task_items.items


@pytest.mark.asyncio
async def test_ambiguous_task_is_rejected_before_write() -> None:
    service = _Service()
    service.task_items.items.extend(
        [
            {"id": "one", "title": "Дубль", "status": "needsAction"},
            {"id": "two", "title": "дубль", "status": "needsAction"},
        ]
    )
    client = _client(service)

    with pytest.raises(RuntimeError, match="google_task_ambiguous"):
        await client.execute(
            GoogleTaskAction(
                kind=GoogleTaskActionKind.COMPLETE,
                target="Дубль",
            ),
            idempotency_key=_key("e"),
        )

    assert service.task_items.patch_calls == 0


def test_contract_is_strict_and_delete_needs_target() -> None:
    with pytest.raises(ValidationError):
        GoogleTaskAction.model_validate(
            {"kind": "create", "title": "Задача", "unexpected": True}
        )
    with pytest.raises(ValidationError):
        GoogleTaskAction(kind=GoogleTaskActionKind.DELETE)
    with pytest.raises(ValidationError):
        GoogleTaskAction(kind=GoogleTaskActionKind.UPDATE, target="Задача")


@pytest.mark.asyncio
async def test_invalid_idempotency_key_is_rejected_before_api() -> None:
    service = _Service()
    client = _client(service)

    with pytest.raises(ValueError, match="idempotency"):
        await client.execute(
            GoogleTaskAction(
                kind=GoogleTaskActionKind.CREATE,
                title="Задача",
            ),
            idempotency_key="unsafe",
        )

    assert service.task_items.insert_calls == 0
