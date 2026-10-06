from __future__ import annotations

from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
from uuid import uuid4

import pytest

from src.integrations.nobus_document_delivery import NobusDocumentDelivery


def test_unextended_installed_sender_fails_closed(tmp_path: Path) -> None:
    runtime = (
        Path.home() / ".codex" / "skills" / "nobus-send-results"
        / "scripts" / "telegram_delivery_runtime.py"
    )
    if "def receipt(self, delivery_key:" in runtime.read_text(encoding="utf-8"):
        pytest.skip("installed sender already has the reviewed v2 extension")
    with pytest.raises(ValueError, match="lacks operation receipts"):
        NobusDocumentDelivery(
            runtime_path=runtime,
            ledger_path=tmp_path / "ledger.sqlite3",
            bot_id=123, bot_username="Nobusspacebot",
            group_binding_ref="sha256:" + "a" * 64,
            group_chat_id=-1001, group_tenant_id="owner",
        )


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
    source = runtime.read_text(encoding="utf-8")
    config = {
        "ledger_path": tmp_path / "telegram-document-delivery.sqlite3",
        "bot_id": 123,
        "bot_username": "Nobusspacebot",
        "group_binding_ref": "sha256:" + "a" * 64,
        "group_chat_id": -1001,
        "group_tenant_id": "owner",
    }
    if "def receipt(self, delivery_key:" not in source:
        repo_root = Path(__file__).resolve().parents[1]
        scratch_root = repo_root / ".runtime"
        scratch_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            dir=scratch_root, prefix="sender-v2-test-"
        ) as scratch:
            patched = Path(scratch) / "telegram_delivery_runtime.py"
            shutil.copyfile(runtime, patched)
            patch = (
                repo_root / "docs" / "gates" / "mvp2" / "m2-desktop"
                / "telegram-delivery-runtime-v2.patch"
            )
            subprocess.run(
                [
                    "git", "apply",
                    "--directory=" + patched.parent.relative_to(repo_root).as_posix(),
                    str(patch),
                ],
                cwd=repo_root, check=True, capture_output=True,
            )
            delivery = NobusDocumentDelivery(runtime_path=patched, **config)
    else:
        delivery = NobusDocumentDelivery(runtime_path=runtime, **config)
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
    assert replay.status == "sent_existing" and replay.message_id == 101
    assert new_request.status == "sent" and new_request.message_id == 102
    assert len(api.calls) == 2
    assert all(call[3] == 7 for call in api.calls)
    with sqlite3.connect(tmp_path / "telegram-document-delivery.sqlite3") as connection:
        rows = connection.execute(
            "SELECT destination_ref,delivery_key,message_id FROM telegram_document_deliveries"
        ).fetchall()
    assert len(rows) == 2
    assert rows[0][0] == rows[1][0]
    assert rows[0][1] != rows[1][1]
    with pytest.raises(ValueError, match="request is invalid"):
        await delivery.deliver(
            api=api,
            request_id=uuid4(),
            operation_id="sha256:" + "g" * 64,
            tenant_id="owner",
            chat_id=-1001,
            topic_id=7,
            filename="result.txt",
            content=b"same bytes",
        )
    assert len(api.calls) == 2
