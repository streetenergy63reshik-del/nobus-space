from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.application.desktop_bridge import DesktopBridgeService
from src.application.telegram_product import ProductTelegramControlPlane
from src.application.desktop_bridge_state import (
    BridgeRequestStatus, DesktopMenuCallbackStore, SQLiteDesktopBridgeState,
)
from src.contracts import IngressKind, IngressSource, TrustedIngressEnvelope
from src.integrations.codex_desktop_catalog import (
    CatalogProject, CatalogTask, CodexDesktopCatalog, DesktopCatalogError,
)
from src.integrations.codex_desktop_ipc import DesktopIpcError
from src.transport.telegram.gateway import InMemoryUpdateIdStore, TelegramGateway
from src.transport.telegram.models import ActorBinding, CallbackQuery, TextMessage
from src.transport.telegram.models import IngressStatus


PROJECT_ID = "21bb4a0e-3f4a-4674-a9eb-e38ab8ac2a80"
THREAD_ID = "01a0e1df-a0bc-73a2-8c2b-f75ed9dc0a47"


class Catalog:
    def __init__(self, path: Path) -> None:
        self.project = CatalogProject(PROJECT_ID, "Nobus Space", path)
        self.task = CatalogTask(THREAD_ID, "Задача в Desktop", PROJECT_ID, 100)
        self.reads = 0

    def projects(self):
        self.reads += 1
        return (self.project,)

    def tasks(self, project_id):
        assert project_id == PROJECT_ID
        self.reads += 1
        return (self.task,)


class Api:
    def __init__(self) -> None:
        self.sent = []
        self.edits = []
        self.answers = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text, kwargs))
        return len(self.sent)

    async def edit_message_text(self, chat_id, message_id, text, **kwargs):
        self.edits.append((chat_id, message_id, text, kwargs))

    async def answer_callback_query(self, query_id, *, text=None):
        self.answers.append((query_id, text))


class Ipc:
    available = True

    @property
    def connected(self):
        return self.available

    async def start(self):
        if not self.available:
            raise RuntimeError("offline")

    async def close(self):
        pass


def _state(path: Path):
    return SQLiteDesktopBridgeState(
        path, encode=lambda value: json.dumps(value).encode(),
        decode=lambda value: json.loads(value),
    )


def _envelope(message_id: int) -> TrustedIngressEnvelope:
    return TrustedIngressEnvelope.model_construct(
        schema_version="1", ingress_id=uuid4(), tenant_id="owner",
        actor_identity="telegram:participant:41",
        auth_context_ref="sha256:" + "a" * 64,
        source=IngressSource.TELEGRAM, kind=IngressKind.TEXT,
        external_message_id=f"message:{message_id}",
        idempotency_key="sha256:" + format(message_id, "064x"),
        content_ref="sha256:" + "c" * 64,
        received_at=datetime.now(UTC), envelope_revision="sha256:" + "d" * 64,
    )


def _text(text: str, message_id: int, *, reply: int | None = None,
          user_id: int = 41, is_bot: bool = False) -> TextMessage:
    return TextMessage(
        update_id=message_id, tenant_id="owner",
        actor_identity=f"telegram:participant:{user_id}", actor_role="participant",
        auth_context_ref="sha256:" + "a" * 64, user_id=user_id,
        is_bot=is_bot, is_forwarded=False, chat_id=-1001,
        message_thread_id=7, reply_to_message_id=reply,
        binding_purpose="business_notes", message_id=message_id, text=text,
    )


def _callback(token: str, *, user_id: int = 41) -> CallbackQuery:
    return CallbackQuery(
        update_id=200, tenant_id="owner",
        actor_identity=f"telegram:participant:{user_id}", actor_role="participant",
        auth_context_ref="sha256:" + "a" * 64, user_id=user_id,
        is_bot=False, is_forwarded=False, chat_id=-1001,
        message_thread_id=7, binding_purpose="business_notes",
        message_id=1, query_id="query-1", callback_token=token,
    )


def _service(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    api, ipc = Api(), Ipc()
    state = _state(tmp_path / "state.sqlite3")
    service = DesktopBridgeService(
        api=api, state=state, uia=object(),
        projects={"Nobus Space": project}, catalog=Catalog(project),
        owner_user_id=99, owner_private_chat_id=99,
        bot_username="Nobusspacebot", ipc_factory=lambda: ipc,
    )
    scheduled = []
    service._schedule = scheduled.append
    return service, api, ipc, state, scheduled


@pytest.mark.asyncio
async def test_tile_menu_selects_exact_desktop_task_and_submits_once(tmp_path: Path):
    service, api, _, state, scheduled = _service(tmp_path)
    assert await service.handle(_text("/codex", 11), _envelope(11))
    project_button = api.sent[0][2]["button_rows"][0][0][1]
    assert await service.handle(_callback(project_button), _envelope(200))
    task_button = api.edits[-1][3]["button_rows"][0][1][1]
    assert await service.handle(_callback(task_button), _envelope(201))
    assert api.sent[1][2]["force_reply"] is True
    assert await service.handle(_text("Сделай проверку", 12, reply=2), _envelope(12))
    requests = state.list_requests(statuses=frozenset({BridgeRequestStatus.RECEIVED}))
    assert len(requests) == 1
    assert requests[0].operation == "continue"
    assert requests[0].desktop_thread_id == THREAD_ID
    assert requests[0].project_name == "Nobus Space"
    assert requests[0].payload["instruction"] == "Сделай проверку"
    assert requests[0].payload["requested_task_title"] == "Задача в Desktop"
    assert scheduled == [requests[0].request_id]
    await service.handle(_text("Сделай проверку", 13, reply=2), _envelope(13))
    assert len(state.list_requests(statuses=frozenset({BridgeRequestStatus.RECEIVED}))) == 1


@pytest.mark.asyncio
async def test_inactive_desktop_blocks_any_menu_button(tmp_path: Path):
    service, api, ipc, state, _ = _service(tmp_path)
    await service.handle(_text("/codex", 11), _envelope(11))
    token = api.sent[0][2]["button_rows"][0][0][1]
    ipc.available = False
    assert await service.handle(_callback(token), _envelope(200))
    assert "Codex не активен" in api.answers[-1][1]
    assert not api.edits
    menu = state.menu_for_reply(chat_id=-1001, message_id=1)
    assert menu is not None and menu.stage == "projects"


@pytest.mark.asyncio
async def test_issued_tile_passes_gateway_and_stale_tile_is_rejected(tmp_path: Path):
    service, api, ipc, state, _ = _service(tmp_path)
    await service.handle(_text("/codex", 11), _envelope(11))
    token = api.sent[0][2]["button_rows"][0][0][1]
    legacy_claims = []

    class LegacyActions:
        def claim(self, value, user_id, chat_id):
            legacy_claims.append((value, user_id, chat_id))
            return False

    callback_store = DesktopMenuCallbackStore(LegacyActions(), state)
    gateway = TelegramGateway(
        actor_bindings={(99, -1001): ActorBinding(
            tenant_id="owner", actor_identity="telegram:owner",
            role="owner", auth_context_ref="sha256:" + "a" * 64,
            purpose="business_notes",
        )},
        update_id_store=InMemoryUpdateIdStore(),
        callback_token_store=callback_store,
    )

    def update(update_id):
        return {"update_id": update_id, "callback_query": {
            "id": f"query-{update_id}", "from": {"id": 41},
            "message": {"message_id": 1, "chat": {"id": -1001},
                        "message_thread_id": 7}, "data": token,
        }}

    assert not callback_store.claim(token, 42, -1001)
    assert not callback_store.claim(token, 41, -1002)
    assert not callback_store.claim("unknown-action-token", 41, -1001)
    assert legacy_claims == [("unknown-action-token", 41, -1001)]
    ipc.available = False
    offline = gateway.process_update(update(201))
    assert offline.status is IngressStatus.ACCEPTED
    assert await service.handle(offline.payload, offline.envelope)
    assert "Codex не активен" in api.answers[-1][1]
    ipc.available = True
    accepted = gateway.process_update(update(202))
    assert accepted.status is IngressStatus.ACCEPTED
    assert await service.handle(accepted.payload, accepted.envelope)
    assert api.edits
    assert gateway.process_update(update(203)).status is IngressStatus.REJECTED


@pytest.mark.asyncio
async def test_bot_agent_uses_same_menu_by_numbered_replies(tmp_path: Path):
    service, api, _, state, scheduled = _service(tmp_path)
    await service.handle(_text("/codex@Nobusspacebot", 11, is_bot=True), _envelope(11))
    await service.handle(_text("1", 12, reply=1, is_bot=True), _envelope(12))
    await service.handle(_text("2", 13, reply=1, is_bot=True), _envelope(13))
    await service.handle(_text("Продолжи задачу", 14, reply=2, is_bot=True), _envelope(14))
    requests = state.list_requests(statuses=frozenset({BridgeRequestStatus.RECEIVED}))
    assert len(requests) == 1
    assert requests[0].desktop_thread_id == THREAD_ID
    assert len(scheduled) == 1


@pytest.mark.asyncio
async def test_other_participant_cannot_use_menu(tmp_path: Path):
    service, api, _, _, _ = _service(tmp_path)
    await service.handle(_text("/codex", 11), _envelope(11))
    token = api.sent[0][2]["button_rows"][0][0][1]
    await service.handle(_callback(token, user_id=42), _envelope(200))
    assert "недоступно" in api.answers[-1][1]
    assert not api.edits


@pytest.mark.asyncio
async def test_back_at_each_stage_and_stale_prompt_cannot_dispatch(tmp_path: Path):
    service, api, _, state, _ = _service(tmp_path)
    await service.handle(_text("/codex", 11), _envelope(11))
    project_token = api.sent[0][2]["button_rows"][0][0][1]
    await service.handle(_callback(project_token), _envelope(200))
    task_token = api.edits[-1][3]["button_rows"][0][1][1]
    await service.handle(_callback(task_token), _envelope(201))
    back_from_prompt = api.edits[-1][3]["button_rows"][0][0][1]
    await service.handle(_callback(back_from_prompt), _envelope(202))
    await service.handle(_text("Старый промт", 15, reply=2), _envelope(15))
    assert not state.list_requests(statuses=frozenset({BridgeRequestStatus.RECEIVED}))
    back_from_tasks = api.edits[-1][3]["button_rows"][-1][0][1]
    await service.handle(_callback(back_from_tasks), _envelope(203))
    back_from_projects = api.edits[-1][3]["button_rows"][-1][-1][1]
    await service.handle(_callback(back_from_projects), _envelope(204))
    assert "закрыто" in api.edits[-1][2]


@pytest.mark.asyncio
async def test_new_task_tile_uses_current_project_name(tmp_path: Path):
    service, api, _, state, scheduled = _service(tmp_path)
    await service.handle(_text("/codex", 11), _envelope(11))
    catalog = service._catalog
    assert catalog is not None
    catalog.project = CatalogProject(PROJECT_ID, "Переименованный проект", catalog.project.cwd)
    project_token = api.sent[0][2]["button_rows"][0][0][1]
    await service.handle(_callback(project_token), _envelope(200))
    new_token = api.edits[-1][3]["button_rows"][0][0][1]
    await service.handle(_callback(new_token), _envelope(201))
    await service.handle(_text("Новая работа", 12, reply=2), _envelope(12))
    requests = state.list_requests(statuses=frozenset({BridgeRequestStatus.RECEIVED}))
    assert len(requests) == 1
    assert requests[0].operation == "create"
    assert requests[0].project_name == "Переименованный проект"
    assert requests[0].payload["catalog_project_id"] == PROJECT_ID
    assert requests[0].payload["catalog_project_cwd"] == str(catalog.project.cwd)
    assert (await service._bound_project(requests[0])).cwd == catalog.project.cwd
    catalog.project = CatalogProject(str(uuid4()), "Переименованный проект", catalog.project.cwd)
    with pytest.raises(DesktopIpcError, match="desktop-project-changed"):
        await service._bound_project(requests[0])
    catalog.project = CatalogProject(PROJECT_ID, "Переименованный проект", tmp_path)
    with pytest.raises(DesktopIpcError, match="desktop-project-changed"):
        await service._bound_project(requests[0])
    assert scheduled == [requests[0].request_id]


def test_catalog_reads_current_saved_projects_and_tasks(tmp_path: Path):
    owner = tmp_path / "owner"
    project_root = owner / "project"
    project_root.mkdir(parents=True)
    project_root = project_root.resolve()
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    state_path = codex_home / ".codex-global-state.json"
    state_path.write_text(json.dumps({
        "local-projects": {PROJECT_ID: {
            "id": PROJECT_ID, "name": "Nobus Space", "rootPaths": [str(project_root)],
        }},
        "project-order": [PROJECT_ID],
        "thread-project-assignments": {THREAD_ID: {
            "projectKind": "local", "projectId": PROJECT_ID,
        }},
    }), encoding="utf-8")
    with sqlite3.connect(codex_home / "state_5.sqlite") as db:
        db.execute("""CREATE TABLE threads (
            id TEXT, name TEXT, title TEXT, recency_at_ms INTEGER,
            thread_source TEXT, agent_path TEXT, archived INTEGER)""")
        db.execute("INSERT INTO threads VALUES (?,?,?,?,?,?,?)",
                   (THREAD_ID, "Точное имя", "старый заголовок", 100,
                    "user", None, 0))
    catalog = CodexDesktopCatalog(codex_home, owner_root=owner)
    assert catalog.projects()[0].name == "Nobus Space"
    assert catalog.tasks(PROJECT_ID)[0].title == "Точное имя"
    with sqlite3.connect(codex_home / "state_5.sqlite") as db:
        db.execute("UPDATE threads SET name='Новое имя' WHERE id=?", (THREAD_ID,))
    assert catalog.tasks(PROJECT_ID)[0].title == "Новое имя"
    remote_id, subagent_id = str(uuid4()), str(uuid4())
    snapshot = json.loads(state_path.read_text(encoding="utf-8"))
    snapshot["thread-project-assignments"].update({
        remote_id: {"projectKind": "local", "projectId": PROJECT_ID},
        subagent_id: {"projectKind": "local", "projectId": PROJECT_ID},
    })
    snapshot["thread-project-membership-host-ids"] = {remote_id: "remote-host"}
    state_path.write_text(json.dumps(snapshot), encoding="utf-8")
    with sqlite3.connect(codex_home / "state_5.sqlite") as db:
        db.executemany("INSERT INTO threads VALUES (?,?,?,?,?,?,?)", [
            (remote_id, "Чужой host", "", 200, "user", None, 0),
            (subagent_id, "Внутренний агент", "", 300, "subagent", None, 0),
        ])
    assert [item.thread_id for item in catalog.tasks(PROJECT_ID)] == [THREAD_ID]


def test_catalog_rejects_project_outside_owner_root(tmp_path: Path):
    owner = tmp_path / "owner"
    outside = tmp_path / "outside"
    owner.mkdir()
    outside.mkdir()
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    (codex_home / ".codex-global-state.json").write_text(json.dumps({
        "local-projects": {PROJECT_ID: {
            "id": PROJECT_ID, "name": "Outside", "rootPaths": [str(outside.resolve())],
        }},
        "project-order": [PROJECT_ID],
    }), encoding="utf-8")
    with pytest.raises(DesktopCatalogError, match="desktop-catalog-root"):
        CodexDesktopCatalog(codex_home, owner_root=owner).projects()


@pytest.mark.asyncio
async def test_business_notes_callback_reaches_desktop_bridge_before_other_routes():
    callback = _callback("CdxM_" + "a" * 32 + "_1_0")
    seen = []

    class Bridge:
        async def handle(self, payload, envelope):
            seen.append((payload, envelope))
            return True

    control = SimpleNamespace(_desktop_bridge=Bridge(), _enable_extended_routes=False)
    envelope = _envelope(200)
    ingress = SimpleNamespace(
        status=IngressStatus.ACCEPTED, payload=callback, envelope=envelope,
    )
    assert await ProductTelegramControlPlane._handle_ingress(control, ingress)
    assert seen == [(callback, envelope)]
