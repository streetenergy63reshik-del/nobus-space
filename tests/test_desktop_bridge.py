from __future__ import annotations

import json
import sqlite3
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import src.application.desktop_bridge as desktop_bridge_module

from src.application.desktop_bridge import (
    DesktopBridgeService,
    _bridge_turn_text,
    _desktop_execution_settings,
    _desktop_final_text,
    inspect_artifacts,
    snapshot_artifacts,
    telegram_text_parts,
    telegram_visible_final,
    _pending_matches_interaction,
    _interprocess_bootstrap_lock,
    _parse_thread_ref,
    _desktop_cwd_belongs_to_project,
)
from src.application.desktop_bridge_state import (
    BridgeRequestStatus,
    DesktopBridgeStateError,
    InteractionKind,
    SQLiteDesktopBridgeState,
)
from src.integrations.codex_desktop_ipc import (
    DesktopAgentMessage,
    DesktopPendingRequest,
    DesktopTurnState,
    DesktopIpcError,
    DesktopIpcUnavailableError,
)
from src.integrations.codex_desktop_uia import DesktopUiAutomationError
from src.contracts import IngressKind, IngressSource, TrustedIngressEnvelope
from src.transport.telegram.models import TextMessage, VoiceMessage, VoiceMetadata


def _codec():
    return (
        lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True).encode(),
        lambda value: json.loads(value),
    )


def _state(path: Path) -> SQLiteDesktopBridgeState:
    encode, decode = _codec()
    return SQLiteDesktopBridgeState(path, encode=encode, decode=decode)


def _request(state: SQLiteDesktopBridgeState, *, ingress: str, request_id=None):
    return state.create_request(
        request_id=request_id or uuid4(),
        ingress_key=ingress,
        tenant_id="owner",
        author_user_id=41,
        author_identity="telegram:member:41",
        chat_id=-1001,
        topic_id=7,
        source_message_id=12,
        operation="create",
        project_name="nobus-orchestrator-dev",
        payload={"instruction": "Проверь задачу"},
    )


def test_bootstrap_turn_is_bound_once_for_notifier_correlation(tmp_path: Path) -> None:
    state = _state(tmp_path / "telegram-state.sqlite3")
    request = _request(state, ingress="sha256:" + "b" * 64)
    thread_id, turn_id = str(uuid4()), str(uuid4())
    state.transition(
        request.request_id,
        expected=frozenset({BridgeRequestStatus.RECEIVED}),
        status=BridgeRequestStatus.DISPATCHING,
    )
    state.bind_desktop(
        request.request_id, thread_id=thread_id, turn_id=None,
        client_message_id=f"nobus:{request.request_id}",
        status=BridgeRequestStatus.RECEIVED,
    )
    assert state.bind_bootstrap_turn(
        request.request_id, thread_id=thread_id, turn_id=turn_id
    )
    assert state.bind_bootstrap_turn(
        request.request_id, thread_id=thread_id, turn_id=turn_id
    )
    assert not state.bind_bootstrap_turn(
        request.request_id, thread_id=thread_id, turn_id=str(uuid4())
    )


def test_verified_title_is_bound_to_exact_thread_and_survives_store_reopen(tmp_path: Path) -> None:
    path = tmp_path / "telegram-state.sqlite3"
    state = _state(path)
    request = _request(state, ingress="sha256:" + "e" * 64)
    thread_id = str(uuid4())
    state.bind_desktop(
        request.request_id, thread_id=thread_id, turn_id=None,
        client_message_id=f"nobus:{request.request_id}",
        status=BridgeRequestStatus.RECEIVED,
    )
    with pytest.raises(DesktopBridgeStateError, match="thread_conflict"):
        state.remember_thread_title(request.request_id, thread_id=str(uuid4()), title="Wrong")
    assert state.known_thread_title(thread_id) is None
    state.remember_thread_title(request.request_id, thread_id=thread_id, title="Точная задача")
    assert _state(path).known_thread_title(thread_id) == "Точная задача"
    assert state.known_thread_title(str(uuid4())) is None


@pytest.mark.asyncio
async def test_unloaded_owner_opens_only_verified_title_then_rediscovers_exact_id(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path / "telegram-state.sqlite3")
    request = _request(state, ingress="sha256:" + "f" * 64)
    thread_id = str(uuid4())
    request = state.bind_desktop(
        request.request_id, thread_id=thread_id, turn_id=None,
        client_message_id=f"nobus:{request.request_id}",
        status=BridgeRequestStatus.RECEIVED,
    )
    calls: list[tuple[str, str]] = []

    class Client:
        async def find_thread_owner(self, candidate: str):
            calls.append(("discover", candidate))
            if len(calls) == 1:
                raise DesktopIpcUnavailableError("no-client-found")
            return object()

    class Uia:
        async def open_existing(self, *, project_name: str, task_title: str):
            calls.append((project_name, task_title))

    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBridgeService(
        api=_Api(), state=state, uia=Uia(),
        projects={"nobus-orchestrator-dev": project},
        owner_user_id=99, owner_private_chat_id=99, bot_username="Nobusspacebot",
    )
    with pytest.raises(DesktopIpcUnavailableError, match="no-client-found"):
        await service._find_or_open_owner(Client(), request)
    assert calls == [("discover", thread_id)]
    state.remember_thread_title(request.request_id, thread_id=thread_id, title="Точная задача")
    calls.clear()
    owner = await service._find_or_open_owner(Client(), request)
    assert owner is not None
    assert calls == [
        ("discover", thread_id),
        ("nobus-orchestrator-dev", "Точная задача"),
        ("discover", thread_id),
    ]


@pytest.mark.asyncio
async def test_opened_wrong_or_still_unloaded_task_never_substitutes_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state(tmp_path / "telegram-state.sqlite3")
    request = _request(state, ingress="sha256:" + "1" * 64)
    thread_id = str(uuid4())
    request = state.bind_desktop(
        request.request_id, thread_id=thread_id, turn_id=None,
        client_message_id=f"nobus:{request.request_id}",
        status=BridgeRequestStatus.RECEIVED,
    )
    state.remember_thread_title(request.request_id, thread_id=thread_id, title="Старый заголовок")
    calls: list[str] = []

    class Client:
        async def find_thread_owner(self, candidate: str):
            assert candidate == thread_id
            calls.append("discover")
            raise DesktopIpcUnavailableError("no-client-found")

    class Uia:
        async def open_existing(self, *, project_name: str, task_title: str):
            assert project_name == "nobus-orchestrator-dev"
            assert task_title == "Старый заголовок"
            calls.append("open-only")

    async def no_wait(_seconds: float) -> None:
        return None

    monkeypatch.setattr(desktop_bridge_module.asyncio, "sleep", no_wait)
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBridgeService(
        api=_Api(), state=state, uia=Uia(),
        projects={"nobus-orchestrator-dev": project},
        owner_user_id=99, owner_private_chat_id=99, bot_username="Nobusspacebot",
    )
    with pytest.raises(DesktopIpcUnavailableError, match="no-client-found"):
        await service._find_or_open_owner(Client(), request)
    assert calls == ["discover", "open-only"] + ["discover"] * 6
    assert state.read_request(request.request_id).desktop_turn_id is None


def test_existing_bridge_database_adds_bootstrap_turn_binding(tmp_path: Path) -> None:
    path = tmp_path / "telegram-state.sqlite3"
    _state(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "ALTER TABLE desktop_bridge_requests DROP COLUMN bootstrap_turn_id"
        )
    state = _state(path)
    request = _request(state, ingress="sha256:" + "c" * 64)
    thread_id, turn_id = str(uuid4()), str(uuid4())
    state.bind_desktop(
        request.request_id, thread_id=thread_id, turn_id=None,
        client_message_id=f"nobus:{request.request_id}",
        status=BridgeRequestStatus.RECEIVED,
    )
    assert state.bind_bootstrap_turn(
        request.request_id, thread_id=thread_id, turn_id=turn_id
    )


def test_request_replay_is_idempotent_but_conflict_fails_closed(tmp_path: Path) -> None:
    state = _state(tmp_path / "telegram-state.sqlite3")
    request_id = uuid4()
    first = _request(state, ingress="sha256:" + "1" * 64, request_id=request_id)
    replay = _request(state, ingress="sha256:" + "1" * 64, request_id=request_id)
    assert replay == first
    with pytest.raises(DesktopBridgeStateError, match="ingress_conflict"):
        state.create_request(
            request_id=request_id,
            ingress_key="sha256:" + "1" * 64,
            tenant_id="owner",
            author_user_id=99,
            author_identity="telegram:member:99",
            chat_id=-1001,
            topic_id=7,
            source_message_id=12,
            operation="create",
            project_name="nobus-orchestrator-dev",
            payload={"instruction": "Проверь задачу"},
        )


def test_bridge_capacity_allows_replay_and_releases_terminal_slot(
    tmp_path: Path,
) -> None:
    encode, decode = _codec()
    state = SQLiteDesktopBridgeState(
        tmp_path / "telegram-state.sqlite3",
        encode=encode,
        decode=decode,
        max_active_requests=1,
    )
    request_id = uuid4()
    first = _request(
        state, ingress="sha256:" + "1" * 64, request_id=request_id
    )
    assert _request(
        state, ingress="sha256:" + "1" * 64, request_id=request_id
    ) == first
    with pytest.raises(DesktopBridgeStateError, match="queue_full"):
        _request(state, ingress="sha256:" + "2" * 64)
    assert state.transition(
        first.request_id,
        expected=frozenset({BridgeRequestStatus.RECEIVED}),
        status=BridgeRequestStatus.DELIVERED,
    )
    assert _request(state, ingress="sha256:" + "2" * 64)


def test_pending_interaction_capacity_is_per_request_and_idempotent(
    tmp_path: Path,
) -> None:
    encode, decode = _codec()
    state = SQLiteDesktopBridgeState(
        tmp_path / "telegram-state.sqlite3",
        encode=encode,
        decode=decode,
        max_pending_interactions=1,
    )
    request = _request(state, ingress="sha256:" + "3" * 64)
    kwargs = {
        "request_id": request.request_id,
        "kind": InteractionKind.QUESTION,
        "desktop_request_id": 1,
        "desktop_turn_id": "turn-1",
        "target_user_id": 41,
        "generation": 1,
        "payload": {"params": {"questions": [{"id": "q"}]}},
        "expires_at": datetime.now(UTC) + timedelta(hours=1),
    }
    first = state.put_interaction(interaction_id="question-capacity-1", **kwargs)
    assert state.put_interaction(
        interaction_id="question-capacity-1", **kwargs
    ) == first
    with pytest.raises(DesktopBridgeStateError, match="interaction_capacity"):
        state.put_interaction(
            interaction_id="question-capacity-2",
            **{**kwargs, "desktop_request_id": 2},
        )
    assert state.close_interaction(first.interaction_id, status="superseded")
    assert state.put_interaction(
        interaction_id="question-capacity-2",
        **{**kwargs, "desktop_request_id": 2},
    )


def test_pending_interaction_rebinds_exact_request_after_reconnect(tmp_path: Path) -> None:
    state = _state(tmp_path / "telegram-state.sqlite3")
    request = _request(state, ingress="sha256:" + "d" * 64)
    kwargs = dict(
        interaction_id="same-pending", request_id=request.request_id,
        kind=InteractionKind.QUESTION, desktop_request_id=10,
        desktop_turn_id="turn-1", target_user_id=41,
        payload={"method": "item/tool/requestUserInput", "params": {"questions": [{"id": "color"}]}},
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    first = state.put_interaction(generation=1, **kwargs)
    rebound = state.put_interaction(generation=2, **kwargs)
    assert rebound.generation == 2
    assert rebound.expires_at == first.expires_at
    with pytest.raises(DesktopBridgeStateError, match="interaction_conflict"):
        state.put_interaction(generation=3, **{**kwargs, "target_user_id": 99})
    with pytest.raises(DesktopBridgeStateError, match="interaction_conflict"):
        state.put_interaction(generation=3, **{**kwargs, "payload": {"changed": True}})
    with pytest.raises(DesktopBridgeStateError, match="interaction_conflict"):
        state.put_interaction(generation=1, **kwargs)


def test_request_user_input_routes_data_question_but_not_consent() -> None:
    method = "item/tool/requestUserInput"
    def payload(question: str):
        return {"id": 10, "method": method, "params": {
            "questions": [{"id": "choice", "question": question,
                           "options": [{"label": "Да"}, {"label": "Нет"}]}]
        }}
    assert desktop_bridge_module._interaction_kind(
        method, payload("Какой цвет записать в отчёт?")) is InteractionKind.QUESTION
    assert desktop_bridge_module._interaction_kind(
        method, payload("Нужен заголовок в отчёте?")) is InteractionKind.QUESTION
    assert desktop_bridge_module._interaction_kind(
        method, payload("Разрешаете удалить файл?")) is InteractionKind.UNKNOWN
    assert desktop_bridge_module._interaction_kind(
        method, payload("Можно ли мне отправить документ наружу?")) is InteractionKind.UNKNOWN
    assert desktop_bridge_module._interaction_kind(
        method, {**payload("Какой цвет?"), "origin": "app"}
    ) is InteractionKind.UNKNOWN


def test_async_question_is_not_a_final_and_uses_same_authority_classifier() -> None:
    question = DesktopAgentMessage(
        "call-question-1", "Какой цвет записать в отчёт?", "final_answer",
        delivery="async",
        questions=({"title": "Какой цвет записать в отчёт?"},),
    )
    final = DesktopAgentMessage("msg-final-1", "Синий.", "final_answer")
    turn = DesktopTurnState(
        turn_id="turn-1", client_user_message_id="nobus:request-1",
        status="completed", user_text=("test",),
        agent_messages=(question, final), plan_items=(), text_outputs=(question, final),
    )
    assert _desktop_final_text(turn) == "Синий."
    payload = {
        "id": "call-question-1", "method": "item/tool/requestUserInputAsync",
        "params": {"threadId": "thread-1", "turnId": "turn-1",
                   "itemId": "call-question-1", "questions": [
                       {"id": '["request_user_input_async","call-question-1",0]',
                        "question": "Какой цвет записать в отчёт?"},
                   ]},
    }
    assert desktop_bridge_module._interaction_kind(
        "item/tool/requestUserInputAsync", payload,
    ) is InteractionKind.QUESTION
    assert not desktop_bridge_module.render_interaction(
        "user_input", payload,
    ).requires_manual_review
    reply = desktop_bridge_module._async_question_reply_text(payload, "синий")
    assert reply == (
        '<send_user_message_question_reply>\n'
        '[{"questionItemId":"[\\"request_user_input_async\\",\\"call-question-1\\",0]",'
        '"question":"Какой цвет записать в отчёт?","answer":"синий"}]\n'
        '</send_user_message_question_reply>'
    )
    payload["params"]["questions"][0]["question"] = "Разрешаете удалить файл?"
    assert desktop_bridge_module._interaction_kind(
        "item/tool/requestUserInputAsync", payload,
    ) is InteractionKind.UNKNOWN


def test_command_approval_uses_advertised_installed_desktop_decisions() -> None:
    payload = {"params": {"availableDecisions": ["accept", {"acceptWithExecpolicyAmendment": {}}, "cancel"]}}
    assert desktop_bridge_module._command_approval_decision(payload, "разрешаю") == "accept"
    assert desktop_bridge_module._command_approval_decision(payload, "отказать") == "cancel"
    with pytest.raises(DesktopIpcError, match="approval-decision-unavailable"):
        desktop_bridge_module._command_approval_decision(
            {"params": {"availableDecisions": ["cancel"]}}, "разрешаю",
        )


@pytest.mark.asyncio
async def test_async_question_answer_uses_owner_steering_not_sync_input(tmp_path: Path) -> None:
    state = _state(tmp_path / "telegram-state.sqlite3")
    request = _request(state, ingress="sha256:" + "e" * 64)
    request = state.bind_desktop(
        request.request_id, thread_id="thread-1", turn_id="turn-1",
        client_message_id=f"nobus:{request.request_id}",
        status=BridgeRequestStatus.RUNNING,
    )
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBridgeService(
        api=_Api(), state=state, uia=_Uia(), projects={"nobus-orchestrator-dev": project},
        owner_user_id=99, owner_private_chat_id=99, bot_username="Nobusspacebot",
    )
    payload = {
        "id": "call-question-1", "method": "item/tool/requestUserInputAsync",
        "params": {"threadId": "thread-1", "turnId": "turn-1",
                   "itemId": "call-question-1", "questions": [
                       {"id": '["request_user_input_async","call-question-1",0]',
                        "question": "Какой цвет записать в отчёт?"},
                   ]},
    }
    pending = DesktopPendingRequest("call-question-1", payload["method"], payload)
    calls = []

    class Client:
        async def steer_turn(self, *args, **kwargs):
            calls.append((args, kwargs))

        async def submit_user_input(self, *args, **kwargs):
            raise AssertionError("sync input must not handle async question")

    await service._submit_interaction_answer(
        Client(), object(), request,
        SimpleNamespace(kind=InteractionKind.QUESTION, interaction_id="interaction-1"),
        pending, "синий", desktop_cwd=str(project.resolve()),
    )
    assert len(calls) == 1
    assert calls[0][0] == ("thread-1",)
    assert calls[0][1]["client_user_message_id"] == "nobus:question:interaction-1"
    assert "<send_user_message_question_reply>" in calls[0][1]["input_items"][0]["text"]
    restore = calls[0][1]["restore_message"]
    assert restore["id"] == "nobus:question:interaction-1"
    assert restore["cwd"] == str(project.resolve())
    assert restore["text"] == "синий"
    assert restore["context"]["turnTrigger"] == "send_user_message_async_question"


def test_delivery_key_scopes_same_bytes_to_request(tmp_path: Path) -> None:
    state = _state(tmp_path / "telegram-state.sqlite3")
    first = _request(state, ingress="sha256:" + "1" * 64)
    second = _request(state, ingress="sha256:" + "2" * 64)
    digest = "sha256:" + "a" * 64
    one = state.claim_delivery(
        request_id=first.request_id,
        kind="artifact",
        ordinal=0,
        source_digest=digest,
        destination_ref="telegram:-1001:topic:7:reply:12",
        payload={"filename": "same.txt"},
    )
    replay = state.claim_delivery(
        request_id=first.request_id,
        kind="artifact",
        ordinal=0,
        source_digest=digest,
        destination_ref="telegram:-1001:topic:7:reply:12",
        payload={"filename": "same.txt"},
    )
    new_request = state.claim_delivery(
        request_id=second.request_id,
        kind="artifact",
        ordinal=0,
        source_digest=digest,
        destination_ref="telegram:-1001:topic:7:reply:12",
        payload={"filename": "same.txt"},
    )
    assert replay.operation_key == one.operation_key
    assert replay.status == "unknown"
    assert new_request.operation_key != one.operation_key


def test_known_failed_delivery_can_retry_but_inflight_replay_is_unknown(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path / "telegram-state.sqlite3")
    request = _request(state, ingress="sha256:" + "c" * 64)
    values = {
        "request_id": request.request_id,
        "kind": "artifact",
        "ordinal": 0,
        "source_digest": "sha256:" + "d" * 64,
        "destination_ref": "telegram:-1001:topic:7:reply:12",
        "payload": {"filename": "report.bin"},
    }
    first = state.claim_delivery(**values)
    assert first.status == "claimed"
    assert state.finish_delivery(
        first.operation_key,
        telegram_message_id=None,
        status="failed",
    )
    retry = state.claim_delivery(**values)
    assert retry.status == "claimed"
    replay = state.claim_delivery(**values)
    assert replay.status == "unknown"


def test_partial_delivery_releases_active_request_capacity(tmp_path: Path) -> None:
    encode, decode = _codec()
    state = SQLiteDesktopBridgeState(
        tmp_path / "telegram-state.sqlite3",
        encode=encode,
        decode=decode,
        max_active_requests=1,
    )
    first = _request(state, ingress="sha256:" + "e" * 64)
    assert state.transition(
        first.request_id,
        expected=frozenset({BridgeRequestStatus.RECEIVED}),
        status=BridgeRequestStatus.DELIVERY_PARTIAL,
    )
    assert _request(state, ingress="sha256:" + "f" * 64)


def test_same_thread_requests_are_strictly_ordered(tmp_path: Path) -> None:
    state = _state(tmp_path / "telegram-state.sqlite3")
    first = _request(state, ingress="sha256:" + "6" * 64)
    first = state.bind_desktop(
        first.request_id,
        thread_id="thread-serial",
        turn_id="turn-first",
        client_message_id="client-first",
        status=BridgeRequestStatus.RUNNING,
    )
    second = _request(state, ingress="sha256:" + "7" * 64)
    second = state.bind_desktop(
        second.request_id,
        thread_id="thread-serial",
        turn_id=None,
        client_message_id="client-second",
        status=BridgeRequestStatus.RECEIVED,
    )
    assert not state.has_prior_thread_request(first)
    assert state.has_prior_thread_request(second)
    assert state.next_received_for_thread("thread-serial") == second
    state.transition(
        first.request_id,
        expected=frozenset({BridgeRequestStatus.RUNNING}),
        status=BridgeRequestStatus.DELIVERED,
    )
    assert not state.has_prior_thread_request(second)


def test_interaction_is_bound_to_numeric_recipient(tmp_path: Path) -> None:
    state = _state(tmp_path / "telegram-state.sqlite3")
    request = _request(state, ingress="sha256:" + "1" * 64)
    interaction = state.put_interaction(
        interaction_id="question-1",
        request_id=request.request_id,
        kind=InteractionKind.QUESTION,
        desktop_request_id=21,
        desktop_turn_id="turn-1",
        target_user_id=41,
        generation=2,
        payload={"questions": []},
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    assert state.bind_interaction_message(
        interaction.interaction_id,
        telegram_chat_id=-1001,
        telegram_message_id=55,
    )
    assert not state.resolve_interaction(interaction.interaction_id, responder_user_id=42)
    assert state.resolve_interaction(interaction.interaction_id, responder_user_id=41)
    assert not state.resolve_interaction(interaction.interaction_id, responder_user_id=41)


def test_approval_claim_is_exact_atomic_and_expires_before_effect(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    clock_value = [now]
    encode, decode = _codec()
    state = SQLiteDesktopBridgeState(
        tmp_path / "telegram-state.sqlite3", encode=encode, decode=decode,
        clock=lambda: clock_value[0],
    )
    request = _request(state, ingress="sha256:" + "6" * 64)
    payload = {
        "id": 23,
        "method": "item/commandExecution/requestApproval",
        "params": {"threadId": "thread-1", "turnId": "turn-1", "command": "safe"},
    }
    interaction = state.put_interaction(
        interaction_id="approval-claim", request_id=request.request_id,
        kind=InteractionKind.COMMAND_APPROVAL, desktop_request_id=23,
        desktop_turn_id="turn-1", target_user_id=99, generation=1,
        payload=payload, expires_at=now + timedelta(seconds=5),
    )
    same = DesktopPendingRequest(23, payload["method"], payload)
    assert _pending_matches_interaction(same, interaction, "thread-1")
    changed = {
        **payload,
        "params": {**payload["params"], "turnId": "turn-2", "command": "unsafe"},
    }
    assert not _pending_matches_interaction(
        DesktopPendingRequest(23, payload["method"], changed), interaction,
        "thread-1",
    )
    assert not state.claim_interaction_answer(interaction, responder_user_id=41)
    assert state.claim_interaction_answer(interaction, responder_user_id=99)
    assert not state.claim_interaction_answer(interaction, responder_user_id=99)
    assert state.finish_interaction_answer(interaction.interaction_id, status="answered")
    assert not state.claim_interaction_answer(interaction, responder_user_id=99)
    later = state.put_interaction(
        interaction_id="approval-expired-before-claim", request_id=request.request_id,
        kind=InteractionKind.COMMAND_APPROVAL, desktop_request_id=24,
        desktop_turn_id="turn-1", target_user_id=99, generation=1,
        payload={**payload, "id": 24}, expires_at=now + timedelta(seconds=5),
    )
    clock_value[0] = now + timedelta(seconds=6)
    assert not state.claim_interaction_answer(later, responder_user_id=99)


@pytest.mark.asyncio
@pytest.mark.parametrize("change_during_read", ["payload", "expiry"])
async def test_changed_or_expired_approval_never_calls_desktop_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change_during_read: str,
) -> None:
    now = datetime.now(UTC)
    clock_value = [now]
    encode, decode = _codec()
    state = SQLiteDesktopBridgeState(
        tmp_path / "telegram-state.sqlite3", encode=encode, decode=decode,
        clock=lambda: clock_value[0],
    )
    request = _request(state, ingress="sha256:" + "7" * 64)
    state.bind_desktop(
        request.request_id, thread_id="thread-1", turn_id="turn-1",
        client_message_id="client-1", status=BridgeRequestStatus.WAITING_OWNER,
    )
    payload = {
        "id": 23, "method": "item/commandExecution/requestApproval",
        "params": {"threadId": "thread-1", "turnId": "turn-1", "command": "safe"},
    }
    interaction = state.put_interaction(
        interaction_id="approval-read-race", request_id=request.request_id,
        kind=InteractionKind.COMMAND_APPROVAL, desktop_request_id=23,
        desktop_turn_id="turn-1", target_user_id=99, generation=1,
        payload=payload, expires_at=now + timedelta(seconds=5),
    )

    class Client:
        async def find_thread_owner(self, _thread_id):
            return object()

        async def load_complete_history_snapshot(self, _thread_id, *, owner):
            if change_during_read == "expiry":
                clock_value[0] = now + timedelta(seconds=6)
            return object()

        async def close(self):
            pass

    changed_payload = {
        **payload,
        "params": {**payload["params"], "turnId": "turn-2", "command": "unsafe"},
    }
    current = changed_payload if change_during_read == "payload" else payload
    monkeypatch.setattr(
        desktop_bridge_module, "project_desktop_conversation",
        lambda _snapshot: SimpleNamespace(pending_requests=(
            DesktopPendingRequest(23, payload["method"], current),
        )),
    )
    project = tmp_path / "project"
    project.mkdir()
    api = _Api()
    service = DesktopBridgeService(
        api=api, state=state, uia=_Uia(), projects={"project": project},
        owner_user_id=99, owner_private_chat_id=99, bot_username="Nobusspacebot",
        ipc_factory=Client, clock=lambda: clock_value[0],
    )
    calls = []

    async def send_answer(*args):
        calls.append(args)

    monkeypatch.setattr(service, "_submit_interaction_answer", send_answer)
    await service._answer_interaction(
        _origin_message("разрешаю", user_id=99), interaction
    )
    assert calls == []
    assert any(
        word in api.messages[-1][1]
        for word in ("не отправлен", "остановлен", "истёк")
    )


@pytest.mark.asyncio
async def test_error_after_claim_stops_request_as_unknown_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state(tmp_path / "telegram-state.sqlite3")
    request = _request(state, ingress="sha256:" + "8" * 64)
    state.bind_desktop(
        request.request_id, thread_id="thread-1", turn_id="turn-1",
        client_message_id="client-1", status=BridgeRequestStatus.WAITING_OWNER,
    )
    payload = {
        "id": 23, "method": "item/commandExecution/requestApproval",
        "params": {"threadId": "thread-1", "turnId": "turn-1", "command": "safe"},
    }
    interaction = state.put_interaction(
        interaction_id="approval-post-claim-error", request_id=request.request_id,
        kind=InteractionKind.COMMAND_APPROVAL, desktop_request_id=23,
        desktop_turn_id="turn-1", target_user_id=99, generation=1,
        payload=payload, expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    monkeypatch.setattr(
        desktop_bridge_module, "project_desktop_conversation",
        lambda _snapshot: SimpleNamespace(
            pending_requests=(DesktopPendingRequest(23, payload["method"], payload),),
            cwd=str(tmp_path),
        ),
    )

    class Client:
        async def find_thread_owner(self, _thread_id):
            return object()

        async def load_complete_history_snapshot(self, _thread_id, *, owner):
            return object()

        async def close(self):
            pass

    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBridgeService(
        api=_Api(), state=state, uia=_Uia(),
        projects={"nobus-orchestrator-dev": project},
        owner_user_id=99, owner_private_chat_id=99, bot_username="Nobusspacebot",
        ipc_factory=Client,
    )

    async def failed_after_claim(*args, **kwargs):
        raise DesktopIpcError("desktop IPC owner rejected mutation")

    monkeypatch.setattr(service, "_submit_interaction_answer", failed_after_claim)
    await service._answer_interaction(_origin_message("разрешаю", user_id=99), interaction)
    assert state.read_request(request.request_id).status is BridgeRequestStatus.UNKNOWN_DISPATCH
    assert not state.claim_interaction_answer(interaction, responder_user_id=99)


def test_approval_reply_is_bound_to_owner_private_chat(tmp_path: Path) -> None:
    state = _state(tmp_path / "telegram-state.sqlite3")
    request = _request(state, ingress="sha256:" + "a" * 64)
    state.bind_desktop(
        request.request_id,
        thread_id="thread-owner-private",
        turn_id="turn-owner-private",
        client_message_id="client-owner-private",
        status=BridgeRequestStatus.WAITING_OWNER,
    )
    interaction = state.put_interaction(
        interaction_id="approval-owner-private",
        request_id=request.request_id,
        kind=InteractionKind.COMMAND_APPROVAL,
        desktop_request_id=23,
        desktop_turn_id="turn-owner-private",
        target_user_id=99,
        generation=1,
        payload={"params": {"command": "safe"}},
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    assert state.bind_interaction_message(
        interaction.interaction_id,
        telegram_chat_id=99,
        telegram_message_id=77,
    )

    assert state.pending_interaction_for_reply(
        chat_id=-1001,
        telegram_message_id=77,
    ) is None
    pending = state.pending_interaction_for_reply(
        chat_id=99,
        telegram_message_id=77,
    )
    assert pending is not None
    assert pending.target_user_id == 99
    assert pending.telegram_chat_id == 99


def test_expired_interaction_fails_closed_without_answering_desktop(tmp_path: Path) -> None:
    now = datetime(2026, 9, 22, 12, tzinfo=UTC)
    encode, decode = _codec()
    state = SQLiteDesktopBridgeState(
        tmp_path / "telegram-state.sqlite3",
        encode=encode,
        decode=decode,
        clock=lambda: now,
    )
    request = _request(state, ingress="sha256:" + "3" * 64)
    state.bind_desktop(
        request.request_id,
        thread_id="thread-1",
        turn_id="turn-1",
        client_message_id="client-1",
        status=BridgeRequestStatus.WAITING_OWNER,
    )
    interaction = state.put_interaction(
        interaction_id="approval-expiry",
        request_id=request.request_id,
        kind=InteractionKind.COMMAND_APPROVAL,
        desktop_request_id=22,
        desktop_turn_id="turn-1",
        target_user_id=41,
        generation=2,
        payload={"command": "safe"},
        expires_at=now + timedelta(seconds=1),
    )
    now += timedelta(seconds=2)
    expired = state.expire_interactions()
    assert [item.interaction_id for item in expired] == [interaction.interaction_id]
    assert state.read_request(request.request_id).status is BridgeRequestStatus.FAILED
    assert not state.resolve_interaction(interaction.interaction_id, responder_user_id=41)
    assert state.expire_interactions() == ()


def test_telegram_projection_is_lossless_for_unicode_and_code() -> None:
    text = ("Начало 🧪\n```python\nprint('тест')\n```\n| A | Б |\n" * 250) + "конец"
    parts = telegram_text_parts(text, max_bytes=512)
    assert len(parts) > 2
    assert all(len(part.encode("utf-8")) <= 512 for part in parts)
    assert "".join(parts) == text


def test_telegram_projection_removes_only_terminal_notifier_marker() -> None:
    text = "Полный ответ\n\n<!-- nobus-notify:complete|Служебное резюме -->"
    assert telegram_visible_final(text) == "Полный ответ\n"
    assert telegram_visible_final("Текст <!-- nobus-notify:complete|не в конце --> ещё") == (
        "Текст <!-- nobus-notify:complete|не в конце --> ещё"
    )


def test_multiple_final_blocks_strip_each_marker_without_progress() -> None:
    turn = DesktopTurnState(
        turn_id="turn-final",
        client_user_message_id="client-final",
        status="completed",
        user_text=("request",),
        agent_messages=(
            DesktopAgentMessage("progress", "internal progress", None),
            DesktopAgentMessage(
                "final-1",
                "Первый\n<!-- nobus-notify:complete|Первый -->",
                "final_answer",
            ),
            DesktopAgentMessage(
                "final-2",
                "Второй\n<!-- nobus-notify:complete|Второй -->",
                "final_answer",
            ),
        ),
        plan_items=(),
        text_outputs=(),
    )

    assert _desktop_final_text(turn) == "Первый\n\nВторой"


@pytest.mark.asyncio
async def test_delivery_formats_visible_final_as_telegram_html(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    state = _state(tmp_path / "telegram-state.sqlite3")
    request = _request(state, ingress="sha256:" + "b" * 64)
    request = state.bind_desktop(
        request.request_id, thread_id="thread-1", turn_id="turn-1",
        client_message_id="client-1", status=BridgeRequestStatus.EXECUTION_COMPLETED,
    )
    api = _Api()
    service = DesktopBridgeService(
        api=api, state=state, uia=_Uia(), projects={"project": project},
        owner_user_id=99, owner_private_chat_id=99, bot_username="Nobusspacebot",
    )
    turn = DesktopTurnState(
        turn_id="turn-1", client_user_message_id="client-1", status="completed",
        user_text=("request",),
        agent_messages=(DesktopAgentMessage("final-1", "**Готово** и `код`", "final_answer"),),
        plan_items=(), text_outputs=(),
    )
    await service._deliver(request, SimpleNamespace(cwd=str(project)), turn)
    assert state.read_request(request.request_id).status is BridgeRequestStatus.DELIVERED
    assert len(api.messages) == 1
    assert api.messages[0][2]["parse_mode"] == "HTML"
    assert "<b>Готово</b>" in api.messages[0][1]
    assert "<code>код</code>" in api.messages[0][1]


@pytest.mark.asyncio
async def test_partial_artifact_retry_keeps_original_slots_and_receipts(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    a, b = project / "a.txt", project / "b.txt"
    b.write_bytes(b"B")
    state = _state(tmp_path / "telegram-state.sqlite3")
    request = _request(state, ingress="sha256:" + "e" * 64)
    request = state.bind_desktop(
        request.request_id, thread_id="thread-1", turn_id="turn-1",
        client_message_id="client-1", status=BridgeRequestStatus.EXECUTION_COMPLETED,
    )
    class Delivery:
        def __init__(self):
            self.calls = []
        async def deliver(self, **kwargs):
            self.calls.append((kwargs["filename"], kwargs["operation_id"]))
            return SimpleNamespace(status="sent", message_id=100 + len(self.calls))
    delivery = Delivery()
    api = _Api()
    service = DesktopBridgeService(
        api=api, state=state, uia=_Uia(), projects={"project": project},
        owner_user_id=99, owner_private_chat_id=99, bot_username="Nobusspacebot",
        document_delivery=delivery,
    )
    final = f"[A]({a.as_posix()})\n[B]({b.as_posix()})"
    turn = DesktopTurnState(
        turn_id="turn-1", client_user_message_id="client-1", status="completed",
        user_text=("request",),
        agent_messages=(DesktopAgentMessage("final-1", final, "final_answer"),),
        plan_items=(), text_outputs=(),
    )
    await service._deliver(request, SimpleNamespace(cwd=str(project)), turn)
    assert state.read_request(request.request_id).status is BridgeRequestStatus.DELIVERY_PARTIAL
    a.write_bytes(b"A")
    await service._deliver(state.read_request(request.request_id), SimpleNamespace(cwd=str(project)), turn)
    assert state.read_request(request.request_id).status is BridgeRequestStatus.DELIVERED
    assert [name for name, _ in delivery.calls].count("a.txt") == 1
    assert [name for name, _ in delivery.calls].count("b.txt") == 1
    assert len(api.messages) == 1
    assert state.read_request(request.request_id).payload["_delivery_plan"]["snapshots"]
    assert _request(
        state, ingress="sha256:" + "e" * 64, request_id=request.request_id
    ).request_id == request.request_id


@pytest.mark.asyncio
async def test_changed_artifact_after_partial_delivery_stops_before_repeat(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    missing, stable = project / "missing.txt", project / "stable.txt"
    stable.write_bytes(b"old")
    state = _state(tmp_path / "telegram-state.sqlite3")
    request = _request(state, ingress="sha256:" + "f" * 64)
    request = state.bind_desktop(
        request.request_id, thread_id="thread-1", turn_id="turn-1",
        client_message_id="client-1", status=BridgeRequestStatus.EXECUTION_COMPLETED,
    )
    class Delivery:
        def __init__(self):
            self.calls = []
        async def deliver(self, **kwargs):
            self.calls.append(kwargs["filename"])
            return SimpleNamespace(status="sent", message_id=100 + len(self.calls))
    delivery = Delivery()
    service = DesktopBridgeService(
        api=_Api(), state=state, uia=_Uia(), projects={"project": project},
        owner_user_id=99, owner_private_chat_id=99, bot_username="Nobusspacebot",
        document_delivery=delivery,
    )
    final = f"[M]({missing.as_posix()})\n[S]({stable.as_posix()})"
    turn = DesktopTurnState(
        turn_id="turn-1", client_user_message_id="client-1", status="completed",
        user_text=("request",),
        agent_messages=(DesktopAgentMessage("final-1", final, "final_answer"),),
        plan_items=(), text_outputs=(),
    )
    await service._deliver(request, SimpleNamespace(cwd=str(project)), turn)
    assert state.read_request(request.request_id).status is BridgeRequestStatus.DELIVERY_PARTIAL
    stable.write_bytes(b"changed")
    missing.write_bytes(b"now")
    await service._deliver(state.read_request(request.request_id), SimpleNamespace(cwd=str(project)), turn)
    assert state.read_request(request.request_id).status is BridgeRequestStatus.DELIVERY_UNKNOWN
    assert delivery.calls.count("stable.txt") == 1
    assert "missing.txt" not in delivery.calls


def test_bridge_turn_contains_exact_durable_request_marker(tmp_path: Path) -> None:
    state = _state(tmp_path / "telegram-state.sqlite3")
    request = _request(state, ingress="sha256:" + "8" * 64)
    text = _bridge_turn_text(request)
    assert text.startswith(f"NOBUS-BRIDGE-REQUEST:{request.request_id}\n")
    assert "Не вызывай nobus-send-results" in text
    assert text.endswith("\nПроверь задачу")


def test_desktop_turn_preserves_plan_and_requires_owner_review() -> None:
    mode = {
        "mode": "plan",
        "settings": {
            "model": "gpt-test", "reasoning_effort": "high",
            "developer_instructions": "project rule",
        },
    }
    state = {
        "latestCollaborationMode": mode,
        "latestThreadSettings": {
            "collaborationMode": mode,
            "approvalPolicy": "on-request",
            "approvalsReviewer": "auto_review",
            "sandboxPolicy": {"type": "workspaceWrite"},
        },
    }
    assert _desktop_execution_settings(state) == {
        "approvalPolicy": "on-request",
        "approvalsReviewer": "user",
        "collaborationMode": mode,
    }
    state["latestCollaborationMode"] = {
        **mode, "settings": {**mode["settings"], "developer_instructions": None}
    }
    assert _desktop_execution_settings(state)["collaborationMode"] == mode
    state["latestThreadSettings"] = {
        **state["latestThreadSettings"], "collaborationMode": {**mode, "mode": "unknown"}
    }
    with pytest.raises(Exception, match="desktop-collaboration-mode-unsupported"):
        _desktop_execution_settings(state)
    state["latestThreadSettings"] = {
        **state["latestThreadSettings"],
        "collaborationMode": mode,
        "approvalsReviewer": "new-unknown-reviewer",
    }
    with pytest.raises(Exception, match="desktop-permission-settings-missing"):
        _desktop_execution_settings(state)


def test_artifact_snapshot_requires_explicit_regular_file_below_project(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    artifact = project / "result.txt"
    artifact.write_bytes("точные байты".encode())
    outside = tmp_path / "outside.txt"
    outside.write_text("no", encoding="utf-8")
    snapshots = snapshot_artifacts(
        f"Файл: {artifact}\nНе брать: {outside}", allowed_root=project
    )
    assert [(item.filename, item.content) for item in snapshots] == [
        ("result.txt", "точные байты".encode())
    ]


def test_artifact_snapshot_allows_unknown_extension_but_blocks_credentials(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    visual = project / "diagram.custom-binary"
    visual.write_bytes(b"\x00\x01visual-bytes")
    secret = project / ".env"
    secret.write_text("API_KEY=not-a-real-secret-value", encoding="utf-8")

    inspection = inspect_artifacts(
        f"{visual}\n{secret}",
        allowed_root=project,
    )

    assert [item.filename for item in inspection.snapshots] == [visual.name]
    assert [(item.filename, item.reason) for item in inspection.failures] == [
        (secret.name, "sensitive_file")
    ]


def test_markdown_forward_slash_artifact_and_explicit_extra_root(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    documents = tmp_path / "documents"
    documents.mkdir()
    artifact = documents / "report.txt"
    artifact.write_bytes(b"report bytes")
    link = f"[report]({artifact.as_posix()})"
    blocked = inspect_artifacts(link, allowed_root=project)
    assert not blocked.snapshots
    assert any(item.reason == "outside_allowed_roots" for item in blocked.failures)
    allowed = inspect_artifacts(
        link, allowed_root=project, additional_roots=(documents,)
    )
    assert [(item.filename, item.content) for item in allowed.snapshots] == [
        ("report.txt", b"report bytes")
    ]


def test_ui_bootstrap_lock_blocks_second_creator(tmp_path: Path) -> None:
    path = tmp_path / "desktop-bootstrap.lock"
    with _interprocess_bootstrap_lock(path):
        with pytest.raises(DesktopIpcUnavailableError, match="desktop-ui-bootstrap-(busy|lock-unavailable)"):
            with _interprocess_bootstrap_lock(path):
                pass


class _Api:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str, dict[str, object]]] = []

    async def send_message(self, *args, **kwargs):
        self.messages.append((args[0], args[1], dict(kwargs)))
        return len(self.messages)

    async def download_file(self, *args, **kwargs):
        return b"voice"

    async def send_document(self, *args, **kwargs):
        return 2


class _Uia:
    pass


@pytest.mark.asyncio
async def test_existing_desktop_draft_is_reported_without_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Client:
        async def start(self):
            pass

        async def close(self):
            pass

    project = tmp_path / "nobus-orchestrator-dev"
    project.mkdir()
    state = _state(tmp_path / "telegram-state.sqlite3")
    request = _request(state, ingress="sha256:" + "d" * 64)
    api = _Api()
    service = DesktopBridgeService(
        api=api, state=state, uia=_Uia(), projects={project.name: project},
        owner_user_id=99, owner_private_chat_id=99, bot_username="Nobusspacebot",
        ipc_factory=Client,
    )

    async def fail_before_send(*_args):
        raise DesktopUiAutomationError("desktop-uia-existing-draft")

    monkeypatch.setattr(service, "_create_desktop_task", fail_before_send)
    await service._run_request(request.request_id)

    assert state.read_request(request.request_id).status is BridgeRequestStatus.UNKNOWN_DISPATCH
    assert len(api.messages) == 1
    assert "несохранённый черновик" in api.messages[0][1]
    assert "повтор требует сверки" in api.messages[0][1]


class _Voice:
    def __init__(self, transcript: str) -> None:
        self._transcript = transcript

    async def preview_from_bytes(self, _audio: bytes):
        return SimpleNamespace(transcript=self._transcript)


def test_bridge_health_retains_completed_worker_failure(tmp_path: Path) -> None:
    project = tmp_path / "nobus-orchestrator-dev"
    project.mkdir()
    service = DesktopBridgeService(
        api=_Api(),
        state=_state(tmp_path / "telegram-state.sqlite3"),
        uia=_Uia(),  # type: ignore[arg-type]
        projects={project.name: project},
        owner_user_id=1,
        owner_private_chat_id=1,
        bot_username="Nobusspacebot",
    )
    service._worker_error = RuntimeError("unexpected worker failure")
    with pytest.raises(RuntimeError, match="desktop bridge worker stopped"):
        service.assert_healthy()


def test_project_name_with_spaces_and_task_link_are_parsed(tmp_path: Path) -> None:
    project = tmp_path / "Business Project"
    project.mkdir()
    service = DesktopBridgeService(
        api=_Api(), state=_state(tmp_path / "telegram-state.sqlite3"),
        uia=_Uia(), projects={"Business Project": project},
        owner_user_id=99, owner_private_chat_id=99, bot_username="Nobusspacebot",
    )
    parsed = service._parse_command(
        _message("/codex new Business Project\nСделай отчёт")
    )
    assert parsed is not None
    assert (parsed.operation, parsed.project_name, parsed.instruction) == (
        "create", "Business Project", "Сделай отчёт",
    )
    task_id = str(uuid4())
    link = service._parse_command(
        _message(f"/codex continue codex://threads/{task_id}\nПродолжи")
    )
    assert link is not None and link.thread_id == f"codex://threads/{task_id}"
    assert _parse_thread_ref(link.thread_id) == task_id
    assert _parse_thread_ref(task_id) == task_id


@pytest.mark.asyncio
async def test_natural_create_missing_project_waits_for_bound_author_choice(tmp_path: Path) -> None:
    project = tmp_path / "Business Project"
    project.mkdir()
    state = _state(tmp_path / "telegram-state.sqlite3")
    api = _Api()
    service = DesktopBridgeService(
        api=api, state=state, uia=_Uia(), projects={"Business Project": project},
        owner_user_id=99, owner_private_chat_id=99, bot_username="Nobusspacebot",
    )
    scheduled = []
    service._schedule = scheduled.append
    initial = _message("@Nobusspacebot создай задачу: составь план")
    assert await service.handle(initial, _envelope())
    assert scheduled == []
    assert "Business Project" in api.messages[0][1]
    pending = state.pending_interaction_for_reply(chat_id=-1001, telegram_message_id=1)
    assert pending is not None
    stranger = _origin_message("Business Project", user_id=55, reply=1).model_copy(update={"message_id": 13})
    await service.handle(stranger, _envelope().model_copy(update={"idempotency_key": "sha256:" + "c" * 64}))
    assert scheduled == []
    answer = _message("Business Project", reply=1).model_copy(update={"message_id": 14, "update_id": 3})
    await service.handle(answer, _envelope().model_copy(update={
        "idempotency_key": "sha256:" + "d" * 64, "external_message_id": "message:14",
    }))
    assert len(scheduled) == 1
    created = state.read_request(scheduled[0])
    assert created.project_name == "Business Project"
    assert created.payload["instruction"] == "составь план"
    assert state.read_request(pending.request_id).status is BridgeRequestStatus.CANCELLED


@pytest.mark.asyncio
async def test_natural_voice_create_requires_transcript_and_project_choice(tmp_path: Path) -> None:
    project = tmp_path / "Business Project"
    project.mkdir()
    state = _state(tmp_path / "telegram-state.sqlite3")
    api = _Api()
    service = DesktopBridgeService(
        api=api, state=state, uia=_Uia(), projects={"Business Project": project},
        owner_user_id=99, owner_private_chat_id=99, bot_username="Nobusspacebot",
        voice_service=_Voice("Создай задачу: составь план"),
    )
    scheduled = []
    service._schedule = scheduled.append
    assert await service.handle(_voice_message(), _envelope())
    voice = state.list_requests(statuses=frozenset({BridgeRequestStatus.NEEDS_VOICE_CONFIRMATION}))
    assert len(voice) == 1 and voice[0].operation == "create"
    assert voice[0].project_name is None and scheduled == []
    confirm = _message("да", reply=1).model_copy(update={"message_id": 14})
    await service.handle(confirm, _envelope())
    assert state.read_request(voice[0].request_id).status is BridgeRequestStatus.NEEDS_TARGET
    assert scheduled == []
    target_card_id = next(index for index, item in enumerate(api.messages, 1)
                          if "выберите существующий проект" in item[1])
    choose = _message("Business Project", reply=target_card_id).model_copy(
        update={"message_id": 15, "update_id": 4})
    await service.handle(choose, _envelope().model_copy(update={
        "idempotency_key": "sha256:" + "e" * 64, "external_message_id": "message:15",
    }))
    assert len(scheduled) == 1
    launched = state.read_request(scheduled[0])
    assert launched.project_name == "Business Project"
    assert launched.payload["instruction"] == "составь план"


def test_natural_create_with_exact_project_never_becomes_topic(tmp_path: Path) -> None:
    project = tmp_path / "Business Project"
    project.mkdir()
    service = DesktopBridgeService(
        api=_Api(), state=_state(tmp_path / "telegram-state.sqlite3"),
        uia=_Uia(), projects={"Business Project": project},
        owner_user_id=99, owner_private_chat_id=99, bot_username="Nobusspacebot",
    )
    parsed = service._parse_command(_message(
        "@Nobusspacebot создай задачу в проекте Business Project: составь план"
    ))
    assert (parsed.operation, parsed.project_name, parsed.instruction) == (
        "create", "Business Project", "составь план",
    )


def test_name_address_and_wrong_bot_command_are_not_ambient_commands(tmp_path: Path) -> None:
    project = tmp_path / "Business Project"
    project.mkdir()
    service = DesktopBridgeService(
        api=_Api(), state=_state(tmp_path / "telegram-state.sqlite3"),
        uia=_Uia(), projects={"Business Project": project},
        owner_user_id=99, owner_private_chat_id=99, bot_username="Nobusspacebot",
    )
    addressed = service._parse_command(_message(
        "Нобус, создай задачу в проекте Business Project: составь план"
    ))
    assert addressed is not None and addressed.operation == "create"
    assert service._parse_command(_message("/codex@OtherBot new Business Project\nТест")) is None
    assert service._parse_command(_message("@OtherBot создай задачу: тест")) is None
    assert service._parse_command(_message("Обычная заметка")) is None


def test_reply_to_bound_result_continues_without_command_prefix(tmp_path: Path) -> None:
    project = tmp_path / "Business Project"
    project.mkdir()
    state = _state(tmp_path / "telegram-state.sqlite3")
    previous = state.create_request(
        request_id=uuid4(), ingress_key="sha256:" + "f" * 64,
        tenant_id="owner", author_user_id=41,
        author_identity="telegram:member:41", chat_id=-1001, topic_id=7,
        source_message_id=12, operation="create", project_name="Business Project",
        payload={"instruction": "первое поручение"},
    )
    state.bind_desktop(previous.request_id, thread_id=str(uuid4()), turn_id="turn-1",
                       client_message_id="nobus:" + str(previous.request_id),
                       status=BridgeRequestStatus.DELIVERED)
    service = DesktopBridgeService(
        api=_Api(), state=state, uia=_Uia(), projects={"Business Project": project},
        owner_user_id=99, owner_private_chat_id=99, bot_username="Nobusspacebot",
    )
    parsed = service._parse_command(_message("Продолжи анализ", reply=12))
    assert parsed is not None and parsed.operation == "topic"
    assert parsed.instruction == "Продолжи анализ"


def test_only_registered_git_worktree_belongs_to_saved_desktop_project(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    def git(*args: str) -> None:
        subprocess.run(["git", *args], check=True, capture_output=True, text=True)
    git("-C", str(project), "init")
    git("-C", str(project), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "commit", "--allow-empty", "-m", "test")
    managed = tmp_path / "managed"
    git("-C", str(project), "worktree", "add", "--detach", str(managed))
    other = tmp_path / "other"
    other.mkdir()
    git("-C", str(other), "init")
    assert _desktop_cwd_belongs_to_project(str(project), project)
    assert _desktop_cwd_belongs_to_project(str(managed), project)
    assert not _desktop_cwd_belongs_to_project(str(other), project)
    assert not _desktop_cwd_belongs_to_project(str(managed / "subdir"), project)


def test_backup_rebind_migrates_exact_previous_bridge_schema_on_isolated_copy(tmp_path: Path) -> None:
    from scripts.run_telegram_backup_cycle import _migrate_exact_previous_desktop_schema

    runtime = tmp_path / "isolated-old-runtime"
    runtime.mkdir()
    database = runtime / "telegram-state.sqlite3"
    old_ddl = (Path(__file__).parent / "fixtures" /
               "desktop_bridge_requests_3ea2438.sql").read_text(encoding="utf-8")
    with sqlite3.connect(database) as connection:
        connection.executescript(old_ddl)
        before = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='desktop_bridge_requests'"
        ).fetchone()[0]
    from src.application.runtime_maintenance import _ddl_digest
    assert _ddl_digest(before) == (
        "c9b10b0ff3ed2e0474e68b6e951177e39f70e2e46c6281f913c4056b8bac4fe6"
    )
    assert _migrate_exact_previous_desktop_schema(runtime)
    with sqlite3.connect(database) as connection:
        columns = [row[1] for row in connection.execute(
            "PRAGMA table_info(desktop_bridge_requests)"
        )]
    assert "bootstrap_turn_id" in columns
    assert not _migrate_exact_previous_desktop_schema(runtime)


def test_migration_rejects_untrusted_table_identifier_before_sql_interpolation(tmp_path: Path) -> None:
    from scripts.migrate_telegram_runtime import _rows

    database = tmp_path / "identifier.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute('CREATE TABLE "bad-name" (value TEXT)')
        with pytest.raises(ValueError, match="invalid migration schema"):
            _rows(connection)


def test_reply_resolves_older_task_and_ambiguous_topic_stops(tmp_path: Path) -> None:
    state = _state(tmp_path / "telegram-state.sqlite3")
    first = _request(state, ingress="sha256:" + "1" * 64)
    state.bind_desktop(
        first.request_id, thread_id=str(uuid4()), turn_id="turn-1",
        client_message_id="client-1", status=BridgeRequestStatus.RUNNING,
    )
    second = state.create_request(
        request_id=uuid4(), ingress_key="sha256:" + "2" * 64,
        tenant_id="owner", author_user_id=41,
        author_identity="telegram:member:41", chat_id=-1001, topic_id=7,
        source_message_id=13, operation="create",
        project_name="nobus-orchestrator-dev", payload={"instruction": "second"},
    )
    state.bind_desktop(
        second.request_id, thread_id=str(uuid4()), turn_id="turn-2",
        client_message_id="client-2", status=BridgeRequestStatus.RUNNING,
    )
    project = tmp_path / "project"
    project.mkdir()
    service = DesktopBridgeService(
        api=_Api(), state=state, uia=_Uia(), projects={"project": project},
        owner_user_id=99, owner_private_chat_id=99, bot_username="Nobusspacebot",
    )
    assert state.topic_thread_count(chat_id=-1001, topic_id=7) == 2
    assert service._topic_predecessor(_message("/codex дальше")) is None
    assert service._topic_predecessor(
        _message("/codex дальше", reply=12)
    ).request_id == first.request_id
    assert service._topic_predecessor(
        _message("/codex дальше", reply=13)
    ).request_id == second.request_id


@pytest.mark.asyncio
async def test_redelivery_only_schedules_known_partial_in_same_topic(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    state = _state(tmp_path / "telegram-state.sqlite3")
    request = _request(state, ingress="sha256:" + "c" * 64)
    state.bind_desktop(
        request.request_id, thread_id=str(uuid4()), turn_id="turn-1",
        client_message_id=f"nobus:{request.request_id}",
        status=BridgeRequestStatus.DELIVERY_PARTIAL,
    )
    api = _Api()
    service = DesktopBridgeService(
        api=api, state=state, uia=_Uia(), projects={"project": project},
        owner_user_id=99, owner_private_chat_id=99, bot_username="Nobusspacebot",
    )
    scheduled = []
    service._schedule = scheduled.append
    await service._redeliver_known_partial(
        _origin_message("restore", user_id=41), str(request.request_id)
    )
    assert scheduled == [request.request_id]
    await service._redeliver_known_partial(
        _origin_message("restore", user_id=55), str(request.request_id)
    )
    assert scheduled == [request.request_id]
    state.transition(
        request.request_id,
        expected=frozenset({BridgeRequestStatus.DELIVERY_PARTIAL}),
        status=BridgeRequestStatus.DELIVERY_UNKNOWN,
    )
    await service._redeliver_known_partial(
        _origin_message("restore", user_id=41), str(request.request_id)
    )
    assert scheduled == [request.request_id]


def _message(text: str, *, reply: int | None = None) -> TextMessage:
    return TextMessage(
        update_id=1,
        tenant_id="owner",
        actor_identity="telegram:member:41",
        actor_role="member",
        auth_context_ref="sha256:" + "a" * 64,
        user_id=41,
        is_bot=False,
        is_forwarded=False,
        chat_id=-1001,
        message_thread_id=7,
        reply_to_message_id=reply,
        binding_purpose="business_notes",
        message_id=12,
        text=text,
    )


def _origin_message(
    text: str,
    *,
    reply: int | None = None,
    user_id: int = 41,
    chat_id: int = -1001,
    is_bot: bool = False,
    is_forwarded: bool = False,
) -> TextMessage:
    return _message(text, reply=reply).model_copy(
        update={
            "user_id": user_id,
            "chat_id": chat_id,
            "is_bot": is_bot,
            "is_forwarded": is_forwarded,
        }
    )


def _voice_message(*, reply: int | None = None) -> VoiceMessage:
    return VoiceMessage(
        update_id=2,
        tenant_id="owner",
        actor_identity="telegram:member:41",
        actor_role="member",
        auth_context_ref="sha256:" + "a" * 64,
        user_id=41,
        is_bot=False,
        is_forwarded=False,
        chat_id=-1001,
        message_thread_id=7,
        reply_to_message_id=reply,
        binding_purpose="business_notes",
        message_id=13,
        file_id="voice-file",
        duration=2,
        metadata=VoiceMetadata(
            file_unique_id="voice-unique",
            file_size=100,
            mime_type="audio/ogg",
        ),
    )


def _envelope() -> TrustedIngressEnvelope:
    return TrustedIngressEnvelope.model_construct(
        schema_version="1",
        ingress_id=uuid4(),
        tenant_id="owner",
        actor_identity="telegram:member:41",
        auth_context_ref="sha256:" + "a" * 64,
        source=IngressSource.TELEGRAM,
        kind=IngressKind.TEXT,
        external_message_id="message:12",
        idempotency_key="sha256:" + "b" * 64,
        content_ref="sha256:" + "c" * 64,
        received_at=datetime.now(UTC),
        envelope_revision="sha256:" + "d" * 64,
    )


@pytest.mark.asyncio
async def test_bridge_ignores_background_notes_and_accepts_explicit_create(
    tmp_path: Path,
) -> None:
    project = tmp_path / "nobus-orchestrator-dev"
    project.mkdir()
    state = _state(tmp_path / "telegram-state.sqlite3")
    service = DesktopBridgeService(
        api=_Api(), state=state, uia=_Uia(),  # type: ignore[arg-type]
        projects={project.name: project}, owner_user_id=1,
        owner_private_chat_id=1, bot_username="Nobusspacebot",
    )
    scheduled = []
    service._schedule = scheduled.append  # type: ignore[method-assign]
    assert not await service.handle(_message("Обычная заметка"), _envelope())
    assert not await service.handle(
        _message(
            "@Nobusspacebot #NOBUS-BIND-PARTICIPANT:exact-challenge-123"
        ),
        _envelope(),
    )
    assert await service.handle(
        _origin_message(
            "/codex new nobus-orchestrator-dev\nПересланная команда",
            is_forwarded=True,
        ),
        _envelope(),
    )
    assert "не создаёт задачу" in service._api.messages[-1][1]
    assert await service.handle(
        _message("/codex new nobus-orchestrator-dev\nПроверь контекст"), _envelope()
    )
    requests = state.list_requests(statuses=frozenset({BridgeRequestStatus.RECEIVED}))
    assert len(requests) == 1
    assert requests[0].payload["instruction"] == "Проверь контекст"
    assert scheduled == [requests[0].request_id]


@pytest.mark.asyncio
async def test_voice_can_create_desktop_task_after_author_preview(
    tmp_path: Path,
) -> None:
    project = tmp_path / "nobus-orchestrator-dev"
    project.mkdir()
    state = _state(tmp_path / "telegram-state.sqlite3")
    api = _Api()
    service = DesktopBridgeService(
        api=api,
        state=state,
        uia=_Uia(),  # type: ignore[arg-type]
        projects={project.name: project},
        owner_user_id=1,
        owner_private_chat_id=1,
        bot_username="Nobusspacebot",
        voice_service=_Voice(
            "новая nobus-orchestrator-dev Создай тестовый отчёт"
        ),
    )
    scheduled: list[object] = []
    service._schedule = scheduled.append  # type: ignore[method-assign]

    assert await service.handle(_voice_message(), _envelope())

    requests = state.list_requests(
        statuses=frozenset({BridgeRequestStatus.NEEDS_VOICE_CONFIRMATION})
    )
    assert len(requests) == 1
    assert requests[0].operation == "create"
    assert requests[0].project_name == project.name
    assert requests[0].payload["instruction"] == "Создай тестовый отчёт"
    assert scheduled == []
    assert "Распознано" in api.messages[-1][1]


@pytest.mark.asyncio
async def test_background_voice_without_desktop_command_is_not_consumed(
    tmp_path: Path,
) -> None:
    project = tmp_path / "nobus-orchestrator-dev"
    project.mkdir()
    api = _Api()
    service = DesktopBridgeService(
        api=api,
        state=_state(tmp_path / "telegram-state.sqlite3"),
        uia=_Uia(),  # type: ignore[arg-type]
        projects={project.name: project},
        owner_user_id=1,
        owner_private_chat_id=1,
        bot_username="Nobusspacebot",
        voice_service=_Voice("Обычная голосовая заметка"),
    )

    assert not await service.handle(_voice_message(), _envelope())
    assert api.messages == []


@pytest.mark.asyncio
async def test_bot_requests_are_bounded_without_blocking_human_participants(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 9, 22, 12, tzinfo=UTC)
    project = tmp_path / "nobus-orchestrator-dev"
    project.mkdir()
    encode, decode = _codec()
    state = SQLiteDesktopBridgeState(
        tmp_path / "telegram-state.sqlite3",
        encode=encode,
        decode=decode,
        clock=lambda: now,
    )
    api = _Api()
    service = DesktopBridgeService(
        api=api,
        state=state,
        uia=_Uia(),  # type: ignore[arg-type]
        projects={project.name: project},
        owner_user_id=1,
        owner_private_chat_id=1,
        bot_username="Nobusspacebot",
        clock=lambda: now,
    )
    scheduled: list[object] = []
    service._schedule = scheduled.append  # type: ignore[method-assign]
    for index in range(4):
        envelope = _envelope().model_copy(
            update={"idempotency_key": "sha256:" + str(index + 1) * 64}
        )
        message = _origin_message(
            f"/codex new nobus-orchestrator-dev\nЗадача {index}",
            is_bot=True,
        ).model_copy(update={"message_id": 100 + index, "update_id": 100 + index})
        assert await service.handle(message, envelope)
    limited = _origin_message(
        "/codex new nobus-orchestrator-dev\nЛишняя задача", is_bot=True
    ).model_copy(update={"message_id": 200, "update_id": 200})
    assert await service.handle(
        limited,
        _envelope().model_copy(update={"idempotency_key": "sha256:" + "9" * 64}),
    )
    human = _origin_message(
        "/codex new nobus-orchestrator-dev\nЧеловеческая задача",
        is_bot=False,
        user_id=42,
    ).model_copy(update={"message_id": 201, "update_id": 201})
    assert await service.handle(
        human,
        _envelope().model_copy(update={"idempotency_key": "sha256:" + "a" * 64}),
    )
    assert len(scheduled) == 5
    assert any("Лимит агента" in item[1] for item in api.messages)


@pytest.mark.asyncio
async def test_forwarded_owner_reply_cannot_answer_approval(tmp_path: Path) -> None:
    project = tmp_path / "nobus-orchestrator-dev"
    project.mkdir()
    api = _Api()
    state = _state(tmp_path / "telegram-state.sqlite3")
    request = _request(state, ingress="sha256:" + "4" * 64)
    state.bind_desktop(
        request.request_id,
        thread_id="thread-1",
        turn_id="turn-1",
        client_message_id="client-1",
        status=BridgeRequestStatus.WAITING_OWNER,
    )
    interaction = state.put_interaction(
        interaction_id="approval-forward",
        request_id=request.request_id,
        kind=InteractionKind.COMMAND_APPROVAL,
        desktop_request_id=23,
        desktop_turn_id="turn-1",
        target_user_id=41,
        generation=1,
        payload={"params": {"command": "safe"}},
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    state.bind_interaction_message(
        interaction.interaction_id,
        telegram_chat_id=-1001,
        telegram_message_id=77,
    )
    service = DesktopBridgeService(
        api=api,
        state=state,
        uia=_Uia(),  # type: ignore[arg-type]
        projects={project.name: project},
        owner_user_id=41,
        owner_private_chat_id=41,
        bot_username="Nobusspacebot",
    )
    assert await service.handle(
        _origin_message(
            "разрешаю",
            reply=77,
            chat_id=-1001,
            is_forwarded=True,
        ),
        _envelope(),
    )
    assert state.pending_interaction_for_reply(
        chat_id=-1001, telegram_message_id=77
    ) is not None
    assert "не подтверждает" in api.messages[-1][1]


@pytest.mark.asyncio
async def test_permission_worded_user_input_goes_to_owner_for_manual_review(
    tmp_path: Path,
) -> None:
    project = tmp_path / "nobus-orchestrator-dev"
    project.mkdir()
    api = _Api()
    state = _state(tmp_path / "telegram-state.sqlite3")
    request = _request(state, ingress="sha256:" + "f" * 64)
    request = state.bind_desktop(
        request.request_id, thread_id="thread-1", turn_id="turn-1",
        client_message_id="client-1", status=BridgeRequestStatus.RUNNING,
    )
    service = DesktopBridgeService(
        api=api, state=state, uia=_Uia(),
        projects={project.name: project}, owner_user_id=99,
        owner_private_chat_id=99, bot_username="Nobusspacebot",
    )
    turn = DesktopTurnState(
        turn_id="turn-1", client_user_message_id="client-1",
        status="inProgress", user_text=("test",), agent_messages=(),
        plan_items=(), text_outputs=(),
    )
    pending = [DesktopPendingRequest(
        request_id=3, method="item/tool/requestUserInput",
        payload={"params": {"questions": [{"id": "q", "question": "Разрешаете удалить файл?"}]}},
    )]
    await service._publish_interactions(request, turn, pending, 1)
    assert 'tg://user?id=99' in api.messages[0][1]
    assert 'tg://user?id=41' not in api.messages[0][1]
    assert state.read_request(request.request_id).status is BridgeRequestStatus.WAITING_OWNER
    assert state.pending_interaction_for_reply(
        chat_id=-1001, telegram_message_id=api.messages[-1][2]["reply_to_message_id"]
    ) is None


@pytest.mark.asyncio
async def test_mixed_question_and_approval_stay_in_source_topic_with_numeric_mentions(
    tmp_path: Path,
) -> None:
    project = tmp_path / "nobus-orchestrator-dev"
    project.mkdir()
    api = _Api()
    state = _state(tmp_path / "telegram-state.sqlite3")
    request = _request(state, ingress="sha256:" + "5" * 64)
    request = state.bind_desktop(
        request.request_id,
        thread_id="thread-1",
        turn_id="turn-1",
        client_message_id="client-1",
        status=BridgeRequestStatus.RUNNING,
    )
    service = DesktopBridgeService(
        api=api,
        state=state,
        uia=_Uia(),  # type: ignore[arg-type]
        projects={project.name: project},
        owner_user_id=99,
        owner_private_chat_id=99,
        bot_username="Nobusspacebot",
    )
    turn = DesktopTurnState(
        turn_id="turn-1",
        client_user_message_id="client-1",
        status="inProgress",
        user_text=("test",),
        agent_messages=(),
        plan_items=(),
        text_outputs=(),
    )
    await service._publish_interactions(
        request,
        turn,
        [
            DesktopPendingRequest(
                request_id=1,
                method="item/tool/requestUserInput",
                payload={"params": {"questions": [{"id": "q", "question": "Уточнить?"}]}},
            ),
            DesktopPendingRequest(
                request_id=2,
                method="item/commandExecution/requestApproval",
                payload={"params": {"command": "echo **literal**"}},
            ),
        ],
        1,
    )
    assert [item[0] for item in api.messages] == [-1001] * 4
    assert all(item[2]["message_thread_id"] == 7 for item in api.messages)
    assert api.messages[0][2]["reply_to_message_id"] == 12
    assert api.messages[2][2]["reply_to_message_id"] == 12
    assert 'tg://user?id=41' in api.messages[0][1]
    assert 'tg://user?id=99' in api.messages[2][1]
    assert api.messages[0][2]["parse_mode"] == "HTML"
    assert api.messages[2][2]["parse_mode"] == "HTML"
    assert api.messages[1][2].get("parse_mode") is None
    assert api.messages[3][2].get("parse_mode") is None
    assert "echo **literal**" in api.messages[3][1]
    assert state.read_request(request.request_id).status is BridgeRequestStatus.WAITING_OWNER


@pytest.mark.asyncio
async def test_lost_card_ack_does_not_resend_interaction(tmp_path: Path) -> None:
    class _LostAckApi(_Api):
        async def send_message(self, *args, **kwargs):
            receipt = await super().send_message(*args, **kwargs)
            if len(self.messages) == 1:
                raise RuntimeError("telegram-ack-lost")
            return receipt

    project = tmp_path / "project"
    project.mkdir()
    state = _state(tmp_path / "telegram-state.sqlite3")
    request = _request(state, ingress="sha256:" + "e" * 64)
    request = state.bind_desktop(
        request.request_id, thread_id="thread-1", turn_id="turn-1",
        client_message_id="client-1", status=BridgeRequestStatus.RUNNING,
    )
    api = _LostAckApi()
    service = DesktopBridgeService(
        api=api, state=state, uia=_Uia(), projects={"project": project},
        owner_user_id=99, owner_private_chat_id=99, bot_username="Nobusspacebot",
    )
    turn = DesktopTurnState(
        turn_id="turn-1", client_user_message_id="client-1",
        status="inProgress", user_text=("test",), agent_messages=(),
        plan_items=(), text_outputs=(),
    )
    pending = [DesktopPendingRequest(
        request_id=8, method="item/commandExecution/requestApproval",
        payload={"params": {"turnId": "turn-1", "command": "echo safe"}},
    )]
    await service._publish_interactions(request, turn, pending, 1)
    await service._publish_interactions(request, turn, pending, 1)
    assert len(api.messages) == 1
    assert state.read_request(request.request_id).status is BridgeRequestStatus.UNKNOWN_DISPATCH


def test_unconfirmed_interaction_card_survives_store_reopen(tmp_path: Path) -> None:
    path = tmp_path / "telegram-state.sqlite3"
    state = _state(path)
    request = _request(state, ingress="sha256:" + "0" * 64)
    interaction = state.put_interaction(
        interaction_id="card-crash", request_id=request.request_id,
        kind=InteractionKind.QUESTION, desktop_request_id=3,
        desktop_turn_id="turn-1", target_user_id=41, generation=1,
        payload={"params": {"questions": [{"id": "q", "question": "Уточнить?"}]}},
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    assert state.claim_interaction_delivery(interaction.interaction_id)
    reopened = _state(path).put_interaction(
        interaction_id="card-crash", request_id=request.request_id,
        kind=InteractionKind.QUESTION, desktop_request_id=3,
        desktop_turn_id="turn-1", target_user_id=41, generation=1,
        payload={"params": {"questions": [{"id": "q", "question": "Уточнить?"}]}},
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    assert reopened.status == "unknown"
    assert not _state(path).claim_interaction_delivery(interaction.interaction_id)


@pytest.mark.asyncio
async def test_manual_review_card_is_not_resent_each_monitor_cycle(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    state = _state(tmp_path / "telegram-state.sqlite3")
    request = _request(state, ingress="sha256:" + "d" * 64)
    request = state.bind_desktop(
        request.request_id, thread_id="thread-1", turn_id="turn-1",
        client_message_id="client-1", status=BridgeRequestStatus.RUNNING,
    )
    api = _Api()
    service = DesktopBridgeService(
        api=api, state=state, uia=_Uia(), projects={"project": project},
        owner_user_id=99, owner_private_chat_id=99, bot_username="Nobusspacebot",
    )
    turn = DesktopTurnState(
        turn_id="turn-1", client_user_message_id="client-1",
        status="inProgress", user_text=("test",), agent_messages=(),
        plan_items=(), text_outputs=(),
    )
    pending = [DesktopPendingRequest(
        request_id=9, method="unknown/request",
        payload={"id": 9, "method": "unknown/request", "params": {"turnId": "turn-1"}},
    )]
    await service._publish_interactions(request, turn, pending, 1)
    sent = len(api.messages)
    assert sent >= 2
    await service._publish_interactions(request, turn, pending, 1)
    assert len(api.messages) == sent
