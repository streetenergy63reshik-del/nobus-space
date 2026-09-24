"""Version-bound client for the private IPC router of a running Codex Desktop.

This adapter deliberately does not start a second Codex runtime and never falls
back to CLI/App Server execution.  The wire profile is pinned to the Desktop
build observed for M2-DESKTOP; incompatible responses fail closed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import struct
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Protocol, TypeAlias, cast
from uuid import uuid4


DESKTOP_PIPE_NAME = r"\\.\pipe\codex-ipc"
INITIAL_CLIENT_ID = "initializing-client"
PROTOCOL_PROFILE = "codex-desktop-26.917.9434.0"
HARD_MAX_FRAME_BYTES = 256 * 1024 * 1024
DEFAULT_MAX_FRAME_BYTES = 16 * 1024 * 1024
DEFAULT_CONNECT_TIMEOUT_MS = 1_500
DEFAULT_REQUEST_TIMEOUT_MS = 20_000
DEFAULT_OWNER_DISCOVERY_TIMEOUT_MS = 5_000
DEFAULT_HISTORY_TIMEOUT_MS = 305_000

METHOD_VERSIONS: Mapping[str, int] = MappingProxyType(
    {
        "initialize": 0,
        "thread-owner-discovery": 1,
        "thread-follower-start-turn": 2,
        "thread-follower-load-complete-history": 1,
        "thread-follower-steer-turn": 1,
        "thread-follower-interrupt-turn": 4,
        "thread-follower-update-thread-settings": 2,
        "thread-follower-command-approval-decision": 1,
        "thread-follower-file-approval-decision": 1,
        "thread-follower-permissions-request-approval-response": 1,
        "thread-follower-submit-user-input": 1,
        "thread-follower-submit-mcp-server-elicitation-response": 1,
    }
)

BROADCAST_VERSIONS: Mapping[str, int] = MappingProxyType(
    {
        "thread-stream-state-changed": 11,
        "thread-stream-following-changed": 1,
        "thread-stream-following-status-requested": 1,
    }
)

JsonObject: TypeAlias = dict[str, Any]
RequestId: TypeAlias = str | int


class DesktopIpcError(RuntimeError):
    """Base class for failures at the Desktop IPC boundary."""


class DesktopIpcUnavailableError(DesktopIpcError):
    """The running Desktop or the required owner is unavailable."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class DesktopIpcProtocolError(DesktopIpcError):
    """A frame or envelope does not satisfy the observed contract."""


class DesktopIpcCompatibilityError(DesktopIpcError):
    """The installed Desktop no longer matches the pinned private protocol."""

    def __init__(self, method: str, reason: str) -> None:
        super().__init__(f"desktop IPC compatibility failure for {method}: {reason}")
        self.method = method
        self.reason = reason


class DesktopIpcRequestError(DesktopIpcError):
    """Desktop returned a definite error response for one request."""

    def __init__(self, method: str, reason: str) -> None:
        super().__init__(f"desktop IPC request failed for {method}: {reason}")
        self.method = method
        self.reason = reason


class DesktopIpcTimeoutError(DesktopIpcError):
    """A read-only request timed out and may be repeated safely."""

    def __init__(self, method: str) -> None:
        super().__init__(f"desktop IPC request timed out: {method}")
        self.method = method


class DesktopIpcUnknownOutcome(DesktopIpcError):
    """A mutation was dispatched but its acknowledgement was not observed."""

    def __init__(
        self,
        *,
        method: str,
        request_id: str,
        request_digest: str,
        reason: str,
    ) -> None:
        super().__init__(
            f"desktop IPC mutation outcome is unknown for {method}; readback required"
        )
        self.method = method
        self.request_id = request_id
        self.request_digest = request_digest
        self.reason = reason


class RecoveryVerdict(str, Enum):
    CONFIRMED = "confirmed"
    ABSENT = "absent"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    verdict: RecoveryVerdict
    readback_digest: str
    observed_reference: str | None = None


@dataclass(frozen=True, slots=True)
class OwnerBinding:
    conversation_id: str
    owner_client_id: str
    supports_untrusted_app_input: bool | None


@dataclass(frozen=True, slots=True)
class DesktopIpcAck:
    method: str
    request_id: str
    handled_by_client_id: str | None
    result: JsonObject


@dataclass(frozen=True, slots=True)
class StartTurnReceipt:
    request_id: str
    request_digest: str
    client_user_message_id: str
    owner_client_id: str
    turn_id: str
    status: str | None


@dataclass(frozen=True, slots=True)
class DesktopIpcEvent:
    method: str
    version: int
    source_client_id: str | None
    params: JsonObject


@dataclass(frozen=True, slots=True)
class DesktopHistorySnapshot:
    conversation_id: str
    owner_client_id: str
    revision: int
    conversation_state: JsonObject
    acknowledgement: DesktopIpcAck


@dataclass(frozen=True, slots=True)
class DesktopAgentMessage:
    item_id: str
    text: str
    phase: str | None
    delivery: str | None = None
    questions: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class DesktopTurnState:
    turn_id: str
    client_user_message_id: str
    status: str
    user_text: tuple[str, ...]
    agent_messages: tuple[DesktopAgentMessage, ...]
    plan_items: tuple[DesktopAgentMessage, ...]
    text_outputs: tuple[DesktopAgentMessage, ...]

    @property
    def complete_text_output(self) -> tuple[DesktopAgentMessage, ...]:
        return self.text_outputs


@dataclass(frozen=True, slots=True)
class DesktopPendingRequest:
    request_id: RequestId
    method: str
    payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class DesktopConversationProjection:
    conversation_id: str
    title: str
    cwd: str
    runtime_status: str
    turns: tuple[DesktopTurnState, ...]
    pending_requests: tuple[DesktopPendingRequest, ...]

    def turn_by_client_message_id(
        self, client_user_message_id: str
    ) -> DesktopTurnState | None:
        matches = [
            turn
            for turn in self.turns
            if turn.client_user_message_id == client_user_message_id
        ]
        if len(matches) > 1:
            raise DesktopIpcProtocolError(
                "desktop IPC client message correlation is ambiguous"
            )
        return matches[0] if matches else None


class IpcReader(Protocol):
    async def readexactly(self, count: int) -> bytes: ...


class IpcWriter(Protocol):
    def write(self, data: bytes) -> None: ...

    async def drain(self) -> None: ...

    def close(self) -> None: ...

    async def wait_closed(self) -> None: ...

    def is_closing(self) -> bool: ...


PipeConnector: TypeAlias = Callable[
    [str, int], Awaitable[tuple[IpcReader, IpcWriter]]
]
Readback: TypeAlias = Callable[[], Awaitable[Mapping[str, Any]]]
RecoveryClassifier: TypeAlias = Callable[
    [Mapping[str, Any], DesktopIpcUnknownOutcome],
    tuple[RecoveryVerdict, str | None],
]


@dataclass(slots=True)
class _PendingRequest:
    method: str
    request_id: str
    request_digest: str
    mutating: bool
    future: asyncio.Future[JsonObject]


def encode_frame(
    message: Mapping[str, Any], *, max_frame_bytes: int = DEFAULT_MAX_FRAME_BYTES
) -> bytes:
    """Encode one bounded little-endian length-prefixed JSON object."""
    _validate_frame_limit(max_frame_bytes)
    try:
        payload = json.dumps(
            dict(message),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DesktopIpcProtocolError("desktop IPC message is not JSON-safe") from exc
    if not payload or len(payload) > max_frame_bytes:
        raise DesktopIpcProtocolError("desktop IPC frame size is invalid")
    return struct.pack("<I", len(payload)) + payload


async def read_frame(
    reader: IpcReader, *, max_frame_bytes: int = DEFAULT_MAX_FRAME_BYTES
) -> JsonObject:
    """Read and validate one complete Desktop IPC frame."""
    _validate_frame_limit(max_frame_bytes)
    try:
        header = await reader.readexactly(4)
        frame_bytes = struct.unpack("<I", header)[0]
        if frame_bytes == 0 or frame_bytes > max_frame_bytes:
            raise DesktopIpcProtocolError("desktop IPC frame size is invalid")
        payload = await reader.readexactly(frame_bytes)
        message = json.loads(payload.decode("utf-8"))
    except DesktopIpcProtocolError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, struct.error) as exc:
        raise DesktopIpcProtocolError("desktop IPC frame is malformed") from exc
    if not isinstance(message, dict) or not isinstance(message.get("type"), str):
        raise DesktopIpcProtocolError("desktop IPC envelope is invalid")
    return cast(JsonObject, message)


class CodexDesktopIpcClient:
    """Async owner-follower client with fail-closed mutation recovery."""

    def __init__(
        self,
        *,
        connector: PipeConnector | None = None,
        client_type: str = "nobus-space-m2-desktop",
        max_frame_bytes: int = DEFAULT_MAX_FRAME_BYTES,
        connect_timeout_ms: int = DEFAULT_CONNECT_TIMEOUT_MS,
        request_timeout_ms: int = DEFAULT_REQUEST_TIMEOUT_MS,
        owner_discovery_timeout_ms: int = DEFAULT_OWNER_DISCOVERY_TIMEOUT_MS,
        reconnect_delays_ms: tuple[int, ...] = (250, 500, 1_000, 2_000, 4_000),
    ) -> None:
        _validate_frame_limit(max_frame_bytes)
        self._client_type = _bounded_text(client_type, "client type")
        self._connector = connector or _open_windows_named_pipe
        self._max_frame_bytes = max_frame_bytes
        self._connect_timeout_ms = _positive_timeout(
            connect_timeout_ms, "connect timeout"
        )
        self._request_timeout_ms = _positive_timeout(
            request_timeout_ms, "request timeout"
        )
        self._owner_discovery_timeout_ms = _positive_timeout(
            owner_discovery_timeout_ms, "owner discovery timeout"
        )
        self._reconnect_delays_ms = _validate_reconnect_delays(
            reconnect_delays_ms
        )
        self._reader: IpcReader | None = None
        self._writer: IpcWriter | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._client_id = INITIAL_CLIENT_ID
        self._generation = 0
        self._pending: dict[str, _PendingRequest] = {}
        self._events: asyncio.Queue[DesktopIpcEvent | DesktopIpcError] = (
            asyncio.Queue(maxsize=256)
        )
        self._connection_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._closed = False

    @property
    def connected(self) -> bool:
        return (
            not self._closed
            and self._writer is not None
            and not self._writer.is_closing()
            and self._reader_task is not None
            and not self._reader_task.done()
            and self._client_id != INITIAL_CLIENT_ID
        )

    @property
    def generation(self) -> int:
        return self._generation

    async def start(self) -> None:
        """Connect and initialize, retrying only the connection handshake."""
        if self._closed:
            raise DesktopIpcUnavailableError("client-closed")
        if self.connected:
            return
        attempts = (0, *self._reconnect_delays_ms)
        last_error: DesktopIpcError | None = None
        for delay_ms in attempts:
            if delay_ms:
                await asyncio.sleep(delay_ms / 1_000)
            try:
                await self._connect_once()
                return
            except DesktopIpcCompatibilityError:
                raise
            except DesktopIpcError as exc:
                last_error = exc
        raise last_error or DesktopIpcUnavailableError("connect-failed")

    async def close(self) -> None:
        self._closed = True
        await self._drop_connection(
            DesktopIpcUnavailableError("client-closed"),
            cancel_reader=True,
        )

    async def find_thread_owner(
        self,
        conversation_id: str,
        *,
        host_id: str = "local",
    ) -> OwnerBinding:
        conversation_id = _bounded_text(conversation_id, "conversation id")
        envelope = await self._request_read(
            "thread-owner-discovery",
            {
                "hostId": _bounded_text(host_id, "host id"),
                "conversationId": conversation_id,
            },
            timeout_ms=self._owner_discovery_timeout_ms,
            retries=1,
            return_envelope=True,
        )
        owner_client_id = _optional_text(envelope.get("handledByClientId"))
        if owner_client_id is None:
            raise DesktopIpcUnavailableError("no-client-found")
        result = _json_object(envelope.get("result"), "owner discovery result")
        supports = result.get("supportsUntrustedAppInput")
        return OwnerBinding(
            conversation_id=conversation_id,
            owner_client_id=owner_client_id,
            supports_untrusted_app_input=(
                supports if isinstance(supports, bool) else None
            ),
        )

    async def load_complete_history(
        self,
        conversation_id: str,
        *,
        owner: OwnerBinding | None = None,
    ) -> DesktopIpcAck:
        conversation_id = _bounded_text(conversation_id, "conversation id")
        binding = await self._owner_for(conversation_id, owner)
        envelope = await self._request_read(
            "thread-follower-load-complete-history",
            {"conversationId": conversation_id},
            timeout_ms=DEFAULT_HISTORY_TIMEOUT_MS,
            retries=1,
            target_client_id=binding.owner_client_id,
            return_envelope=True,
        )
        return _ack_from_envelope(
            "thread-follower-load-complete-history", envelope
        )

    async def set_thread_following(
        self,
        conversation_id: str,
        following: bool,
        *,
        owner: OwnerBinding,
        host_id: str = "local",
    ) -> None:
        """Register or remove this client as a stream follower for one owner."""
        conversation_id = _bounded_text(conversation_id, "conversation id")
        if owner.conversation_id != conversation_id:
            raise ValueError("desktop IPC owner binding conflicts")
        if type(following) is not bool:
            raise ValueError("desktop IPC following state is invalid")
        await self.start()
        await self._send_broadcast(
            "thread-stream-following-changed",
            {
                "conversationId": conversation_id,
                "hostId": _bounded_text(host_id, "host id"),
                "following": following,
            },
            target_client_ids=(owner.owner_client_id,),
        )

    async def load_complete_history_snapshot(
        self,
        conversation_id: str,
        *,
        owner: OwnerBinding | None = None,
        timeout_ms: int = 30_000,
    ) -> DesktopHistorySnapshot:
        """Follow the owner, request complete history, and await its snapshot."""
        conversation_id = _bounded_text(conversation_id, "conversation id")
        timeout_ms = _positive_timeout(timeout_ms, "history snapshot timeout")
        binding = await self._owner_for(conversation_id, owner)
        await self.set_thread_following(
            conversation_id, True, owner=binding
        )
        acknowledgement = await self.load_complete_history(
            conversation_id, owner=binding
        )
        nested_value = acknowledgement.result.get("result")
        nested = (
            cast(JsonObject, nested_value)
            if isinstance(nested_value, dict)
            else acknowledgement.result
        )
        revision = nested.get("revision")
        if type(revision) is not int or revision < 0:
            raise DesktopIpcProtocolError(
                "desktop IPC history revision is invalid"
            )
        event = await self._wait_for_snapshot(
            conversation_id,
            owner_client_id=binding.owner_client_id,
            minimum_revision=revision,
            timeout_ms=timeout_ms,
        )
        change = _json_object(event.params.get("change"), "stream change")
        state = _json_object(
            change.get("conversationState"), "conversation state"
        )
        return DesktopHistorySnapshot(
            conversation_id=conversation_id,
            owner_client_id=binding.owner_client_id,
            revision=change["revision"],
            conversation_state=state,
            acknowledgement=acknowledgement,
        )

    async def start_turn(
        self,
        conversation_id: str,
        *,
        input_items: list[Mapping[str, Any]],
        client_user_message_id: str,
        owner: OwnerBinding | None = None,
        request_values: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
    ) -> StartTurnReceipt:
        """Dispatch exactly once; a lost ACK raises ``UnknownOutcome``."""
        conversation_id = _bounded_text(conversation_id, "conversation id")
        message_id = _bounded_text(client_user_message_id, "client message id")
        if not input_items or not all(isinstance(item, Mapping) for item in input_items):
            raise ValueError("desktop IPC turn input is invalid")
        binding = await self._owner_for(conversation_id, owner)
        request = dict(request_values or {})
        if "threadId" in request and request["threadId"] != conversation_id:
            raise ValueError("desktop IPC thread binding conflicts")
        if (
            "clientUserMessageId" in request
            and request["clientUserMessageId"] != message_id
        ):
            raise ValueError("desktop IPC message binding conflicts")
        request.update(
            {
                "input": [dict(item) for item in input_items],
                "threadId": conversation_id,
                "clientUserMessageId": message_id,
            }
        )
        turn_context = dict(context or {})
        turn_context.setdefault("attachments", [])
        turn_context.setdefault("commentAttachments", [])
        envelope = await self._request_mutation(
            "thread-follower-start-turn",
            {
                "conversationId": conversation_id,
                "turnStart": {"request": request, "context": turn_context},
            },
            target_client_id=binding.owner_client_id,
            return_envelope=True,
        )
        ack = _ack_from_envelope("thread-follower-start-turn", envelope)
        nested = _json_object(ack.result.get("result"), "start turn result")
        turn = _json_object(nested.get("turn"), "start turn acknowledgement")
        turn_id = _bounded_text(turn.get("id"), "turn id")
        status = _optional_text(turn.get("status"))
        return StartTurnReceipt(
            request_id=ack.request_id,
            request_digest=_message_digest(
                {
                    "method": ack.method,
                    "params": {
                        "conversationId": conversation_id,
                        "turnStart": {"request": request, "context": turn_context},
                    },
                }
            ),
            client_user_message_id=message_id,
            owner_client_id=binding.owner_client_id,
            turn_id=turn_id,
            status=status,
        )

    async def steer_turn(
        self,
        conversation_id: str,
        *,
        input_items: list[Mapping[str, Any]],
        client_user_message_id: str,
        restore_message: Mapping[str, Any],
        owner: OwnerBinding,
    ) -> DesktopIpcAck:
        """Steer one active owner turn; never retry after an unknown ACK."""
        conversation_id = _bounded_text(conversation_id, "conversation id")
        if owner.conversation_id != conversation_id:
            raise ValueError("desktop IPC owner binding conflicts")
        if not input_items or not all(isinstance(item, Mapping) for item in input_items):
            raise ValueError("desktop IPC steering input is invalid")
        message_id = _bounded_text(client_user_message_id, "client message id")
        if (
            not isinstance(restore_message, Mapping)
            or restore_message.get("id") != message_id
            or not isinstance(restore_message.get("cwd"), str)
            or not isinstance(restore_message.get("context"), Mapping)
        ):
            raise ValueError("desktop IPC steering restore message is invalid")
        envelope = await self._request_mutation(
            "thread-follower-steer-turn",
            {
                "conversationId": conversation_id,
                "input": [dict(item) for item in input_items],
                "clientUserMessageId": message_id,
                "restoreMessage": dict(restore_message),
                "attachments": [],
            },
            target_client_id=owner.owner_client_id,
            return_envelope=True,
        )
        return _ack_from_envelope("thread-follower-steer-turn", envelope)

    async def answer_command_approval(
        self,
        conversation_id: str,
        request_id: RequestId,
        decision: str,
        *,
        owner: OwnerBinding,
    ) -> DesktopIpcAck:
        return await self._answer_request(
            "thread-follower-command-approval-decision",
            conversation_id,
            request_id,
            {"decision": _bounded_text(decision, "approval decision")},
            owner=owner,
        )

    async def answer_file_approval(
        self,
        conversation_id: str,
        request_id: RequestId,
        decision: str,
        *,
        owner: OwnerBinding,
    ) -> DesktopIpcAck:
        return await self._answer_request(
            "thread-follower-file-approval-decision",
            conversation_id,
            request_id,
            {"decision": _bounded_text(decision, "approval decision")},
            owner=owner,
        )

    async def answer_permissions_request(
        self,
        conversation_id: str,
        request_id: RequestId,
        response: Mapping[str, Any],
        *,
        owner: OwnerBinding,
    ) -> DesktopIpcAck:
        return await self._answer_request(
            "thread-follower-permissions-request-approval-response",
            conversation_id,
            request_id,
            {"response": dict(response)},
            owner=owner,
        )

    async def submit_user_input(
        self,
        conversation_id: str,
        request_id: RequestId,
        response: Mapping[str, Any],
        *,
        owner: OwnerBinding,
    ) -> DesktopIpcAck:
        return await self._answer_request(
            "thread-follower-submit-user-input",
            conversation_id,
            request_id,
            {"response": dict(response)},
            owner=owner,
        )

    async def submit_mcp_elicitation_response(
        self,
        conversation_id: str,
        request_id: RequestId,
        response: Mapping[str, Any],
        *,
        owner: OwnerBinding,
    ) -> DesktopIpcAck:
        return await self._answer_request(
            "thread-follower-submit-mcp-server-elicitation-response",
            conversation_id,
            request_id,
            {"response": dict(response)},
            owner=owner,
        )

    async def next_event(self, *, timeout_ms: int) -> DesktopIpcEvent:
        timeout_ms = _positive_timeout(timeout_ms, "event timeout")
        await self.start()
        try:
            event = await asyncio.wait_for(
                self._events.get(), timeout=timeout_ms / 1_000
            )
        except TimeoutError as exc:
            raise DesktopIpcTimeoutError("broadcast") from exc
        if isinstance(event, DesktopIpcError):
            raise event
        return event

    async def _wait_for_snapshot(
        self,
        conversation_id: str,
        *,
        owner_client_id: str,
        minimum_revision: int,
        timeout_ms: int,
    ) -> DesktopIpcEvent:
        deadline = asyncio.get_running_loop().time() + timeout_ms / 1_000
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise DesktopIpcTimeoutError("thread-stream-state-changed")
            try:
                queued = await asyncio.wait_for(
                    self._events.get(), timeout=remaining
                )
            except TimeoutError as exc:
                raise DesktopIpcTimeoutError(
                    "thread-stream-state-changed"
                ) from exc
            if isinstance(queued, DesktopIpcError):
                raise queued
            params = queued.params
            change = params.get("change")
            if (
                queued.method == "thread-stream-state-changed"
                and queued.source_client_id == owner_client_id
                and params.get("conversationId") == conversation_id
                and isinstance(change, dict)
                and change.get("type") == "snapshot"
                and type(change.get("revision")) is int
                and change["revision"] >= minimum_revision
                and isinstance(change.get("conversationState"), dict)
            ):
                return queued

    async def _send_broadcast(
        self,
        method: str,
        params: Mapping[str, Any],
        *,
        target_client_ids: tuple[str, ...] = (),
    ) -> None:
        version = BROADCAST_VERSIONS.get(method)
        if version is None:
            raise DesktopIpcCompatibilityError(
                method, "unknown-broadcast-version"
            )
        message: JsonObject = {
            "type": "broadcast",
            "method": method,
            "sourceClientId": self._client_id,
            "version": version,
            "params": dict(params),
        }
        if target_client_ids:
            message["targetClientIds"] = [
                _bounded_text(client_id, "target client id")
                for client_id in target_client_ids
            ]
        await self._write_control_message(message)

    async def _answer_request(
        self,
        method: str,
        conversation_id: str,
        request_id: RequestId,
        extra: Mapping[str, Any],
        *,
        owner: OwnerBinding,
    ) -> DesktopIpcAck:
        conversation_id = _bounded_text(conversation_id, "conversation id")
        if owner.conversation_id != conversation_id:
            raise ValueError("desktop IPC owner binding conflicts")
        params: JsonObject = {
            "conversationId": conversation_id,
            "requestId": _request_identifier(request_id, "request id"),
            **dict(extra),
        }
        envelope = await self._request_mutation(
            method,
            params,
            target_client_id=owner.owner_client_id,
            return_envelope=True,
        )
        return _ack_from_envelope(method, envelope)

    async def _owner_for(
        self, conversation_id: str, owner: OwnerBinding | None
    ) -> OwnerBinding:
        if owner is None:
            return await self.find_thread_owner(conversation_id)
        if owner.conversation_id != conversation_id:
            raise ValueError("desktop IPC owner binding conflicts")
        return owner

    async def _request_read(
        self,
        method: str,
        params: Mapping[str, Any],
        *,
        timeout_ms: int,
        retries: int,
        target_client_id: str | None = None,
        return_envelope: bool = False,
    ) -> JsonObject:
        if type(retries) is not int or not 0 <= retries <= 2:
            raise ValueError("desktop IPC read retry count is invalid")
        last_error: DesktopIpcError | None = None
        for attempt in range(retries + 1):
            try:
                await self.start()
                envelope = await self._send_request(
                    method,
                    params,
                    timeout_ms=timeout_ms,
                    target_client_id=target_client_id,
                    mutating=False,
                )
                return envelope if return_envelope else _json_object(
                    envelope.get("result"), "request result"
                )
            except DesktopIpcCompatibilityError:
                raise
            except (DesktopIpcUnavailableError, DesktopIpcTimeoutError) as exc:
                last_error = exc
                if attempt >= retries:
                    raise
                await self._drop_connection(exc, cancel_reader=True)
        raise last_error or DesktopIpcUnavailableError("read-failed")

    async def _request_mutation(
        self,
        method: str,
        params: Mapping[str, Any],
        *,
        target_client_id: str,
        return_envelope: bool = False,
    ) -> JsonObject:
        await self.start()
        envelope = await self._send_request(
            method,
            params,
            timeout_ms=self._request_timeout_ms,
            target_client_id=target_client_id,
            mutating=True,
        )
        return envelope if return_envelope else _json_object(
            envelope.get("result"), "request result"
        )

    async def _connect_once(self) -> None:
        async with self._connection_lock:
            if self.connected:
                return
            if self._closed:
                raise DesktopIpcUnavailableError("client-closed")
            await self._drop_connection(
                DesktopIpcUnavailableError("reconnect"), cancel_reader=True
            )
            try:
                reader, writer = await asyncio.wait_for(
                    self._connector(DESKTOP_PIPE_NAME, self._max_frame_bytes),
                    timeout=self._connect_timeout_ms / 1_000,
                )
            except TimeoutError as exc:
                raise DesktopIpcUnavailableError("connect-timeout") from exc
            except (OSError, DesktopIpcError) as exc:
                if isinstance(exc, DesktopIpcError):
                    raise
                raise DesktopIpcUnavailableError("connect-failed") from exc
            self._reader = reader
            self._writer = writer
            self._client_id = INITIAL_CLIENT_ID
            self._generation += 1
            generation = self._generation
            self._reader_task = asyncio.create_task(
                self._reader_loop(generation, reader),
                name=f"codex-desktop-ipc-reader-{generation}",
            )
            try:
                envelope = await self._send_request(
                    "initialize",
                    {"clientType": self._client_type},
                    timeout_ms=self._connect_timeout_ms,
                    mutating=False,
                )
                result = _json_object(envelope.get("result"), "initialize result")
                self._client_id = _bounded_text(result.get("clientId"), "client id")
            except BaseException:
                await self._drop_connection(
                    DesktopIpcUnavailableError("initialize-failed"),
                    cancel_reader=True,
                )
                raise

    async def _send_request(
        self,
        method: str,
        params: Mapping[str, Any],
        *,
        timeout_ms: int,
        target_client_id: str | None = None,
        mutating: bool,
    ) -> JsonObject:
        version = METHOD_VERSIONS.get(method)
        if version is None:
            raise DesktopIpcCompatibilityError(method, "unknown-method-version")
        timeout_ms = _positive_timeout(timeout_ms, "request timeout")
        writer = self._writer
        if writer is None or writer.is_closing():
            raise DesktopIpcUnavailableError("not-connected")
        request_id = str(uuid4())
        message: JsonObject = {
            "type": "request",
            "requestId": request_id,
            "sourceClientId": self._client_id,
            "version": version,
            "method": method,
            "params": dict(params),
            "timeoutMs": timeout_ms,
        }
        if target_client_id:
            message["targetClientId"] = _bounded_text(
                target_client_id, "target client id"
            )
        request_digest = _message_digest(
            {"method": method, "version": version, "params": dict(params)}
        )
        future: asyncio.Future[JsonObject] = (
            asyncio.get_running_loop().create_future()
        )
        pending = _PendingRequest(
            method=method,
            request_id=request_id,
            request_digest=request_digest,
            mutating=mutating,
            future=future,
        )
        self._pending[request_id] = pending
        attempted_write = False
        try:
            frame = encode_frame(message, max_frame_bytes=self._max_frame_bytes)
            async with self._write_lock:
                if self._writer is not writer or writer.is_closing():
                    raise DesktopIpcUnavailableError("connection-changed")
                attempted_write = True
                writer.write(frame)
                await asyncio.wait_for(
                    writer.drain(), timeout=self._connect_timeout_ms / 1_000
                )
            try:
                return await asyncio.wait_for(
                    asyncio.shield(future), timeout=(timeout_ms + 250) / 1_000
                )
            except TimeoutError as exc:
                if mutating:
                    raise _unknown_outcome(pending, "ack-timeout") from exc
                raise DesktopIpcTimeoutError(method) from exc
        except asyncio.CancelledError as exc:
            if mutating and attempted_write:
                raise _unknown_outcome(pending, "caller-cancelled") from exc
            raise
        except DesktopIpcUnknownOutcome:
            raise
        except DesktopIpcError:
            raise
        except (OSError, ConnectionError) as exc:
            if mutating and attempted_write:
                raise _unknown_outcome(pending, "connection-lost") from exc
            raise DesktopIpcUnavailableError("connection-lost") from exc
        finally:
            self._pending.pop(request_id, None)
            if not future.done():
                future.cancel()

    async def _reader_loop(self, generation: int, reader: IpcReader) -> None:
        try:
            while True:
                message = await read_frame(
                    reader, max_frame_bytes=self._max_frame_bytes
                )
                await self._handle_message(message)
        except asyncio.CancelledError:
            return
        except asyncio.IncompleteReadError as exc:
            await self._connection_lost(
                generation, DesktopIpcUnavailableError("connection-closed")
            )
        except DesktopIpcError as exc:
            await self._connection_lost(generation, exc)
        except (OSError, ConnectionError) as exc:
            await self._connection_lost(
                generation, DesktopIpcUnavailableError("connection-lost")
            )
        except Exception as exc:
            await self._connection_lost(
                generation,
                DesktopIpcProtocolError(
                    f"desktop IPC reader failed: {type(exc).__name__}"
                ),
            )

    async def _handle_message(self, message: JsonObject) -> None:
        message_type = message.get("type")
        if message_type == "response":
            request_id = _optional_text(message.get("requestId"))
            if request_id is None:
                raise DesktopIpcProtocolError("response request id is missing")
            pending = self._pending.get(request_id)
            if pending is None or pending.future.done():
                return
            result_type = message.get("resultType")
            if result_type == "success":
                pending.future.set_result(message)
                return
            reason = _safe_reason(message.get("error"))
            if reason.startswith("request-version-mismatch"):
                error: DesktopIpcError = DesktopIpcCompatibilityError(
                    pending.method, "request-version-mismatch"
                )
            elif reason.startswith("no-client-found"):
                error = DesktopIpcUnavailableError("no-client-found")
            else:
                error = DesktopIpcRequestError(pending.method, reason)
            pending.future.set_exception(error)
            return
        if message_type == "client-discovery-request":
            await self._write_control_message(
                {
                    "type": "client-discovery-response",
                    "requestId": _bounded_text(
                        message.get("requestId"), "discovery request id"
                    ),
                    "response": {"canHandle": False},
                }
            )
            return
        if message_type == "request":
            await self._write_control_message(
                {
                    "type": "response",
                    "requestId": _bounded_text(
                        message.get("requestId"), "inbound request id"
                    ),
                    "resultType": "error",
                    "error": "no-handler-for-request",
                }
            )
            return
        if message_type == "broadcast":
            method = _bounded_text(message.get("method"), "broadcast method")
            version = message.get("version")
            expected = BROADCAST_VERSIONS.get(method)
            if expected is None:
                return
            if version != expected:
                raise DesktopIpcCompatibilityError(
                    method, f"expected-version-{expected}"
                )
            if type(version) is not int:
                raise DesktopIpcProtocolError("broadcast version is invalid")
            if self._events.full():
                raise DesktopIpcProtocolError("desktop IPC event queue overflow")
            self._events.put_nowait(
                DesktopIpcEvent(
                    method=method,
                    version=version,
                    source_client_id=_optional_text(message.get("sourceClientId")),
                    params=_json_object(message.get("params"), "broadcast params"),
                )
            )
            return
        raise DesktopIpcProtocolError("desktop IPC message type is unsupported")

    async def _write_control_message(self, message: Mapping[str, Any]) -> None:
        writer = self._writer
        if writer is None or writer.is_closing():
            raise DesktopIpcUnavailableError("not-connected")
        frame = encode_frame(message, max_frame_bytes=self._max_frame_bytes)
        async with self._write_lock:
            if self._writer is not writer or writer.is_closing():
                raise DesktopIpcUnavailableError("connection-changed")
            writer.write(frame)
            await writer.drain()

    async def _connection_lost(
        self, generation: int, error: DesktopIpcError
    ) -> None:
        if generation != self._generation:
            return
        writer = self._writer
        self._reader = None
        self._writer = None
        self._client_id = INITIAL_CLIENT_ID
        self._fail_pending(error)
        if isinstance(error, DesktopIpcCompatibilityError) and not self._events.full():
            self._events.put_nowait(error)
        if writer is not None:
            writer.close()

    async def _drop_connection(
        self, error: DesktopIpcError, *, cancel_reader: bool
    ) -> None:
        task = self._reader_task
        self._reader_task = None
        writer = self._writer
        self._reader = None
        self._writer = None
        self._client_id = INITIAL_CLIENT_ID
        self._fail_pending(error)
        if cancel_reader and task is not None and task is not asyncio.current_task():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except (AttributeError, OSError, ConnectionError):
                pass

    def _fail_pending(self, error: DesktopIpcError) -> None:
        for pending in tuple(self._pending.values()):
            if pending.future.done():
                continue
            if pending.mutating:
                pending.future.set_exception(
                    _unknown_outcome(pending, "connection-lost")
                )
            else:
                pending.future.set_exception(error)


def _answered_async_question_ids(items: list[Any]) -> frozenset[str]:
    """Find only Desktop's exact steered async-question reply envelope."""
    opening = "<send_user_message_question_reply>"
    closing = "</send_user_message_question_reply>"
    found: set[str] = set()
    for raw_item in items:
        if not isinstance(raw_item, dict) or raw_item.get("type") != "steeringUserMessage":
            continue
        parts = raw_item.get("input")
        if not isinstance(parts, list) or len(parts) != 1 or not isinstance(parts[0], dict):
            continue
        text = parts[0].get("text") if parts[0].get("type") == "text" else None
        if not isinstance(text, str):
            continue
        value = text.strip()
        if not value.startswith(opening) or not value.endswith(closing):
            continue
        try:
            answers = json.loads(value[len(opening):-len(closing)].strip())
        except json.JSONDecodeError:
            continue
        if not isinstance(answers, list):
            continue
        for answer in answers:
            if not isinstance(answer, dict):
                continue
            question_id = answer.get("questionItemId")
            if isinstance(question_id, str) and isinstance(answer.get("answer"), str):
                found.add(question_id)
    return frozenset(found)


def project_desktop_conversation(
    snapshot: DesktopHistorySnapshot,
) -> DesktopConversationProjection:
    """Project the complete canonical Desktop state without shortening output."""
    state = snapshot.conversation_state
    state_id = _bounded_text(state.get("id"), "conversation state id")
    if state_id != snapshot.conversation_id:
        raise DesktopIpcProtocolError(
            "desktop IPC conversation state binding conflicts"
        )
    turn_history = _json_object(state.get("turnHistory"), "turn history")
    if turn_history.get("kind") != "canonical":
        raise DesktopIpcCompatibilityError(
            "thread-stream-state-changed", "unsupported-turn-history-kind"
        )
    history = _json_object(turn_history.get("history"), "canonical history")
    if history.get("isComplete") is not True:
        raise DesktopIpcProtocolError(
            "desktop IPC canonical history is incomplete"
        )
    entities = _json_object(history.get("entitiesByKey"), "history entities")
    islands = history.get("islands")
    if not isinstance(islands, list) or not islands:
        raise DesktopIpcProtocolError("desktop IPC history islands are invalid")

    ordered_entity_keys: list[str] = []
    seen_entity_keys: set[str] = set()
    for island in islands:
        island_object = _json_object(island, "history island")
        entries = island_object.get("entries")
        if not isinstance(entries, list):
            raise DesktopIpcProtocolError(
                "desktop IPC history island entries are invalid"
            )
        for entry in entries:
            entry_object = _json_object(entry, "history island entry")
            entity_key = _bounded_text(
                entry_object.get("value"), "history entity key"
            )
            if entity_key in seen_entity_keys:
                raise DesktopIpcProtocolError(
                    "desktop IPC history contains duplicate entity"
                )
            if entity_key not in entities:
                raise DesktopIpcProtocolError(
                    "desktop IPC history entity is missing"
                )
            seen_entity_keys.add(entity_key)
            ordered_entity_keys.append(entity_key)
    if seen_entity_keys != set(entities):
        raise DesktopIpcProtocolError(
            "desktop IPC history contains unordered entities"
        )

    turns: list[DesktopTurnState] = []
    async_questions: list[DesktopPendingRequest] = []
    for entity_key in ordered_entity_keys:
        entity = _json_object(entities[entity_key], "history turn")
        params = _json_object(entity.get("params"), "history turn params")
        items = entity.get("items")
        if not isinstance(items, list):
            raise DesktopIpcProtocolError("desktop IPC turn items are invalid")
        user_text: list[str] = []
        agent_messages: list[DesktopAgentMessage] = []
        plan_items: list[DesktopAgentMessage] = []
        text_outputs: list[DesktopAgentMessage] = []
        answered_async_ids = _answered_async_question_ids(items)
        for raw_item in items:
            item = _json_object(raw_item, "history item")
            item_type = item.get("type")
            if item_type == "userMessage":
                content = item.get("content")
                if not isinstance(content, list):
                    raise DesktopIpcProtocolError(
                        "desktop IPC user message content is invalid"
                    )
                for raw_part in content:
                    part = _json_object(raw_part, "user message part")
                    if part.get("type") == "text":
                        text = part.get("text")
                        if not isinstance(text, str):
                            raise DesktopIpcProtocolError(
                                "desktop IPC user message text is invalid"
                            )
                        user_text.append(text)
            elif item_type == "agentMessage":
                text = item.get("text")
                if not isinstance(text, str):
                    raise DesktopIpcProtocolError(
                        "desktop IPC agent message text is invalid"
                    )
                delivery = _optional_text(item.get("delivery"))
                raw_questions = item.get("questions")
                if raw_questions is None:
                    questions: tuple[Mapping[str, Any], ...] = ()
                elif isinstance(raw_questions, list) and all(
                    isinstance(question, dict) for question in raw_questions
                ):
                    questions = tuple(dict(question) for question in raw_questions)
                else:
                    raise DesktopIpcProtocolError(
                        "desktop IPC async questions are invalid"
                    )
                output = DesktopAgentMessage(
                    item_id=_bounded_text(item.get("id"), "agent item id"),
                    text=text,
                    phase=_optional_text(item.get("phase")),
                    delivery=delivery,
                    questions=questions,
                )
                agent_messages.append(output)
                text_outputs.append(output)
                if delivery == "async" and questions and entity.get("status") == "inProgress":
                    pending_questions: list[dict[str, Any]] = []
                    for index, question in enumerate(questions):
                        title = _bounded_text(question.get("title"), "async question title")
                        question_id = json.dumps(
                            ["request_user_input_async", output.item_id, index],
                            separators=(",", ":"),
                        )
                        if question_id in answered_async_ids:
                            continue
                        options = question.get("options", [])
                        if not isinstance(options, list):
                            raise DesktopIpcProtocolError("desktop IPC async question options are invalid")
                        pending_questions.append({
                            "id": question_id, "question": title,
                            "options": options,
                        })
                    if pending_questions:
                        async_questions.append(DesktopPendingRequest(
                            request_id=output.item_id,
                            method="item/tool/requestUserInputAsync",
                            payload={
                                "id": output.item_id,
                                "method": "item/tool/requestUserInputAsync",
                                "params": {
                                    "threadId": snapshot.conversation_id,
                                    "turnId": entity.get("turnId"),
                                    "itemId": output.item_id,
                                    "questions": pending_questions,
                                },
                            },
                        ))
            elif item_type == "plan":
                text = item.get("text")
                if not isinstance(text, str):
                    raise DesktopIpcProtocolError(
                        "desktop IPC plan text is invalid"
                    )
                output = DesktopAgentMessage(
                    item_id=_bounded_text(item.get("id"), "plan item id"),
                    text=text,
                    phase="plan",
                )
                plan_items.append(output)
                text_outputs.append(output)
        turns.append(
            DesktopTurnState(
                turn_id=_bounded_text(entity.get("turnId"), "turn id"),
                client_user_message_id=_bounded_text(
                    params.get("clientUserMessageId"), "client message id"
                ),
                status=_bounded_text(entity.get("status"), "turn status"),
                user_text=tuple(user_text),
                agent_messages=tuple(agent_messages),
                plan_items=tuple(plan_items),
                text_outputs=tuple(text_outputs),
            )
        )

    requests = state.get("requests")
    if not isinstance(requests, list):
        raise DesktopIpcProtocolError("desktop IPC pending requests are invalid")
    pending_requests: list[DesktopPendingRequest] = []
    seen_request_ids: set[RequestId] = set()
    for raw_request in requests:
        request = _json_object(raw_request, "pending request")
        request_id = _request_identifier(
            request.get("id"), "pending request id"
        )
        if request_id in seen_request_ids:
            raise DesktopIpcProtocolError(
                "desktop IPC pending request id is duplicated"
            )
        seen_request_ids.add(request_id)
        pending_requests.append(
            DesktopPendingRequest(
                request_id=request_id,
                method=_bounded_text(
                    request.get("method"), "pending request method"
                ),
                payload=MappingProxyType(dict(request)),
            )
        )
    for pending in async_questions:
        if pending.request_id in seen_request_ids:
            raise DesktopIpcProtocolError("desktop IPC async question id is duplicated")
        seen_request_ids.add(pending.request_id)
        pending_requests.append(pending)

    runtime_status_value = state.get("threadRuntimeStatus")
    if isinstance(runtime_status_value, dict):
        runtime_status = _bounded_text(
            runtime_status_value.get("type"), "thread runtime status"
        )
    else:
        runtime_status = _bounded_text(
            runtime_status_value, "thread runtime status"
        )

    return DesktopConversationProjection(
        conversation_id=state_id,
        title=_bounded_text(state.get("title"), "conversation title"),
        cwd=_bounded_text(state.get("cwd"), "conversation cwd"),
        runtime_status=runtime_status,
        turns=tuple(turns),
        pending_requests=tuple(pending_requests),
    )


async def reconcile_unknown_outcome(
    unknown: DesktopIpcUnknownOutcome,
    *,
    readback: Readback,
    classify: RecoveryClassifier,
) -> RecoveryResult:
    """Read actual state once; this helper never resends the mutation."""
    state = await readback()
    if not isinstance(state, Mapping):
        raise DesktopIpcProtocolError("desktop IPC readback is invalid")
    verdict, reference = classify(state, unknown)
    if not isinstance(verdict, RecoveryVerdict):
        raise TypeError("desktop IPC recovery classifier is invalid")
    return RecoveryResult(
        verdict=verdict,
        readback_digest=_message_digest(state),
        observed_reference=reference,
    )


def classify_history_by_client_message_id(
    history: Mapping[str, Any],
    unknown: DesktopIpcUnknownOutcome,
    *,
    client_user_message_id: str,
) -> tuple[RecoveryVerdict, str | None]:
    """Confirm a unique persisted correlation token; absence remains UNKNOWN."""
    del unknown
    token = _bounded_text(client_user_message_id, "client message id")
    references: list[str | None] = []

    def visit(value: Any, inherited_reference: str | None = None) -> None:
        if isinstance(value, Mapping):
            reference = inherited_reference
            for key in ("turnId", "turn_id"):
                candidate = _optional_text(value.get(key))
                if candidate is not None:
                    reference = candidate
                    break
            if value.get("clientUserMessageId") == token:
                references.append(reference)
            for child in value.values():
                visit(child, reference)
        elif isinstance(value, list):
            for child in value:
                visit(child, inherited_reference)

    visit(history)
    if len(references) == 1:
        return RecoveryVerdict.CONFIRMED, references[0]
    if len(references) > 1:
        return RecoveryVerdict.CONFLICT, None
    # The current live contract has not yet proved that every history response
    # preserves clientUserMessageId, so a miss cannot authorize a resend.
    return RecoveryVerdict.UNKNOWN, None


async def _open_windows_named_pipe(
    pipe_name: str, max_frame_bytes: int
) -> tuple[IpcReader, IpcWriter]:
    if os.name != "nt" or pipe_name != DESKTOP_PIPE_NAME:
        raise DesktopIpcUnavailableError("unsupported-platform-or-pipe")
    loop = asyncio.get_running_loop()
    create_pipe_connection = getattr(loop, "create_pipe_connection", None)
    if not callable(create_pipe_connection):
        raise DesktopIpcUnavailableError("named-pipe-event-loop-unavailable")
    reader = asyncio.StreamReader(limit=max_frame_bytes + 4)
    protocol = asyncio.StreamReaderProtocol(reader)
    transport, _ = await create_pipe_connection(lambda: protocol, pipe_name)
    writer = asyncio.StreamWriter(transport, protocol, reader, loop)
    return reader, writer


def _ack_from_envelope(method: str, envelope: Mapping[str, Any]) -> DesktopIpcAck:
    return DesktopIpcAck(
        method=method,
        request_id=_bounded_text(envelope.get("requestId"), "request id"),
        handled_by_client_id=_optional_text(envelope.get("handledByClientId")),
        result=_json_object(envelope.get("result"), "request result"),
    )


def _unknown_outcome(
    pending: _PendingRequest, reason: str
) -> DesktopIpcUnknownOutcome:
    return DesktopIpcUnknownOutcome(
        method=pending.method,
        request_id=pending.request_id,
        request_digest=pending.request_digest,
        reason=reason,
    )


def _message_digest(value: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            dict(value),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DesktopIpcProtocolError("desktop IPC value is not JSON-safe") from exc
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _json_object(value: Any, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise DesktopIpcProtocolError(f"desktop IPC {label} is invalid")
    return cast(JsonObject, value)


def _bounded_text(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"desktop IPC {label} is invalid")
    normalized = value.strip()
    if not normalized or len(normalized) > 512 or any(
        character in normalized for character in "\r\n\x00"
    ):
        raise ValueError(f"desktop IPC {label} is invalid")
    return normalized


def _optional_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return _bounded_text(value, "text value")


def _request_identifier(value: Any, label: str) -> RequestId:
    if type(value) is int:
        if 0 <= value <= 9_007_199_254_740_991:
            return value
        raise ValueError(f"desktop IPC {label} is invalid")
    return _bounded_text(value, label)


def _safe_reason(value: Any) -> str:
    if not isinstance(value, str):
        return "request-failed"
    code = value.split(":", 1)[0].strip().lower()
    if not code or len(code) > 64 or any(
        character not in "abcdefghijklmnopqrstuvwxyz0123456789-_"
        for character in code
    ):
        return "request-failed"
    return code


def _positive_timeout(value: Any, label: str) -> int:
    if type(value) is not int or not 1 <= value <= 600_000:
        raise ValueError(f"desktop IPC {label} is invalid")
    return value


def _validate_frame_limit(value: Any) -> None:
    if type(value) is not int or not 1_024 <= value <= HARD_MAX_FRAME_BYTES:
        raise ValueError("desktop IPC frame limit is invalid")


def _validate_reconnect_delays(value: Any) -> tuple[int, ...]:
    if not isinstance(value, tuple) or len(value) > 8:
        raise ValueError("desktop IPC reconnect delays are invalid")
    if any(type(delay) is not int or not 0 <= delay <= 60_000 for delay in value):
        raise ValueError("desktop IPC reconnect delays are invalid")
    return value
