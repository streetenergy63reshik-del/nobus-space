"""Minimal fail-closed reader for Windows Generic Credentials."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass

from pydantic import SecretStr


_CRED_TYPE_GENERIC = 1
_MAX_TARGET_LENGTH = 256
_MAX_USERNAME_LENGTH = 256
_MAX_BLOB_BYTES = 1024
_ERROR_MESSAGES = {
    "credential_configuration_invalid": "Credential configuration is invalid.",
    "credential_unavailable": "Credential is unavailable.",
}


class CredentialStoreError(RuntimeError):
    """Stable public failure containing no credential metadata or secret."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(_ERROR_MESSAGES[code])


@dataclass(frozen=True)
class GenericCredential:
    username: str
    secret: SecretStr


def read_generic_credential(target: str) -> GenericCredential:
    """Read one Windows Generic Credential without exposing raw failures."""

    if not _bounded_text(target, _MAX_TARGET_LENGTH):
        raise CredentialStoreError("credential_configuration_invalid")

    failure = False
    raw: tuple[str, bytes] | None = None
    try:
        raw = _read_windows_credential(target.strip())
    except BaseException:
        failure = True
    if failure or raw is None:
        raise CredentialStoreError("credential_unavailable")

    username, blob = raw
    if not _bounded_text(username, _MAX_USERNAME_LENGTH):
        raise CredentialStoreError("credential_unavailable")
    secret = _decode_credential_blob(blob)
    return GenericCredential(username=username.strip(), secret=SecretStr(secret))


def _decode_credential_blob(blob: bytes) -> str:
    if (
        type(blob) is not bytes
        or not blob
        or len(blob) > _MAX_BLOB_BYTES
        or len(blob) % 2
    ):
        raise CredentialStoreError("credential_unavailable")
    failure = False
    secret = ""
    try:
        secret = blob.decode("utf-16-le", errors="strict")
    except UnicodeError:
        failure = True
    if failure or not secret or "\x00" in secret:
        raise CredentialStoreError("credential_unavailable")
    return secret


def _read_windows_credential(target: str) -> tuple[str, bytes]:
    from ctypes import wintypes

    class CredentialAttribute(ctypes.Structure):
        _fields_ = [
            ("Keyword", wintypes.LPWSTR),
            ("Flags", wintypes.DWORD),
            ("ValueSize", wintypes.DWORD),
            ("Value", ctypes.POINTER(ctypes.c_ubyte)),
        ]

    class Credential(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.POINTER(CredentialAttribute)),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    credential_pointer = ctypes.POINTER(Credential)
    pointer = credential_pointer()
    library = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    cred_read = library.CredReadW
    cred_read.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(credential_pointer),
    ]
    cred_read.restype = wintypes.BOOL
    cred_free = library.CredFree
    cred_free.argtypes = [ctypes.c_void_p]
    cred_free.restype = None

    if not cred_read(target, _CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
        raise OSError("credential read failed")
    try:
        credential = pointer.contents
        size = int(credential.CredentialBlobSize)
        address = ctypes.cast(credential.CredentialBlob, ctypes.c_void_p).value
        if size <= 0 or size > _MAX_BLOB_BYTES or address is None:
            raise ValueError("credential blob invalid")
        return credential.UserName or "", ctypes.string_at(address, size)
    finally:
        cred_free(pointer)


def _bounded_text(value: object, limit: int) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= limit
        and "\x00" not in value
    )
