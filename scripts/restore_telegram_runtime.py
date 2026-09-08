"""Authenticated staged restore with exact target and no stale-state overwrite."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application.runtime_maintenance import (
    BACKUP_SCHEMA_VERSION, MAX_BACKUP_DATABASE_BYTES, RUNTIME_DATABASE_NAMES,
    REQUIRED_RUNTIME_DATABASE_NAMES, application_binding, checked_path, checkpoint,
    cleanup_staging, copy_durable, database_state_digest, expire_runtime_voice,
    file_evidence, invalidate_restored_authority, lock_runtime_databases,
    recover_interrupted_restore, replace_durable, require_free_space,
    restore_journal_values, runtime_database_paths, runtime_target_binding,
    unlink_durable, unprotect_backup, validate_runtime_database, validate_runtime_set,
    write_bytes_durable, write_journal,
)
from src.application.windows_singleton import WindowsNamedMutex
from src.contracts.models import canonical_json_digest
from src.security.dpapi import unprotect_current_user

RUNTIME = (ROOT / ".runtime").resolve()
_BACKUP_ENTROPY = b"nobus-space:runtime-backup:v3"
_NAMES = RUNTIME_DATABASE_NAMES
_APPROVAL = re.compile(r"^telegram-owner-confirmation:sha256:[0-9a-f]{64}$")


def restore(manifest_path: Path, *, approval_ref: str, expected_target: str,
            expected_manifest: str, runtime: Path | None = None) -> None:
    if _APPROVAL.fullmatch(approval_ref) is None:
        raise ValueError("restore approval is invalid")
    with WindowsNamedMutex():
        _restore_quiescent(manifest_path, runtime or RUNTIME,
                           expected_target=expected_target, expected_manifest=expected_manifest)


def _verified_manifest(manifest_path: Path) -> dict:
    manifest_path = checked_path(manifest_path)
    if not manifest_path.is_file() or manifest_path.stat().st_size > 64 * 1024:
        raise ValueError("backup manifest is invalid")
    values = json.loads(manifest_path.read_text(encoding="utf-8"))
    try:
        unsigned = {key: value for key, value in values.items() if key != "authentication"}
        digest = canonical_json_digest(unsigned)
        auth_path = checked_path(manifest_path.parent / "manifest-auth.bin")
        if not auth_path.is_file() or not 0 < auth_path.stat().st_size <= 4096:
            raise ValueError("backup authentication is invalid")
        authenticated = unprotect_current_user(
            auth_path.read_bytes(),
            entropy=_BACKUP_ENTROPY).decode("ascii")
    except Exception:
        raise ValueError("backup manifest authentication failed") from None
    files = values.get("files")
    if (set(values) != {"schema_version", "created_at", "quiescent", "source_binding", "application", "files", "authentication"}
            or type(values["schema_version"]) is not int or values["schema_version"] != BACKUP_SCHEMA_VERSION
            or values["quiescent"] is not True or authenticated != digest
            or values["authentication"] != {"file": "manifest-auth.bin", "manifest_digest": digest}
            or not isinstance(values["source_binding"], str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", values["source_binding"]) is None
            or not isinstance(files, list) or not 3 <= len(files) <= 4):
        raise ValueError("backup manifest is invalid")
    try:
        created = datetime.fromisoformat(values["created_at"])
        if created.tzinfo is None or created.utcoffset() is None:
            raise ValueError
        names = {item["name"] for item in files}
        if not REQUIRED_RUNTIME_DATABASE_NAMES <= names <= RUNTIME_DATABASE_NAMES or len(names) != len(files):
            raise ValueError
        for item in files:
            if (set(item) != {"name", "bytes", "sha256", "plaintext_bytes", "plaintext_sha256", "state_digest"}
                    or type(item["bytes"]) is not int or not 0 < item["bytes"] <= 72 * 1024 * 1024
                    or type(item["plaintext_bytes"]) is not int or not 0 < item["plaintext_bytes"] <= MAX_BACKUP_DATABASE_BYTES
                    or any(not isinstance(item[key], str) or re.fullmatch(r"[0-9a-f]{64}", item[key]) is None for key in ("sha256", "plaintext_sha256"))
                    or re.fullmatch(r"sha256:[0-9a-f]{64}", item["state_digest"]) is None):
                raise ValueError
    except (ValueError, TypeError, KeyError):
        raise ValueError("backup manifest is invalid") from None
    current = application_binding()
    binding = values["application"]
    if (not isinstance(binding, dict) or set(binding) != set(current)
            or re.fullmatch(r"[0-9a-f]{40}", str(binding.get("source_commit"))) is None
            or any(binding[key] != current[key] for key in current if key != "source_commit")):
        raise ValueError("backup application version mismatch")
    return values


def _restore_quiescent(manifest_path: Path, runtime: Path, *, expected_target: str | None = None,
                       expected_manifest: str | None = None) -> None:
    runtime = checked_path(runtime)
    values = _verified_manifest(manifest_path)
    if (expected_target != runtime_target_binding(runtime)
            or expected_manifest != values["authentication"]["manifest_digest"]):
        raise ValueError("restore target or manifest binding mismatch")
    files = values["files"]
    names = {item["name"] for item in files}
    runtime.mkdir(parents=True, exist_ok=True)
    recover_interrupted_restore(runtime)
    present = tuple(path for path in runtime_database_paths(runtime) if path.exists())
    if present:
        if {path.name for path in present} != names:
            raise RuntimeError("restore target requires reconciliation")
        with lock_runtime_databases(present):
            validate_runtime_set(runtime)
            if any(database_state_digest(runtime / item["name"]) != item["state_digest"] for item in files):
                raise RuntimeError("restore target requires reconciliation")
    else:
        if any((runtime / (name + suffix)).exists() for name in names for suffix in ("-wal", "-shm")):
            raise RuntimeError("restore target requires reconciliation")
    require_free_space(runtime, sum(item["plaintext_bytes"] for item in files) * 3)
    staging = Path(tempfile.mkdtemp(prefix="restore-", dir=runtime))
    identity = (staging.stat().st_dev, staging.stat().st_ino)
    journal_written = False
    try:
        for item in files:
            source = checked_path(manifest_path.parent / (item["name"] + ".dpapi"))
            if file_evidence(source) != {"bytes": item["bytes"], "sha256": item["sha256"]}:
                raise ValueError("backup file integrity mismatch")
            content = unprotect_backup(source.read_bytes())
            if len(content) != item["plaintext_bytes"] or hashlib.sha256(content).hexdigest() != item["plaintext_sha256"]:
                raise ValueError("backup plaintext integrity mismatch")
            staged = staging / item["name"]
            write_bytes_durable(staged, content)
            # Original encrypted files are never modified or decoded as application payload.
            expire_runtime_voice(staged)
            validate_runtime_database(staged)
        validate_runtime_set(staging)
        invalidate_restored_authority(staging)
        from src.application.runtime_reconciliation import bind_restore
        bind_restore(staging, runtime, values)
        for name in sorted(names):
            checkpoint(staging / name)
            target = runtime / name
            checkpoint(target)
            if target.exists():
                copy_durable(target, staging / (name + ".previous"))
        # Recheck after lock/space/staging work: rollback never overwrites a newer watermark.
        if present and any(database_state_digest(runtime / item["name"]) != item["state_digest"] for item in files):
            raise RuntimeError("restore target requires reconciliation")
        write_journal(runtime, restore_journal_values(runtime, staging, names))
        journal_written = True
        for name in sorted(names):
            replace_durable(staging / name, checked_path(runtime / name, root=runtime))
            for suffix in ("-wal", "-shm"):
                unlink_durable(checked_path(runtime / (name + suffix), root=runtime))
        validate_runtime_set(runtime)
        unlink_durable(runtime / "restore-journal.json")
        journal_written = False
        cleanup_staging(runtime, staging, identity, names)
    except BaseException:
        if journal_written:
            recover_interrupted_restore(runtime)
        elif staging.exists():
            cleanup_staging(runtime, staging, identity, names)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--approval-ref", required=True)
    parser.add_argument("--target-binding", required=True)
    parser.add_argument("--manifest-digest", required=True)
    parser.add_argument("--runtime", type=Path, default=RUNTIME)
    values = parser.parse_args()
    try:
        restore(values.manifest, approval_ref=values.approval_ref, expected_target=values.target_binding,
                expected_manifest=values.manifest_digest, runtime=values.runtime)
    except Exception:
        print('{"status":"FAIL","code":"restore_unavailable_reconcile_required"}')
        return 1
    print('{"status":"PASS"}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
