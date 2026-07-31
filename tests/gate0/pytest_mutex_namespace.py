"""Pytest-only namespace for the Windows singleton mutex.

Load explicitly with ``-p tests.gate0.pytest_mutex_namespace`` so offline
backup/restore tests never contend with the live production runner.
"""

from __future__ import annotations

import os

from src.application import windows_singleton


_PRODUCTION_MUTEX = windows_singleton.WindowsNamedMutex
_TEST_MUTEX_NAME = rf"Global\NobusSpaceBot-Pytest-{os.getpid()}"


class _PytestWindowsNamedMutex(_PRODUCTION_MUTEX):
    def __init__(self, name: str = _TEST_MUTEX_NAME) -> None:
        super().__init__(name)


def pytest_configure() -> None:
    windows_singleton.WindowsNamedMutex = _PytestWindowsNamedMutex


def pytest_unconfigure() -> None:
    windows_singleton.WindowsNamedMutex = _PRODUCTION_MUTEX
