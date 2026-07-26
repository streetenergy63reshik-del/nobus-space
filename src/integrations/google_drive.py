"""Owner-bound read-only Google Drive search and download adapter."""

from __future__ import annotations

import asyncio
from enum import Enum
from pathlib import Path
import re
import time
import threading
from typing import Any, Callable
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.integrations.google_transport import execute_request, load_service


_MAX_DOWNLOAD_BYTES = 49 * 1024 * 1024
_SEARCH_TIMEOUT_SECONDS = 90.0
_THREAD_DRAIN_TIMEOUT_SECONDS = 65.0
_SEARCH_MAX_REQUESTS = 256
_SEARCH_MAX_PAGES_PER_TERM = 2
_SEARCH_MAX_CANDIDATES = 200
_TRUSTED_DRIVE_HOSTS = frozenset(
    {
        "docs.google.com",
        "drive.google.com",
        "forms.google.com",
        "sheets.google.com",
        "sites.google.com",
        "slides.google.com",
    }
)
_SEARCH_STOPWORDS = frozenset(
    {
        "google",
        "drive",
        "бренд",
        "бренда",
        "бренду",
        "гугл",
        "диск",
        "диска",
        "папка",
        "папке",
        "таблица",
        "таблицу",
    }
)
_EXPORTS = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
}


class GoogleDriveActionKind(str, Enum):
    NONE = "none"
    SEARCH = "search"
    LINK = "link"
    DOWNLOAD = "download"


class GoogleDriveAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: GoogleDriveActionKind
    query: str | None = Field(default=None, max_length=1_024)
    folder: str | None = Field(default=None, max_length=1_024)

    @model_validator(mode="after")
    def validate_action(self) -> "GoogleDriveAction":
        if self.kind is GoogleDriveActionKind.NONE:
            if self.query is not None or self.folder is not None:
                raise ValueError("none Drive action must be empty")
        elif self.query is None or not self.query.strip() or "\x00" in self.query:
            raise ValueError("Drive query is invalid")
        if self.folder is not None and (
            not self.folder.strip() or "\x00" in self.folder
        ):
            raise ValueError("Drive folder is invalid")
        return self


class GoogleDriveFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    file_id: str = Field(min_length=1, max_length=2_048)
    name: str = Field(min_length=1, max_length=1_024)
    mime_type: str = Field(min_length=1, max_length=512)
    size: int | None = Field(default=None, ge=0)
    modified_time: str | None = Field(default=None, max_length=128)
    web_view_link: str | None = Field(default=None, max_length=2_048)
    parents: tuple[str, ...] = Field(default=(), max_length=100)

    @model_validator(mode="after")
    def validate_link(self) -> "GoogleDriveFile":
        if self.web_view_link is not None:
            try:
                parsed = urlsplit(self.web_view_link)
                port = parsed.port
            except ValueError:
                raise ValueError("Drive web link is invalid") from None
            if (
                parsed.scheme != "https"
                or parsed.hostname not in _TRUSTED_DRIVE_HOSTS
                or parsed.username is not None
                or parsed.password is not None
                or port not in (None, 443)
                or any(character.isspace() for character in self.web_view_link)
            ):
                raise ValueError("Drive web link is invalid")
        return self


class GoogleDriveResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    message: str = Field(min_length=1, max_length=3_400)
    filename: str | None = Field(default=None, max_length=1_024)
    content: bytes | None = Field(default=None, max_length=_MAX_DOWNLOAD_BYTES)

    @model_validator(mode="after")
    def validate_file(self) -> "GoogleDriveResult":
        if (self.filename is None) is not (self.content is None):
            raise ValueError("Drive file result is incomplete")
        return self


class GoogleDriveClient:
    def __init__(
        self,
        token_path: str | Path,
        *,
        service_factory: Callable[[], Any] | None = None,
        downloader_factory: Callable[[Any, Any, int], Any] | None = None,
    ) -> None:
        path = Path(token_path).resolve(strict=False)
        if not path.is_absolute():
            raise ValueError("Google Drive configuration is invalid")
        self._token_path = path
        self._service_factory = service_factory
        self._downloader_factory = downloader_factory
        self._service_instance: Any | None = None
        self._operation_lock = asyncio.Lock()

    async def execute(self, action: GoogleDriveAction) -> GoogleDriveResult:
        async with self._operation_lock:
            action = GoogleDriveAction.model_validate(action.model_dump())
            stop = threading.Event()
            operation = asyncio.create_task(
                asyncio.to_thread(self._execute_sync, action, stop)
            )
            try:
                return await asyncio.wait_for(
                    asyncio.shield(operation),
                    timeout=_SEARCH_TIMEOUT_SECONDS,
                )
            except (TimeoutError, asyncio.CancelledError) as exc:
                stop.set()
                try:
                    await asyncio.wait_for(
                        asyncio.shield(operation),
                        timeout=_THREAD_DRAIN_TIMEOUT_SECONDS,
                    )
                except Exception:
                    pass
                if isinstance(exc, asyncio.CancelledError):
                    raise
                raise RuntimeError("google_drive_timeout") from None

    def _service(self) -> Any:
        if self._service_instance is not None:
            return self._service_instance
        if self._service_factory is not None:
            self._service_instance = self._service_factory()
            return self._service_instance
        if not self._token_path.is_file():
            raise RuntimeError("google_drive_credentials_unavailable")
        try:
            scopes = (
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/drive.file",
                "https://www.googleapis.com/auth/drive",
            )
            self._service_instance = load_service(
                self._token_path,
                api="drive",
                version="v3",
                required_scopes=scopes,
                any_scope=True,
            )
            return self._service_instance
        except ImportError:
            raise RuntimeError("google_drive_dependency_unavailable") from None
        except RuntimeError:
            raise RuntimeError("google_drive_credentials_unavailable") from None
        except Exception:
            raise RuntimeError("google_drive_unavailable") from None

    def _execute_sync(
        self,
        action: GoogleDriveAction,
        stop: threading.Event,
    ) -> GoogleDriveResult:
        deadline = time.monotonic() + _SEARCH_TIMEOUT_SECONDS
        if action.kind is GoogleDriveActionKind.SEARCH:
            matches = self._search_sync(
                action.query or "", action.folder, deadline=deadline, stop=stop
            )
            if not matches:
                return GoogleDriveResult(message="В Google Drive ничего не найдено.")
            lines: list[str] = []
            length = len("Google Drive:\n\n")
            displayed = 0
            for item in matches[:20]:
                name = self._display_name(item.name)
                line = (
                    f"• {name[:180]}"
                    + (
                        f" — {item.modified_time[:10]}"
                        if item.modified_time
                        else ""
                    )
                    + (f"\n{item.web_view_link}" if item.web_view_link else "")
                )
                if length + len(line) + 1 > 3_300:
                    break
                lines.append(line)
                length += len(line) + 1
                displayed += 1
            suffix = (
                f"\n\nПоказаны первые {displayed} из {len(matches)}."
                if displayed < len(matches)
                else ""
            )
            return GoogleDriveResult(
                message="Google Drive:\n\n" + "\n".join(lines) + suffix
            )
        if action.kind is GoogleDriveActionKind.LINK:
            selected = self._resolve_unique_sync(
                action.query or "", action.folder, deadline=deadline, stop=stop
            )
            if selected.web_view_link is None:
                raise RuntimeError("google_drive_link_unavailable")
            return GoogleDriveResult(
                message=(
                    f"Google Drive:\n\n• {self._display_name(selected.name)[:180]}\n"
                    f"{selected.web_view_link}"
                )
            )
        if action.kind is GoogleDriveActionKind.DOWNLOAD:
            selected = self._resolve_unique_sync(
                action.query or "", action.folder, deadline=deadline, stop=stop
            )
            filename, content = self._download_sync(
                selected, deadline, stop
            )
            return GoogleDriveResult(
                message=f"Файл «{filename}» получен из Google Drive.",
                filename=filename,
                content=content,
            )
        raise ValueError("Google Drive action is not executable")

    def _search_sync(
        self,
        query: str,
        folder: str | None = None,
        *,
        deadline: float | None = None,
        stop: threading.Event | None = None,
    ) -> tuple[GoogleDriveFile, ...]:
        deadline = deadline or (time.monotonic() + _SEARCH_TIMEOUT_SECONDS)
        stop = stop or threading.Event()
        budget = [_SEARCH_MAX_REQUESTS]
        matches = self._search_term_sync(query, deadline, budget, stop)
        if matches:
            filtered = self._filter_folder_sync(
                matches, folder, deadline, budget, stop
            )
            if filtered or folder is None:
                return filtered
            return ()
        tokens = sorted(
            {
                token
                for token in re.findall(
                    r"[0-9A-Za-zА-Яа-яЁё]{4,}", query.casefold()
                )
                if token not in _SEARCH_STOPWORDS
            },
            key=lambda value: (-len(value), value),
        )[:3]
        if len(tokens) < 2:
            return ()
        candidates: dict[str, GoogleDriveFile] = {}
        for token in tokens:
            for item in self._search_term_sync(
                token, deadline, budget, stop, max_pages=1
            ):
                candidates.setdefault(item.file_id, item)
        brand_match = re.search(
            r"\b(?:по\s+)?бренд\w*\s+([0-9A-Za-zА-Яа-яЁё_-]{3,})",
            query,
            re.IGNORECASE,
        )
        brand = brand_match.group(1).casefold() if brand_match else None

        def score(item: GoogleDriveFile) -> int:
            normalized = item.name.casefold().replace("-", " ").replace("_", " ")
            return sum(token in normalized for token in tokens)

        selected = [
            item
            for item in candidates.values()
            if score(item) >= 2
            and (brand is None or self._name_contains_brand(item.name, brand))
        ]
        filtered = self._filter_folder_sync(
            selected, folder, deadline, budget, stop
        )
        return tuple(
            sorted(filtered, key=lambda item: (-score(item), item.name.casefold()))
        )

    def _search_term_sync(
        self,
        query: str,
        deadline: float,
        budget: list[int],
        stop: threading.Event,
        *,
        max_pages: int = _SEARCH_MAX_PAGES_PER_TERM,
        folders_only: bool = False,
    ) -> tuple[GoogleDriveFile, ...]:
        escaped = query.strip().replace("\\", "\\\\").replace("'", "\\'")
        try:
            items: list[object] = []
            token: str | None = None
            seen: set[str] = set()
            for _ in range(max_pages):
                self._check_search_budget(deadline, budget, stop)
                kind_filter = (
                    " and mimeType = 'application/vnd.google-apps.folder'"
                    if folders_only
                    else ""
                )
                values = execute_request(
                    self._service().files().list(
                        q=(
                            f"name contains '{escaped}' and trashed = false"
                            f"{kind_filter}"
                        ),
                        spaces="drive",
                        fields=(
                            "nextPageToken,files(id,name,mimeType,size,"
                            "modifiedTime,webViewLink,parents)"
                        ),
                        pageSize=100,
                        orderBy="modifiedTime desc",
                        pageToken=token,
                    ),
                    retries=0,
                )
                self._check_search_budget(deadline, budget, stop, consume=False)
                if not isinstance(values, dict):
                    raise ValueError
                page = values.get("files", [])
                if not isinstance(page, list):
                    raise ValueError
                items.extend(page[: _SEARCH_MAX_CANDIDATES - len(items)])
                if len(items) >= _SEARCH_MAX_CANDIDATES:
                    return tuple(self._file(item) for item in items)
                next_token = values.get("nextPageToken")
                if next_token is None:
                    return tuple(self._file(item) for item in items)
                if (
                    not isinstance(next_token, str)
                    or not next_token
                    or len(next_token) > 2_048
                    or next_token in seen
                ):
                    raise RuntimeError("google_drive_pagination_invalid")
                seen.add(next_token)
                token = next_token
            return tuple(self._file(item) for item in items)
        except (RuntimeError, ValueError):
            raise
        except Exception:
            raise RuntimeError("google_drive_search_failed") from None

    def _resolve_unique_sync(
        self,
        query: str,
        folder: str | None = None,
        *,
        deadline: float | None = None,
        stop: threading.Event | None = None,
    ) -> GoogleDriveFile:
        values = self._search_sync(
            query, folder, deadline=deadline, stop=stop
        )
        normalized = query.strip().casefold()
        exact = [
            item
            for item in values
            if item.name.casefold() == normalized
            or Path(item.name).stem.casefold() == normalized
        ]
        selected = exact or list(values)
        if not selected:
            raise RuntimeError("google_drive_file_not_found")
        if len(selected) != 1:
            raise RuntimeError("google_drive_file_ambiguous")
        return selected[0]

    def _filter_folder_sync(
        self,
        values: list[GoogleDriveFile] | tuple[GoogleDriveFile, ...],
        folder: str | None,
        deadline: float,
        budget: list[int],
        stop: threading.Event,
    ) -> tuple[GoogleDriveFile, ...]:
        if folder is None:
            return tuple(values)
        folder_ids = self._resolve_folder_ids_sync(
            folder, deadline, budget, stop
        )
        if not folder_ids:
            return ()
        direct = [
            item for item in values if folder_ids.intersection(item.parents)
        ]
        if direct:
            return tuple(direct)
        batch_selected = self._filter_folder_batch_sync(
            values, folder_ids, deadline, budget, stop
        )
        if batch_selected is not None:
            return batch_selected
        selected: list[GoogleDriveFile] = []
        parent_cache: dict[str, GoogleDriveFile] = {}
        per_candidate = max(
            1,
            min(12, max(budget[0] - 1, 1) // max(len(values), 1)),
        )
        for item in values:
            if stop.is_set():
                raise RuntimeError("google_drive_timeout")
            if time.monotonic() >= deadline:
                raise RuntimeError("google_drive_search_budget_exceeded")
            if budget[0] <= 0:
                break
            if self._is_within_folder_sync(
                item,
                folder_ids,
                deadline,
                budget,
                stop,
                max_requests=per_candidate,
                parent_cache=parent_cache,
            ):
                selected.append(item)
        return tuple(selected)


    def _filter_folder_batch_sync(
        self,
        values: list[GoogleDriveFile] | tuple[GoogleDriveFile, ...],
        folder_ids: set[str],
        deadline: float,
        budget: list[int],
        stop: threading.Event,
    ) -> tuple[GoogleDriveFile, ...] | None:
        """Resolve ancestry breadth-first using official Google batch requests."""
        service = self._service()
        batch_factory = getattr(service, "new_batch_http_request", None)
        if not callable(batch_factory):
            return None
        by_id = {item.file_id: item for item in values}
        frontier = {
            item.file_id: set(item.parents)
            for item in values
        }
        seen = {item.file_id: set() for item in values}
        selected: set[str] = set()
        parent_cache: dict[str, GoogleDriveFile] = {}
        for _ in range(12):
            needed: set[str] = set()
            active = False
            for item_id, parents in frontier.items():
                if item_id in selected:
                    continue
                if parents.intersection(folder_ids):
                    selected.add(item_id)
                    continue
                fresh = parents - seen[item_id]
                seen[item_id].update(fresh)
                needed.update(
                    parent_id
                    for parent_id in fresh
                    if parent_id not in parent_cache
                )
                active = active or bool(fresh)
            if not active:
                break
            ordered = sorted(needed)
            for offset in range(0, len(ordered), 100):
                chunk = ordered[offset : offset + 100]
                if not chunk:
                    continue
                self._check_search_budget(deadline, budget, stop)
                responses: dict[str, object] = {}
                failures: list[object] = []

                def callback(
                    request_id: str,
                    response: object,
                    exception: object,
                ) -> None:
                    if exception is not None:
                        failures.append(exception)
                    else:
                        responses[request_id] = response

                batch = batch_factory(callback=callback)
                for parent_id in chunk:
                    batch.add(
                        service.files().get(
                            fileId=parent_id,
                            fields="id,name,mimeType,parents",
                        ),
                        request_id=parent_id,
                    )
                try:
                    execute_request(batch, retries=0)
                    self._check_search_budget(
                        deadline, budget, stop, consume=False
                    )
                    if failures or set(responses) != set(chunk):
                        raise ValueError
                    for parent_id, raw in responses.items():
                        parent = self._file(raw)
                        if parent.file_id != parent_id:
                            raise ValueError
                        parent_cache[parent_id] = parent
                except (RuntimeError, ValueError):
                    raise
                except Exception:
                    raise RuntimeError("google_drive_search_failed") from None
            frontier = {
                item_id: {
                    ancestor
                    for parent_id in parents
                    for ancestor in (
                        parent_cache[parent_id].parents
                        if parent_id in parent_cache
                        else ()
                    )
                }
                for item_id, parents in frontier.items()
                if item_id not in selected
            }
        return tuple(
            item for item in values if item.file_id in selected
        )
    def _resolve_folder_ids_sync(
        self,
        folder: str,
        deadline: float,
        budget: list[int],
        stop: threading.Event,
    ) -> set[str]:
        whole = self._search_term_sync(
            folder, deadline, budget, stop, max_pages=1, folders_only=True
        )
        exact = {
            item.file_id
            for item in whole
            if self._folder_name_matches(item.name, folder)
        }
        if len(exact) == 1:
            return exact
        if len(exact) > 1:
            raise RuntimeError("google_drive_folder_ambiguous")
        segments = [
            value.strip()
            for value in re.split(r"\s*(?:→|->|>|/|\\|[—–-])\s*", folder)
            if value.strip()
        ]
        if len(segments) < 2:
            return set()
        current: list[GoogleDriveFile] = []
        for index, segment in enumerate(segments):
            candidates = list(
                self._folder_candidates_sync(
                    segment, deadline, budget, stop
                )
            )
            if index:
                parent_ids = {item.file_id for item in current}
                candidates = [
                    item
                    for item in candidates
                    if self._is_within_folder_sync(
                        item, parent_ids, deadline, budget, stop
                    )
                ]
            if not candidates:
                return set()
            current = candidates
        ids = {item.file_id for item in current}
        if len(ids) != 1:
            raise RuntimeError("google_drive_folder_ambiguous")
        return ids

    def _folder_candidates_sync(
        self,
        segment: str,
        deadline: float,
        budget: list[int],
        stop: threading.Event,
    ) -> tuple[GoogleDriveFile, ...]:
        values: dict[str, GoogleDriveFile] = {}
        terms = [segment]
        folded = segment.casefold()
        if len(segment) > 6 and (
            folded.startswith("pro") or folded.startswith("\u043f\u0440\u043e")
        ):
            terms.append(segment[3:])
        for term in terms:
            for item in self._search_term_sync(
                term,
                deadline,
                budget,
                stop,
                max_pages=1,
                folders_only=True,
            ):
                if self._folder_name_matches(item.name, segment):
                    values.setdefault(item.file_id, item)
        return tuple(values.values())

    @staticmethod
    def _name_contains_brand(name: str, brand: str) -> bool:
        brand_tokens = tuple(
            re.findall(r"[0-9A-Za-zА-Яа-яЁё]+", brand.casefold())
        )
        name_tokens = tuple(
            re.findall(r"[0-9A-Za-zА-Яа-яЁё]+", name.casefold())
        )
        if not brand_tokens or sum(map(len, brand_tokens)) < 3:
            return False
        width = len(brand_tokens)
        return any(
            name_tokens[index : index + width] == brand_tokens
            for index in range(len(name_tokens) - width + 1)
        )

    @staticmethod
    def _folder_name_matches(name: str, requested: str) -> bool:
        normalize = lambda value: "".join(
            character for character in value.casefold() if character.isalnum()
        )
        actual = normalize(name)
        expected = normalize(requested)
        return actual == expected or (
            expected.startswith("про") and actual == "pro" + expected[3:]
        )

    @staticmethod
    def _check_search_budget(
        deadline: float,
        budget: list[int],
        stop: threading.Event,
        *,
        consume: bool = True,
    ) -> None:
        if stop.is_set():
            raise RuntimeError("google_drive_timeout")
        if time.monotonic() >= deadline or budget[0] <= 0:
            raise RuntimeError("google_drive_search_budget_exceeded")
        if consume:
            budget[0] -= 1

    def _is_within_folder_sync(
        self,
        item: GoogleDriveFile,
        folder_ids: set[str],
        deadline: float,
        budget: list[int],
        stop: threading.Event,
        *,
        max_requests: int = 12,
        parent_cache: dict[str, GoogleDriveFile] | None = None,
    ) -> bool:
        pending = list(item.parents)
        seen: set[str] = set()
        requests = 0
        cache = parent_cache if parent_cache is not None else {}
        while pending:
            parent_id = pending.pop(0)
            if parent_id in folder_ids:
                return True
            if parent_id in seen:
                continue
            seen.add(parent_id)
            parent = cache.get(parent_id)
            if parent is None:
                if requests >= max_requests:
                    return False
                self._check_search_budget(deadline, budget, stop)
                try:
                    raw = execute_request(
                        self._service().files().get(
                            fileId=parent_id,
                            fields="id,name,mimeType,parents",
                        ),
                        retries=0,
                    )
                    self._check_search_budget(
                        deadline, budget, stop, consume=False
                    )
                    parent = self._file(raw)
                    cache[parent_id] = parent
                    requests += 1
                except (RuntimeError, ValueError):
                    raise
                except Exception:
                    raise RuntimeError("google_drive_search_failed") from None
            pending.extend(parent.parents)
        return False

    @staticmethod
    def _display_name(value: str) -> str:
        return " ".join(value.split())

    def _download_sync(
        self,
        item: GoogleDriveFile,
        deadline: float,
        stop: threading.Event,
    ) -> tuple[str, bytes]:
        if item.size is not None and item.size > _MAX_DOWNLOAD_BYTES:
            raise RuntimeError("google_drive_file_too_large")
        export = _EXPORTS.get(item.mime_type)
        try:
            if export is None:
                request = self._service().files().get_media(fileId=item.file_id)
                filename = item.name
            else:
                media_type, suffix = export
                request = self._service().files().export_media(
                    fileId=item.file_id,
                    mimeType=media_type,
                )
                filename = (
                    item.name
                    if item.name.casefold().endswith(suffix)
                    else item.name + suffix
                )
            content = self._stream_download(
                request, deadline=deadline, stop=stop
            )
            return self._safe_download_filename(filename), content
        except RuntimeError:
            raise
        except Exception:
            raise RuntimeError("google_drive_download_failed") from None

    def _stream_download(
        self,
        request: Any,
        *,
        deadline: float,
        stop: threading.Event,
    ) -> bytes:
        factory = self._downloader_factory
        if factory is None:
            try:
                from googleapiclient.http import MediaIoBaseDownload
            except ImportError:
                raise RuntimeError(
                    "google_drive_dependency_unavailable"
                ) from None
            factory = MediaIoBaseDownload
        sink = _BoundedBuffer(_MAX_DOWNLOAD_BYTES)
        try:
            download = factory(sink, request, 1024 * 1024)
            for _ in range(64):
                if stop.is_set() or time.monotonic() >= deadline:
                    raise RuntimeError("google_drive_timeout")
                before = sink.size
                _, done = download.next_chunk(num_retries=0)
                if stop.is_set() or time.monotonic() >= deadline:
                    raise RuntimeError("google_drive_timeout")
                if done:
                    content = sink.value()
                    if not content:
                        raise RuntimeError(
                            "google_drive_download_invalid"
                        )
                    return content
                if sink.size <= before:
                    raise RuntimeError("google_drive_download_invalid")
        except RuntimeError:
            raise
        except Exception:
            raise RuntimeError("google_drive_download_failed") from None
        raise RuntimeError("google_drive_file_too_large")

    @staticmethod
    def _safe_download_filename(value: str) -> str:
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "_", value)
        cleaned = " ".join(cleaned.split()).strip(" .") or "file"
        suffix = Path(cleaned).suffix[:20]
        stem = cleaned[: -len(suffix)] if suffix else cleaned
        limit = 220 - len(suffix.encode("utf-8"))
        encoded = stem.encode("utf-8")
        if len(encoded) > limit:
            encoded = encoded[:limit]
            while True:
                try:
                    stem = encoded.decode("utf-8")
                    break
                except UnicodeDecodeError:
                    encoded = encoded[:-1]
            stem = stem.rstrip(" .") or "file"
        return stem + suffix

    @staticmethod
    def _file(raw: object) -> GoogleDriveFile:
        if not isinstance(raw, dict):
            raise RuntimeError("google_drive_response_invalid")
        try:
            size = raw.get("size")
            parents = raw.get("parents", ())
            if (
                not isinstance(parents, (list, tuple))
                or not all(
                    isinstance(parent, str) and parent
                    for parent in parents
                )
            ):
                raise ValueError
            return GoogleDriveFile(
                file_id=raw["id"],
                name=raw["name"],
                mime_type=raw["mimeType"],
                size=None if size is None else int(size),
                modified_time=raw.get("modifiedTime"),
                web_view_link=raw.get("webViewLink"),
                parents=tuple(parents),
            )
        except Exception:
            raise RuntimeError("google_drive_response_invalid") from None


class _BoundedBuffer:
    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._data = bytearray()

    @property
    def size(self) -> int:
        return len(self._data)

    def write(self, value: bytes) -> int:
        if not isinstance(value, bytes):
            raise RuntimeError("google_drive_download_invalid")
        if len(self._data) + len(value) > self._limit:
            raise RuntimeError("google_drive_file_too_large")
        self._data.extend(value)
        return len(value)

    def value(self) -> bytes:
        return bytes(self._data)
