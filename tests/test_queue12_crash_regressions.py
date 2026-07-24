from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import httpx
import pytest

from src.application.durable_confirmations import DurableTaskConfirmationStore
from src.application.durable_product import DurableProductTelegramControlPlane
from src.application.durable_telegram_state import SQLiteTelegramState
from src.application.network_commands import NetworkCommandRunner
from src.application.network_tools import Quarantine, SafeDownloader
from src.application.owner_workspace import OwnerWorkspace
from src.application.product_effects import (
    DurableProductEffectVault,
    ProductEffectKind,
    ProductEffectService,
    approval_reference,
)
from src.application.runtime_maintenance import (
    JOURNAL_NAME,
    RUNTIME_DATABASE_NAMES,
    recover_interrupted_restore,
    write_journal,
)
from src.application.task_confirmation import TaskConfirmationStatus
from tests.test_product_effect_routes import PUBLIC
from tests.test_telegram_product import _product, text_update


def _encode(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _decode(value: bytes) -> object:
    return json.loads(value)


@pytest.mark.asyncio
async def test_confirmed_voice_capability_survives_admission_failure_and_restart(
    tmp_path: Path,
) -> None:
    harness = _product(tmp_path)
    ingress = harness.control._gateway.process_update(text_update("safe task", 1))
    assert ingress.payload is not None and ingress.envelope is not None
    prepared = await harness.runtime.prepare_instruction(
        "safe task", ingress.envelope
    )
    path = tmp_path / "telegram-state.sqlite3"
    state = SQLiteTelegramState(
        path,
        encode=_encode,
        decode=_decode,
        clock=harness.clock,
    )
    first = DurableTaskConfirmationStore(state, clock=harness.clock)
    challenge = first.issue(
        message=ingress.payload,
        envelope=ingress.envelope,
        prepared=prepared,
    )
    token = challenge.confirmation_token.get_secret_value()

    consumed = first.consume(
        token=token,
        action=TaskConfirmationStatus.CONFIRMED,
        message=ingress.payload,
        envelope=ingress.envelope,
    )
    assert consumed.prepared == prepared

    # A failed durable enqueue releases only the in-process claim. The
    # encrypted capability must still hydrate after a fresh process starts.
    first.release(token, ingress.payload.tenant_id)
    restarted = DurableTaskConfirmationStore(
        SQLiteTelegramState(
            path,
            encode=_encode,
            decode=_decode,
            clock=harness.clock,
        ),
        clock=harness.clock,
    )
    replay = restarted.consume(
        token=token,
        action=TaskConfirmationStatus.CONFIRMED,
        message=ingress.payload,
        envelope=ingress.envelope,
    )

    assert replay.prepared == prepared
    assert restarted.acknowledge(token, ingress.payload.tenant_id)


@pytest.mark.asyncio
async def test_restarted_executing_network_effect_is_never_run_twice(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "NOBUS SPACE BOT"
    quarantine = workspace / "downloads"
    workspace.mkdir()
    quarantine.mkdir()
    (workspace / "requirements.txt").write_text(
        "example==1.0 --hash=sha256:" + "a" * 64 + "\n",
        encoding="utf-8",
    )
    git = tmp_path / "git.exe"
    python = tmp_path / "python.exe"
    git.touch()
    python.touch()
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500))
    )
    vault = DurableProductEffectVault(
        SQLiteTelegramState(
            tmp_path / "effects.sqlite3",
            encode=_encode,
            decode=_decode,
        )
    )
    runner = NetworkCommandRunner(
        workspace_root=workspace,
        git_executable=git,
        python_executable=python,
    )
    service = ProductEffectService(
        vault=vault,
        workspace=OwnerWorkspace(workspace),
        downloader=SafeDownloader(
            client=client, resolver=lambda *args, **kwargs: PUBLIC
        ),
        quarantine=Quarantine(quarantine),
        network_runner=runner,
    )
    challenge = service.prepare_network(
        "pip-install|.|requirements.txt",
        tenant_id="owner",
        user_id=7,
        chat_id=7,
    )
    binding = vault.read(
        challenge.token,
        tenant_id="owner",
        user_id=7,
        chat_id=7,
    )
    assert binding is not None
    vault.transition(binding, state="executing")

    def forbidden_run(*args: object, **kwargs: object) -> object:
        raise AssertionError("an interrupted network effect must not rerun")

    runner.run = forbidden_run  # type: ignore[method-assign]
    result = await service.resolve(
        challenge.token,
        expected_kind=ProductEffectKind.NETWORK,
        approve=True,
        tenant_id="owner",
        user_id=7,
        chat_id=7,
        approval_ref=approval_reference(
            actor_identity="telegram:owner",
            query_id="restart",
            effect_token=challenge.token,
        ),
    )

    assert "ручной" in result.message
    assert service.acknowledge_delivery(
        challenge.token,
        tenant_id="owner",
        user_id=7,
        chat_id=7,
    )
    await client.aclose()


def _database(path: Path, marker: str) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE marker(value TEXT NOT NULL)")
        connection.execute("INSERT INTO marker VALUES (?)", (marker,))
        connection.commit()


def _marker(path: Path) -> str:
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute("SELECT value FROM marker").fetchone()[0]


def test_startup_recovers_power_loss_during_multi_database_restore(
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "runtime"
    staging = runtime / "restore-test"
    runtime.mkdir()
    staging.mkdir()
    names = sorted(RUNTIME_DATABASE_NAMES)
    for name in names:
        _database(runtime / name, "partially-installed")
        _database(staging / f"{name}.previous", f"before-restore:{name}")
        (runtime / f"{name}-wal").write_bytes(b"orphan")
        (runtime / f"{name}-shm").write_bytes(b"orphan")
    write_journal(
        runtime,
        {
            "schema_version": 1,
            "staging": str(staging),
            "names": names,
        },
    )

    assert recover_interrupted_restore(runtime)
    for name in names:
        assert _marker(runtime / name) == f"before-restore:{name}"
        assert not (runtime / f"{name}-wal").exists()
        assert not (runtime / f"{name}-shm").exists()
    assert not (runtime / JOURNAL_NAME).exists()
    assert not staging.exists()


def test_restore_recovery_is_idempotent_after_second_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.application import runtime_maintenance

    runtime = tmp_path / "runtime"
    staging = runtime / "restore-test"
    runtime.mkdir()
    staging.mkdir()
    names = sorted(RUNTIME_DATABASE_NAMES)
    for name in names:
        _database(runtime / name, "partially-installed")
        _database(staging / f"{name}.previous", f"before-restore:{name}")
    write_journal(
        runtime,
        {
            "schema_version": 1,
            "staging": str(staging),
            "names": names,
        },
    )
    original_replace = runtime_maintenance.replace_durable
    replacements = 0

    def fail_second(source: Path, target: Path) -> None:
        nonlocal replacements
        replacements += 1
        if replacements == 2:
            raise OSError("second recovery crash")
        original_replace(source, target)

    monkeypatch.setattr(runtime_maintenance, "replace_durable", fail_second)
    with pytest.raises(RuntimeError, match="interrupted restore recovery failed"):
        recover_interrupted_restore(runtime)
    assert (runtime / JOURNAL_NAME).is_file()
    assert all((staging / f"{name}.previous").is_file() for name in names)

    monkeypatch.setattr(
        runtime_maintenance,
        "replace_durable",
        original_replace,
    )
    assert recover_interrupted_restore(runtime)
    for name in names:
        assert _marker(runtime / name) == f"before-restore:{name}"
    assert not (runtime / JOURNAL_NAME).exists()
    assert not staging.exists()


@pytest.mark.parametrize(
    "values",
    (
        {"schema_version": 1, "names": ["telegram-state.sqlite3"]},
        {
            "schema_version": True,
            "names": sorted(RUNTIME_DATABASE_NAMES),
        },
        {
            "schema_version": 1.0,
            "names": sorted(RUNTIME_DATABASE_NAMES),
        },
        {
            "schema_version": 2,
            "names": sorted(RUNTIME_DATABASE_NAMES),
        },
        {
            "schema_version": 1,
            "names": [
                "telegram-checkpoint.sqlite3",
                "task-runtime.sqlite3",
                "unknown.sqlite3",
            ],
        },
    ),
)
def test_restore_recovery_rejects_untrusted_journal_shape(
    tmp_path: Path,
    values: dict[str, object],
) -> None:
    runtime = tmp_path / "runtime"
    staging = runtime / "restore-test"
    runtime.mkdir()
    staging.mkdir()
    write_journal(
        runtime,
        {**values, "staging": str(staging)},
    )

    with pytest.raises(RuntimeError, match="interrupted restore recovery failed"):
        recover_interrupted_restore(runtime)


def test_restore_recovery_rejects_runtime_as_staging(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    names = sorted(RUNTIME_DATABASE_NAMES)
    for name in names:
        _database(runtime / name, f"original:{name}")
    write_journal(
        runtime,
        {
            "schema_version": 1,
            "staging": str(runtime),
            "names": names,
        },
    )

    with pytest.raises(RuntimeError, match="interrupted restore recovery failed"):
        recover_interrupted_restore(runtime)
    assert runtime.is_dir()
    for name in names:
        assert _marker(runtime / name) == f"original:{name}"


@pytest.mark.asyncio
async def test_progress_binding_survives_telegram_delete_failure(
    tmp_path: Path,
) -> None:
    state = SQLiteTelegramState(
        tmp_path / "telegram-state.sqlite3",
        encode=_encode,
        decode=_decode,
    )
    task_id = __import__("uuid").uuid4()
    state.save_progress(
        tenant_id="owner",
        task_id=task_id,
        chat_id=7,
        message_id=11,
    )

    class Api:
        fail = True

        async def delete_message(self, chat_id: int, message_id: int) -> None:
            assert (chat_id, message_id) == (7, 11)
            if self.fail:
                raise RuntimeError("temporary Telegram failure")

    control = object.__new__(DurableProductTelegramControlPlane)
    control._telegram_state = state
    control._api = Api()

    with pytest.raises(RuntimeError, match="progress message cleanup failed"):
        await control._clear_progress_binding("owner", task_id)
    assert state.read_progress(tenant_id="owner", task_id=task_id) is not None

    control._api.fail = False
    await control._clear_progress_binding("owner", task_id)
    assert state.read_progress(tenant_id="owner", task_id=task_id) is None
