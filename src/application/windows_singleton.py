"""Cross-session Windows named mutex for one Telegram runner."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


class RunnerAlreadyActive(RuntimeError):
    pass


class WindowsNamedMutex:
    """Hold one bounded named mutex until the process exits."""

    def __init__(self, name: str = r"Global\NobusSpaceBot") -> None:
        if (
            os.name != "nt"
            or not isinstance(name, str)
            or not name.startswith("Global\\")
            or not 7 <= len(name) <= 128
            or "\x00" in name
        ):
            raise ValueError("runner mutex configuration is invalid")
        self._name = name
        self._handle: int | None = None

    def __enter__(self) -> "WindowsNamedMutex":
        kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
        create = kernel32.CreateMutexW
        create.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
        create.restype = wintypes.HANDLE
        handle = create(None, False, self._name)
        if not handle:
            raise RuntimeError("runner mutex unavailable")
        if ctypes.get_last_error() == 183:
            kernel32.CloseHandle(handle)
            raise RunnerAlreadyActive("Telegram runner is already active")
        self._handle = int(handle)
        return self

    def __exit__(self, *values: object) -> None:
        handle, self._handle = self._handle, None
        if handle is not None:
            ctypes.WinDLL("Kernel32.dll", use_last_error=True).CloseHandle(handle)
