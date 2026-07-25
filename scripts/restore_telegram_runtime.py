"""Crash-recoverable L4 restore of the Telegram SQLite database set."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.application.runtime_maintenance import (
    checkpoint,
    copy_durable,
    fsync_directory,
    recover_interrupted_restore,
    replace_durable,
    unlink_durable,
    validate_runtime_database,
    write_bytes_durable,
    write_journal,
)
from src.application.windows_singleton import WindowsNamedMutex
from src.contracts.models import canonical_json_digest
from src.security.dpapi import unprotect_current_user

RUNTIME = (ROOT / ".runtime").resolve()
_BACKUP_ENTROPY = b"nobus-space:runtime-backup:v1"
_NAMES = {
    "telegram-checkpoint.sqlite3",
    "task-runtime.sqlite3",
    "telegram-state.sqlite3",
    "business-notes.sqlite3",
}
_APPROVAL = re.compile(
    r"^telegram-owner-confirmation:sha256:[0-9a-f]{64}$"
)


def restore(manifest_path: Path, *, approval_ref: str) -> None:
    if _APPROVAL.fullmatch(approval_ref) is None:
        raise ValueError("restore approval is invalid")
    with WindowsNamedMutex():
        _restore_quiescent(manifest_path, RUNTIME)


def _restore_quiescent(manifest_path: Path, runtime: Path) -> None:
    runtime.mkdir(parents=True, exist_ok=True)
    recover_interrupted_restore(runtime)
    manifest_path = manifest_path.resolve(strict=True)
    values = json.loads(manifest_path.read_text(encoding="utf-8"))
    authentication = (
        values.get("authentication") if isinstance(values, dict) else None
    )
    unsigned = (
        {key: value for key, value in values.items() if key != "authentication"}
        if isinstance(values, dict)
        else {}
    )
    expected_manifest_digest = canonical_json_digest(unsigned)
    authentication_path = manifest_path.parent / "manifest-auth.bin"
    try:
        authenticated_digest = unprotect_current_user(
            authentication_path.read_bytes(),
            entropy=_BACKUP_ENTROPY,
        ).decode("ascii")
    except Exception:
        raise ValueError("backup manifest authentication failed") from None
    files = values.get("files") if isinstance(values, dict) else None
    created_at_valid = False
    if isinstance(values, dict) and isinstance(values.get("created_at"), str):
        try:
            created_at = datetime.fromisoformat(values["created_at"])
            created_at_valid = (
                created_at.tzinfo is not None
                and created_at.utcoffset() is not None
            )
        except ValueError:
            pass
    files_valid = (
        isinstance(files, list)
        and len(files) == len(_NAMES)
        and all(
            isinstance(item, dict)
            and set(item) == {"name", "bytes", "sha256"}
            and item["name"] in _NAMES
            and type(item["bytes"]) is int
            and item["bytes"] >= 0
            and isinstance(item["sha256"], str)
            and re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is not None
            for item in files
        )
        and {item["name"] for item in files} == _NAMES
    )
    if (
        authentication
        != {
            "file": "manifest-auth.bin",
            "manifest_digest": expected_manifest_digest,
        }
        or authenticated_digest != expected_manifest_digest
        or type(values.get("schema_version")) is not int
        or values["schema_version"] != 2
        or set(values) != {
            "schema_version",
            "created_at",
            "quiescent",
            "files",
            "authentication",
        }
        or not created_at_valid
        or values.get("quiescent") is not True
        or not files_valid
    ):
        raise ValueError("backup manifest is invalid")
    staging = Path(tempfile.mkdtemp(prefix="restore-", dir=runtime))
    journal_written = False
    try:
        for item in files:
            source = manifest_path.parent / item["name"]
            content = source.read_bytes()
            if (
                len(content) != item["bytes"]
                or hashlib.sha256(content).hexdigest() != item["sha256"]
            ):
                raise ValueError("backup manifest is invalid")
            staged = staging / item["name"]
            write_bytes_durable(staged, content)
            validate_runtime_database(staged)
        for name in sorted(_NAMES):
            target = runtime / name
            checkpoint(target)
            if target.exists():
                copy_durable(target, staging / f"{name}.previous")
        write_journal(
            runtime,
            {
                "schema_version": 1,
                "staging": str(staging),
                "names": sorted(_NAMES),
            },
        )
        journal_written = True
        for name in sorted(_NAMES):
            target = runtime / name
            replace_durable(staging / name, target)
            unlink_durable(runtime / f"{name}-wal")
            unlink_durable(runtime / f"{name}-shm")
        for name in sorted(_NAMES):
            validate_runtime_database(runtime / name)
        unlink_durable(runtime / "restore-journal.json")
        journal_written = False
        shutil.rmtree(staging)
        fsync_directory(runtime)
    except BaseException:
        if journal_written:
            recover_interrupted_restore(runtime)
        else:
            shutil.rmtree(staging, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--approval-ref", required=True)
    values = parser.parse_args()
    restore(values.manifest, approval_ref=values.approval_ref)
    print('{"status":"PASS"}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
