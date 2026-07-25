"""Owner-bound, bounded local document selection for Telegram delivery."""

from __future__ import annotations

import asyncio
import ctypes
import hashlib
import html
import io
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable
from xml.etree import ElementTree

from src.workers import find_owner_file_paths


MAX_OWNER_DOCUMENT_BYTES = 50 * 1024 * 1024
MAX_OWNER_CONTEXT_BYTES = 96 * 1024
MAX_OWNER_CONTEXT_CHARS = 24_000
_ALLOWED_SUFFIXES = frozenset(
    {".csv", ".docx", ".htm", ".html", ".json", ".md", ".pdf", ".txt", ".xlsx"}
)
_CONTEXT_SUFFIXES = _ALLOWED_SUFFIXES - {".pdf"}
_WHITESPACE_RE = re.compile(r"\s+")
_FILE_NAME_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)

_SENSITIVE_TEXT_RE = re.compile(
    r"(?i)(?:api[\s_-]*key|client[\s_-]*secret|access[\s_-]*token|"
    r"refresh[\s_-]*token|authorization\s*:|bearer\s+[a-z0-9._~-]+|"
    r"password|passwd|парол\w*|токен\w*|секрет\w*|"
    r"паспорт\w*|снилс\w*|персональн\w*\s+данн\w*|"
    r"-----BEGIN\s+(?:RSA|OPENSSH|EC|DSA|PRIVATE)\s+KEY-----|"
    r"\bsk-[a-z0-9_-]{16,}\b)"
)
_EMAIL_RE = re.compile(
    r"(?i)\b[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+\b"
)
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+7|8)[\s()\-]*\d{3}[\s()\-]*\d{3}"
    r"[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)"
)
_LONG_NUMBER_RE = re.compile(r"(?<!\d)\d{12,19}(?!\d)")
_SEPARATED_LONG_NUMBER_RE = re.compile(
    r"(?<!\d)(?:\d[ .-]?){11,18}\d(?!\d)"
)
_KNOWN_TOKEN_RE = re.compile(
    r"(?i)\b(?:(?:AKIA|ASIA)[0-9A-Z]{16}|"
    r"AIza[0-9A-Za-z_-]{20,255}|"
    r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,255}|"
    r"github_pat_[A-Za-z0-9_]{20,255}|"
    r"(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{16,255}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,255}|"
    r"eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,})\b"
)
_OPAQUE_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{24,4096}(?![A-Za-z0-9_-])"
)
_CHUNKED_BASE64_RE = re.compile(
    r"(?:(?:[A-Za-z0-9+/]{8,23})[ \t\r\n]+){3,}"
    r"[A-Za-z0-9+/=]{4,23}"
)
_CHUNKED_HEX_RE = re.compile(
    r"(?i)(?:(?:[0-9a-f]{8,23})[ .:\t\r\n-]+){3,}"
    r"[0-9a-f]{4,23}"
)


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


class OwnerFileSensitiveError(ValueError):
    """Selected file may disclose protected data to an external model."""


@dataclass(frozen=True, slots=True)
class OwnerFileContext:
    relative_path: str
    text: str
    content_digest: str


@dataclass(frozen=True, slots=True)
class OwnerFileContextSelection:
    context: OwnerFileContext | None = None
    choices: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.context is not None and self.choices:
            raise ValueError("owner file context selection is ambiguous")


def _normalized_file_phrase(value: str) -> str:
    return " ".join(_FILE_NAME_WORD_RE.findall(value.casefold()))


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
        query_phrase = _normalized_file_phrase(normalized)
        stem_matches = tuple(
            (len(stem_phrase), path)
            for path in supported
            if (stem_phrase := _normalized_file_phrase(Path(path).stem))
            and stem_phrase in query_phrase
        )
        longest_stem_matches: tuple[str, ...] = ()
        if stem_matches:
            longest = max(length for length, _ in stem_matches)
            longest_stem_matches = tuple(
                path for length, path in stem_matches if length == longest
            )
        candidates = exact or longest_stem_matches or supported
        if not candidates:
            return OwnerFileSelection()
        if len(candidates) > 1:
            return OwnerFileSelection(choices=candidates)
        document = await asyncio.to_thread(self._read, candidates[0])
        return OwnerFileSelection(document=document)

    async def context(self, query: str) -> OwnerFileContextSelection:
        selection = await self.select(query)
        if selection.document is None:
            return OwnerFileContextSelection(choices=selection.choices)
        document = selection.document
        suffix = Path(document.relative_path).suffix.casefold()
        if suffix not in _CONTEXT_SUFFIXES:
            raise ValueError("owner document text is unavailable")
        extracted = await asyncio.to_thread(
            _extract_text, suffix, document.content
        )
        if not extracted:
            raise ValueError("owner document text is unavailable")
        if _contains_sensitive_text(extracted):
            raise OwnerFileSensitiveError("owner document contains protected data")
        return OwnerFileContextSelection(
            context=OwnerFileContext(
                relative_path=document.relative_path,
                text=extracted,
                content_digest="sha256:"
                + hashlib.sha256(document.content).hexdigest(),
            )
        )

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


def _contains_sensitive_text(value: str) -> bool:
    if any(
        pattern.search(value) is not None
        for pattern in (
            _SENSITIVE_TEXT_RE,
            _EMAIL_RE,
            _PHONE_RE,
            _LONG_NUMBER_RE,
            _SEPARATED_LONG_NUMBER_RE,
            _KNOWN_TOKEN_RE,
        )
    ):
        return True
    if _CHUNKED_BASE64_RE.search(value) or _CHUNKED_HEX_RE.search(value):
        return True
    return any(_looks_opaque(match.group(0)) for match in _OPAQUE_TOKEN_RE.finditer(value))


def _looks_opaque(value: str) -> bool:
    categories = sum(
        bool(pattern.search(value))
        for pattern in (
            re.compile(r"[a-z]"),
            re.compile(r"[A-Z]"),
            re.compile(r"\d"),
            re.compile(r"[_-]"),
        )
    )
    if categories < 2:
        return False
    frequencies = {character: value.count(character) for character in set(value)}
    entropy = -sum(
        (count / len(value)) * __import__("math").log2(count / len(value))
        for count in frequencies.values()
    )
    return entropy >= 3.5


def owner_file_answer_is_safe(source: str, answer: str) -> bool:
    """Reject sensitive or substantially verbatim durable owner-file answers."""
    if (
        not isinstance(source, str)
        or not isinstance(answer, str)
        or _contains_sensitive_text(answer)
    ):
        return False
    normalized_source = _WHITESPACE_RE.sub(" ", source).strip().casefold()
    normalized_answer = _WHITESPACE_RE.sub(" ", answer).strip().casefold()
    if not normalized_source or not normalized_answer:
        return True
    if (
        normalized_source in normalized_answer
        or normalized_source[::-1] in normalized_answer
    ):
        return False
    source_tokens = re.findall(r"\w+", normalized_source)
    answer_tokens = re.findall(r"\w+", normalized_answer)
    if len(source_tokens) >= 3:
        width = min(8, len(source_tokens))
        answer_windows = {
            tuple(answer_tokens[index : index + width])
            for index in range(max(0, len(answer_tokens) - width + 1))
        }
        source_windows = {
            tuple(source_tokens[index : index + width])
            for index in range(len(source_tokens) - width + 1)
        }
        reverse_windows = {
            tuple(reversed(window)) for window in source_windows
        }
        if answer_windows & (source_windows | reverse_windows):
            return False
        from collections import Counter

        source_counts = Counter(source_tokens)
        answer_counts = Counter(answer_tokens)
        overlap = sum((source_counts & answer_counts).values())
        if overlap / len(source_tokens) >= 0.35:
            return False
    return True


def _extract_text(suffix: str, content: bytes) -> str:
    if suffix in {".csv", ".json", ".md", ".txt"}:
        extracted = _decode_text(content[: MAX_OWNER_CONTEXT_BYTES + 1])
    elif suffix in {".htm", ".html"}:
        source = _decode_text(content[: MAX_OWNER_CONTEXT_BYTES + 1])
        source = re.sub(
            r"(?is)<(?:script|style)\b.*?</(?:script|style)>", " ", source
        )
        extracted = html.unescape(re.sub(r"(?s)<[^>]+>", " ", source))
    elif suffix == ".docx":
        extracted = _extract_zip_xml_text(
            content,
            lambda name: name == "word/document.xml",
            (".//{*}t",),
        )
    elif suffix == ".xlsx":
        extracted = _extract_zip_xml_text(
            content,
            lambda name: name == "xl/sharedStrings.xml"
            or (
                name.startswith("xl/worksheets/")
                and name.endswith(".xml")
            ),
            (".//{*}t", ".//{*}v"),
        )
    else:
        raise ValueError("owner document text is unavailable")
    return _WHITESPACE_RE.sub(" ", extracted).strip()[:MAX_OWNER_CONTEXT_CHARS]


def _decode_text(content: bytes) -> str:
    if len(content) > MAX_OWNER_CONTEXT_BYTES:
        raise ValueError("owner document text is unavailable")
    encodings = ("utf-16",) if content.startswith(
        (b"\xff\xfe", b"\xfe\xff")
    ) else ("utf-8-sig", "cp1251")
    for encoding in encodings:
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("owner document text is unavailable")


def _extract_zip_xml_text(
    content: bytes,
    wanted: Callable[[str], bool],
    selectors: tuple[str, ...],
) -> str:
    parts: list[str] = []
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            all_infos = archive.infolist()
            if len(all_infos) > 512:
                raise ValueError("owner document text is unavailable")
            infos = tuple(
                info for info in all_infos if wanted(info.filename)
            )
            if not infos or len(infos) > 256:
                raise ValueError("owner document text is unavailable")
            for info in infos:
                if info.file_size > MAX_OWNER_CONTEXT_BYTES:
                    raise ValueError("owner document text is unavailable")
                total += info.file_size
                if total > MAX_OWNER_CONTEXT_BYTES:
                    raise ValueError("owner document text is unavailable")
                root = ElementTree.fromstring(archive.read(info))
                for selector in selectors:
                    parts.extend(
                        node.text
                        for node in root.findall(selector)
                        if node.text
                    )
    except (ElementTree.ParseError, OSError, ValueError, zipfile.BadZipFile):
        raise ValueError("owner document text is unavailable") from None
    return " ".join(parts)


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
