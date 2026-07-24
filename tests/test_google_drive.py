from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.integrations.google_drive import (
    GoogleDriveAction,
    GoogleDriveActionKind,
    GoogleDriveClient,
)


class _Request:
    def __init__(self, value: object) -> None:
        self.value = value

    def execute(self) -> object:
        return deepcopy(self.value)


class _Downloader:
    def __init__(self, sink: object, request: _Request, _: int) -> None:
        self._sink = sink
        self._request = request
        self._done = False

    def next_chunk(self, *, num_retries: int) -> tuple[None, bool]:
        assert num_retries == 2
        if not self._done:
            value = self._request.execute()
            assert isinstance(value, bytes)
            self._sink.write(value)
            self._done = True
        return None, True


def _download_factory(
    sink: object, request: _Request, chunksize: int
) -> _Downloader:
    return _Downloader(sink, request, chunksize)


class _Files:
    def __init__(self) -> None:
        self.values: list[dict[str, object]] = []
        self.contents: dict[str, bytes] = {}
        self.queries: list[str] = []
        self.exports: list[tuple[str, str]] = []

    def list(self, *, q: str, **_: object) -> _Request:
        self.queries.append(q)
        return _Request({"files": self.values})

    def get_media(self, *, fileId: str) -> _Request:
        return _Request(self.contents[fileId])

    def export_media(self, *, fileId: str, mimeType: str) -> _Request:
        self.exports.append((fileId, mimeType))
        return _Request(self.contents[fileId])


class _Service:
    def __init__(self) -> None:
        self.boundary = _Files()

    def files(self) -> _Files:
        return self.boundary


def _client(service: _Service) -> GoogleDriveClient:
    return GoogleDriveClient(
        Path("C:/unused/google-token.json"),
        service_factory=lambda: service,
        downloader_factory=_download_factory,
    )


@pytest.mark.asyncio
async def test_search_and_exact_binary_download() -> None:
    service = _Service()
    service.boundary.values.append(
        {
            "id": "file-1",
            "name": "Отчёт.pdf",
            "mimeType": "application/pdf",
            "size": "8",
            "modifiedTime": "2026-07-24T10:00:00Z",
        }
    )
    service.boundary.contents["file-1"] = b"%PDF-1.4"
    client = _client(service)

    listed = await client.execute(
        GoogleDriveAction(
            kind=GoogleDriveActionKind.SEARCH,
            query="Отчёт",
        )
    )
    downloaded = await client.execute(
        GoogleDriveAction(
            kind=GoogleDriveActionKind.DOWNLOAD,
            query="Отчёт.pdf",
        )
    )

    assert "Отчёт.pdf" in listed.message
    assert downloaded.filename == "Отчёт.pdf"
    assert downloaded.content == b"%PDF-1.4"
    assert "trashed = false" in service.boundary.queries[0]


@pytest.mark.asyncio
async def test_google_document_is_exported_to_docx() -> None:
    service = _Service()
    service.boundary.values.append(
        {
            "id": "doc-1",
            "name": "План",
            "mimeType": "application/vnd.google-apps.document",
        }
    )
    service.boundary.contents["doc-1"] = b"docx-bytes"
    client = _client(service)

    result = await client.execute(
        GoogleDriveAction(
            kind=GoogleDriveActionKind.DOWNLOAD,
            query="План",
        )
    )

    assert result.filename == "План.docx"
    assert result.content == b"docx-bytes"
    assert service.boundary.exports == [
        (
            "doc-1",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    ]


@pytest.mark.asyncio
async def test_ambiguous_download_is_rejected() -> None:
    service = _Service()
    service.boundary.values.extend(
        [
            {"id": "1", "name": "План A", "mimeType": "text/plain"},
            {"id": "2", "name": "План B", "mimeType": "text/plain"},
        ]
    )
    client = _client(service)

    with pytest.raises(RuntimeError, match="ambiguous"):
        await client.execute(
            GoogleDriveAction(
                kind=GoogleDriveActionKind.DOWNLOAD,
                query="План",
            )
        )


def test_drive_contract_is_strict() -> None:
    with pytest.raises(ValidationError):
        GoogleDriveAction.model_validate(
            {"kind": "search", "query": "Файл", "extra": True}
        )
    with pytest.raises(ValidationError):
        GoogleDriveAction(kind=GoogleDriveActionKind.DOWNLOAD)
