from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
import threading
import time

import pytest
from pydantic import ValidationError

from src.integrations.google_drive import (
    GoogleDriveAction,
    GoogleDriveActionKind,
    GoogleDriveClient,
    GoogleDriveFile,
)
from src.transport.telegram.bot_api import _safe_upload_filename


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
        assert num_retries == 0
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
        needle = q.split("name contains '", 1)[1].split("' and", 1)[0]
        values = [
            item
            for item in self.values
            if needle.casefold() in str(item["name"]).casefold()
        ]
        return _Request({"files": values})

    def get(self, *, fileId: str, **_: object) -> _Request:
        return _Request(next(item for item in self.values if item["id"] == fileId))

    def get_media(self, *, fileId: str) -> _Request:
        return _Request(self.contents[fileId])

    def export_media(self, *, fileId: str, mimeType: str) -> _Request:
        self.exports.append((fileId, mimeType))
        return _Request(self.contents[fileId])


class _Batch:
    def __init__(self, callback: object) -> None:
        self._callback = callback
        self._requests: list[tuple[str, _Request]] = []

    def add(self, request: _Request, *, request_id: str) -> None:
        self._requests.append((request_id, request))

    def execute(self) -> None:
        for request_id, request in self._requests:
            try:
                response = request.execute()
            except Exception as error:
                self._callback(request_id, None, error)
            else:
                self._callback(request_id, response, None)


class _Service:
    def __init__(self) -> None:
        self.boundary = _Files()

    def files(self) -> _Files:
        return self.boundary

    def new_batch_http_request(self, *, callback: object) -> _Batch:
        return _Batch(callback)


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
            "webViewLink": "https://drive.google.com/file/d/file-1/view",
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
    assert "https://drive.google.com/file/d/file-1/view" in listed.message
    assert downloaded.filename == "Отчёт.pdf"
    assert downloaded.content == b"%PDF-1.4"
    assert "trashed = false" in service.boundary.queries[0]


@pytest.mark.asyncio
async def test_fuzzy_search_resolves_natural_owner_title_and_returns_link() -> None:
    service = _Service()
    service.boundary.values.extend(
        [
            {
                "id": "target",
                "name": "HomeEdit_Юнит-экономика_v2.xlsx",
                "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "webViewLink": "https://drive.google.com/file/d/target/view",
            },
            {
                "id": "other",
                "name": "Юнит-экономика Ozon",
                "mimeType": "application/vnd.google-apps.spreadsheet",
                "webViewLink": "https://docs.google.com/spreadsheets/d/other/edit",
            },
        ]
    )
    client = _client(service)

    result = await client.execute(
        GoogleDriveAction(
            kind=GoogleDriveActionKind.SEARCH,
            query="Юнит экономика Ozon по бренду HomeEdit",
        )
    )

    assert "HomeEdit_Юнит-экономика_v2.xlsx" in result.message
    assert "Юнит-экономика Ozon" not in result.message
    assert "https://drive.google.com/file/d/target/view" in result.message
    assert len(service.boundary.queries) > 1

    link = await client.execute(
        GoogleDriveAction(
            kind=GoogleDriveActionKind.LINK,
            query="Юнит экономика Ozon по бренду HomeEdit",
        )
    )
    assert "HomeEdit_Юнит-экономика_v2.xlsx" in link.message
    assert "Юнит-экономика Ozon\n" not in link.message
    assert "https://drive.google.com/file/d/target/view" in link.message


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


@pytest.mark.parametrize(
    "link",
    (
        "https://evil.example/phish",
        "https://drive.google.com.evil/file",
        "https://drive.google.com@evil.example/file",
        "https://",
    ),
)
def test_drive_link_rejects_untrusted_or_malformed_hosts(link: str) -> None:
    with pytest.raises(ValidationError):
        GoogleDriveFile(
            file_id="file",
            name="File",
            mime_type="text/plain",
            web_view_link=link,
        )


@pytest.mark.asyncio
async def test_ambiguous_link_is_rejected_instead_of_guessing() -> None:
    service = _Service()
    service.boundary.values.extend(
        [
            {
                "id": "1",
                "name": "Plan A",
                "mimeType": "text/plain",
                "webViewLink": "https://drive.google.com/file/d/1/view",
            },
            {
                "id": "2",
                "name": "Plan B",
                "mimeType": "text/plain",
                "webViewLink": "https://drive.google.com/file/d/2/view",
            },
        ]
    )
    with pytest.raises(RuntimeError, match="ambiguous"):
        await _client(service).execute(
            GoogleDriveAction(kind=GoogleDriveActionKind.LINK, query="Plan")
        )


@pytest.mark.asyncio
async def test_fuzzy_search_has_a_small_request_budget() -> None:
    service = _Service()
    service.boundary.values.extend(
        {
            "id": str(index),
            "name": f"alpha beta gamma delta {index}",
            "mimeType": "text/plain",
        }
        for index in range(400)
    )
    await _client(service).execute(
        GoogleDriveAction(
            kind=GoogleDriveActionKind.SEARCH,
            query="alpha beta gamma delta missing",
        )
    )
    assert len(service.boundary.queries) <= 4



@pytest.mark.asyncio
async def test_paginated_initial_search_still_has_four_request_ceiling() -> None:
    class PaginatedFiles(_Files):
        def list(self, *, q: str, pageToken: str | None = None, **_: object):
            self.queries.append(q)
            if pageToken is None and len(self.queries) == 1:
                return _Request({"files": [], "nextPageToken": "next"})
            return _Request({"files": []})

    service = _Service()
    service.boundary = PaginatedFiles()
    await _client(service).execute(
        GoogleDriveAction(
            kind=GoogleDriveActionKind.SEARCH,
            query="alpha beta gamma delta missing",
        )
    )

    assert len(service.boundary.queries) == 4


@pytest.mark.asyncio
async def test_folder_hint_filters_by_ancestor() -> None:
    service = _Service()
    service.boundary.values.extend(
        [
            {
                "id": "folder-root",
                "name": "Пространство-Клиенты",
                "mimeType": "application/vnd.google-apps.folder",
            },
            {
                "id": "folder-client",
                "name": "HomeEdit",
                "mimeType": "application/vnd.google-apps.folder",
                "parents": ["folder-root"],
            },
            {
                "id": "target",
                "name": "Юнит экономика HomeEdit.xlsx",
                "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "parents": ["folder-client"],
                "webViewLink": "https://drive.google.com/file/d/target/view",
            },
            {
                "id": "foreign",
                "name": "Юнит экономика HomeEdit copy.xlsx",
                "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "parents": ["other-root"],
                "webViewLink": "https://drive.google.com/file/d/foreign/view",
            },
            {
                "id": "other-root",
                "name": "Другая папка",
                "mimeType": "application/vnd.google-apps.folder",
            },
        ]
    )
    result = await _client(service).execute(
        GoogleDriveAction(
            kind=GoogleDriveActionKind.LINK,
            query="Юнит экономика HomeEdit",
            folder="Пространство-Клиенты",
        )
    )
    assert "target/view" in result.message
    assert "foreign/view" not in result.message


@pytest.mark.asyncio
async def test_duplicate_folder_names_are_rejected_as_ambiguous() -> None:
    service = _Service()
    service.boundary.values.extend(
        [
            {
                "id": "folder-a",
                "name": "Clients",
                "mimeType": "application/vnd.google-apps.folder",
            },
            {
                "id": "folder-b",
                "name": "Clients",
                "mimeType": "application/vnd.google-apps.folder",
            },
            {
                "id": "file",
                "name": "Plan.xlsx",
                "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "parents": ["folder-a"],
                "webViewLink": "https://drive.google.com/file/d/file/view",
            },
        ]
    )
    with pytest.raises(RuntimeError, match="folder_ambiguous"):
        await _client(service).execute(
            GoogleDriveAction(
                kind=GoogleDriveActionKind.LINK,
                query="Plan",
                folder="Clients",
            )
        )


def test_download_loop_stops_before_next_chunk_when_cancelled() -> None:
    service = _Service()
    client = _client(service)
    stop = threading.Event()
    stop.set()
    with pytest.raises(RuntimeError, match="google_drive_timeout"):
        client._stream_download(
            _Request(b"content"),
            deadline=time.monotonic() + 1,
            stop=stop,
        )


@pytest.mark.asyncio
async def test_download_filename_is_safe_for_telegram() -> None:
    service = _Service()
    raw_name = "bad/name\\with\ncontrol\x7f.pdf"
    service.boundary.values.append(
        {
            "id": "unsafe",
            "name": raw_name,
            "mimeType": "application/pdf",
        }
    )
    service.boundary.contents["unsafe"] = b"%PDF"
    result = await _client(service).execute(
        GoogleDriveAction(
            kind=GoogleDriveActionKind.DOWNLOAD,
            query=raw_name,
        )
    )
    assert result.filename is not None
    assert result.filename.endswith(".pdf")
    assert "/" not in result.filename
    assert "\\" not in result.filename
    assert "\n" not in result.filename
    assert "\x7f" not in result.filename
    assert _safe_upload_filename(result.filename)
    assert len(result.filename.encode("utf-8")) <= 220

def test_drive_rejects_scalar_parents_in_google_response() -> None:
    with pytest.raises(RuntimeError, match="response_invalid"):
        _client(_Service())._file(
            {
                "id": "bad",
                "name": "bad.txt",
                "mimeType": "text/plain",
                "parents": "abc",
            }
        )


@pytest.mark.asyncio
async def test_folder_human_path_and_many_foreign_candidates_resolve_target() -> None:
    service = _Service()
    service.boundary.values.extend(
        [
            {
                "id": "root",
                "name": "PRO\u0441\u0442\u0440\u0430\u043d\u0441\u0442\u0432\u043e",
                "mimeType": "application/vnd.google-apps.folder",
            },
            {
                "id": "clients",
                "name": "\u041a\u041b\u0418\u0415\u041d\u0422\u042b",
                "mimeType": "application/vnd.google-apps.folder",
                "parents": ["root"],
            },
            {
                "id": "homeedit",
                "name": "HomeEdit",
                "mimeType": "application/vnd.google-apps.folder",
                "parents": ["clients"],
            },
        ]
    )
    for index in range(39):
        folder_id = f"foreign-folder-{index}"
        service.boundary.values.extend(
            [
                {
                    "id": folder_id,
                    "name": f"Foreign {index}",
                    "mimeType": "application/vnd.google-apps.folder",
                },
                {
                    "id": f"foreign-{index}",
                    "name": f"Unit economics HomeEdit copy {index}.xlsx",
                    "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "parents": [folder_id],
                    "webViewLink": f"https://drive.google.com/file/d/foreign-{index}/view",
                },
            ]
        )
    service.boundary.values.append(
        {
            "id": "target",
            "name": "Unit economics HomeEdit.xlsx",
            "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "parents": ["homeedit"],
            "webViewLink": "https://drive.google.com/file/d/target/view",
        }
    )

    result = await _client(service).execute(
        GoogleDriveAction(
            kind=GoogleDriveActionKind.LINK,
            query="Unit economics HomeEdit",
            folder="PRO\u0441\u0442\u0440\u0430\u043d\u0441\u0442\u0432\u043e -> \u041a\u041b\u0418\u0415\u041d\u0422\u042b",
        )
    )

    assert "target/view" in result.message
    assert "foreign" not in result.message


def test_search_stop_is_checked_after_transport_returns() -> None:
    stop = threading.Event()

    class StopRequest:
        def execute(self) -> object:
            stop.set()
            return {"files": [], "nextPageToken": "again"}

    class StopFiles:
        calls = 0

        def list(self, **_: object) -> StopRequest:
            self.calls += 1
            return StopRequest()

    class StopService:
        def __init__(self) -> None:
            self.boundary = StopFiles()

        def files(self) -> StopFiles:
            return self.boundary

    service = StopService()
    client = GoogleDriveClient(
        Path("C:/unused/google-token.json"),
        service_factory=lambda: service,
        downloader_factory=_download_factory,
    )
    with pytest.raises(RuntimeError, match="google_drive_timeout"):
        client._search_term_sync(
            "x",
            time.monotonic() + 1,
            [40],
            stop,
        )
    assert service.boundary.calls == 1


@pytest.mark.asyncio
async def test_shared_google_transport_is_not_used_concurrently() -> None:
    guard = threading.Lock()
    active = 0
    overlap = False

    class SlowRequest:
        def __init__(self, query: str) -> None:
            self.query = query

        def execute(self) -> object:
            nonlocal active, overlap
            with guard:
                active += 1
                overlap = overlap or active > 1
            time.sleep(0.05)
            with guard:
                active -= 1
            return {
                "files": [
                    {
                        "id": self.query,
                        "name": self.query,
                        "mimeType": "text/plain",
                    }
                ]
            }

    class SlowFiles:
        def list(self, *, q: str, **_: object) -> SlowRequest:
            query = q.split("name contains '", 1)[1].split("' and", 1)[0]
            return SlowRequest(query)

    class SlowService:
        def files(self) -> SlowFiles:
            return SlowFiles()

    client = GoogleDriveClient(
        Path("C:/unused/google-token.json"),
        service_factory=SlowService,
        downloader_factory=_download_factory,
    )
    first, second = await asyncio.gather(
        client.execute(GoogleDriveAction(kind=GoogleDriveActionKind.SEARCH, query="one")),
        client.execute(GoogleDriveAction(kind=GoogleDriveActionKind.SEARCH, query="two")),
    )

    assert "one" in first.message
    assert "two" in second.message
    assert overlap is False
@pytest.mark.asyncio
async def test_explicit_folder_never_falls_back_to_foreign_unique_file() -> None:
    service = _Service()
    service.boundary.values.append(
        {
            "id": "unique",
            "name": "HomeEdit unit economics.xlsx",
            "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "parents": ["actual-project-folder"],
            "webViewLink": "https://drive.google.com/file/d/unique/view",
        }
    )

    with pytest.raises(RuntimeError, match="file_not_found"):
        await _client(service).execute(
            GoogleDriveAction(
                kind=GoogleDriveActionKind.LINK,
                query="Unit economics по бренду HomeEdit",
                folder="Human approximate alias",
            )
        )

def test_folder_name_alias_is_exact_not_suffix_based() -> None:
    assert GoogleDriveClient._folder_name_matches(
        "PRO\u0441\u0442\u0440\u0430\u043d\u0441\u0442\u0432\u043e", "\u041f\u0440\u043e\u0441\u0442\u0440\u0430\u043d\u0441\u0442\u0432\u043e"
    )
    assert not GoogleDriveClient._folder_name_matches("OtherClients", "Clients")



def test_brand_match_accepts_exact_separator_alias_only() -> None:
    assert GoogleDriveClient._name_contains_brand(
        "Home_edit_ЮНИТКА_OZON.xlsx",
        "HomeEdit",
    )
    assert not GoogleDriveClient._name_contains_brand(
        "HomeEditorial_OZON.xlsx",
        "HomeEdit",
    )


def test_scoped_token_fallback_ignores_unrelated_initial_match() -> None:
    service = _Service()
    client = _client(service)
    foreign = GoogleDriveFile(
        file_id="foreign",
        name="Юнит-экономика Ozon",
        mime_type="application/vnd.google-apps.spreadsheet",
    )
    desired = GoogleDriveFile(
        file_id="desired",
        name="Home_edit_ЮНИТКА_OZON.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        parents=("homeedit",),
    )
    full_query = "юнит-экономика Ozon по бренду HomeEdit"

    def search_term(query: str, *args: object, **kwargs: object):
        if query == full_query:
            return (foreign,)
        if query.casefold() == "юнит":
            return (foreign, desired)
        return ()

    client._search_term_sync = search_term
    client._filter_folder_sync = (
        lambda values, folder, *args: tuple(
            item for item in values if item.file_id == "desired"
        )
    )

    assert client._search_sync(full_query, "PROстранство — Клиенты") == (
        desired,
    )



def test_explicit_path_cannot_be_shadowed_by_literal_folder_name() -> None:
    service = _Service()
    client = _client(service)
    captured: list[str] = []

    def search_term(query: str, *args: object, **kwargs: object):
        captured.append(query)
        if query == "Root — Clients":
            return (
                GoogleDriveFile(
                    file_id="impostor",
                    name="Root — Clients",
                    mime_type="application/vnd.google-apps.folder",
                ),
            )
        return ()

    def candidates(
        segment: str,
        *args: object,
        **kwargs: object,
    ) -> tuple[GoogleDriveFile, ...]:
        if segment == "Root":
            return (
                GoogleDriveFile(
                    file_id="root",
                    name="Root",
                    mime_type="application/vnd.google-apps.folder",
                ),
            )
        return (
            GoogleDriveFile(
                file_id="clients",
                name="Clients",
                mime_type="application/vnd.google-apps.folder",
                parents=("root",),
            ),
        )

    client._search_term_sync = search_term
    client._folder_candidates_sync = candidates
    client._is_within_folder_sync = (
        lambda item, folder_ids, *args, **kwargs: bool(
            folder_ids.intersection(item.parents)
        )
    )

    result = client._resolve_folder_ids_sync(
        "Root — Clients",
        time.monotonic() + 1,
        [10],
        threading.Event(),
    )

    assert result == {"clients"}
    assert "Root — Clients" not in captured


def test_hyphen_inside_single_folder_name_is_not_a_path_separator() -> None:
    service = _Service()
    client = _client(service)
    folder = GoogleDriveFile(
        file_id="home-edit",
        name="Home-Edit",
        mime_type="application/vnd.google-apps.folder",
    )
    client._search_term_sync = lambda query, *args, **kwargs: (
        (folder,) if query == "Home-Edit" else ()
    )

    assert client._resolve_folder_ids_sync(
        "Home-Edit",
        time.monotonic() + 1,
        [10],
        threading.Event(),
    ) == {"home-edit"}


def test_folder_path_accepts_unicode_dash_separator() -> None:
    service = _Service()
    client = _client(service)
    captured: list[str] = []

    def candidates(
        segment: str,
        deadline: float,
        budget: list[int],
        stop: threading.Event,
    ) -> tuple[GoogleDriveFile, ...]:
        captured.append(segment)
        if segment == "PROстранство":
            return (
                GoogleDriveFile(
                    file_id="root",
                    name="PROстранство",
                    mime_type="application/vnd.google-apps.folder",
                ),
            )
        return (
            GoogleDriveFile(
                file_id="clients",
                name="Клиенты",
                mime_type="application/vnd.google-apps.folder",
                parents=("root",),
            ),
        )

    client._search_term_sync = lambda *args, **kwargs: ()
    client._folder_candidates_sync = candidates
    client._is_within_folder_sync = (
        lambda item, folder_ids, *args, **kwargs: bool(
            folder_ids.intersection(item.parents)
        )
    )

    result = client._resolve_folder_ids_sync(
        "PROстранство — Клиенты",
        time.monotonic() + 1,
        [10],
        threading.Event(),
    )

    assert result == {"clients"}
    assert captured == ["PROстранство", "Клиенты"]


@pytest.mark.asyncio
async def test_unique_result_never_bypasses_unrelated_folder_without_brand() -> None:
    service = _Service()
    service.boundary.values.append(
        {
            "id": "unrelated",
            "name": "Quarterly Report Q4.xlsx",
            "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "parents": ["unrelated-secret-folder"],
            "webViewLink": "https://drive.google.com/file/d/unrelated/view",
        }
    )

    with pytest.raises(RuntimeError, match="file_not_found"):
        await _client(service).execute(
            GoogleDriveAction(
                kind=GoogleDriveActionKind.LINK,
                query="Quarterly Report Q4",
                folder="Expected Client Folder",
            )
        )

@pytest.mark.asyncio
async def test_short_brand_substring_never_bypasses_folder() -> None:
    service = _Service()
    service.boundary.values.append(
        {
            "id": "unrelated",
            "name": "HomeEdit unit economics.xlsx",
            "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "parents": ["unrelated-secret-folder"],
            "webViewLink": "https://drive.google.com/file/d/unrelated/view",
        }
    )

    with pytest.raises(RuntimeError, match="file_not_found"):
        await _client(service).execute(
            GoogleDriveAction(
                kind=GoogleDriveActionKind.LINK,
                query="Unit economics по бренду IT",
                folder="Expected Client Folder",
            )
        )


@pytest.mark.asyncio
async def test_deep_foreign_candidates_do_not_hide_direct_folder_target() -> None:
    service = _Service()
    service.boundary.values.append(
        {
            "id": "target-folder",
            "name": "Clients",
            "mimeType": "application/vnd.google-apps.folder",
        }
    )
    for index in range(39):
        parent = f"foreign-{index}-0"
        service.boundary.values.append(
            {
                "id": f"foreign-file-{index}",
                "name": f"Invoice {index}.xlsx",
                "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "parents": [parent],
                "webViewLink": f"https://drive.google.com/file/d/foreign-{index}/view",
            }
        )
        for depth in range(7):
            next_parent = f"foreign-{index}-{depth + 1}"
            service.boundary.values.append(
                {
                    "id": parent,
                    "name": f"Foreign {index} depth {depth}",
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": [next_parent] if depth < 6 else [],
                }
            )
            parent = next_parent
    service.boundary.values.append(
        {
            "id": "target",
            "name": "Invoice target.xlsx",
            "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "parents": ["target-folder"],
            "webViewLink": "https://drive.google.com/file/d/target/view",
        }
    )

    result = await _client(service).execute(
        GoogleDriveAction(
            kind=GoogleDriveActionKind.LINK,
            query="Invoice",
            folder="Clients",
        )
    )

    assert "target/view" in result.message
    assert "foreign" not in result.message


@pytest.mark.asyncio
async def test_batch_ancestry_finds_nested_target_after_deep_foreign_fanout() -> None:
    service = _Service()
    service.boundary.values.append(
        {
            "id": "target-folder",
            "name": "Clients",
            "mimeType": "application/vnd.google-apps.folder",
        }
    )
    for index in range(39):
        parent = f"foreign-deep-{index}-0"
        service.boundary.values.append(
            {
                "id": f"foreign-deep-file-{index}",
                "name": f"Invoice {index}.xlsx",
                "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "parents": [parent],
                "webViewLink": f"https://drive.google.com/file/d/foreign-deep-{index}/view",
            }
        )
        for depth in range(7):
            next_parent = f"foreign-deep-{index}-{depth + 1}"
            service.boundary.values.append(
                {
                    "id": parent,
                    "name": f"Foreign deep {index} level {depth}",
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": [next_parent] if depth < 6 else [],
                }
            )
            parent = next_parent
    target_parent = "target-deep-0"
    service.boundary.values.append(
        {
            "id": "target-deep-file",
            "name": "Invoice target.xlsx",
            "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "parents": [target_parent],
            "webViewLink": "https://drive.google.com/file/d/target-deep/view",
        }
    )
    for depth in range(7):
        next_parent = f"target-deep-{depth + 1}"
        service.boundary.values.append(
            {
                "id": target_parent,
                "name": f"Target level {depth}",
                "mimeType": "application/vnd.google-apps.folder",
                "parents": (
                    ["target-folder"]
                    if depth == 6
                    else [next_parent]
                ),
            }
        )
        target_parent = next_parent

    result = await _client(service).execute(
        GoogleDriveAction(
            kind=GoogleDriveActionKind.LINK,
            query="Invoice",
            folder="Clients",
        )
    )

    assert "target-deep/view" in result.message
    assert "foreign-deep" not in result.message


def test_batch_parent_response_id_mismatch_fails_closed() -> None:
    class MismatchBatch:
        def __init__(self, callback: object) -> None:
            self._callback = callback
            self._request_id: str | None = None

        def add(self, request: _Request, *, request_id: str) -> None:
            self._request_id = request_id

        def execute(self) -> None:
            assert self._request_id is not None
            self._callback(
                self._request_id,
                {
                    "id": "mismatched-parent",
                    "name": "Mismatched",
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": ["target-folder"],
                },
                None,
            )

    class MismatchService(_Service):
        def new_batch_http_request(self, *, callback: object) -> MismatchBatch:
            return MismatchBatch(callback)

    service = MismatchService()
    service.boundary.values.append(
        {
            "id": "evil-parent",
            "name": "Evil",
            "mimeType": "application/vnd.google-apps.folder",
        }
    )
    client = _client(service)
    item = GoogleDriveFile(
        file_id="unrelated-file",
        name="Invoice.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        parents=("evil-parent",),
    )

    with pytest.raises(ValueError):
        client._filter_folder_batch_sync(
            [item],
            {"target-folder"},
            time.monotonic() + 5,
            [10],
            threading.Event(),
        )


@pytest.mark.asyncio
async def test_approximate_folder_hint_never_guesses_between_files() -> None:
    service = _Service()
    for index in range(2):
        service.boundary.values.append(
            {
                "id": f"candidate-{index}",
                "name": f"HomeEdit plan {index}.xlsx",
                "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "parents": [f"folder-{index}"],
                "webViewLink": f"https://drive.google.com/file/d/candidate-{index}/view",
            }
        )

    with pytest.raises(RuntimeError, match="file_not_found"):
        await _client(service).execute(
            GoogleDriveAction(
                kind=GoogleDriveActionKind.LINK,
                query="HomeEdit plan",
                folder="Human approximate alias",
            )
        )
