from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType

import pytest

from tests.test_google_drive import _download_factory

from src.integrations import (
    GoogleDriveAction,
    GoogleDriveActionKind,
    GoogleDriveClient,
)


class _Request:
    def __init__(self, value: object) -> None:
        self._value = value

    def execute(self) -> object:
        return deepcopy(self._value)


class _PagedFiles:
    def __init__(self) -> None:
        self.tokens: list[str | None] = []

    def list(self, *, pageToken: str | None = None, **_: object) -> _Request:
        self.tokens.append(pageToken)
        if pageToken is None:
            return _Request(
                {
                    "files": [
                        {
                            "id": "other",
                            "name": "Другой.docx",
                            "mimeType": "application/octet-stream",
                            "size": "3",
                        }
                    ],
                    "nextPageToken": "page-2",
                }
            )
        return _Request(
            {
                "files": [
                    {
                        "id": "target",
                        "name": "Отчёт.docx",
                        "mimeType": "application/octet-stream",
                        "size": "3",
                    }
                ]
            }
        )

    def get_media(self, *, fileId: str) -> _Request:
        assert fileId == "target"
        return _Request(b"doc")


class _Service:
    def __init__(self) -> None:
        self.files_api = _PagedFiles()

    def files(self) -> _PagedFiles:
        return self.files_api


@pytest.mark.asyncio
async def test_exact_drive_file_is_found_on_second_page() -> None:
    service = _Service()
    client = GoogleDriveClient(
        Path("C:/unused/google-token.json"),
        service_factory=lambda: service,
        downloader_factory=_download_factory,
    )

    result = await client.execute(
        GoogleDriveAction(
            kind=GoogleDriveActionKind.DOWNLOAD,
            query="Отчёт.docx",
        )
    )

    assert result.content == b"doc"
    assert result.filename == "Отчёт.docx"
    assert service.files_api.tokens == [None, "page-2"]


def _module(name: str) -> ModuleType:
    value = ModuleType(name)
    value.__path__ = []  # type: ignore[attr-defined]
    return value


def test_saved_drive_grant_is_checked_without_scope_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = tmp_path / "token.json"
    token.write_text("{}", encoding="utf-8")
    calls: list[tuple[object, ...]] = []

    class Credentials:
        scopes = ("https://www.googleapis.com/auth/calendar",)
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

    client = GoogleDriveClient(token)
    with pytest.raises(RuntimeError, match="credentials_unavailable"):
        client._service()

    assert calls == [()]


@pytest.mark.asyncio
async def test_large_drive_file_is_searchable_but_not_downloaded() -> None:
    service = _Service()
    media_called = False

    def one_file(**_: object) -> _Request:
        return _Request(
            {
                "files": [
                    {
                        "id": "large",
                        "name": "large.bin",
                        "mimeType": "application/octet-stream",
                        "size": str(50 * 1024 * 1024),
                    }
                ]
            }
        )

    def get_media(**_: object) -> _Request:
        nonlocal media_called
        media_called = True
        return _Request(b"must not download")

    service.files_api.list = one_file  # type: ignore[method-assign]
    service.files_api.get_media = get_media  # type: ignore[method-assign]
    client = GoogleDriveClient(
        Path("C:/unused/google-token.json"),
        service_factory=lambda: service,
        downloader_factory=_download_factory,
    )

    search = await client.execute(
        GoogleDriveAction(
            kind=GoogleDriveActionKind.SEARCH,
            query="large.bin",
        )
    )
    assert "large.bin" in search.message

    with pytest.raises(RuntimeError, match="file_too_large"):
        await client.execute(
            GoogleDriveAction(
                kind=GoogleDriveActionKind.DOWNLOAD,
                query="large.bin",
            )
        )
    assert media_called is False


@pytest.mark.asyncio
async def test_streaming_download_stops_before_exceeding_memory_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.integrations.google_drive as drive_module

    service = _Service()
    service.files_api = _PagedFiles()
    service.files_api.tokens = []
    original_list = service.files_api.list

    def one_file(**values: object) -> _Request:
        if values.get("pageToken") is not None:
            return original_list(**values)
        return _Request(
            {
                "files": [
                    {
                        "id": "target",
                        "name": "Большой документ",
                        "mimeType": "application/vnd.google-apps.document",
                    }
                ]
            }
        )

    service.files_api.list = one_file  # type: ignore[method-assign]
    service.files_api.export_media = lambda **_: _Request(b"unused")  # type: ignore[attr-defined]
    captured: list[object] = []

    class _OversizeDownloader:
        def __init__(self, sink: object) -> None:
            self._sink = sink
            self._step = 0

        def next_chunk(self, *, num_retries: int) -> tuple[None, bool]:
            assert num_retries == 2
            self._step += 1
            self._sink.write(b"1234" if self._step == 1 else b"5")
            return None, False

    def factory(sink: object, request: object, chunksize: int) -> object:
        assert request is not None
        assert chunksize == 1024 * 1024
        captured.append(sink)
        return _OversizeDownloader(sink)

    monkeypatch.setattr(drive_module, "_MAX_DOWNLOAD_BYTES", 4)
    client = GoogleDriveClient(
        Path("C:/unused/google-token.json"),
        service_factory=lambda: service,
        downloader_factory=factory,
    )

    with pytest.raises(RuntimeError, match="file_too_large"):
        await client.execute(
            GoogleDriveAction(
                kind=GoogleDriveActionKind.DOWNLOAD,
                query="Большой документ",
            )
        )

    assert len(captured) == 1
    assert captured[0].size == 4
