"""Quiescent encrypted backup of the actual local runtime store inventory."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application.runtime_maintenance import (
    BACKUP_SCHEMA_VERSION, MAX_BACKUP_DATABASE_BYTES, application_binding,
    checked_path, database_connection_state_digest, database_state_digest,
    expire_runtime_voice,
    file_evidence, fsync_directory, lock_runtime_databases, protect_backup,
    require_free_space, runtime_database_paths, runtime_target_binding,
    validate_runtime_database, validate_runtime_set, write_bytes_durable,
)
from src.application.windows_singleton import WindowsNamedMutex
from src.contracts.models import canonical_json_digest
from src.security.dpapi import protect_current_user

_BACKUP_ENTROPY = b"nobus-space:runtime-backup:v3"


def backup(sources: tuple[Path, ...], destination: Path) -> Path:
    with WindowsNamedMutex():
        return _backup_quiescent(sources, destination)


def _backup_quiescent(sources: tuple[Path, ...], destination: Path) -> Path:
    destination = checked_path(destination)
    if destination.exists() or not sources:
        raise ValueError("backup destination must be a new directory")
    sources = tuple(checked_path(path) for path in sources)
    runtime = sources[0].parent
    if len(set(sources)) != len(sources) or set(sources) != set(runtime_database_paths(runtime)):
        raise ValueError("backup requires the complete runtime database set")
    if destination == runtime or runtime.is_relative_to(destination):
        raise ValueError("backup destination is invalid")
    identity = application_binding()
    for source in sources:
        expire_runtime_voice(source, require_quiescent=True)
    with lock_runtime_databases(sources):
        validate_runtime_set(runtime)
        sizes = []
        for source in sources:
            with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as connection:
                size = connection.execute("PRAGMA page_count").fetchone()[0] * connection.execute("PRAGMA page_size").fetchone()[0]
            if not 0 < size <= MAX_BACKUP_DATABASE_BYTES:
                raise RuntimeError("backup database size limit exceeded")
            sizes.append(size)
        destination.parent.mkdir(parents=True, exist_ok=True)
        require_free_space(destination.parent, sum(sizes) * 3)
        destination.mkdir()
        manifest: dict[str, object] = {
            "schema_version": BACKUP_SCHEMA_VERSION,
            "created_at": datetime.now(UTC).isoformat(), "quiescent": True,
            "source_binding": runtime_target_binding(runtime),
            "application": identity, "files": [],
        }
        for source in sorted(sources):
            with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as current, closing(sqlite3.connect(":memory:")) as output:
                current.execute("PRAGMA temp_store=MEMORY")
                output.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
                output.setconfig(sqlite3.SQLITE_DBCONFIG_TRUSTED_SCHEMA, False)
                output.execute("PRAGMA temp_store=MEMORY")
                current.backup(output)
                if output.execute("PRAGMA quick_check").fetchone() != ("ok",):
                    raise RuntimeError("backup database verification failed")
                if output.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise RuntimeError("backup foreign key mismatch")
                state_digest = database_connection_state_digest(output)
                content = output.serialize()
            if not 0 < len(content) <= MAX_BACKUP_DATABASE_BYTES:
                raise RuntimeError("backup database size limit exceeded")
            if database_state_digest(source) != state_digest:
                raise RuntimeError("runtime changed during backup")
            encrypted = destination / (source.name + ".dpapi")
            write_bytes_durable(encrypted, protect_backup(content))
            manifest["files"].append({
                "name": source.name, **file_evidence(encrypted),
                "plaintext_bytes": len(content),
                "plaintext_sha256": hashlib.sha256(content).hexdigest(),
                "state_digest": state_digest,
            })
        if identity != application_binding():
            raise RuntimeError("application changed during backup")
    digest = canonical_json_digest(manifest)
    write_bytes_durable(destination / "manifest-auth.bin", protect_current_user(digest.encode("ascii"), entropy=_BACKUP_ENTROPY))
    manifest["authentication"] = {"file": "manifest-auth.bin", "manifest_digest": digest}
    manifest_path = destination / "manifest.json"
    write_bytes_durable(manifest_path, (json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode())
    fsync_directory(destination)
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument("--source", action="append", type=Path, default=None)
    parser.add_argument("--runtime", type=Path, default=ROOT / ".runtime")
    values = parser.parse_args()
    try:
        manifest = backup(tuple(values.source) if values.source else runtime_database_paths(values.runtime), values.destination)
        digest = json.loads(manifest.read_text())["authentication"]["manifest_digest"]
    except Exception:
        print('{"status":"FAIL","code":"backup_unavailable"}')
        return 1
    print(json.dumps({"status": "PASS", "manifest_digest": digest}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
