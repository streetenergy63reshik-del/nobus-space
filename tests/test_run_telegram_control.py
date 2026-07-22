"""Offline tests for Telegram control runner bootstrap semantics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts.run_telegram_control import (
    _arguments,
    _bootstrap_checkpoint,
    _poll_once_and_announce,
)
from src.transport.telegram.bot_api import (
    PollBatchResult,
    TelegramBotApiError,
)
from src.transport.telegram.sqlite_checkpoint import (
    SQLitePollingCheckpointError,
    SQLitePollingCheckpointStore,
)


def test_bootstrap_sets_exact_offset_once(tmp_path: Path) -> None:
    store = SQLitePollingCheckpointStore(
        tmp_path / "polling.sqlite3",
        consumer_id="test-owner",
    )
    _bootstrap_checkpoint(store, 11)
    _bootstrap_checkpoint(store, 11)
    with pytest.raises(SQLitePollingCheckpointError):
        _bootstrap_checkpoint(store, 12)


def test_arguments_require_bounded_explicit_mode() -> None:
    values = _arguments(["--once", "--timeout", "0", "--bootstrap-next-offset", "11"])
    assert values.once and not values.serve
    assert values.timeout == 0
    assert values.bootstrap_next_offset == 11
    for invalid in (
        [],
        ["--once", "--timeout", "51"],
        ["--serve", "--timeout", "0"],
        ["--once", "--bootstrap-next-offset", "9223372036854775808"],
    ):
        with pytest.raises(SystemExit):
            _arguments(invalid)


class FakePolling:
    def __init__(
        self,
        *,
        result: PollBatchResult | None = None,
        failure: Exception | None = None,
    ) -> None:
        self.result = result or PollBatchResult(None, 0, False)
        self.failure = failure

    async def poll_once(self, *, timeout: int, limit: int) -> PollBatchResult:
        assert 0 <= timeout <= 50
        assert limit == 20
        if self.failure is not None:
            raise self.failure
        return self.result


class FakeApi:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> int:
        self.sent.append((chat_id, text))
        return 1


@pytest.mark.asyncio
async def test_announcement_follows_successful_poll_and_uses_bound_chat() -> None:
    api = FakeApi()
    acknowledged = await _poll_once_and_announce(
        FakePolling(result=PollBatchResult(12, 2, False)),  # type: ignore[arg-type]
        api,  # type: ignore[arg-type]
        {(42, 42): object()},
        timeout=0,
        announce=True,
    )
    assert acknowledged == 2
    assert len(api.sent) == 1
    assert api.sent[0][0] == 42
    assert "polling cycle" in api.sent[0][1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "polling",
    [
        FakePolling(failure=RuntimeError("checkpoint failed")),
        FakePolling(result=PollBatchResult(None, 0, True)),
    ],
)
async def test_poll_failure_never_sends_success_announcement(polling: Any) -> None:
    api = FakeApi()
    with pytest.raises((RuntimeError, TelegramBotApiError)):
        await _poll_once_and_announce(
            polling,
            api,  # type: ignore[arg-type]
            {(42, 42): object()},
            timeout=0,
            announce=True,
        )
    assert api.sent == []
