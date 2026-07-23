"""Offline regressions for the Telegram MVP-1 executable bootstrap."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_telegram_mvp1 as runner


def _bundled_cli(home: Path, version: str) -> Path:
    path = (
        home
        / ".vscode"
        / "extensions"
        / f"openai.chatgpt-{version}-win32-x64"
        / "bin"
        / "windows-x86_64"
        / "codex.exe"
    )
    path.parent.mkdir(parents=True)
    path.touch()
    return path


def test_selector_prefers_newest_working_vscode_codex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    older = _bundled_cli(tmp_path, "2.0.0")
    newest = _bundled_cli(tmp_path, "10.0.0")
    calls: list[Path] = []

    monkeypatch.setattr(runner.shutil, "which", lambda name: None)

    def run(argv: tuple[str, str], **options: object) -> SimpleNamespace:
        calls.append(Path(argv[0]))
        assert argv[1] == "--version"
        assert options["shell"] is False
        return SimpleNamespace(returncode=0, stdout=b"codex-cli 1.0\n", stderr=b"")

    monkeypatch.setattr(runner.subprocess, "run", run)

    assert runner._required_codex_executable(tmp_path) == newest.resolve()
    assert calls == [newest.resolve()]
    assert older.resolve() not in calls


def test_selector_skips_cli_that_cannot_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = _bundled_cli(tmp_path, "2.0.0")
    working = _bundled_cli(tmp_path, "1.0.0")
    monkeypatch.setattr(runner.shutil, "which", lambda name: None)

    def run(argv: tuple[str, str], **options: object) -> SimpleNamespace:
        if Path(argv[0]) == broken.resolve():
            raise OSError("access denied")
        return SimpleNamespace(returncode=0, stdout=b"codex-cli 1.0\n", stderr=b"")

    monkeypatch.setattr(runner.subprocess, "run", run)

    assert runner._required_codex_executable(tmp_path) == working.resolve()


def test_live_polling_lease_covers_network_and_long_handler() -> None:
    assert runner._POLLING_LEASE_SECONDS == 300
    assert runner._POLLING_LEASE_SECONDS > 30 + 120
