"""Current-user Windows DPAPI codec for sensitive local runtime payloads."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


class DpapiError(RuntimeError):
    """Stable failure that never includes protected content."""


class _DataBlob(ctypes.Structure):
    _fields_ = (
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    )


def protect_current_user(value: bytes, *, entropy: bytes) -> bytes:
    """Encrypt bytes for the current Windows user without persisting a key."""
    return _crypt(value, entropy=entropy, protect=True)


def unprotect_current_user(value: bytes, *, entropy: bytes) -> bytes:
    """Decrypt bytes previously protected for the current Windows user."""
    return _crypt(value, entropy=entropy, protect=False)


def _crypt(value: bytes, *, entropy: bytes, protect: bool) -> bytes:
    if (
        os.name != "nt"
        or type(value) is not bytes
        or not value
        or len(value) > 2 * 1024 * 1024
        or type(entropy) is not bytes
        or not 16 <= len(entropy) <= 128
    ):
        raise DpapiError("dpapi_operation_failed")
    data_buffer = ctypes.create_string_buffer(value)
    entropy_buffer = ctypes.create_string_buffer(entropy)
    source = _DataBlob(
        len(value),
        ctypes.cast(data_buffer, ctypes.POINTER(ctypes.c_ubyte)),
    )
    entropy_blob = _DataBlob(
        len(entropy),
        ctypes.cast(entropy_buffer, ctypes.POINTER(ctypes.c_ubyte)),
    )
    output = _DataBlob()
    library = ctypes.WinDLL("Crypt32.dll", use_last_error=True)
    local_free = ctypes.WinDLL("Kernel32.dll", use_last_error=True).LocalFree
    local_free.argtypes = (wintypes.HLOCAL,)
    local_free.restype = wintypes.HLOCAL
    function = (
        library.CryptProtectData if protect else library.CryptUnprotectData
    )
    if protect:
        function.argtypes = (
            ctypes.POINTER(_DataBlob),
            wintypes.LPCWSTR,
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        )
        args = (
            ctypes.byref(source),
            None,
            ctypes.byref(entropy_blob),
            None,
            None,
            0x1,
            ctypes.byref(output),
        )
    else:
        function.argtypes = (
            ctypes.POINTER(_DataBlob),
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        )
        args = (
            ctypes.byref(source),
            None,
            ctypes.byref(entropy_blob),
            None,
            None,
            0x1,
            ctypes.byref(output),
        )
    function.restype = wintypes.BOOL
    if not function(*args):
        raise DpapiError("dpapi_operation_failed")
    try:
        if not output.pbData or output.cbData <= 0 or output.cbData > 2 * 1024 * 1024:
            raise DpapiError("dpapi_operation_failed")
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        if output.pbData:
            local_free(ctypes.cast(output.pbData, wintypes.HLOCAL))
