"""Explicit network-read and L4-bound network-effect boundaries."""

from __future__ import annotations

import hashlib
import ipaddress
import os
import re
import socket
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote, urljoin, urlsplit

import httpx


MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
_APPROVAL_RE = re.compile(r"^telegram-owner-confirmation:sha256:[0-9a-f]{64}$")
_SAFE_NAME_RE = re.compile(r"^[^<>:\"/\\|?*\x00-\x1f]{1,180}$")
_DOWNLOAD_TYPES = frozenset(
    {
        "application/json",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "image/jpeg",
        "image/png",
        "text/csv",
        "text/html",
        "text/plain",
    }
)


class NetworkBoundaryError(RuntimeError):
    """Stable network failure without remote or local sensitive details."""


@dataclass(frozen=True, repr=False, slots=True)
class DownloadProposal:
    source_url: str
    final_url: str
    filename: str
    media_type: str
    content: bytes
    content_digest: str


class ResearchProvider(Protocol):
    async def research(self, instruction: str) -> str: ...


class SafeDownloader:
    """Download one bounded HTTPS resource; never execute or write it."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        resolver=socket.getaddrinfo,
        max_bytes: int = MAX_DOWNLOAD_BYTES,
    ) -> None:
        if type(max_bytes) is not int or not 1 <= max_bytes <= 100 * 1024 * 1024:
            raise ValueError("download limit is invalid")
        self._client = client or httpx.AsyncClient(
            timeout=60, follow_redirects=False, trust_env=False
        )
        self._owns_client = client is None
        self._require_peer_verification = client is None
        self._resolver = resolver
        self._max_bytes = max_bytes

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def preview(self, url: str) -> DownloadProposal:
        current = _validated_https_url(url, self._resolver)
        try:
            for _ in range(4):
                expected_addresses = _public_addresses(
                    urlsplit(current).hostname or "", self._resolver
                )
                async with self._client.stream("GET", current) as response:
                    if (
                        self._require_peer_verification
                        and _connected_peer(response) not in expected_addresses
                    ):
                        raise NetworkBoundaryError("download_url_invalid")
                    if _public_addresses(
                        urlsplit(current).hostname or "", self._resolver
                    ) != expected_addresses:
                        raise NetworkBoundaryError("download_url_invalid")
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise NetworkBoundaryError("download_redirect_invalid")
                        current = _validated_https_url(
                            urljoin(current, location), self._resolver
                        )
                        continue
                    if response.status_code != 200:
                        raise NetworkBoundaryError("download_failed")
                    media_type = response.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
                    length = response.headers.get("content-length")
                    if (
                        media_type not in _DOWNLOAD_TYPES
                        or (length is not None and (not length.isdigit() or int(length) > self._max_bytes))
                    ):
                        raise NetworkBoundaryError("download_rejected")
                    output = bytearray()
                    async for chunk in response.aiter_bytes():
                        output.extend(chunk)
                        if len(output) > self._max_bytes:
                            raise NetworkBoundaryError("download_too_large")
                    content = bytes(output)
                    if not content or not _magic_matches(media_type, content):
                        raise NetworkBoundaryError("download_rejected")
                    filename = _download_name(current, response.headers.get("content-disposition"))
                    return DownloadProposal(
                        source_url=url,
                        final_url=current,
                        filename=filename,
                        media_type=media_type,
                        content=content,
                        content_digest=_digest(content),
                    )
            raise NetworkBoundaryError("download_redirect_invalid")
        except NetworkBoundaryError:
            raise
        except Exception:
            raise NetworkBoundaryError("download_failed") from None


class Quarantine:
    """Write an approved download atomically into a non-executable directory."""

    def __init__(self, root: str | Path) -> None:
        configured = Path(root)
        if configured.is_symlink() or (
            hasattr(configured, "is_junction") and configured.is_junction()
        ):
            raise ValueError("quarantine root is invalid")
        self._root = configured.resolve(strict=True)
        if not self._root.is_dir():
            raise ValueError("quarantine root is invalid")
        self._root_identity = _directory_identity(self._root)

    def _validate_root(self) -> None:
        if (
            self._root.is_symlink()
            or (hasattr(self._root, "is_junction") and self._root.is_junction())
            or not self._root.is_dir()
            or _directory_identity(self._root) != self._root_identity
        ):
            raise RuntimeError("quarantine root changed")

    def recover(self, proposal: DownloadProposal) -> Path | None:
        if (
            not isinstance(proposal, DownloadProposal)
            or proposal.content_digest != _digest(proposal.content)
            or not _SAFE_NAME_RE.fullmatch(proposal.filename)
        ):
            raise ValueError("download recovery is invalid")
        self._validate_root()
        target = self._root / proposal.filename
        if not target.is_file() or target.is_symlink():
            return None
        return target if _digest(target.read_bytes()) == proposal.content_digest else None

    def store(self, proposal: DownloadProposal, *, approval_ref: str) -> Path:
        if (
            not isinstance(proposal, DownloadProposal)
            or _APPROVAL_RE.fullmatch(approval_ref) is None
            or proposal.content_digest != _digest(proposal.content)
            or not _SAFE_NAME_RE.fullmatch(proposal.filename)
            or len(proposal.content) > MAX_DOWNLOAD_BYTES
        ):
            raise ValueError("download approval is invalid")
        self._validate_root()
        target = self._root / proposal.filename
        if target.exists():
            raise FileExistsError("quarantine target already exists")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".download-", suffix=".tmp", dir=self._root
        )
        self._validate_root()
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(proposal.content)
                stream.flush()
                os.fsync(stream.fileno())
            if _digest(temporary.read_bytes()) != proposal.content_digest:
                raise RuntimeError("download write verification failed")
            self._validate_root()
            try:
                os.link(temporary, target)
            except FileExistsError:
                raise FileExistsError(
                    "quarantine target already exists"
                ) from None
            temporary.unlink()
            return target
        except BaseException:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise



def _directory_identity(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino

def _connected_peer(response: httpx.Response) -> str:
    try:
        stream = response.extensions["network_stream"]
        peer = stream.get_extra_info("server_addr")
        value = peer[0] if isinstance(peer, tuple) else peer
        address = str(ipaddress.ip_address(value))
        if not _public_ip(address):
            raise ValueError
        return address
    except Exception:
        raise NetworkBoundaryError("download_url_invalid") from None


def _validated_https_url(url: str, resolver) -> str:
    if not isinstance(url, str) or len(url) > 2_048 or "\x00" in url:
        raise NetworkBoundaryError("download_url_invalid")
    parsed = urlsplit(url.strip())
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.port not in {None, 443}
    ):
        raise NetworkBoundaryError("download_url_invalid")
    _public_addresses(parsed.hostname, resolver)
    return parsed.geturl()


def _public_addresses(hostname: str, resolver) -> frozenset[str]:
    try:
        addresses = frozenset(
            item[4][0]
            for item in resolver(hostname, 443, type=socket.SOCK_STREAM)
        )
        if not addresses or any(not _public_ip(value) for value in addresses):
            raise ValueError
        return addresses
    except Exception:
        raise NetworkBoundaryError("download_url_invalid") from None


def _public_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _download_name(url: str, disposition: str | None) -> str:
    name = ""
    if disposition:
        match = re.search(r"(?:^|;)\s*filename=\"?([^\";]+)", disposition, re.I)
        if match:
            name = unquote(match.group(1)).strip()
    if not name:
        name = Path(unquote(urlsplit(url).path)).name
    if not _SAFE_NAME_RE.fullmatch(name) or name in {".", ".."}:
        raise NetworkBoundaryError("download_rejected")
    return name


def _magic_matches(media_type: str, content: bytes) -> bool:
    if media_type == "application/pdf":
        return content.startswith(b"%PDF-")
    if media_type.endswith("document") or media_type.endswith("sheet"):
        return content.startswith(b"PK\x03\x04")
    if media_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if media_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if media_type.startswith("text/") or media_type == "application/json":
        return b"\x00" not in content[:4096]
    return False


def _digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"
