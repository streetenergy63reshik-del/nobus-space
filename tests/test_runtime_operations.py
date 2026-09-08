from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest

from scripts import restore_telegram_runtime
from src.application.durable_product import DurableProductTelegramControlPlane
from src.application.durable_telegram_state import DurableJob
from src.application.fake_vertical import FakeVerticalResponse, FakeVerticalStatus
from src.application.patch_confirmation import PatchProposal, patch_proposal_digest
from src.application.telegram_product import _QueuedPatch
from src.contracts.models import canonical_json_digest


def _proposal() -> PatchProposal:
    task_id = uuid4()
    values: dict[str, object] = {
        "tenant_id": "owner",
        "task_id": task_id,
        "contract_digest": canonical_json_digest({"contract": str(task_id)}),
        "result_revision": 1,
        "result_digest": canonical_json_digest({"result": str(task_id)}),
        "output_digest": canonical_json_digest({"output": str(task_id)}),
        "base_revision": "a" * 40,
        "summary": "safe",
        "patch": (
            "diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n"
            "@@ -1 +1 @@\n-a\n+b\n"
        ),
        "paths": ("a.txt",),
    }
    return PatchProposal(
        **values,
        patch_digest=patch_proposal_digest(
            {**values, "task_id": str(task_id)}
        ),
    )


@pytest.mark.asyncio
async def test_lost_lease_cancels_long_operation() -> None:
    started = __import__("asyncio").Event()
    cancelled = __import__("asyncio").Event()

    class Runtime:
        async def apply_proposal(self, *args, **kwargs):
            started.set()
            try:
                await __import__("asyncio").Event().wait()
            except __import__("asyncio").CancelledError:
                cancelled.set()
                raise

    control = object.__new__(DurableProductTelegramControlPlane)
    control._cleanup_pending = set()
    control._product_runtime = Runtime()

    async def no_delivery():
        return None

    async def lose_lease(_job):
        await started.wait()
        raise RuntimeError("lease lost")

    control.deliver_pending = no_delivery
    control._renew = lose_lease
    proposal = _proposal()
    queued = _QueuedPatch(proposal, "telegram:owner", "approval")
    durable = DurableJob(
        uuid4(),
        "patch",
        "owner",
        proposal.task_id,
        proposal.patch_digest,
        {},
        1,
        uuid4(),
    )

    with pytest.raises(RuntimeError, match="lease lost"):
        await control._execute_with_lease(durable, queued)
    assert cancelled.is_set()


def _database(path: Path, marker: str) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE marker(value TEXT NOT NULL)")
        connection.execute("INSERT INTO marker VALUES (?)", (marker,))
        connection.commit()


def _marker(path: Path) -> str:
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute("SELECT value FROM marker").fetchone()[0]


@pytest.mark.parametrize("schema_version", (True, 1.0))
def test_restore_manifest_requires_exact_integer_schema_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    schema_version: object,
) -> None:
    backup = tmp_path / "backup"
    runtime = tmp_path / "runtime"
    backup.mkdir()
    unsigned = {
        "schema_version": schema_version,
        "quiescent": True,
        "files": [
            {"name": name}
            for name in sorted(restore_telegram_runtime._NAMES)
        ],
    }
    manifest_digest = canonical_json_digest(unsigned)
    manifest = backup / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                **unsigned,
                "authentication": {
                    "file": "manifest-auth.bin",
                    "manifest_digest": manifest_digest,
                },
            }
        ),
        encoding="utf-8",
    )
    (backup / "manifest-auth.bin").write_bytes(b"test-auth")
    monkeypatch.setattr(
        restore_telegram_runtime,
        "unprotect_current_user",
        lambda value, *, entropy: manifest_digest.encode("ascii"),
    )

    with pytest.raises(ValueError, match="backup manifest is invalid"):
        restore_telegram_runtime._restore_quiescent(manifest, runtime)


@pytest.mark.parametrize(
    "mutation",
    ("missing_created_at", "extra_root", "extra_file", "bool_bytes"),
)
def test_restore_manifest_v2_requires_exact_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    backup = tmp_path / "backup"
    runtime = tmp_path / "runtime"
    backup.mkdir()
    files = [
        {"name": name, "bytes": 0, "sha256": "0" * 64}
        for name in sorted(restore_telegram_runtime._NAMES)
    ]
    unsigned: dict[str, object] = {
        "schema_version": 2,
        "created_at": "2026-07-24T00:00:00+00:00",
        "quiescent": True,
        "files": files,
    }
    if mutation == "missing_created_at":
        unsigned.pop("created_at")
    elif mutation == "extra_root":
        unsigned["unexpected"] = True
    elif mutation == "extra_file":
        files[0]["unexpected"] = True
    else:
        files[0]["bytes"] = True
    digest = canonical_json_digest(unsigned)
    manifest = backup / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                **unsigned,
                "authentication": {
                    "file": "manifest-auth.bin",
                    "manifest_digest": digest,
                },
            }
        ),
        encoding="utf-8",
    )
    (backup / "manifest-auth.bin").write_bytes(b"test-auth")
    monkeypatch.setattr(
        restore_telegram_runtime,
        "unprotect_current_user",
        lambda value, *, entropy: digest.encode("ascii"),
    )

    with pytest.raises(ValueError, match="backup manifest is invalid"):
        restore_telegram_runtime._restore_quiescent(manifest, runtime)


def test_restore_refuses_partial_existing_target(tmp_path: Path) -> None:
    from tests.test_c5_backup_recovery import fixture_runtime, safe_restore
    from scripts.backup_telegram_runtime import _backup_quiescent
    from src.application.runtime_maintenance import runtime_database_paths
    source = tmp_path / "source"
    fixture_runtime(source)
    manifest = _backup_quiescent(runtime_database_paths(source), tmp_path / "backup")
    target = tmp_path / "partial"
    target.mkdir()
    _database(target / "task-runtime.sqlite3", "preserve-original")
    with pytest.raises(RuntimeError, match="reconciliation"):
        safe_restore(manifest, target)
    assert _marker(target / "task-runtime.sqlite3") == "preserve-original"
