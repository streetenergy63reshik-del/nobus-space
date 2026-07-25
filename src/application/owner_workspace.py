"""L4-bound artifact creation inside the single Nobus owner workspace."""

from __future__ import annotations

import ctypes
import hashlib
import html
import io
import json
import os
import re
import subprocess
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape


MAX_ARTIFACT_BYTES = 50 * 1024 * 1024
_APPROVAL_RE = re.compile(r"^telegram-owner-confirmation:sha256:[0-9a-f]{64}$")
_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".html": "text/html; charset=utf-8",
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@dataclass(frozen=True, repr=False, slots=True)
class ArtifactProposal:
    relative_path: str
    media_type: str
    content: bytes
    content_digest: str
    current_digest: str | None


class OwnerWorkspace:
    """Render and atomically write only exact approved artifacts under one root."""

    def __init__(
        self,
        root: str | Path,
        *,
        pdf_renderer: Callable[
            [str, tuple[str, ...], tuple[tuple[str, ...], ...]], bytes
        ] | None = None,
        snapshot_root: str | Path | None = None,
    ) -> None:
        configured = Path(root)
        if configured.is_symlink() or (
            hasattr(configured, "is_junction") and configured.is_junction()
        ):
            raise ValueError("owner workspace root is invalid")
        resolved = configured.resolve(strict=True)
        if not resolved.is_dir():
            raise ValueError("owner workspace root is invalid")
        self._root = resolved
        configured_snapshot = (
            None if snapshot_root is None else Path(snapshot_root)
        )
        if configured_snapshot is not None:
            if configured_snapshot.is_symlink() or (
                hasattr(configured_snapshot, "is_junction")
                and configured_snapshot.is_junction()
            ):
                raise ValueError("artifact snapshot root is invalid")
            resolved_snapshot = configured_snapshot.resolve(strict=True)
            if (
                not resolved_snapshot.is_dir()
                or resolved_snapshot == resolved
                or resolved_snapshot.is_relative_to(resolved)
            ):
                raise ValueError("artifact snapshot root is invalid")
            snapshot_identity = _directory_identity(resolved_snapshot)
        else:
            resolved_snapshot = None
            snapshot_identity = None
        self._snapshot_root = resolved_snapshot
        self._snapshot_identity = snapshot_identity
        if resolved_snapshot is not None:
            _recover_replace_journals(resolved, resolved_snapshot)
        self._pdf_renderer = pdf_renderer or _pdf_document

    @property
    def root(self) -> Path:
        return self._root

    def propose(
        self,
        relative_path: str,
        *,
        title: str,
        paragraphs: tuple[str, ...] = (),
        rows: tuple[tuple[str, ...], ...] = (),
    ) -> ArtifactProposal:
        target = self._target(relative_path)
        suffix = target.suffix.casefold()
        if suffix not in _TYPES or not _text(title, 256):
            raise ValueError("artifact request is invalid")
        if (
            type(paragraphs) is not tuple
            or len(paragraphs) > 10_000
            or any(not _text(value, 20_000) for value in paragraphs)
            or type(rows) is not tuple
            or len(rows) > 100_000
            or any(
                type(row) is not tuple
                or len(row) > 1_000
                or any(not _text(value, 32_000) for value in row)
                for row in rows
            )
        ):
            raise ValueError("artifact content is invalid")
        renderer = {
            ".html": _html_document,
            ".docx": _docx_document,
            ".xlsx": _xlsx_document,
            ".pdf": self._pdf_renderer,
        }[suffix]
        content = renderer(title.strip(), paragraphs, rows)
        if not content or len(content) > MAX_ARTIFACT_BYTES:
            raise ValueError("artifact content is invalid")
        current = _digest_file(target) if target.exists() else None
        return ArtifactProposal(
            relative_path=target.relative_to(self._root).as_posix(),
            media_type=_TYPES[suffix],
            content=content,
            content_digest=_digest(content),
            current_digest=current,
        )

    def recover(self, proposal: ArtifactProposal) -> Path | None:
        if (
            not isinstance(proposal, ArtifactProposal)
            or proposal.content_digest != _digest(proposal.content)
        ):
            raise ValueError("artifact recovery is invalid")
        target = self._target(proposal.relative_path)
        if not target.is_file():
            return None
        _reject_linked_ancestors(self._root, target.parent)
        return target if _digest_file(target) == proposal.content_digest else None

    def apply(self, proposal: ArtifactProposal, *, approval_ref: str) -> Path:
        if (
            not isinstance(proposal, ArtifactProposal)
            or _APPROVAL_RE.fullmatch(approval_ref) is None
            or proposal.content_digest != _digest(proposal.content)
            or len(proposal.content) > MAX_ARTIFACT_BYTES
        ):
            raise ValueError("artifact approval is invalid")
        target = self._target(proposal.relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        _reject_linked_ancestors(self._root, target.parent)
        parent_identity = _directory_identity(target.parent)
        lock_path = target.parent / f".{target.name}.nobus.lock"
        artifact_lock = _acquire_artifact_lock(lock_path)
        try:
            current = _digest_file(target) if target.exists() else None
            if current != proposal.current_digest:
                raise RuntimeError("artifact changed after preview")
            identity = _file_identity(target) if target.exists() else None
            if target.exists():
                self._snapshot_current(
                    target,
                    proposal.relative_path,
                    current,
                )
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
            )
            temporary = Path(temporary_name)
        except BaseException:
            _release_artifact_lock(artifact_lock)
            raise
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(proposal.content)
                stream.flush()
                os.fsync(stream.fileno())
            if _digest_file(temporary) != proposal.content_digest:
                raise RuntimeError("artifact write verification failed")
            _reject_linked_ancestors(self._root, target.parent)
            if (
                _directory_identity(target.parent) != parent_identity
                or self._target(proposal.relative_path).parent.resolve(strict=True)
                != target.parent.resolve(strict=True)
                or (_file_identity(target) if target.exists() else None)
                != identity
            ):
                raise RuntimeError("artifact changed during approved write")
            _replace_with_pinned_parent(
                temporary,
                target,
                trusted_root=self._root,
                replace=True,
                expected_digest=proposal.content_digest,
                expected_destination_digest=proposal.current_digest,
                journal_root=self._snapshot_root,
            )
            if _digest_file(target) != proposal.content_digest:
                raise RuntimeError("artifact write verification failed")
            return target
        except BaseException:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        finally:
            _release_artifact_lock(artifact_lock)


    def restore_snapshot(
        self,
        relative_path: str,
        *,
        snapshot_digest: str,
        expected_current_digest: str,
        approval_ref: str,
    ) -> Path:
        if (
            self._snapshot_root is None
            or self._snapshot_identity is None
            or _APPROVAL_RE.fullmatch(approval_ref) is None
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", snapshot_digest)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_current_digest)
        ):
            raise ValueError("artifact restore is invalid")
        target = self._target(relative_path)
        if (
            not target.is_file()
            or _digest_file(target) != expected_current_digest
            or _directory_identity(self._snapshot_root) != self._snapshot_identity
        ):
            raise RuntimeError("artifact changed before restore")
        snapshot = (
            self._snapshot_root
            / Path(target.relative_to(self._root).as_posix())
            / f"{snapshot_digest.removeprefix('sha256:')}.bak"
        )
        try:
            snapshot.resolve(strict=True).relative_to(self._snapshot_root)
            _reject_linked_ancestors(self._snapshot_root, snapshot.parent)
            if snapshot.is_symlink() or not snapshot.is_file():
                raise RuntimeError
            content = _read_bounded_file(snapshot, MAX_ARTIFACT_BYTES)
            if _digest(content) != snapshot_digest:
                raise RuntimeError
        except (OSError, RuntimeError, ValueError):
            raise RuntimeError("artifact snapshot is unavailable") from None
        proposal = ArtifactProposal(
            relative_path=target.relative_to(self._root).as_posix(),
            media_type=_TYPES[target.suffix.casefold()],
            content=content,
            content_digest=snapshot_digest,
            current_digest=expected_current_digest,
        )
        return self.apply(proposal, approval_ref=approval_ref)


    def _snapshot_current(
        self,
        target: Path,
        relative_path: str,
        current_digest: str | None,
    ) -> Path:
        if (
            self._snapshot_root is None
            or self._snapshot_identity is None
            or current_digest is None
        ):
            raise RuntimeError("artifact snapshot is unavailable")
        if (
            _directory_identity(self._snapshot_root)
            != self._snapshot_identity
            or target.stat().st_size > MAX_ARTIFACT_BYTES
        ):
            raise RuntimeError("artifact snapshot is unavailable")
        content = _read_bounded_file(target, MAX_ARTIFACT_BYTES)
        if _digest(content) != current_digest:
            raise RuntimeError("artifact changed before snapshot")
        snapshot = (
            self._snapshot_root
            / Path(relative_path)
            / f"{current_digest.removeprefix('sha256:')}.bak"
        )
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        _reject_linked_ancestors(self._snapshot_root, snapshot.parent)
        snapshot_parent_identity = _directory_identity(snapshot.parent)
        if snapshot.exists():
            if (
                snapshot.is_symlink()
                or not snapshot.is_file()
                or _digest_file(snapshot) != current_digest
            ):
                raise RuntimeError("artifact snapshot conflict")
            return snapshot
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{snapshot.name}.",
            suffix=".tmp",
            dir=snapshot.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if _digest_file(temporary) != current_digest:
                raise RuntimeError("artifact snapshot verification failed")
            _reject_linked_ancestors(self._snapshot_root, snapshot.parent)
            try:
                snapshot.parent.resolve(strict=True).relative_to(
                    self._snapshot_root
                )
            except (OSError, RuntimeError, ValueError):
                raise RuntimeError("artifact snapshot root changed") from None
            if (
                _directory_identity(self._snapshot_root)
                != self._snapshot_identity
                or _directory_identity(snapshot.parent)
                != snapshot_parent_identity
            ):
                raise RuntimeError("artifact snapshot root changed")
            _replace_with_pinned_parent(
                temporary,
                snapshot,
                trusted_root=self._snapshot_root,
                replace=False,
                expected_digest=current_digest,
            )
            return snapshot
        except BaseException:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def diff_summary(self, proposal: ArtifactProposal) -> str:
        """Return a bounded byte-level manifest for the exact proposed change."""
        if not isinstance(proposal, ArtifactProposal):
            raise ValueError("artifact proposal is invalid")
        target = self._target(proposal.relative_path)
        current_size = target.stat().st_size if target.is_file() else 0
        previous = proposal.current_digest or "new"
        return (
            f"{previous} ({current_size} bytes) -> "
            f"{proposal.content_digest} ({len(proposal.content)} bytes)"
        )

    def _target(self, relative_path: str) -> Path:
        if (
            not isinstance(relative_path, str)
            or not relative_path.strip()
            or "\x00" in relative_path
            or len(relative_path) > 1_024
        ):
            raise ValueError("artifact path is invalid")
        relative = Path(relative_path.strip())
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError("artifact path is invalid")
        target = self._root / relative
        try:
            target.resolve(strict=False).relative_to(self._root)
        except (OSError, RuntimeError, ValueError):
            raise ValueError("artifact path is invalid") from None
        return target



@dataclass(frozen=True, slots=True)
class _ArtifactLock:
    handle: int
    windows_mutex: bool


def _acquire_artifact_lock(path: Path) -> _ArtifactLock:
    """Acquire a process-crash-safe lock without an existence sentinel."""
    identity = hashlib.sha256(
        str(path.resolve(strict=False)).casefold().encode("utf-8")
    ).hexdigest()
    if os.name == "nt":
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_mutex = kernel32.CreateMutexW
        create_mutex.argtypes = (
            wintypes.LPVOID,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        )
        create_mutex.restype = wintypes.HANDLE
        wait = kernel32.WaitForSingleObject
        wait.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        wait.restype = wintypes.DWORD
        close = kernel32.CloseHandle
        close.argtypes = (wintypes.HANDLE,)
        close.restype = wintypes.BOOL
        handle = create_mutex(
            None, False, f"Local\\NobusSpaceArtifact-{identity}"
        )
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        status = wait(handle, 0)
        if status not in {0x00000000, 0x00000080}:
            close(handle)
            if status == 0x00000102:
                raise RuntimeError(
                    "artifact write is already in progress"
                ) from None
            raise ctypes.WinError(ctypes.get_last_error())
        return _ArtifactLock(int(handle), True)

    import fcntl

    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError):
        os.close(descriptor)
        raise RuntimeError("artifact write is already in progress") from None
    return _ArtifactLock(descriptor, False)


def _release_artifact_lock(lock: _ArtifactLock) -> None:
    if lock.windows_mutex:
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        release = kernel32.ReleaseMutex
        release.argtypes = (wintypes.HANDLE,)
        release.restype = wintypes.BOOL
        close = kernel32.CloseHandle
        close.argtypes = (wintypes.HANDLE,)
        close.restype = wintypes.BOOL
        release(lock.handle)
        close(lock.handle)
        return

    import fcntl

    try:
        fcntl.flock(lock.handle, fcntl.LOCK_UN)
    finally:
        os.close(lock.handle)


def _write_replace_journal(root: Path, payload: dict[str, object]) -> Path:
    if _directory_identity(root) != _directory_identity(root.resolve(strict=True)):
        raise RuntimeError("artifact recovery journal is unavailable")
    name = f"artifact-replace-{os.urandom(12).hex()}.json"
    journal = root / name
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{name}.", suffix=".tmp", dir=root
    )
    temporary = Path(temporary_name)
    try:
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, journal)
        return journal
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def _recover_replace_journals(owner_root: Path, journal_root: Path) -> None:
    journals = tuple(sorted(journal_root.glob("artifact-replace-*.json")))
    if len(journals) > 100:
        raise RuntimeError("artifact recovery journal is invalid")
    for journal in journals:
        try:
            payload = json.loads(journal.read_text(encoding="utf-8"))
            if (
                type(payload) is not dict
                or payload.get("schema_version") != 1
                or set(payload)
                != {
                    "schema_version",
                    "relative_path",
                    "rollback_name",
                    "previous_digest",
                    "new_digest",
                }
            ):
                raise ValueError
            relative_path = payload["relative_path"]
            rollback_name = payload["rollback_name"]
            previous_digest = payload["previous_digest"]
            new_digest = payload["new_digest"]
            if (
                not isinstance(relative_path, str)
                or not relative_path
                or Path(relative_path).is_absolute()
                or any(part in {"", ".", ".."} for part in Path(relative_path).parts)
                or not isinstance(rollback_name, str)
                or re.fullmatch(
                    r"\.[^\\/]{1,255}\.nobus-rollback-[0-9a-f]{16}",
                    rollback_name,
                )
                is None
                or not isinstance(previous_digest, str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", previous_digest) is None
                or not isinstance(new_digest, str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", new_digest) is None
            ):
                raise ValueError
            target = owner_root / Path(relative_path)
            target.resolve(strict=False).relative_to(owner_root)
            rollback = target.parent / rollback_name
            _reject_linked_ancestors(owner_root, target.parent)
            if rollback.exists():
                if (
                    rollback.is_symlink()
                    or not rollback.is_file()
                    or _digest_file(rollback) != previous_digest
                ):
                    raise RuntimeError
                if not target.exists():
                    os.replace(rollback, target)
                    if _digest_file(target) != previous_digest:
                        raise RuntimeError
                elif _digest_file(target) == new_digest:
                    snapshot = (
                        journal_root
                        / Path(relative_path)
                        / f"{previous_digest.removeprefix('sha256:')}.bak"
                    )
                    if (
                        not snapshot.is_file()
                        or _digest_file(snapshot) != previous_digest
                    ):
                        raise RuntimeError
                    rollback.unlink()
                else:
                    raise RuntimeError
            elif not target.is_file() or _digest_file(target) not in {
                previous_digest,
                new_digest,
            }:
                raise RuntimeError
            try:
                journal.unlink()
            except OSError:
                # A verified state is safe to serve. The idempotent journal
                # will be retried at the next startup.
                pass
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
            raise RuntimeError("artifact recovery journal is invalid") from None


def _replace_with_pinned_parent(
    source: Path,
    destination: Path,
    *,
    trusted_root: Path,
    replace: bool,
    expected_digest: str,
    expected_destination_digest: str | None = None,
    journal_root: Path | None = None,
) -> None:
    """CAS rename using pinned parent, source and existing-target handles."""
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_digest):
        raise ValueError("artifact digest is invalid")
    if expected_destination_digest is not None and re.fullmatch(
        r"sha256:[0-9a-f]{64}", expected_destination_digest
    ) is None:
        raise ValueError("artifact destination digest is invalid")
    try:
        expected_parent = destination.parent.resolve(strict=True)
        expected_parent.relative_to(trusted_root.resolve(strict=True))
        expected_parent_identity = _directory_identity(expected_parent)
    except (OSError, RuntimeError, ValueError):
        raise RuntimeError("artifact destination changed") from None
    _reject_linked_ancestors(trusted_root, destination.parent)
    if os.name != "nt":
        current = _digest_file(destination) if destination.exists() else None
        if current != expected_destination_digest or _digest_file(source) != expected_digest:
            raise RuntimeError("artifact changed during approved write")
        descriptor = os.open(destination.parent, os.O_RDONLY)
        try:
            os.replace(
                source,
                destination.name,
                dst_dir_fd=descriptor,
            ) if replace else os.rename(
                source,
                destination.name,
                dst_dir_fd=descriptor,
            )
        finally:
            os.close(descriptor)
        return

    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    get_process = kernel32.GetCurrentProcess
    get_process.restype = wintypes.HANDLE
    duplicate_handle = kernel32.DuplicateHandle
    duplicate_handle.argtypes = (
        wintypes.HANDLE,
        wintypes.HANDLE,
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    )
    duplicate_handle.restype = wintypes.BOOL
    read_file = kernel32.ReadFile
    read_file.argtypes = (
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    )
    read_file.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    final_path = kernel32.GetFinalPathNameByHandleW
    final_path.argtypes = (
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    )
    final_path.restype = wintypes.DWORD
    ntdll = ctypes.WinDLL("ntdll", use_last_error=True)

    class IoStatusBlock(ctypes.Structure):
        _fields_ = (
            ("Status", ctypes.c_void_p),
            ("Information", ctypes.c_void_p),
        )

    set_info = ntdll.NtSetInformationFile
    set_info.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(IoStatusBlock),
        wintypes.LPVOID,
        wintypes.ULONG,
        ctypes.c_int,
    )
    set_info.restype = wintypes.LONG
    status_to_error = ntdll.RtlNtStatusToDosError
    status_to_error.argtypes = (wintypes.LONG,)
    status_to_error.restype = wintypes.ULONG

    class RenameInfo(ctypes.Structure):
        _fields_ = (
            ("ReplaceIfExists", ctypes.c_ubyte),
            ("RootDirectory", wintypes.HANDLE),
            ("FileNameLength", wintypes.DWORD),
            ("FileName", wintypes.WCHAR * 1),
        )

    def rename_handle(handle: int, root_handle: int, name: str) -> None:
        encoded_name = name.encode("utf-16-le")
        size = RenameInfo.FileName.offset + len(encoded_name) + 2
        raw = ctypes.create_string_buffer(size)
        info = ctypes.cast(raw, ctypes.POINTER(RenameInfo)).contents
        info.ReplaceIfExists = False
        info.RootDirectory = root_handle
        info.FileNameLength = len(encoded_name)
        ctypes.memmove(
            ctypes.addressof(raw) + RenameInfo.FileName.offset,
            encoded_name,
            len(encoded_name),
        )
        io_status = IoStatusBlock()
        status = set_info(
            handle, ctypes.byref(io_status), raw, size, 10
        )
        if status != 0:
            raise ctypes.WinError(status_to_error(status))

    def digest_handle(handle: int) -> str:
        hasher = hashlib.sha256()
        read_buffer = ctypes.create_string_buffer(1024 * 1024)
        while True:
            read = wintypes.DWORD()
            if not read_file(
                handle,
                read_buffer,
                len(read_buffer),
                ctypes.byref(read),
                None,
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            if read.value == 0:
                return f"sha256:{hasher.hexdigest()}"
            hasher.update(read_buffer.raw[: read.value])

    share_all = 0x00000001 | 0x00000002 | 0x00000004
    share_read = 0x00000001
    invalid = wintypes.HANDLE(-1).value
    directory_handle = create_file(
        str(destination.parent),
        0x00000001 | 0x00000002,
        share_all,
        None,
        3,
        0x02000000,
        None,
    )
    if directory_handle == invalid:
        raise ctypes.WinError(ctypes.get_last_error())
    source_handle = None
    target_handle = None
    rollback_name = None
    journal_path = None
    cleanup_deferred = False
    target_moved = False
    source_moved = False
    try:
        buffer = ctypes.create_unicode_buffer(32_768)
        length = final_path(directory_handle, buffer, len(buffer), 0)
        if length == 0 or length >= len(buffer):
            raise ctypes.WinError(ctypes.get_last_error())
        opened = buffer.value
        if opened.startswith("\\\\?\\UNC\\"):
            opened = "\\\\" + opened[8:]
        elif opened.startswith("\\\\?\\"):
            opened = opened[4:]
        opened_path = Path(opened).resolve(strict=True)
        duplicate = wintypes.HANDLE()
        current_process = get_process()
        if not duplicate_handle(
            current_process,
            directory_handle,
            current_process,
            ctypes.byref(duplicate),
            0,
            False,
            0x00000002,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            import msvcrt

            descriptor = msvcrt.open_osfhandle(duplicate.value, os.O_RDONLY)
            duplicate = wintypes.HANDLE()
            try:
                stat = os.fstat(descriptor)
                opened_identity = (stat.st_dev, stat.st_ino)
            finally:
                os.close(descriptor)
        finally:
            if duplicate.value:
                close_handle(duplicate)
        if (
            opened_path != expected_parent
            or opened_identity != expected_parent_identity
        ):
            raise RuntimeError("artifact destination changed")

        source_handle = create_file(
            str(source),
            0x80000000 | 0x00010000,
            0x00000001 | 0x00000004,
            None,
            3,
            0x00000080,
            None,
        )
        if source_handle == invalid:
            raise ctypes.WinError(ctypes.get_last_error())
        if digest_handle(source_handle) != expected_digest:
            raise RuntimeError("artifact temporary content changed")

        if expected_destination_digest is not None:
            target_handle = create_file(
                str(destination),
                0x80000000 | 0x00010000,
                share_read,
                None,
                3,
                0x00000080,
                None,
            )
            if target_handle == invalid:
                raise RuntimeError("artifact changed during approved write")
            if digest_handle(target_handle) != expected_destination_digest:
                raise RuntimeError("artifact changed during approved write")
            if journal_root is None:
                raise RuntimeError("artifact recovery journal is unavailable")
            rollback_name = (
                f".{destination.name}.nobus-rollback-{os.urandom(8).hex()}"
            )
            journal_path = _write_replace_journal(
                journal_root,
                {
                    "schema_version": 1,
                    "relative_path": destination.relative_to(
                        trusted_root
                    ).as_posix(),
                    "rollback_name": rollback_name,
                    "previous_digest": expected_destination_digest,
                    "new_digest": expected_digest,
                },
            )
            rename_handle(target_handle, directory_handle, rollback_name)
            target_moved = True
        elif destination.exists():
            raise RuntimeError("artifact changed during approved write")

        rename_handle(source_handle, directory_handle, destination.name)
        source_moved = True
        if target_moved and target_handle is not None:
            disposition = ctypes.c_ubyte(1)
            io_status = IoStatusBlock()
            status = set_info(
                target_handle,
                ctypes.byref(io_status),
                ctypes.byref(disposition),
                ctypes.sizeof(disposition),
                13,
            )
            cleanup_deferred = status != 0
        if journal_path is not None and not cleanup_deferred:
            try:
                journal_path.unlink(missing_ok=True)
            except OSError:
                # The committed result is authoritative; startup recovery
                # reconciles any journal that cleanup could not remove.
                pass
    except BaseException:
        if target_moved and not source_moved and target_handle is not None:
            try:
                rename_handle(target_handle, directory_handle, destination.name)
                target_moved = False
                if journal_path is not None:
                    journal_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    finally:
        for handle in (target_handle, source_handle, directory_handle):
            if handle not in {None, invalid}:
                close_handle(handle)

def _reject_linked_ancestors(root: Path, parent: Path) -> None:
    current = parent
    while current != root:
        if current.is_symlink() or (
            hasattr(current, "is_junction") and current.is_junction()
        ):
            raise ValueError("artifact path is invalid")
        current = current.parent



class EdgePdfRenderer:
    """Render UTF-8 HTML to PDF with a fixed local Edge binary and no web access."""

    def __init__(
        self,
        executable: str | Path,
        *,
        temp_root: str | Path,
        timeout_seconds: int = 60,
    ) -> None:
        self._executable = Path(executable).resolve(strict=True)
        self._temp_root = Path(temp_root).resolve(strict=True)
        if (
            not self._executable.is_file()
            or not self._temp_root.is_dir()
            or type(timeout_seconds) is not int
            or not 10 <= timeout_seconds <= 300
        ):
            raise ValueError("PDF renderer configuration is invalid")
        self._timeout = timeout_seconds

    def __call__(
        self,
        title: str,
        paragraphs: tuple[str, ...],
        rows: tuple[tuple[str, ...], ...],
    ) -> bytes:
        with tempfile.TemporaryDirectory(
            prefix="nobus-pdf-", dir=self._temp_root
        ) as temporary_name:
            temporary = Path(temporary_name)
            source = temporary / "source.html"
            output = temporary / "output.pdf"
            profile = temporary / "edge-profile"
            source.write_bytes(_html_document(title, paragraphs, rows))
            result = subprocess.run(
                (
                    str(self._executable),
                    "--headless",
                    "--disable-gpu",
                    "--disable-extensions",
                    "--disable-sync",
                    "--disable-background-networking",
                    "--no-first-run",
                    "--no-pdf-header-footer",
                    f"--user-data-dir={profile}",
                    f"--print-to-pdf={output}",
                    source.as_uri(),
                ),
                cwd=temporary,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self._timeout,
                check=False,
                shell=False,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                ),
                env={
                    "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
                    "TEMP": str(temporary),
                    "TMP": str(temporary),
                },
            )
            content = output.read_bytes() if output.is_file() else b""
            if (
                result.returncode != 0
                or not content.startswith(b"%PDF-")
                or len(content) > MAX_ARTIFACT_BYTES
            ):
                raise RuntimeError("PDF rendering failed")
            return content

def _html_document(
    title: str, paragraphs: tuple[str, ...], rows: tuple[tuple[str, ...], ...]
) -> bytes:
    body = "".join(f"<p>{html.escape(value)}</p>" for value in paragraphs)
    if rows:
        body += "<table>" + "".join(
            "<tr>" + "".join(f"<td>{html.escape(value)}</td>" for value in row) + "</tr>"
            for row in rows
        ) + "</table>"
    return (
        "<!doctype html><html lang=\"ru\"><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title><h1>{html.escape(title)}</h1>{body}</html>"
    ).encode()


def _docx_document(
    title: str, paragraphs: tuple[str, ...], rows: tuple[tuple[str, ...], ...]
) -> bytes:
    values = (title, *paragraphs, *(value for row in rows for value in row))
    body = "".join(
        f"<w:p><w:r><w:t xml:space=\"preserve\">{escape(value)}</w:t></w:r></w:p>"
        for value in values
    )
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>"
        ),
        "word/document.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body>{body}<w:sectPr/></w:body></w:document>"
        ),
    }
    return _zip(files)


def _xlsx_document(
    title: str, paragraphs: tuple[str, ...], rows: tuple[tuple[str, ...], ...]
) -> bytes:
    data = rows or tuple((value,) for value in (title, *paragraphs))
    sheet_rows = []
    for row_index, row in enumerate(data, 1):
        cells = "".join(
            f'<c r="{_column(index)}{row_index}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
            for index, value in enumerate(row, 1)
        )
        sheet_rows.append(f'<row r="{row_index}">{cells}</row>')
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>"
        ),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Nobus" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>"
        ),
        "xl/worksheets/sheet1.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f"<sheetData>{''.join(sheet_rows)}</sheetData></worksheet>"
        ),
    }
    return _zip(files)


def _pdf_document(
    title: str, paragraphs: tuple[str, ...], rows: tuple[tuple[str, ...], ...]
) -> bytes:
    values = (title, *paragraphs, *(value for row in rows for value in row))
    if any(any(ord(character) > 255 for character in value) for value in values):
        raise ValueError("PDF without an embedded font supports Latin text only")
    lines = ["BT /F1 12 Tf 50 790 Td"]
    for index, value in enumerate(values):
        escaped = value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        lines.append(("" if index == 0 else "0 -18 Td ") + f"({escaped}) Tj")
    stream = "\n".join(lines + ["ET"]).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = io.BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for number, value in enumerate(objects, 1):
        offsets.append(output.tell())
        output.write(f"{number} 0 obj\n".encode() + value + b"\nendobj\n")
    start = output.tell()
    output.write(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode())
    output.write(
        f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    )
    return output.getvalue()


def _zip(files: dict[str, str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o600 << 16
            archive.writestr(entry, value.encode())
    return output.getvalue()


def _column(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _directory_identity(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino


def _file_identity(path: Path) -> tuple[int, int, int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns



def _read_bounded_file(path: Path, limit: int) -> bytes:
    content = bytearray()
    with path.open("rb") as stream:
        while len(content) <= limit:
            chunk = stream.read(min(1024 * 1024, limit + 1 - len(content)))
            if not chunk:
                return bytes(content)
            content.extend(chunk)
    raise RuntimeError("artifact snapshot is unavailable")


def _digest_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def _text(value: object, limit: int) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= limit
        and not any(
            ord(character) < 32 and character not in "\t\n\r"
            for character in value
        )
    )
