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


def test_restore_rolls_back_new_and_existing_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = tmp_path / "runtime"
    backup = tmp_path / "backup"
    runtime.mkdir()
    backup.mkdir()
    names = sorted(restore_telegram_runtime._NAMES)
    manifest_files = []
    for name in names:
        source = backup / name
        _database(source, f"new:{name}")
        content = source.read_bytes()
        manifest_files.append(
            {
                "name": name,
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    _database(runtime / names[0], "old")
    manifest = backup / "manifest.json"
    unsigned = {
        "schema_version": 1,
        "quiescent": True,
        "files": manifest_files,
    }
    manifest_digest = canonical_json_digest(unsigned)
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
    monkeypatch.setattr(restore_telegram_runtime, "RUNTIME", runtime)
    monkeypatch.setattr(
        restore_telegram_runtime,
        "validate_runtime_database",
        lambda path: None,
    )
    monkeypatch.setattr(
        restore_telegram_runtime,
        "checkpoint",
        lambda path: None,
    )
    original_replace = restore_telegram_runtime.replace_durable
    installed = 0

    def fail_second(source, target):
        nonlocal installed
        if Path(source).name in names:
            installed += 1
            if installed == 2:
                raise OSError("simulated interruption")
        return original_replace(source, target)

    monkeypatch.setattr(
        restore_telegram_runtime, "replace_durable", fail_second
    )
    approval = "telegram-owner-confirmation:sha256:" + "a" * 64
    with pytest.raises(OSError, match="simulated"):
        restore_telegram_runtime.restore(manifest, approval_ref=approval)

    assert _marker(runtime / names[0]) == "old"
    assert not (runtime / names[1]).exists()
    assert not (runtime / names[2]).exists()
