from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from scripts.check_telegram_health import check
from src.application.durable_product import DurableProductTelegramControlPlane
from src.application.durable_telegram_state import (
    DurableTelegramStateError,
    SQLiteTelegramState,
)
from src.application.network_commands import NetworkCommandRunner
from src.application.network_tools import Quarantine, SafeDownloader
from src.application.owner_workspace import OwnerWorkspace
from src.application.product_effects import (
    DurableProductEffectVault,
    ProductEffectService,
)
from src.application.telegram_actions import TelegramAction
from src.contracts.models import canonical_json_digest
from src.transport.telegram import CallbackQuery
from src.workers.codex_cli import _WEB_ARGV
from src.workers.windows_job import _ARGV_PROFILES
from tests.test_product_effect_routes import PUBLIC
from tests.test_telegram_product import (
    _product,
    callback_update,
    text_update,
)


def _encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _decode(value):
    return json.loads(value)


def test_expired_lease_cannot_ack_before_reclaim(tmp_path: Path) -> None:
    now = datetime(2026, 7, 24, tzinfo=UTC)

    def clock() -> datetime:
        return now

    state = SQLiteTelegramState(
        tmp_path / "state.sqlite3",
        encode=_encode,
        decode=_decode,
        clock=clock,
    )
    task_id = uuid4()
    state.enqueue(
        kind="draft",
        tenant_id="owner",
        task_id=task_id,
        binding_digest=canonical_json_digest({"task": str(task_id)}),
        payload={"safe": True},
    )
    owner = uuid4()
    leased = state.claim(lease_owner=owner, lease_seconds=5)
    assert leased is not None
    now += timedelta(seconds=6)
    with pytest.raises(
        DurableTelegramStateError, match="runtime_job_lease_lost"
    ):
        state.ack(leased, lease_owner=owner)


def test_health_rejects_unreadable_protected_payload(tmp_path: Path) -> None:
    path = tmp_path / "telegram-state.sqlite3"
    state = SQLiteTelegramState(path)
    state.put_capability(
        kind="action",
        token_digest="sha256:" + "a" * 64,
        tenant_id="owner",
        payload={"safe": True},
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE telegram_capabilities SET payload=?",
            (b"not-dpapi",),
        )
        connection.commit()
    assert check((path,))["status"] == "FAIL"


def test_web_profile_is_allowlisted_by_windows_job() -> None:
    assert _WEB_ARGV in _ARGV_PROFILES


def test_artifact_rejects_xml_control_characters(tmp_path: Path) -> None:
    workspace = OwnerWorkspace(tmp_path)
    with pytest.raises(ValueError, match="content"):
        workspace.propose(
            "bad.docx",
            title="Bad",
            paragraphs=("unsafe\x07value",),
        )


@pytest.mark.asyncio
async def test_completed_document_survives_send_failure_and_retries(
    tmp_path: Path,
) -> None:
    harness = _product(tmp_path)
    root = tmp_path / "NOBUS SPACE BOT"
    quarantine = root / "Загрузки"
    root.mkdir()
    quarantine.mkdir()
    git = tmp_path / "git.exe"
    python = tmp_path / "python.exe"
    git.touch()
    python.touch()
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500))
    )
    service = ProductEffectService(
        vault=DurableProductEffectVault(
            SQLiteTelegramState(
                tmp_path / "effects.sqlite3",
                encode=_encode,
                decode=_decode,
            )
        ),
        workspace=OwnerWorkspace(root),
        downloader=SafeDownloader(
            client=client, resolver=lambda *args, **kwargs: PUBLIC
        ),
        quarantine=Quarantine(quarantine),
        network_runner=NetworkCommandRunner(
            workspace_root=root,
            git_executable=git,
            python_executable=python,
        ),
    )
    harness.control._product_effects = service
    await harness.control.handle(
        text_update("/document report.html|Отчёт|Готово", 1)
    )
    action_token = harness.api.sent[-1][2][0][1]
    original = harness.api.send_document
    attempts = 0

    async def flaky(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary Telegram failure")
        return await original(*args, **kwargs)

    harness.api.send_document = flaky
    with pytest.raises(RuntimeError, match="temporary"):
        await harness.control.handle(callback_update(action_token, 2))
    assert (root / "report.html").is_file()

    await harness.control.handle(callback_update(action_token, 3))
    assert attempts == 2
    assert len(harness.api.documents) == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_effect_callback_is_durably_enqueued_without_execution(tmp_path: Path) -> None:
    calls = []

    class State:
        def enqueue(self, **values):
            calls.append(values)

    control = object.__new__(DurableProductTelegramControlPlane)
    control._closing = False
    control._telegram_state = State()
    control._execution_workers = ()

    async def start():
        return None

    control.start = start
    control._wake = lambda: None
    harness = _product(tmp_path)
    ingress = harness.control._gateway.process_update(text_update("safe", 1))
    assert ingress.payload is not None and ingress.envelope is not None
    callback = CallbackQuery(
        update_id=2,
        tenant_id=ingress.payload.tenant_id,
        actor_identity=ingress.payload.actor_identity,
        actor_role=ingress.payload.actor_role,
        auth_context_ref=ingress.payload.auth_context_ref,
        user_id=ingress.payload.user_id,
        chat_id=ingress.payload.chat_id,
        message_id=102,
        query_id="query-2",
        callback_token="A" * 32,
    )

    queued = await control._submit_effect(
        callback,
        ingress.envelope,
        TelegramAction.RUN_NETWORK,
        "effect-token",
    )

    assert queued
    assert calls[0]["kind"] == "effect"
