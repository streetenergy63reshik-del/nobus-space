"""Create a quiescent verified backup of the Telegram SQLite set."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.application.runtime_maintenance import (
    RUNTIME_DATABASE_NAMES,
    fsync_directory,
    validate_runtime_database,
    write_bytes_durable,
)
from src.contracts.models import canonical_json_digest
from src.security.dpapi import protect_current_user
from src.application.windows_singleton import WindowsNamedMutex

_BACKUP_ENTROPY = b"nobus-space:runtime-backup:v1"
_SOURCES = (
    ROOT / ".runtime" / "telegram-checkpoint.sqlite3",
    ROOT / ".runtime" / "task-runtime.sqlite3",
    ROOT / ".runtime" / "telegram-state.sqlite3",
    ROOT / ".runtime" / "business-notes.sqlite3",
)


def backup(sources: tuple[Path, ...], destination: Path) -> Path:
    if destination.exists() or destination == ROOT or not sources:
        raise ValueError("backup destination must be a new directory")
    with WindowsNamedMutex():
        return _backup_quiescent(sources, destination)


def _backup_quiescent(
    sources: tuple[Path, ...], destination: Path
) -> Path:
    if (
        len(sources) != len(RUNTIME_DATABASE_NAMES)
        or {Path(source).name for source in sources} != RUNTIME_DATABASE_NAMES
    ):
        raise ValueError("backup requires the complete runtime database set")
    resolved_sources: list[Path] = []
    before: dict[Path, tuple[int, int]] = {}
    for source in sources:
        resolved = source.resolve(strict=True)
        if not resolved.is_file() or resolved.suffix != ".sqlite3":
            raise ValueError("backup source is invalid")
        validate_runtime_database(resolved)
        stat = resolved.stat()
        resolved_sources.append(resolved)
        before[resolved] = (stat.st_size, stat.st_mtime_ns)
    if len({source.parent for source in resolved_sources}) != 1:
        raise ValueError("backup sources must share one runtime directory")
    destination.mkdir(parents=True)
    manifest: dict[str, object] = {
        "schema_version": 2,
        "created_at": datetime.now(UTC).isoformat(),
        "quiescent": True,
        "files": [],
    }
    for resolved in resolved_sources:
        target = destination / resolved.name
        with closing(sqlite3.connect(resolved)) as current, closing(
            sqlite3.connect(target)
        ) as output:
            current.backup(output)
        validate_runtime_database(target)
        manifest["files"].append(
            {
                "name": target.name,
                "bytes": target.stat().st_size,
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            }
        )
    after = {
        source: (source.stat().st_size, source.stat().st_mtime_ns)
        for source in resolved_sources
    }
    if after != before:
        raise RuntimeError("runtime changed during backup")
    manifest_digest = canonical_json_digest(manifest)
    authentication_name = "manifest-auth.bin"
    manifest["authentication"] = {
        "file": authentication_name,
        "manifest_digest": manifest_digest,
    }
    write_bytes_durable(
        destination / authentication_name,
        protect_current_user(
            manifest_digest.encode("ascii"),
            entropy=_BACKUP_ENTROPY,
        ),
    )
    manifest_path = destination / "manifest.json"
    with manifest_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(
            manifest,
            stream,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    fsync_directory(destination)
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument("--source", action="append", type=Path, default=None)
    values = parser.parse_args()
    result = backup(
        tuple(values.source) if values.source else _SOURCES,
        values.destination,
    )
    print(
        json.dumps(
            {"status": "PASS", "manifest": str(result)},
            ensure_ascii=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
