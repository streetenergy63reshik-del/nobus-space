"""Offline protocol and recovery checks for the M2-DESKTOP IPC adapter."""

from __future__ import annotations

import asyncio
import json
import struct
from collections.abc import Callable
from typing import Any

import pytest

from src.integrations.codex_desktop_ipc import (
    CodexDesktopIpcClient,
    DesktopIpcCompatibilityError,
    DesktopIpcProtocolError,
    DesktopIpcUnavailableError,
    DesktopIpcUnknownOutcome,
    DesktopHistorySnapshot,
    DesktopIpcAck,
    OwnerBinding,
    RecoveryVerdict,
    classify_history_by_client_message_id,
    encode_frame,
    project_desktop_conversation,
    read_frame,
    reconcile_unknown_outcome,
)


def canonical_snapshot() -> DesktopHistorySnapshot:
    turn_key = "tail:0:local:turn-1"
    return DesktopHistorySnapshot(
        conversation_id="thread-history",
        owner_client_id="desktop-owner-1",
        revision=7,
        acknowledgement=DesktopIpcAck(
            method="thread-follower-load-complete-history",
            request_id="history-request-1",
            handled_by_client_id="desktop-owner-1",
            result={"revision": 7},
        ),
        conversation_state={
            "id": "thread-history",
            "title": "History smoke",
            "cwd": r"C:\project",
            "threadRuntimeStatus": {"type": "idle"},
            "requests": [
                {
                    "id": 18,
                    "method": "item/tool/requestUserInput",
                    "params": {"questions": [{"id": "choice"}]},
                }
            ],
            "turnHistory": {
                "kind": "canonical",
                "history": {
                    "generation": 0,
                    "isComplete": True,
                    "islands": [
                        {
                            "id": "tail:0",
                            "entries": [{"key": turn_key, "value": turn_key}],
                        }
                    ],
                    "entitiesByKey": {
                        turn_key: {
                            "turnId": "turn-1",
                            "status": "completed",
                            "params": {
                                "clientUserMessageId": "bridge-request-1"
                            },
                            "items": [
                                {
                                    "id": "user-1",
                                    "type": "userMessage",
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": "question",
                                            "text_elements": [],
                                        }
                                    ],
                                },
                                {
                                    "id": "agent-1",
                                    "type": "agentMessage",
                                    "phase": "final_answer",
                                    "text": "part one",
                                },
                                {
                                    "id": "agent-2",
                                    "type": "agentMessage",
                                    "phase": "final_answer",
                                    "text": "part two",
                                },
                                {
                                    "id": "plan-1",
                                    "type": "plan",
                                    "text": "plan output",
                                },
                            ],
                        }
                    },
                },
            },
        },
    )


def test_async_desktop_question_is_pending_until_exact_steering_reply() -> None:
    snapshot = canonical_snapshot()
    snapshot.conversation_state["requests"] = []
    entity = next(iter(snapshot.conversation_state["turnHistory"]["history"]["entitiesByKey"].values()))
    entity["status"] = "inProgress"
    entity["items"] = [
        entity["items"][0],
        {
            "id": "call-question-1",
            "type": "agentMessage",
            "phase": "final_answer",
            "delivery": "async",
            "text": "Какой цвет записать в отчёт?",
            "questions": [{
                "title": "Какой цвет записать в отчёт?",
                "options": [{"label": "синий"}, {"label": "зелёный"}],
            }],
        },
    ]
    pending = project_desktop_conversation(snapshot).pending_requests
    assert len(pending) == 1
    assert pending[0].method == "item/tool/requestUserInputAsync"
    assert pending[0].request_id == "call-question-1"
    question = pending[0].payload["params"]["questions"][0]
    assert question["id"] == '["request_user_input_async","call-question-1",0]'
    assert question["question"] == "Какой цвет записать в отчёт?"

    entity["items"].append({
        "id": "steer-1",
        "type": "steeringUserMessage",
        "input": [{
            "type": "text",
            "text": (
                '<send_user_message_question_reply>\n'
                '[{"questionItemId":"[\\"request_user_input_async\\",\\"call-question-1\\",0]",'
                '"question":"Какой цвет записать в отчёт?","answer":"синий"}]\n'
                '</send_user_message_question_reply>'
            ),
        }],
    })
    assert project_desktop_conversation(snapshot).pending_requests == ()


def decode_frame(frame: bytes) -> dict[str, Any]:
    size = struct.unpack("<I", frame[:4])[0]
    assert size == len(frame) - 4
    return json.loads(frame[4:].decode("utf-8"))


class FakeWriter:
    def __init__(
        self,
        reader: asyncio.StreamReader,
        route: Callable[["FakeWriter", dict[str, Any]], None],
    ) -> None:
        self.reader = reader
        self.route = route
        self.messages: list[dict[str, Any]] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        if self.closed:
            raise ConnectionError("closed")
        message = decode_frame(data)
        self.messages.append(message)
        self.route(self, message)

    async def drain(self) -> None:
        return None

    def send(self, message: dict[str, Any]) -> None:
        self.reader.feed_data(encode_frame(message))

    def disconnect(self) -> None:
        if not self.closed:
            self.closed = True
            self.reader.feed_eof()

    def close(self) -> None:
        self.disconnect()

    async def wait_closed(self) -> None:
        return None

    def is_closing(self) -> bool:
        return self.closed


class FakeConnector:
    def __init__(
        self, route: Callable[[FakeWriter, dict[str, Any]], None]
    ) -> None:
        self.route = route
        self.writers: list[FakeWriter] = []

    async def __call__(
        self, pipe_name: str, max_frame_bytes: int
    ) -> tuple[asyncio.StreamReader, FakeWriter]:
        assert pipe_name == r"\\.\pipe\codex-ipc"
        assert max_frame_bytes >= 1024
        reader = asyncio.StreamReader()
        writer = FakeWriter(reader, self.route)
        self.writers.append(writer)
        return reader, writer


def success(
    writer: FakeWriter,
    request: dict[str, Any],
    result: dict[str, Any],
    *,
    owner: str | None = None,
) -> None:
    response: dict[str, Any] = {
        "type": "response",
        "requestId": request["requestId"],
        "resultType": "success",
        "method": request["method"],
        "result": result,
    }
    if owner is not None:
        response["handledByClientId"] = owner
    writer.send(response)


def standard_route(
    writer: FakeWriter, message: dict[str, Any]
) -> None:
    method = message.get("method")
    if method == "initialize":
        success(writer, message, {"clientId": "nobus-client-1"})
    elif method == "thread-owner-discovery":
        success(
            writer,
            message,
            {"supportsUntrustedAppInput": True},
            owner="desktop-owner-1",
        )
    elif method == "thread-follower-load-complete-history":
        success(
            writer,
            message,
            {"result": {"thread": {"id": message["params"]["conversationId"]}}},
            owner="desktop-owner-1",
        )
    elif method == "thread-follower-start-turn":
        success(
            writer,
            message,
            {"result": {"turn": {"id": "turn-1", "status": "inProgress"}}},
            owner="desktop-owner-1",
        )
    else:
        raise AssertionError(f"unexpected method: {method}")


@pytest.mark.asyncio
async def test_close_is_bounded_when_pipe_never_confirms_close(monkeypatch: pytest.MonkeyPatch) -> None:
    connector = FakeConnector(standard_route)
    client = CodexDesktopIpcClient(
        connector=connector, connect_timeout_ms=30, reconnect_delays_ms=(),
    )
    await client.start()
    cancelled = False

    async def never_closed() -> None:
        nonlocal cancelled
        try:
            await asyncio.Event().wait()
        finally:
            cancelled = True

    monkeypatch.setattr(connector.writers[0], "wait_closed", never_closed)
    await asyncio.wait_for(client.close(), timeout=0.3)
    assert cancelled
    assert not client.connected


@pytest.mark.asyncio
async def test_frame_codec_is_little_endian_and_accepts_fragmented_reads() -> None:
    message = {"type": "response", "resultType": "success", "value": "Привет"}
    frame = encode_frame(message)
    assert struct.unpack("<I", frame[:4])[0] == len(frame) - 4

    reader = asyncio.StreamReader()
    task = asyncio.create_task(read_frame(reader))
    for byte in frame:
        reader.feed_data(bytes([byte]))
        await asyncio.sleep(0)
    assert await task == message


@pytest.mark.asyncio
async def test_frame_codec_rejects_zero_and_oversized_frames_before_body() -> None:
    zero = asyncio.StreamReader()
    zero.feed_data(struct.pack("<I", 0))
    with pytest.raises(DesktopIpcProtocolError, match="frame size"):
        await read_frame(zero, max_frame_bytes=1024)

    oversized = asyncio.StreamReader()
    oversized.feed_data(struct.pack("<I", 1025))
    with pytest.raises(DesktopIpcProtocolError, match="frame size"):
        await read_frame(oversized, max_frame_bytes=1024)


def test_canonical_history_projection_preserves_all_agent_messages() -> None:
    projection = project_desktop_conversation(canonical_snapshot())

    assert projection.conversation_id == "thread-history"
    assert projection.cwd == r"C:\project"
    turn = projection.turn_by_client_message_id("bridge-request-1")
    assert turn is not None
    assert turn.turn_id == "turn-1"
    assert turn.user_text == ("question",)
    assert [message.text for message in turn.agent_messages] == [
        "part one",
        "part two",
    ]
    assert [message.text for message in turn.plan_items] == ["plan output"]
    assert [message.text for message in turn.complete_text_output] == [
        "part one",
        "part two",
        "plan output",
    ]
    assert projection.pending_requests[0].request_id == 18
    assert (
        projection.pending_requests[0].method
        == "item/tool/requestUserInput"
    )


def test_canonical_history_projection_rejects_unordered_entity() -> None:
    snapshot = canonical_snapshot()
    snapshot.conversation_state["turnHistory"]["history"]["entitiesByKey"][
        "tail:0:local:orphan"
    ] = {
        "turnId": "orphan",
        "status": "completed",
        "params": {"clientUserMessageId": "orphan-message"},
        "items": [],
    }

    with pytest.raises(DesktopIpcProtocolError, match="unordered"):
        project_desktop_conversation(snapshot)


@pytest.mark.asyncio
async def test_start_turn_routes_to_discovered_desktop_owner() -> None:
    connector = FakeConnector(standard_route)
    client = CodexDesktopIpcClient(
        connector=connector,
        connect_timeout_ms=100,
        request_timeout_ms=100,
        owner_discovery_timeout_ms=100,
        reconnect_delays_ms=(),
    )
    try:
        receipt = await client.start_turn(
            "thread-1",
            input_items=[{"type": "text", "text": "test", "text_elements": []}],
            client_user_message_id="bridge-request-1",
        )
        assert receipt.turn_id == "turn-1"
        assert receipt.owner_client_id == "desktop-owner-1"
        assert receipt.client_user_message_id == "bridge-request-1"

        methods = [message["method"] for message in connector.writers[0].messages]
        assert methods == [
            "initialize",
            "thread-owner-discovery",
            "thread-follower-start-turn",
        ]
        start = connector.writers[0].messages[-1]
        assert start["version"] == 2
        assert start["targetClientId"] == "desktop-owner-1"
        assert start["params"] == {
            "conversationId": "thread-1",
            "turnStart": {
                "request": {
                    "input": [
                        {"type": "text", "text": "test", "text_elements": []}
                    ],
                    "threadId": "thread-1",
                    "clientUserMessageId": "bridge-request-1",
                },
                "context": {"attachments": [], "commentAttachments": []},
            },
        }
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_steer_turn_uses_exact_owner_and_version_one() -> None:
    def route(writer: FakeWriter, message: dict[str, Any]) -> None:
        if message.get("method") == "thread-follower-steer-turn":
            success(writer, message, {"result": {}}, owner="desktop-owner-1")
            return
        standard_route(writer, message)

    connector = FakeConnector(route)
    client = CodexDesktopIpcClient(
        connector=connector,
        connect_timeout_ms=100,
        request_timeout_ms=100,
        owner_discovery_timeout_ms=100,
        reconnect_delays_ms=(),
    )
    try:
        owner = await client.find_thread_owner("thread-1")
        await client.steer_turn(
            "thread-1",
            owner=owner,
            input_items=[{"type": "text", "text": "safe answer", "text_elements": []}],
            client_user_message_id="nobus:question:1",
            restore_message={"id": "nobus:question:1", "cwd": "C:\\project", "context": {"prompt": "safe answer"}},
        )
        message = connector.writers[0].messages[-1]
        assert message["method"] == "thread-follower-steer-turn"
        assert message["version"] == 1
        assert message["targetClientId"] == "desktop-owner-1"
        assert message["params"] == {
            "conversationId": "thread-1",
            "input": [{"type": "text", "text": "safe answer", "text_elements": []}],
            "clientUserMessageId": "nobus:question:1",
            "restoreMessage": {"id": "nobus:question:1", "cwd": "C:\\project", "context": {"prompt": "safe answer"}},
            "attachments": [],
        }
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_complete_history_registers_follower_and_waits_for_snapshot() -> None:
    def route(writer: FakeWriter, message: dict[str, Any]) -> None:
        if message["type"] == "broadcast":
            assert message["method"] == "thread-stream-following-changed"
            assert message["version"] == 1
            assert message["targetClientIds"] == ["desktop-owner-1"]
            assert message["params"] == {
                "conversationId": "thread-history",
                "hostId": "local",
                "following": True,
            }
            return
        if message["method"] == "thread-follower-load-complete-history":
            writer.send(
                {
                    "type": "broadcast",
                    "method": "unrelated-desktop-broadcast",
                    "version": 99,
                    "sourceClientId": "desktop-owner-1",
                    "params": {},
                }
            )
            writer.send(
                {
                    "type": "broadcast",
                    "method": "thread-stream-state-changed",
                    "version": 11,
                    "sourceClientId": "desktop-owner-1",
                    "params": {
                        "conversationId": "thread-history",
                        "hostId": "local",
                        "change": {
                            "type": "snapshot",
                            "revision": 7,
                            "conversationState": {
                                "title": "History smoke",
                                "turns": [{"turnId": "turn-1"}],
                            },
                        },
                    },
                }
            )
            success(
                writer,
                message,
                {"revision": 7},
                owner="desktop-owner-1",
            )
            return
        standard_route(writer, message)

    connector = FakeConnector(route)
    client = CodexDesktopIpcClient(
        connector=connector,
        connect_timeout_ms=100,
        request_timeout_ms=100,
        owner_discovery_timeout_ms=100,
        reconnect_delays_ms=(),
    )
    try:
        snapshot = await client.load_complete_history_snapshot(
            "thread-history", timeout_ms=100
        )
        assert snapshot.revision == 7
        assert snapshot.owner_client_id == "desktop-owner-1"
        assert snapshot.conversation_state["title"] == "History smoke"
        assert [
            message["type"] for message in connector.writers[0].messages
        ] == ["request", "request", "broadcast", "request"]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_lost_start_ack_is_unknown_and_never_retried_blindly() -> None:
    def route(writer: FakeWriter, message: dict[str, Any]) -> None:
        if message["method"] == "thread-follower-start-turn":
            return
        standard_route(writer, message)

    connector = FakeConnector(route)
    client = CodexDesktopIpcClient(
        connector=connector,
        connect_timeout_ms=100,
        request_timeout_ms=20,
        owner_discovery_timeout_ms=100,
        reconnect_delays_ms=(),
    )
    try:
        with pytest.raises(DesktopIpcUnknownOutcome) as captured:
            await client.start_turn(
                "thread-unknown",
                input_items=[
                    {"type": "text", "text": "only once", "text_elements": []}
                ],
                client_user_message_id="bridge-request-unknown",
            )
        unknown = captured.value
        assert unknown.method == "thread-follower-start-turn"
        assert unknown.reason == "ack-timeout"
        assert sum(
            message.get("method") == "thread-follower-start-turn"
            for writer in connector.writers
            for message in writer.messages
        ) == 1

        reads = 0

        async def readback() -> dict[str, Any]:
            nonlocal reads
            reads += 1
            return {
                "turns": [
                    {
                        "turnId": "turn-confirmed",
                        "items": [
                            {"clientUserMessageId": "bridge-request-unknown"}
                        ],
                    }
                ]
            }

        result = await reconcile_unknown_outcome(
            unknown,
            readback=readback,
            classify=lambda history, failure: (
                classify_history_by_client_message_id(
                    history,
                    failure,
                    client_user_message_id="bridge-request-unknown",
                )
            ),
        )
        assert reads == 1
        assert result.verdict is RecoveryVerdict.CONFIRMED
        assert result.observed_reference == "turn-confirmed"
        assert sum(
            message.get("method") == "thread-follower-start-turn"
            for writer in connector.writers
            for message in writer.messages
        ) == 1
    finally:
        await client.close()


def test_missing_history_correlation_is_not_treated_as_proof_of_absence() -> None:
    unknown = DesktopIpcUnknownOutcome(
        method="thread-follower-start-turn",
        request_id="request-1",
        request_digest="sha256:" + "a" * 64,
        reason="ack-timeout",
    )
    verdict, reference = classify_history_by_client_message_id(
        {"turns": [{"turnId": "different-turn"}]},
        unknown,
        client_user_message_id="bridge-request-missing",
    )
    assert verdict is RecoveryVerdict.UNKNOWN
    assert reference is None


@pytest.mark.asyncio
async def test_version_mismatch_fails_closed_without_fallback() -> None:
    def route(writer: FakeWriter, message: dict[str, Any]) -> None:
        if message["method"] != "thread-follower-start-turn":
            standard_route(writer, message)
            return
        writer.send(
            {
                "type": "response",
                "requestId": message["requestId"],
                "resultType": "error",
                "error": "request-version-mismatch",
            }
        )

    connector = FakeConnector(route)
    client = CodexDesktopIpcClient(
        connector=connector,
        connect_timeout_ms=100,
        request_timeout_ms=100,
        owner_discovery_timeout_ms=100,
        reconnect_delays_ms=(),
    )
    try:
        with pytest.raises(DesktopIpcCompatibilityError):
            await client.start_turn(
                "thread-version",
                input_items=[
                    {"type": "text", "text": "no fallback", "text_elements": []}
                ],
                client_user_message_id="bridge-request-version",
            )
        assert len(connector.writers) == 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_missing_owner_never_switches_to_another_executor() -> None:
    def route(writer: FakeWriter, message: dict[str, Any]) -> None:
        if message["method"] == "initialize":
            success(writer, message, {"clientId": "nobus-client-1"})
            return
        assert message["method"] == "thread-owner-discovery"
        writer.send(
            {
                "type": "response",
                "requestId": message["requestId"],
                "resultType": "error",
                "error": "no-client-found: owner is not active",
            }
        )

    connector = FakeConnector(route)
    client = CodexDesktopIpcClient(
        connector=connector,
        connect_timeout_ms=100,
        request_timeout_ms=100,
        owner_discovery_timeout_ms=100,
        reconnect_delays_ms=(),
    )
    try:
        with pytest.raises(DesktopIpcUnavailableError) as captured:
            await client.start_turn(
                "thread-without-owner",
                input_items=[
                    {"type": "text", "text": "must wait", "text_elements": []}
                ],
                client_user_message_id="bridge-request-wait",
            )
        assert captured.value.reason == "no-client-found"
        assert all(
            message["method"]
            in {"initialize", "thread-owner-discovery"}
            for writer in connector.writers
            for message in writer.messages
        )
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_question_and_approval_responses_are_owner_targeted() -> None:
    received: list[dict[str, Any]] = []

    def route(writer: FakeWriter, message: dict[str, Any]) -> None:
        if message["method"] == "initialize":
            success(writer, message, {"clientId": "nobus-client-1"})
            return
        received.append(message)
        success(writer, message, {"ok": True}, owner="desktop-owner-1")

    connector = FakeConnector(route)
    client = CodexDesktopIpcClient(
        connector=connector,
        connect_timeout_ms=100,
        request_timeout_ms=100,
        owner_discovery_timeout_ms=100,
        reconnect_delays_ms=(),
    )
    try:
        # Supply an explicit binding as the application must verify Telegram
        # authority before invoking an approval method.
        owner = OwnerBinding(
            conversation_id="thread-approval",
            owner_client_id="desktop-owner-1",
            supports_untrusted_app_input=True,
        )
        await client.submit_user_input(
            "thread-approval",
            18,
            {"answers": {"choice": {"answers": ["yes"]}}},
            owner=owner,
        )
        await client.answer_command_approval(
            "thread-approval",
            "approval-1",
            "decline",
            owner=owner,
        )
        assert [message["version"] for message in received] == [1, 1]
        assert [message["targetClientId"] for message in received] == [
            "desktop-owner-1",
            "desktop-owner-1",
        ]
        assert received[0]["params"] == {
            "conversationId": "thread-approval",
            "requestId": 18,
            "response": {"answers": {"choice": {"answers": ["yes"]}}},
        }
        assert received[1]["params"] == {
            "conversationId": "thread-approval",
            "requestId": "approval-1",
            "decision": "decline",
        }
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_safe_history_read_reconnects_but_mutation_is_not_replayed() -> None:
    connector = FakeConnector(standard_route)
    client = CodexDesktopIpcClient(
        connector=connector,
        connect_timeout_ms=100,
        request_timeout_ms=100,
        owner_discovery_timeout_ms=100,
        reconnect_delays_ms=(),
    )
    try:
        owner = await client.find_thread_owner("thread-reconnect")
        assert len(connector.writers) == 1
        connector.writers[0].disconnect()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        history = await client.load_complete_history(
            "thread-reconnect", owner=owner
        )
        assert history.result["result"]["thread"]["id"] == "thread-reconnect"
        assert len(connector.writers) == 2
        assert [message["method"] for message in connector.writers[1].messages] == [
            "initialize",
            "thread-follower-load-complete-history",
        ]
    finally:
        await client.close()
