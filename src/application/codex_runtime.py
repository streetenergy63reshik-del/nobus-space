"""Exact local native SDK runtime; the owner's Codex configuration is untouched."""
from __future__ import annotations

import json
from pathlib import Path

from src.application.runtime_maintenance import checked_path, file_evidence

PROFILE_NAME = "codex-runtime.local.json"
CODEX_VERSION = "0.153.4"
NATIVE_FILES = {
    "codex.exe": {"bytes": 295408944, "sha256": "ccdc9eb9dd71fbcfb03ad42c4eca2b0d6ff6fbd32ebe9416550e6244561e559b"},
    "codex-command-runner.exe": {"bytes": 8204592, "sha256": "326b35527130bfd66aeda214813e418943fad337eaf497372afa5822f7f62d54"},
    "codex-windows-sandbox-setup.exe": {"bytes": 15413040, "sha256": "476502bbe566a87d328d1e0a91680ab2a6536372b2de69818e51c13580ab102e"},
    "codex-code-mode-host.exe": {"bytes": 72475952, "sha256": "11a2ca7db48ee292f177584768657e7488ce8ef1e851b065b2f4d5f37f89a71d"},
}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate native profile field")
        result[key] = value
    return result


def qualified_codex_executable(worktree: Path) -> Path:
    """Validate the profile and all native bytes without launching a process."""
    try:
        root = checked_path(worktree)
        profile = checked_path(root / PROFILE_NAME, root=root)
        if not profile.is_file() or profile.stat().st_size > 4096:
            raise ValueError
        value = json.loads(profile.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        if (not isinstance(value, dict) or set(value) != {"schema", "version", "directory"}
                or value["schema"] != "nobus-codex-runtime-1" or value["version"] != CODEX_VERSION
                or not isinstance(value["directory"], str)):
            raise ValueError
        directory = Path(value["directory"])
        expected = root / ".runtime" / "native" / ("codex-" + CODEX_VERSION)
        if not directory.is_absolute() or checked_path(directory, root=root) != expected:
            raise ValueError
        if {item.name for item in directory.iterdir()} != set(NATIVE_FILES):
            raise ValueError
        for name, evidence in NATIVE_FILES.items():
            if file_evidence(checked_path(directory / name, root=directory)) != evidence:
                raise ValueError
        return directory / "codex.exe"
    except (OSError, ValueError, TypeError, RuntimeError):
        raise RuntimeError("qualified Codex runtime is unavailable") from None
