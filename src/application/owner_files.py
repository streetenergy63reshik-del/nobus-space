"""Owner-bound, bounded local document selection for Telegram delivery."""

from __future__ import annotations

import asyncio
import ctypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from src.workers import find_owner_file_paths


MAX_OWNER_DOCUMENT_BYTES = 50 * 1024 * 1024
_ALLOWED_SUFFIXES = frozenset({".docx", ".htm", ".html", ".pdf", ".xlsx"})


@dataclass(frozen=True, slots=True)
class OwnerDocument:
    relative_path: str
    filename: str
    content: bytes


@dataclass(frozen=True, slots=True)
class OwnerFileSelection:
    document: OwnerDocument | None = None
    choices: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.document is not None and self.choices:
            raise ValueError("owner file selection is ambiguous")


class OwnerFileService:
    """Select and read only approved document types under one fixed root."""

    def __init__(self, root: str | Path) -> None:
        configured = Path(root)
        if (
            configured.is_symlink()
            or (
                hasattr(configured, "is_junction")
                and configured.is_junction()
            )
        ):
            raise ValueError("owner file root is invalid")
        resolved = configured.resolve(strict=True)
        if not resolved.is_dir():
            raise ValueError("owner file root is invalid")
        self._root = resolved

    async def select(self, query: str) -> OwnerFileSelection:
        if (
            not isinstance(query, str)
            or not query.strip()
            or len(query) > 512
            or "\x00" in query
        ):
            raise ValueError("owner file query is invalid")
        normalized = query.strip()
        paths = await asyncio.to_thread(
            find_owner_file_paths, self._root, normalized
        )
        supported = tuple(
            path
            for path in paths
            if Path(path).suffix.casefold() in _ALLOWED_SUFFIXES
        )
        exact = tuple(
            path
            for path in supported
            if path.casefold() == normalized.casefold()
            or Path(path).name.casefold() == normalized.casefold()
        )
        candidates = exact or supported
        if not candidates:
            return OwnerFileSelection()
        if len(candidates) > 1:
            return OwnerFileSelection(choices=candidates)
        document = await asyncio.to_thread(self._read, candidates[0])
        return OwnerFileSelection(document=document)

    def _read(self, relative_path: str) -> OwnerDocument:
        relative = Path(relative_path)
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError("owner document is unavailable")
        candidate = self._root / relative
        expected = Path(os.path.abspath(candidate))
        try:
            if (
                candidate.is_symlink()
                or (
                    hasattr(candidate, "is_junction")
                    and candidate.is_junction()
                )
            ):
                raise ValueError("owner document is unavailable")
            with candidate.open("rb") as stream:
                opened = _opened_final_path(stream)
                opened.relative_to(self._root)
                if (
                    _path_key(opened) != _path_key(expected)
                    or opened.suffix.casefold() not in _ALLOWED_SUFFIXES
                ):
                    raise ValueError("owner document is unavailable")
                before = _file_state(os.fstat(stream.fileno()))
                content = stream.read(MAX_OWNER_DOCUMENT_BYTES + 1)
                after = _file_state(os.fstat(stream.fileno()))
                if (
                    before != after
                    or _opened_final_path(stream) != opened
                    or not content
                    or len(content) > MAX_OWNER_DOCUMENT_BYTES
                ):
                    raise ValueError("owner document is unavailable")
            if (
                candidate.is_symlink()
                or (
                    hasattr(candidate, "is_junction")
                    and candidate.is_junction()
                )
                or _path_key(candidate.resolve(strict=True)) != _path_key(opened)
            ):
                raise ValueError("owner document is unavailable")
        except (OSError, RuntimeError, ValueError):
            raise ValueError("owner document is unavailable") from None
        return OwnerDocument(relative_path, opened.name, content)


def _file_state(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _path_key(value: Path) -> str:
    return os.path.normcase(str(value))


def _opened_final_path(stream: BinaryIO) -> Path:
    """Resolve the exact file bound to an already-open OS handle."""
    if os.name == "nt":
        import msvcrt

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        get_final_path = kernel32.GetFinalPathNameByHandleW
        get_final_path.argtypes = (
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            ctypes.c_ulong,
            ctypes.c_ulong,
        )
        get_final_path.restype = ctypes.c_ulong
        handle = msvcrt.get_osfhandle(stream.fileno())
        buffer = ctypes.create_unicode_buffer(32_768)
        length = get_final_path(handle, buffer, len(buffer), 0)
        if length == 0 or length >= len(buffer):
            raise OSError("final path is unavailable")
        value = buffer.value
        if value.startswith("\\\\?\\UNC\\"):
            value = "\\\\" + value[8:]
        elif value.startswith("\\\\?\\"):
            value = value[4:]
        return Path(value)

    descriptor = Path("/proc/self/fd") / str(stream.fileno())
    return descriptor.resolve(strict=True)
