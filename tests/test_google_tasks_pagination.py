from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

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


class _PagedTaskLists:
    def __init__(self, *, second_page: bool = False) -> None:
        self._second_page = second_page

    def list(self, *, pageToken: str | None = None, **_: object) -> _Request:
        if self._second_page and pageToken is None:
            return _Request(
                {
                    "items": [{"id": "other", "title": "Другое"}],
                    "nextPageToken": "page-2",
                }
            )
        return _Request({"items": [{"id": "list-1", "title": "Основные"}]})


class _PagedTasks:
    def __init__(self) -> None:
        self.items: list[dict[str, object]] = []
        self.insert_calls = 0
        self.marker_on_second_page = False

    def list(self, *, pageToken: str | None = None, **_: object) -> _Request:
        if self.marker_on_second_page:
            if pageToken is None:
                fillers = [
                    {
                        "id": f"filler-{index}",
                        "title": f"Фоновая {index}",
                        "status": "needsAction",
                    }
                    for index in range(100)
                ]
                return _Request(
                    {"items": fillers, "nextPageToken": "task-page-2"}
                )
            return _Request({"items": self.items})
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


class _Service:
    def __init__(self, *, list_on_second_page: bool = False) -> None:
        self.task_lists = _PagedTaskLists(second_page=list_on_second_page)
        self.task_items = _PagedTasks()

    def tasklists(self) -> _PagedTaskLists:
        return self.task_lists

    def tasks(self) -> _PagedTasks:
        return self.task_items


def _client(service: _Service) -> GoogleTasksClient:
    return GoogleTasksClient(
        Path("C:/unused/google-token.json"),
        service_factory=lambda: service,
    )


def _key() -> str:
    return "sha256:" + ("a" * 64)


@pytest.mark.asyncio
async def test_idempotency_marker_is_found_on_second_page() -> None:
    service = _Service()
    client = _client(service)
    action = GoogleTaskAction(
        kind=GoogleTaskActionKind.CREATE,
        title="Подготовить отчёт",
    )

    first = await client.execute(action, idempotency_key=_key())
    service.task_items.marker_on_second_page = True
    replay = await client.execute(action, idempotency_key=_key())

    assert replay.item == first.item
    assert service.task_items.insert_calls == 1


@pytest.mark.asyncio
async def test_named_tasklist_is_found_on_second_page() -> None:
    service = _Service(list_on_second_page=True)
    client = _client(service)

    result = await client.execute(
        GoogleTaskAction(
            kind=GoogleTaskActionKind.CREATE,
            title="Позвонить",
            list_name="Основные",
        ),
        idempotency_key=_key(),
    )

    assert result.item is not None
    assert result.item.tasklist_id == "list-1"
    assert service.task_items.insert_calls == 1


@pytest.mark.asyncio
async def test_repeated_pagination_token_fails_closed() -> None:
    class _LoopingTaskLists:
        def list(
            self, *, pageToken: str | None = None, **_: object
        ) -> _Request:
            return _Request(
                {"items": [], "nextPageToken": pageToken or "same"}
            )

    service = _Service()
    service.task_lists = _LoopingTaskLists()

    with pytest.raises(
        RuntimeError, match="google_tasks_pagination_invalid"
    ):
        await _client(service).execute(
            GoogleTaskAction(
                kind=GoogleTaskActionKind.CREATE,
                title="Не создавать",
            ),
            idempotency_key=_key(),
        )

    assert service.task_items.insert_calls == 0
