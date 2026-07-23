"""Product regressions for the Telegram weekly Codex limit command."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.configure_telegram_profile import _COMMANDS
from src.workers.codex_limits import WeeklyLimitSnapshot
from tests.test_telegram_product import _product, text_update
from tests.test_telegram_task_control import USER_ID


class FakeLimitProvider:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    async def fetch_weekly(self) -> WeeklyLimitSnapshot:
        self.calls += 1
        if self.fail:
            raise RuntimeError("provider detail must stay private")
        return WeeklyLimitSnapshot(used_percent=14, resets_at=1_785_400_820)


def test_product_profile_includes_limit_menu_command() -> None:
    assert ("limit", "Недельный лимит Codex") in _COMMANDS


@pytest.mark.asyncio
async def test_limit_command_renders_weekly_usage_and_is_not_a_task(
    tmp_path: Path,
) -> None:
    harness = _product(tmp_path)
    provider = FakeLimitProvider()
    harness.control._limit_provider = provider  # type: ignore[attr-defined]

    assert await harness.control.handle(text_update("/limit", 1))
    await harness.control.handle(text_update("/help", 2))

    assert "Осталось: 86%" in harness.api.sent[0][1]
    assert "Использовано: 14%" in harness.api.sent[0][1]
    assert "по Москве" in harness.api.sent[0][1]
    assert "/limit" in harness.api.sent[1][1]
    assert provider.calls == 1
    assert harness.runtime.drafted == []


@pytest.mark.asyncio
async def test_limit_provider_failure_is_safe_and_not_a_task(tmp_path: Path) -> None:
    harness = _product(tmp_path)
    harness.control._limit_provider = FakeLimitProvider(  # type: ignore[attr-defined]
        fail=True
    )

    assert await harness.control.handle(text_update("/limit", 1))

    assert harness.api.sent == [
        (USER_ID, "Лимит Codex сейчас недоступен. Попробуйте позже.", ())
    ]
    assert harness.runtime.drafted == []
