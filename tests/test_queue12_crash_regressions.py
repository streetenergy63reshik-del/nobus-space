from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import httpx
import pytest

from src.application.durable_confirmations import DurableTaskConfirmationStore
from src.application import durable_product as durable_product_module
from src.application.durable_product import DurableProductTelegramControlPlane
from src.application.durable_telegram_state import DurableJob, SQLiteTelegramState
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
from src.application.telegram_actions import TelegramAction
from src.application.telegram_product import _QueuedDraft
from src.core.policy import task_contract_digest
from tests.test_product_effect_routes import PUBLIC
from tests.test_telegram_product import (
    _product,
    callback_update,
    text_update,
    voice_update,
)


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
    assert consumed.envelope == ingress.envelope

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
    assert replay.envelope == ingress.envelope
    assert restarted.acknowledge(token, ingress.payload.tenant_id)


def _callback_ingress(
    harness,
    capability_token: str,
    update_id: int,
    user_id: int,
    chat_id: int,
):
    action_token = harness.control._action_store.issue(
        action=TelegramAction.CONFIRM_VOICE,
        capability_token=capability_token,
        user_id=user_id,
        chat_id=chat_id,
        ttl_seconds=300,
    )
    return harness.control._gateway.process_update(
        callback_update(action_token, update_id)
    )


def _expiry_control(harness, confirmations):
    control = object.__new__(DurableProductTelegramControlPlane)
    control._task_confirmations = confirmations
    control._product_runtime = harness.runtime
    control._api = harness.api

    async def deliver_pending():
        return ()

    control.deliver_pending = deliver_pending
    return control


@pytest.mark.asyncio
async def test_expired_durable_voice_confirmation_commits_after_terminal_proof(
    tmp_path: Path,
) -> None:
    harness = _product(tmp_path)
    original = harness.control._gateway.process_update(voice_update(1))
    assert original.payload is not None and original.envelope is not None
    prepared = await harness.runtime.prepare_instruction(
        "voice task", original.envelope
    )
    path = tmp_path / "expired-success.sqlite3"
    state = SQLiteTelegramState(
        path, encode=_encode, decode=_decode, clock=harness.clock
    )
    confirmations = DurableTaskConfirmationStore(state, clock=harness.clock)
    challenge = confirmations.issue(
        message=original.payload,
        envelope=original.envelope,
        prepared=prepared,
        ttl_seconds=1,
    )
    token = challenge.confirmation_token.get_secret_value()
    harness.clock.advance(2)
    callback = _callback_ingress(
        harness, token, 2, original.payload.user_id, original.payload.chat_id
    )
    assert callback.payload is not None and callback.envelope is not None

    await _expiry_control(harness, confirmations)._confirm_voice(
        callback.payload,
        callback.envelope,
        token,
        TaskConfirmationStatus.CONFIRMED,
    )

    restarted = DurableTaskConfirmationStore(
        SQLiteTelegramState(
            path, encode=_encode, decode=_decode, clock=harness.clock
        ),
        clock=harness.clock,
    )
    replay_callback = _callback_ingress(
        harness, token, 3, original.payload.user_id, original.payload.chat_id
    )
    assert replay_callback.payload is not None
    assert replay_callback.envelope is not None
    replay = restarted.consume(
        token=token,
        action=TaskConfirmationStatus.CONFIRMED,
        message=replay_callback.payload,
        envelope=replay_callback.envelope,
    )
    assert replay.status is TaskConfirmationStatus.REJECTED


@pytest.mark.asyncio
async def test_expired_durable_voice_confirmation_retries_after_cancel_failure(
    tmp_path: Path,
) -> None:
    harness = _product(tmp_path)
    original = harness.control._gateway.process_update(voice_update(1))
    assert original.payload is not None and original.envelope is not None
    prepared = await harness.runtime.prepare_instruction(
        "voice task", original.envelope
    )
    path = tmp_path / "expired-retry.sqlite3"
    confirmations = DurableTaskConfirmationStore(
        SQLiteTelegramState(
            path, encode=_encode, decode=_decode, clock=harness.clock
        ),
        clock=harness.clock,
    )
    challenge = confirmations.issue(
        message=original.payload,
        envelope=original.envelope,
        prepared=prepared,
        ttl_seconds=1,
    )
    token = challenge.confirmation_token.get_secret_value()
    harness.clock.advance(2)
    callback = _callback_ingress(
        harness, token, 2, original.payload.user_id, original.payload.chat_id
    )
    assert callback.payload is not None and callback.envelope is not None
    original_cancel = harness.runtime.cancel_prepared
    attempts = 0

    async def fail_cancel(candidate):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("transient cancel failure")

    harness.runtime.cancel_prepared = fail_cancel
    with pytest.raises(RuntimeError, match="could not be terminalized"):
        await _expiry_control(harness, confirmations)._confirm_voice(
            callback.payload,
            callback.envelope,
            token,
            TaskConfirmationStatus.CONFIRMED,
        )
    assert attempts == 3

    successful_attempts = 0

    async def successful_cancel(candidate):
        nonlocal successful_attempts
        successful_attempts += 1
        return await original_cancel(candidate)

    harness.runtime.cancel_prepared = successful_cancel
    restarted = DurableTaskConfirmationStore(
        SQLiteTelegramState(
            path, encode=_encode, decode=_decode, clock=harness.clock
        ),
        clock=harness.clock,
    )
    retry_callback = _callback_ingress(
        harness, token, 3, original.payload.user_id, original.payload.chat_id
    )
    assert retry_callback.payload is not None
    assert retry_callback.envelope is not None
    await _expiry_control(harness, restarted)._confirm_voice(
        retry_callback.payload,
        retry_callback.envelope,
        token,
        TaskConfirmationStatus.CONFIRMED,
    )
    assert successful_attempts == 1
    assert await harness.runtime.is_task_terminal(
        prepared.contract.tenant_id,
        prepared.contract.task_id,
        task_contract_digest(prepared.contract),
    )
    after_commit = DurableTaskConfirmationStore(
        SQLiteTelegramState(
            path, encode=_encode, decode=_decode, clock=harness.clock
        ),
        clock=harness.clock,
    )
    final_callback = _callback_ingress(
        harness, token, 4, original.payload.user_id, original.payload.chat_id
    )
    assert final_callback.payload is not None
    assert final_callback.envelope is not None
    final = after_commit.consume(
        token=token,
        action=TaskConfirmationStatus.CONFIRMED,
        message=final_callback.payload,
        envelope=final_callback.envelope,
    )
    assert final.status is TaskConfirmationStatus.REJECTED


@pytest.mark.asyncio
async def test_durable_voice_job_recovers_with_original_envelope(
    tmp_path: Path,
) -> None:
    harness = _product(tmp_path)
    original = harness.control._gateway.process_update(voice_update(1))
    assert original.payload is not None and original.envelope is not None
    prepared = await harness.runtime.prepare_instruction(
        "voice task", original.envelope
    )
    state = SQLiteTelegramState(
        tmp_path / "voice-state.sqlite3",
        encode=_encode,
        decode=_decode,
        clock=harness.clock,
    )
    confirmations = DurableTaskConfirmationStore(state, clock=harness.clock)
    challenge = confirmations.issue(
        message=original.payload,
        envelope=original.envelope,
        prepared=prepared,
    )
    token = challenge.confirmation_token.get_secret_value()
    callback = _callback_ingress(
        harness, token, 2, original.payload.user_id, original.payload.chat_id
    )
    assert callback.payload is not None and callback.envelope is not None

    admission = object.__new__(DurableProductTelegramControlPlane)
    admission._closing = False
    admission._telegram_state = state
    admission._task_confirmations = confirmations
    admission._product_runtime = harness.runtime
    admission._api = harness.api

    async def start_workers():
        return None

    admission.start = start_workers
    admission._wake = lambda: None
    await admission._confirm_voice(
        callback.payload,
        callback.envelope,
        token,
        TaskConfirmationStatus.CONFIRMED,
    )

    durable = state.claim(lease_owner=__import__("uuid").uuid4())
    assert durable is not None

    class Runtime:
        recovered = None

        async def recover_prepared(self, candidate, envelope):
            self.recovered = (candidate, envelope)
            return True

    runtime = Runtime()
    recovery = object.__new__(DurableProductTelegramControlPlane)
    recovery._product_runtime = runtime
    restored = await recovery._restore(durable)

    assert isinstance(restored, _QueuedDraft)
    assert restored.message == callback.payload
    assert restored.envelope == callback.envelope
    assert runtime.recovered == (prepared, original.envelope)


@pytest.mark.asyncio
async def test_progress_card_gets_stages_and_periodic_heartbeat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _product(tmp_path)
    ingress = harness.control._gateway.process_update(text_update("safe task", 1))
    assert ingress.payload is not None and ingress.envelope is not None
    prepared = await harness.runtime.prepare_instruction(
        "safe task", ingress.envelope
    )
    state = SQLiteTelegramState(
        tmp_path / "progress-state.sqlite3",
        encode=_encode,
        decode=_decode,
    )
    state.save_progress(
        tenant_id=prepared.contract.tenant_id,
        task_id=prepared.contract.task_id,
        chat_id=7,
        message_id=11,
    )
    edits: list[str] = []

    class Api:
        async def edit_message_text(
            self, chat_id: int, message_id: int, text: str
        ) -> None:
            assert (chat_id, message_id) == (7, 11)
            edits.append(text)

    control = object.__new__(DurableProductTelegramControlPlane)
    control._telegram_state = state
    control._api = Api()

    async def draft(prepared_value, message, envelope, *, progress):
        await progress("Codex выполняет задачу")
        await asyncio.sleep(0.03)
        await progress("Проверяю результат")

    async def renew(job):
        await asyncio.Event().wait()

    control._draft_and_present = draft
    control._renew = renew
    monkeypatch.setattr(
        durable_product_module, "_PROGRESS_INTERVAL_SECONDS", 0.01
    )
    job = _QueuedDraft(prepared, ingress.payload, ingress.envelope)
    durable = DurableJob(
        __import__("uuid").uuid4(),
        "draft",
        prepared.contract.tenant_id,
        prepared.contract.task_id,
        task_contract_digest(prepared.contract),
        {},
        1,
    )

    await control._execute_with_lease(durable, job)

    assert any("Codex выполняет задачу" in text for text in edits)
    assert any("Проверяю результат" in text for text in edits)
    assert sum("В работе:" in text for text in edits) >= 3
    assert all("Task:" not in text and "Event:" not in text for text in edits)


@pytest.mark.asyncio
async def test_recovery_error_replaces_progress_card_with_safe_final(
    tmp_path: Path,
) -> None:
    state = SQLiteTelegramState(
        tmp_path / "recovery-progress.sqlite3",
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
    edits: list[str] = []

    class Api:
        async def edit_message_text(
            self, chat_id: int, message_id: int, text: str
        ) -> None:
            edits.append(text)

    control = object.__new__(DurableProductTelegramControlPlane)
    control._telegram_state = state
    control._api = Api()
    durable = DurableJob(
        __import__("uuid").uuid4(),
        "draft",
        "owner",
        task_id,
        "sha256:" + "a" * 64,
        {},
        3,
    )

    await control._finish_progress_with_error(durable)

    assert edits == [
        "⚠️ Задачу не удалось восстановить. Отправьте её повторно."
    ]
    assert state.read_progress(tenant_id="owner", task_id=task_id) is None


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


def test_product_status_surfaces_dead_letter(tmp_path: Path) -> None:
    state = SQLiteTelegramState(
        tmp_path / "status-state.sqlite3",
        encode=_encode,
        decode=_decode,
    )
    task_id = __import__("uuid").uuid4()
    state.enqueue(
        kind="draft",
        tenant_id="owner",
        task_id=task_id,
        binding_digest="sha256:" + "a" * 64,
        payload={"task": str(task_id)},
    )
    owner = __import__("uuid").uuid4()
    job = state.claim(lease_owner=owner)
    assert job is not None
    state.fail(job, lease_owner=owner, failure_code="runtime_job_failed")
    control = object.__new__(DurableProductTelegramControlPlane)
    control._telegram_state = state
    control._voice_service = object()
    control._worker_error = None

    status = control._status_text()

    assert "Сбойных задач: 1" in status
    assert "Состояние очереди: требует проверки" in status


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
