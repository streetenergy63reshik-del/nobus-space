from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

from src.integrations import (
    GoogleTaskAction,
    GoogleTaskActionKind,
    GoogleTasksClient,
)
from tests.test_google_tasks import _Service, _client, _key


@pytest.mark.asyncio
async def test_same_key_with_different_payload_is_rejected() -> None:
    service = _Service()
    client = _client(service)
    key = _key("conflict")

    await client.execute(
        GoogleTaskAction(
            kind=GoogleTaskActionKind.CREATE,
            title="Первый вариант",
        ),
        idempotency_key=key,
    )
    with pytest.raises(RuntimeError, match="idempotency_conflict"):
        await client.execute(
            GoogleTaskAction(
                kind=GoogleTaskActionKind.CREATE,
                title="Другой вариант",
            ),
            idempotency_key=key,
        )

    assert service.task_items.insert_calls == 1


def _module(name: str) -> ModuleType:
    value = ModuleType(name)
    value.__path__ = []  # type: ignore[attr-defined]
    return value


def test_saved_tasks_grant_is_checked_without_scope_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = tmp_path / "token.json"
    token.write_text("{}", encoding="utf-8")
    calls: list[tuple[object, ...]] = []

    class Credentials:
        scopes = ("https://www.googleapis.com/auth/drive.readonly",)
        expired = False
        refresh_token = None
        valid = True

        @classmethod
        def from_authorized_user_file(
            cls, path: str, *values: object
        ) -> "Credentials":
            assert path == str(token)
            calls.append(values)
            return cls()

        def has_scopes(self, required: tuple[str, ...]) -> bool:
            return set(required).issubset(self.scopes)

    google = _module("google")
    oauth2 = _module("google.oauth2")
    credentials = _module("google.oauth2.credentials")
    credentials.Credentials = Credentials  # type: ignore[attr-defined]
    auth = _module("google.auth")
    transport = _module("google.auth.transport")
    requests = _module("google.auth.transport.requests")
    requests.Request = object  # type: ignore[attr-defined]
    api = _module("googleapiclient")
    discovery = _module("googleapiclient.discovery")
    discovery.build = lambda *args, **kwargs: object()  # type: ignore[attr-defined]
    for name, value in {
        "google": google,
        "google.oauth2": oauth2,
        "google.oauth2.credentials": credentials,
        "google.auth": auth,
        "google.auth.transport": transport,
        "google.auth.transport.requests": requests,
        "googleapiclient": api,
        "googleapiclient.discovery": discovery,
    }.items():
        monkeypatch.setitem(sys.modules, name, value)

    client = GoogleTasksClient(token)
    with pytest.raises(RuntimeError, match="credentials_unavailable"):
        client._service()

    assert calls == [()]
