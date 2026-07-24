from __future__ import annotations

from src.application.durable_confirmations import DurableTelegramActionStore
from src.application.durable_telegram_state import SQLiteTelegramState
from src.application.telegram_actions import TelegramAction
from tests.test_telegram_actions import callback


def test_action_route_survives_process_store_recreation(tmp_path):
    path = tmp_path / "runtime.sqlite3"
    first = DurableTelegramActionStore(SQLiteTelegramState(path))
    token = first.issue(
        action=TelegramAction.CONFIRM_VOICE,
        capability_token="c" * 43,
        user_id=1,
        chat_id=1,
        ttl_seconds=60,
    )

    recovered = DurableTelegramActionStore(SQLiteTelegramState(path))
    assert recovered.claim(token, 1, 1)
    action = recovered.consume(callback(token))
    assert action is not None
    assert action.action is TelegramAction.CONFIRM_VOICE
    assert action.capability_token == "c" * 43
    assert recovered.commit(callback(token))

    third = DurableTelegramActionStore(SQLiteTelegramState(path))
    assert not third.claim(token, 1, 1)
