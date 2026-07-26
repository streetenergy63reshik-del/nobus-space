from __future__ import annotations

import asyncio
import ssl
import time
import threading
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

    def execute(self, **_: object) -> object:
        return deepcopy(self._value)


class _TaskLists:
    def __init__(self, values: list[dict[str, str]]) -> None:
        self._values = values

    def list(self, **_: object) -> _Request:
        return _Request({"items": self._values})


class _Tasks:
    def __init__(self) -> None:
        self.items: list[dict[str, object]] = []
        self.insert_calls = 0

    def list(self, **_: object) -> _Request:
        return _Request({"items": self.items})

    def insert(self, *, tasklist: str, body: dict[str, object]) -> _Request:
        self.insert_calls += 1
        item = {
            "id": f"task-{self.insert_calls}",
            "status": "needsAction",
            **body,
        }
        self.items.append(item)
        return _Request(item)


class _Service:
    def __init__(self, values: list[dict[str, str]]) -> None:
        self.task_lists = _TaskLists(values)
        self.task_items = _Tasks()

    def tasklists(self) -> _TaskLists:
        return self.task_lists

    def tasks(self) -> _Tasks:
        return self.task_items


def _key(label: str) -> str:
    return "sha256:" + label.ljust(64, "0")[:64]


@pytest.mark.asyncio
async def test_voice_inflection_resolves_branded_tasklist() -> None:
    service = _Service([{"id": "pro", "title": "PROстранство"}])
    client = GoogleTasksClient(
        Path("C:/unused/google-token.json"),
        service_factory=lambda: service,
    )

    result = await client.execute(
        GoogleTaskAction(
            kind=GoogleTaskActionKind.CREATE,
            title="Тестовая задача",
            list_name="пространства",
        ),
        idempotency_key=_key("voice"),
    )

    assert result.item is not None
    assert result.item.tasklist_id == "pro"
    assert result.item.tasklist_title == "PROстранство"
    assert service.task_items.insert_calls == 1


@pytest.mark.asyncio
async def test_near_tasklist_match_fails_closed_for_write() -> None:
    service = _Service(
        [{"id": "neighbor", "title": "PROстранство2"}]
    )
    client = GoogleTasksClient(
        Path("C:/unused/google-token.json"),
        service_factory=lambda: service,
    )

    with pytest.raises(RuntimeError, match="google_tasklist_not_found"):
        await client.execute(
            GoogleTaskAction(
                kind=GoogleTaskActionKind.CREATE,
                title="Не создавать",
                list_name="PROстранство",
            ),
            idempotency_key=_key("near-neighbor"),
        )

    assert service.task_items.insert_calls == 0

@pytest.mark.asyncio
async def test_google_service_is_not_shared_with_worker_thread() -> None:
    class _ThreadBoundTaskLists:
        def __init__(self) -> None:
            self.owner = threading.get_ident()

        def list(self, **_: object) -> _Request:
            if threading.get_ident() != self.owner:
                raise RuntimeError("cross_thread_transport")
            return _Request({"items": [{"id": "one", "title": "Основные"}]})

    class _ThreadBoundService:
        def __init__(self) -> None:
            self._tasklists = _ThreadBoundTaskLists()

        def tasklists(self) -> _ThreadBoundTaskLists:
            return self._tasklists

        def tasks(self) -> _Tasks:
            return _Tasks()

    client = GoogleTasksClient(
        Path("C:/unused/google-token.json"),
        service_factory=_ThreadBoundService,
    )
    client._service()

    result = await client.execute(
        GoogleTaskAction(kind=GoogleTaskActionKind.LIST),
        idempotency_key=_key("thread"),
    )

    assert "Активных задач нет" in result.message


@pytest.mark.asyncio
async def test_transient_ssl_failure_discards_transport_before_durable_retry() -> None:
    healthy = _Service([{"id": "pro", "title": "PROстранство"}])

    class _FailingRequest:
        def execute(self, **_: object) -> object:
            raise ssl.SSLError("transient")

    class _FailingTaskLists:
        def list(self, **_: object) -> _FailingRequest:
            return _FailingRequest()

    class _FailingService:
        def tasklists(self) -> _FailingTaskLists:
            return _FailingTaskLists()

    services: list[object] = [_FailingService(), healthy]

    def factory() -> object:
        return services.pop(0)

    client = GoogleTasksClient(
        Path("C:/unused/google-token.json"),
        service_factory=factory,
    )
    action = GoogleTaskAction(
        kind=GoogleTaskActionKind.CREATE,
        title="Тестовая задача",
        list_name="пространства",
    )

    with pytest.raises(RuntimeError, match="google_tasks_read_failed"):
        await client.execute(action, idempotency_key=_key("retry"))

    result = await client.execute(action, idempotency_key=_key("retry"))

    assert result.item is not None
    assert result.item.tasklist_title == "PROстранство"
    assert healthy.task_items.insert_calls == 1
    assert services == []


@pytest.mark.asyncio
async def test_concurrent_same_key_create_is_serialized() -> None:
    barrier = threading.Barrier(2)

    class _BarrierTaskLists(_TaskLists):
        def list(self, **values: object) -> _Request:
            barrier.wait(timeout=2)
            return super().list(**values)

    class _SlowTasks(_Tasks):
        def insert(
            self, *, tasklist: str, body: dict[str, object]
        ) -> _Request:
            time.sleep(0.05)
            return super().insert(tasklist=tasklist, body=body)

    service = _Service([{"id": "pro", "title": "PROстранство"}])
    service.task_lists = _BarrierTaskLists(
        [{"id": "pro", "title": "PROстранство"}]
    )
    service.task_items = _SlowTasks()
    client = GoogleTasksClient(
        Path("C:/unused/google-token.json"),
        service_factory=lambda: service,
    )
    action = GoogleTaskAction(
        kind=GoogleTaskActionKind.CREATE,
        title="Одна задача",
        list_name="пространства",
    )

    first, second = await asyncio.gather(
        client.execute(action, idempotency_key=_key("same")),
        client.execute(action, idempotency_key=_key("same")),
    )

    assert first.item == second.item
    assert service.task_items.insert_calls == 1


@pytest.mark.asyncio
async def test_unknown_write_outcome_reconciles_marker_without_duplicate() -> None:
    class _CommitThenFailRequest(_Request):
        def execute(self, **_: object) -> object:
            raise ssl.SSLError("response lost after commit")

    class _UnknownOutcomeTasks(_Tasks):
        def insert(
            self, *, tasklist: str, body: dict[str, object]
        ) -> _Request:
            request = super().insert(tasklist=tasklist, body=body)
            if self.insert_calls == 1:
                return _CommitThenFailRequest(request._value)
            return request

    service = _Service([{"id": "pro", "title": "PROстранство"}])
    service.task_items = _UnknownOutcomeTasks()
    client = GoogleTasksClient(
        Path("C:/unused/google-token.json"),
        service_factory=lambda: service,
    )
    action = GoogleTaskAction(
        kind=GoogleTaskActionKind.CREATE,
        title="Одна задача",
        list_name="пространства",
    )

    with pytest.raises(RuntimeError, match="google_tasks_write_failed"):
        await client.execute(action, idempotency_key=_key("unknown"))
    replay = await client.execute(action, idempotency_key=_key("unknown"))

    assert replay.item is not None
    assert service.task_items.insert_calls == 1
