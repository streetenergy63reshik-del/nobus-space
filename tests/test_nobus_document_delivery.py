from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from src.integrations.nobus_document_delivery import NobusDocumentDelivery


class _Api:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, bytes, int | None]] = []

    async def send_document(
        self,
        chat_id: int,
        filename: str,
        content: bytes,
        *,
        message_thread_id: int | None = None,
    ) -> int:
        self.calls.append((chat_id, filename, content, message_thread_id))
        return 100 + len(self.calls)


@pytest.mark.asyncio
async def test_installed_delivery_owner_dedupes_replay_not_new_request(
    tmp_path: Path,
) -> None:
    runtime = (
        Path.home()
        / ".codex"
        / "skills"
        / "nobus-send-results"
        / "scripts"
        / "telegram_delivery_runtime.py"
    )
    delivery = NobusDocumentDelivery(
        runtime_path=runtime,
        ledger_path=tmp_path / "telegram-document-delivery.sqlite3",
    )
    api = _Api()
    first_request = uuid4()
    operation = "sha256:" + "1" * 64
    first = await delivery.deliver(
        api=api,
        request_id=first_request,
        operation_id=operation,
        tenant_id="owner",
        chat_id=-1001,
        topic_id=7,
        filename="result.txt",
        content=b"same bytes",
    )
    replay = await delivery.deliver(
        api=api,
        request_id=first_request,
        operation_id=operation,
        tenant_id="owner",
        chat_id=-1001,
        topic_id=7,
        filename="result.txt",
        content=b"same bytes",
    )
    new_request = await delivery.deliver(
        api=api,
        request_id=uuid4(),
        operation_id="sha256:" + "2" * 64,
        tenant_id="owner",
        chat_id=-1001,
        topic_id=7,
        filename="result.txt",
        content=b"same bytes",
    )
    assert first.status == "sent" and first.message_id == 101
    assert replay.status == "sent_existing" and replay.message_id is None
    assert new_request.status == "sent" and new_request.message_id == 102
    assert len(api.calls) == 2
    assert all(call[3] == 7 for call in api.calls)
