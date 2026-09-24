"""Contract test for the canonical notifier source and bridge state."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest

from src.application.desktop_bridge_state import BridgeRequestStatus, SQLiteDesktopBridgeState


CANONICAL_NOTIFIER_SOURCE = Path(
    r"C:\Хранилище\АГЕНТ\АРТУР АССИСТЕНТ\System\codex-task-notifier-v2\notify_every_turn.py"
)


def test_patched_notifier_suppresses_only_durable_exact_bridge_turn(tmp_path: Path) -> None:
    notifier_path = CANONICAL_NOTIFIER_SOURCE
    if not notifier_path.is_file():
        pytest.skip("The separate canonical notifier package is unavailable")
    spec = importlib.util.spec_from_file_location("local_notifier_patch", notifier_path)
    assert spec is not None and spec.loader is not None
    notifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(notifier)

    request_id = uuid4()
    thread_id, turn_id = str(uuid4()), str(uuid4())
    state_path = tmp_path / "bridge.sqlite3"
    state = SQLiteDesktopBridgeState(
        state_path,
        encode=lambda item: json.dumps(item).encode(),
        decode=lambda data: json.loads(data),
    )
    state.create_request(
        request_id=request_id, ingress_key="sha256:" + "a" * 64,
        tenant_id="owner", author_user_id=41,
        author_identity="telegram:member:41", chat_id=-1001, topic_id=7,
        source_message_id=12, operation="create", project_name="project",
        payload={"instruction": "test"},
    )
    state.bind_desktop(
        request_id, thread_id=thread_id, turn_id=turn_id,
        client_message_id=f"nobus:{request_id}", status=BridgeRequestStatus.RUNNING,
    )
    bootstrap_turn_id = str(uuid4())
    assert state.bind_bootstrap_turn(
        request_id, thread_id=thread_id, turn_id=bootstrap_turn_id
    )
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    session = sessions / f"session-{thread_id}.jsonl"
    record = {
        "type": "response_item",
        "payload": {
            "type": "message", "role": "user",
            "internal_chat_message_metadata_passthrough": {"turn_id": turn_id},
            "content": [{"type": "input_text", "text": f"NOBUS-BRIDGE-REQUEST:{request_id}"}],
        },
    }
    session.write_text(json.dumps(record) + "\n", encoding="utf-8")
    index = tmp_path / "session_index.json"
    assert notifier.desktop_bridge_turn(thread_id, turn_id, index, state_path)
    record["payload"]["internal_chat_message_metadata_passthrough"]["turn_id"] = bootstrap_turn_id
    session.write_text(json.dumps(record) + "\n", encoding="utf-8")
    assert notifier.desktop_bridge_turn(thread_id, bootstrap_turn_id, index, state_path)
    record["payload"]["internal_chat_message_metadata_passthrough"]["turn_id"] = turn_id
    session.write_text(json.dumps(record) + "\n", encoding="utf-8")
    assert not notifier.desktop_bridge_turn(thread_id, turn_id, index, None)
    assert not notifier.desktop_bridge_turn(thread_id, str(uuid4()), index, state_path)
    record["payload"]["content"][0]["text"] = f"NOBUS-BRIDGE-REQUEST:{uuid4()}"
    session.write_text(json.dumps(record) + "\n", encoding="utf-8")
    assert not notifier.desktop_bridge_turn(thread_id, turn_id, index, state_path)
