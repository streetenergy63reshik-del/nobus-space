"""Minimal Windows helper that starts an allowlisted child after a gated bind."""

from __future__ import annotations

import ctypes
import os
import re
import subprocess
import sys
from pathlib import Path


_READ_ARGV = (
    "exec",
    "--json",
    "--ephemeral",
    "--ignore-user-config",
    "--ignore-rules",
    "--config",
    'web_search="disabled"',
    "--config",
    "mcp_servers={}",
    "--config",
    'shell_environment_policy.inherit="all"',
    "--config",
    'shell_environment_policy.include_only=["PATH","SYSTEMROOT","TEMP","TMP","LANG","NO_COLOR","PYTHONUTF8","TERM"]',
    "--config",
    "shell_environment_policy.experimental_use_profile=false",
    "--sandbox",
    "read-only",
    "-",
)
_WRITE_ARGV = (*_READ_ARGV[:-3], "--sandbox", "workspace-write", "-")
_ARGV_PROFILES = frozenset({_READ_ARGV, _WRITE_ARGV})
_GATE_RE = re.compile(r"^Local\\NobusOrchestrator-[0-9a-f]{32}$")
_SYNCHRONIZE = 0x00100000
_WAIT_OBJECT_0 = 0
_GATE_WAIT_MS = 30_000


def _validated(argv: list[str]) -> tuple[str, tuple[str, ...]]:
    if len(argv) < 3 or argv[1] != "--":
        raise ValueError("helper arguments are invalid")
    gate = argv[0]
    executable = Path(argv[2])
    profile = tuple(argv[3:])
    if (
        os.name != "nt"
        or _GATE_RE.fullmatch(gate) is None
        or not executable.is_absolute()
        or not executable.is_file()
        or profile not in _ARGV_PROFILES
    ):
        raise ValueError("helper arguments are invalid")
    return gate, (str(executable.resolve(strict=True)), *profile)


def _wait_for_gate(name: str) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenEventW.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p)
    kernel32.OpenEventW.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel32.CloseHandle.restype = ctypes.c_int
    handle = kernel32.OpenEventW(_SYNCHRONIZE, False, name)
    if not handle:
        raise OSError("startup gate is unavailable")
    try:
        if kernel32.WaitForSingleObject(handle, _GATE_WAIT_MS) != _WAIT_OBJECT_0:
            raise OSError("startup gate wait failed")
    finally:
        kernel32.CloseHandle(handle)


def main(argv: list[str] | None = None) -> int:
    failed = False
    command: tuple[str, ...] | None = None
    gate = ""
    try:
        gate, command = _validated(list(sys.argv[1:] if argv is None else argv))
        _wait_for_gate(gate)
    except (OSError, RuntimeError, TypeError, ValueError):
        failed = True
    if failed or command is None:
        return 125
    try:
        child = subprocess.Popen(
            command,
            stdin=sys.stdin.buffer,
            stdout=sys.stdout.buffer,
            stderr=sys.stderr.buffer,
            close_fds=True,
        )
        return child.wait()
    except BaseException:
        return 125


if __name__ == "__main__":
    raise SystemExit(main())
