"""Owner-bound read-only Google Drive search and download adapter."""

from __future__ import annotations

import asyncio
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, model_validator


_MAX_DOWNLOAD_BYTES = 49 * 1024 * 1024
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
    DOWNLOAD = "download"


class GoogleDriveAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: GoogleDriveActionKind
    query: str | None = Field(default=None, max_length=1_024)

    @model_validator(mode="after")
    def validate_action(self) -> "GoogleDriveAction":
        if self.kind is GoogleDriveActionKind.NONE:
            if self.query is not None:
                raise ValueError("none Drive action must be empty")
        elif self.query is None or not self.query.strip() or "\x00" in self.query:
            raise ValueError("Drive query is invalid")
        return self


class GoogleDriveFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    file_id: str = Field(min_length=1, max_length=2_048)
    name: str = Field(min_length=1, max_length=1_024)
    mime_type: str = Field(min_length=1, max_length=512)
    size: int | None = Field(default=None, ge=0)
    modified_time: str | None = Field(default=None, max_length=128)


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

    async def execute(self, action: GoogleDriveAction) -> GoogleDriveResult:
        action = GoogleDriveAction.model_validate(action.model_dump())
        return await asyncio.to_thread(self._execute_sync, action)

    def _service(self) -> Any:
        if self._service_instance is not None:
            return self._service_instance
        if self._service_factory is not None:
            self._service_instance = self._service_factory()
            return self._service_instance
        if not self._token_path.is_file():
            raise RuntimeError("google_drive_credentials_unavailable")
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            scopes = ("https://www.googleapis.com/auth/drive.readonly",)
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
                "drive",
                "v3",
                credentials=credentials,
                cache_discovery=False,
            )
            return self._service_instance
        except ImportError:
            raise RuntimeError("google_drive_dependency_unavailable") from None
        except RuntimeError:
            raise RuntimeError("google_drive_credentials_unavailable") from None
        except Exception:
            raise RuntimeError("google_drive_unavailable") from None

    def _execute_sync(self, action: GoogleDriveAction) -> GoogleDriveResult:
        if action.kind is GoogleDriveActionKind.SEARCH:
            matches = self._search_sync(action.query or "")
            if not matches:
                return GoogleDriveResult(message="В Google Drive ничего не найдено.")
            lines = [
                f"• {item.name}"
                + (
                    f" — {item.modified_time[:10]}"
                    if item.modified_time
                    else ""
                )
                for item in matches[:20]
            ]
            return GoogleDriveResult(
                message="Google Drive:\n\n" + "\n".join(lines)
            )
        if action.kind is GoogleDriveActionKind.DOWNLOAD:
            selected = self._resolve_unique_sync(action.query or "")
            filename, content = self._download_sync(selected)
            return GoogleDriveResult(
                message=f"Файл «{filename}» получен из Google Drive.",
                filename=filename,
                content=content,
            )
        raise ValueError("Google Drive action is not executable")

    def _search_sync(self, query: str) -> tuple[GoogleDriveFile, ...]:
        escaped = query.strip().replace("\\", "\\\\").replace("'", "\\'")
        try:
            items: list[object] = []
            token: str | None = None
            seen: set[str] = set()
            for _ in range(100):
                values = (
                    self._service()
                    .files()
                    .list(
                        q=f"name contains '{escaped}' and trashed = false",
                        spaces="drive",
                        fields=(
                            "nextPageToken,"
                            "files(id,name,mimeType,size,modifiedTime)"
                        ),
                        pageSize=100,
                        orderBy="modifiedTime desc",
                        pageToken=token,
                    )
                    .execute()
                )
                if not isinstance(values, dict):
                    raise ValueError
                page = values.get("files", [])
                if not isinstance(page, list):
                    raise ValueError
                items.extend(page)
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
            raise RuntimeError("google_drive_pagination_invalid")
        except (RuntimeError, ValueError):
            raise
        except Exception:
            raise RuntimeError("google_drive_search_failed") from None

    def _resolve_unique_sync(self, query: str) -> GoogleDriveFile:
        values = self._search_sync(query)
        normalized = query.strip().casefold()
        exact = [item for item in values if item.name.casefold() == normalized]
        selected = exact or list(values)
        if not selected:
            raise RuntimeError("google_drive_file_not_found")
        if len(selected) != 1:
            raise RuntimeError("google_drive_file_ambiguous")
        return selected[0]

    def _download_sync(self, item: GoogleDriveFile) -> tuple[str, bytes]:
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
            content = self._stream_download(request)
            return filename, content
        except RuntimeError:
            raise
        except Exception:
            raise RuntimeError("google_drive_download_failed") from None

    def _stream_download(self, request: Any) -> bytes:
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
                before = sink.size
                _, done = download.next_chunk(num_retries=2)
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
    def _file(raw: object) -> GoogleDriveFile:
        if not isinstance(raw, dict):
            raise RuntimeError("google_drive_response_invalid")
        try:
            size = raw.get("size")
            return GoogleDriveFile(
                file_id=raw["id"],
                name=raw["name"],
                mime_type=raw["mimeType"],
                size=None if size is None else int(size),
                modified_time=raw.get("modifiedTime"),
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
