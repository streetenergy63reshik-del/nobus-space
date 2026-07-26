"""Explicit network-read and L4-bound network-effect boundaries."""

from __future__ import annotations

import asyncio
import hashlib
import html
import ipaddress
import os
import re
import socket
import ssl
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, unquote, urljoin, urlsplit

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


@dataclass(frozen=True, repr=False, slots=True)
class _PinnedHttpResponse:
    status_code: int
    headers: dict[str, str]
    content: bytes


async def _read_pinned_response(
    reader: asyncio.StreamReader,
) -> _PinnedHttpResponse:
    try:
        header_blob = await reader.readuntil(b"\r\n\r\n")
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError):
        raise NetworkBoundaryError("download_url_invalid") from None
    if len(header_blob) > 32_768:
        raise NetworkBoundaryError("download_url_invalid")
    lines = header_blob[:-4].split(b"\r\n")
    if not lines:
        raise NetworkBoundaryError("download_url_invalid")
    status_match = re.fullmatch(rb"HTTP/1\.[01] ([0-9]{3})(?: .*)?", lines[0])
    if status_match is None:
        raise NetworkBoundaryError("download_url_invalid")
    status = int(status_match.group(1))
    selected = {
        "content-encoding",
        "content-length",
        "location",
        "transfer-encoding",
    }
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if b":" not in line:
            raise NetworkBoundaryError("download_url_invalid")
        raw_name, raw_value = line.split(b":", 1)
        try:
            name = raw_name.decode("ascii").strip().casefold()
            value = raw_value.decode("latin-1").strip()
        except UnicodeError:
            raise NetworkBoundaryError("download_url_invalid") from None
        if name in selected:
            if name in headers or "\x00" in value or len(value) > 2_048:
                raise NetworkBoundaryError("download_url_invalid")
            headers[name] = value
    if "transfer-encoding" in headers and "content-length" in headers:
        raise NetworkBoundaryError("download_url_invalid")
    if status in {301, 302, 303, 307, 308}:
        return _PinnedHttpResponse(status, headers, b"")
    if headers.get("content-encoding", "identity").casefold() not in {
        "",
        "identity",
    }:
        raise NetworkBoundaryError("download_url_invalid")
    limit = 131_072
    content = bytearray()
    transfer = headers.get("transfer-encoding", "").casefold()
    if transfer:
        if transfer != "chunked":
            raise NetworkBoundaryError("download_url_invalid")
        while len(content) < limit:
            size_line = await reader.readline()
            if not size_line or len(size_line) > 128 or not size_line.endswith(b"\r\n"):
                raise NetworkBoundaryError("download_url_invalid")
            try:
                size = int(size_line[:-2].split(b";", 1)[0], 16)
            except ValueError:
                raise NetworkBoundaryError("download_url_invalid") from None
            if size == 0:
                break
            take = min(size, limit - len(content))
            content.extend(await reader.readexactly(take))
            if take < size:
                break
            if await reader.readexactly(2) != b"\r\n":
                raise NetworkBoundaryError("download_url_invalid")
    else:
        raw_length = headers.get("content-length")
        if raw_length is not None:
            if not raw_length.isdigit():
                raise NetworkBoundaryError("download_url_invalid")
            length = min(int(raw_length), limit)
            if length:
                content.extend(await reader.readexactly(length))
        else:
            while len(content) < limit:
                chunk = await reader.read(min(8_192, limit - len(content)))
                if not chunk:
                    break
                content.extend(chunk)
    return _PinnedHttpResponse(status, headers, bytes(content))


async def _pinned_https_get(
    url: str,
    addresses: frozenset[str],
) -> _PinnedHttpResponse:
    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    ascii_host = hostname.encode("idna").decode("ascii")
    target = quote(
        parsed.path or "/",
        safe="/:@-._~!$&'()*+,;=%",
    )
    if parsed.query:
        target += "?" + quote(
            parsed.query,
            safe="=&?/:@-._~!$'()*+,;%",
        )
    request = (
        f"GET {target} HTTP/1.1\r\n"
        f"Host: {ascii_host}\r\n"
        "Accept: text/html,text/plain,application/json;q=0.9,*/*;q=0.1\r\n"
        "Accept-Encoding: identity\r\n"
        "Connection: close\r\n"
        "Range: bytes=0-131071\r\n"
        "User-Agent: NobusSpaceBot/1.0 source-verifier\r\n\r\n"
    ).encode("ascii")
    context = ssl.create_default_context()
    context.set_alpn_protocols(["http/1.1"])
    for address in sorted(addresses):
        writer: asyncio.StreamWriter | None = None
        try:
            reader, writer = await asyncio.open_connection(
                host=address,
                port=443,
                ssl=context,
                server_hostname=ascii_host,
                limit=32_768,
            )
            peer = writer.get_extra_info("peername")
            peer_value = peer[0] if isinstance(peer, tuple) else peer
            if _normalized_public_ip(str(peer_value)) != address:
                raise NetworkBoundaryError("download_url_invalid")
            writer.write(request)
            await writer.drain()
            return await _read_pinned_response(reader)
        except asyncio.CancelledError:
            raise
        except (OSError, UnicodeError, ValueError, ssl.SSLError, NetworkBoundaryError):
            continue
        finally:
            if writer is not None:
                writer.close()
    raise NetworkBoundaryError("download_url_invalid")


class SafeSourceVerifier:
    """Fetch bounded content from one cited public HTTPS source."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        resolver=socket.getaddrinfo,
        pinned_fetcher=_pinned_https_get,
    ) -> None:
        self._client = client
        self._resolver = resolver
        self._pinned_fetcher = pinned_fetcher

    async def aclose(self) -> None:
        return None

    async def verify(self, url: str, quote: str) -> bool:
        try:
            async with asyncio.timeout(20):
                current = _https_url_syntax(url)
                for _ in range(4):
                    hostname = urlsplit(current).hostname or ""
                    expected_addresses = await asyncio.to_thread(
                        _public_addresses, hostname, self._resolver
                    )
                    if self._client is None:
                        response = await self._pinned_fetcher(
                            current, expected_addresses
                        )
                        status_code = response.status_code
                        headers = response.headers
                        content = response.content
                    else:
                        async with self._client.stream(
                            "GET",
                            current,
                            headers={
                                "accept-encoding": "identity",
                                "range": "bytes=0-131071",
                                "user-agent": (
                                    "NobusSpaceBot/1.0 source-verifier"
                                ),
                            },
                        ) as remote:
                            status_code = remote.status_code
                            headers = dict(remote.headers)
                            if headers.get(
                                "content-encoding", "identity"
                            ).casefold() not in {"", "identity"}:
                                return False
                            if remote.is_stream_consumed:
                                content = remote.content
                                if len(content) > 131_072:
                                    return False
                            else:
                                body = bytearray()
                                async for chunk in remote.aiter_raw(
                                    chunk_size=8_192
                                ):
                                    body.extend(chunk)
                                    if len(body) > 131_072:
                                        return False
                                content = bytes(body)
                    if status_code in {301, 302, 303, 307, 308}:
                        location = headers.get("location")
                        if not location:
                            return False
                        current = _https_url_syntax(
                            urljoin(current, location)
                        )
                        continue
                    if not 200 <= status_code < 300 or not content:
                        return False
                    return _source_quote_matches(content, quote)
                return False
        except asyncio.CancelledError:
            raise
        except (
            TimeoutError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            NetworkBoundaryError,
            OSError,
            UnicodeError,
            ValueError,
            httpx.HTTPError,
        ):
            return False


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



def _source_quote_matches(content: bytes, quote: str) -> bool:
    if not isinstance(quote, str) or not 5 <= len(quote) <= 500:
        return False
    if not 5 <= len(re.findall(r"\w+", quote, re.UNICODE)) <= 30:
        return False
    source = content.decode("utf-8", errors="ignore")
    source = html.unescape(re.sub(r"<[^>]{0,500}>", " ", source))
    normalized_source = " ".join(source.casefold().split())
    normalized_quote = " ".join(html.unescape(quote).casefold().split())
    return bool(normalized_quote) and normalized_quote in normalized_source


def _directory_identity(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino

def _connected_peer(response: httpx.Response) -> str:
    try:
        stream = response.extensions["network_stream"]
        peer = stream.get_extra_info("server_addr")
        value = peer[0] if isinstance(peer, tuple) else peer
        return _normalized_public_ip(str(value))
    except Exception:
        raise NetworkBoundaryError("download_url_invalid") from None


def _https_url_syntax(url: str) -> str:
    if (
        not isinstance(url, str)
        or len(url) > 2_048
        or any(ord(char) <= 32 or ord(char) == 127 for char in url)
    ):
        raise NetworkBoundaryError("download_url_invalid")
    parsed = urlsplit(url)
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.port not in {None, 443}
    ):
        raise NetworkBoundaryError("download_url_invalid")
    return parsed.geturl()


def _validated_https_url(url: str, resolver) -> str:
    value = _https_url_syntax(url)
    _public_addresses(urlsplit(value).hostname or "", resolver)
    return value


def _public_addresses(hostname: str, resolver) -> frozenset[str]:
    try:
        addresses = frozenset(
            _normalized_public_ip(item[4][0])
            for item in resolver(hostname, 443, type=socket.SOCK_STREAM)
        )
        if not addresses:
            raise ValueError
        return addresses
    except Exception:
        raise NetworkBoundaryError("download_url_invalid") from None


def _normalized_public_ip(value: str) -> str:
    address = ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    if (
        not address.is_global
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
        or address.is_loopback
        or address.is_link_local
        or address.is_private
    ):
        raise ValueError
    return str(address)


def _public_ip(value: str) -> bool:
    try:
        _normalized_public_ip(value)
        return True
    except ValueError:
        return False


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
