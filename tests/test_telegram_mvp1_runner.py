"""Offline regressions for the Telegram MVP-1 executable bootstrap."""

from __future__ import annotations

import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_telegram_mvp1 as runner


@pytest.mark.parametrize(
    ("reported_stage", "expected_code"),
    [
        ("worker_probe", "telegram_mvp1_worker_probe_failed"),
        ("token=must-not-leak", "telegram_mvp1_failed"),
    ],
)
def test_main_reports_only_allowlisted_startup_stage(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    reported_stage: str,
    expected_code: str,
) -> None:
    async def fail(values: object, *, report_stage: object) -> object:
        report_stage(reported_stage)  # type: ignore[operator]
        raise RuntimeError("secret exception text must not leak")

    monkeypatch.setattr(runner, "WindowsNamedMutex", nullcontext)
    monkeypatch.setattr(runner, "recover_interrupted_restore", lambda path: None)
    monkeypatch.setattr(runner, "_arguments", lambda: object())
    monkeypatch.setattr(runner, "_run", fail)

    assert runner.main() == 1
    output = capsys.readouterr().out
    assert json.loads(output) == {"status": "FAIL", "code": expected_code}
    assert "secret" not in output
    assert "token" not in output


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


def test_production_selector_prefers_pinned_bundled_codex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundled = tmp_path / "bundled" / "codex.exe"
    bundled.parent.mkdir()
    bundled.touch()
    monkeypatch.setattr(runner, "bundled_codex_path", lambda: bundled)
    monkeypatch.setattr(runner.shutil, "which", lambda name: None)
    calls: list[Path] = []

    def run(argv: tuple[str, str], **options: object) -> SimpleNamespace:
        calls.append(Path(argv[0]))
        return SimpleNamespace(
            returncode=0,
            stdout=b"codex-cli 0.144.4\n",
            stderr=b"",
        )

    monkeypatch.setattr(runner.subprocess, "run", run)

    assert runner._required_codex_executable() == bundled.resolve()
    assert calls == [bundled.resolve()]


def test_live_polling_lease_covers_only_telegram_processing() -> None:
    assert runner._POLLING_LEASE_SECONDS == 240
    assert runner._POLLING_LEASE_SECONDS > 30
    assert runner._POLLING_LEASE_SECONDS < 300


def test_production_runtime_uses_one_canonical_database_directory() -> None:
    assert runner._RUNTIME_ROOT == runner.ROOT / ".runtime"
    paths = (
        runner._CHECKPOINT_PATH,
        runner._TASK_RUNTIME_PATH,
        runner._TELEGRAM_STATE_PATH,
        runner._BUSINESS_NOTES_PATH,
    )

    assert {path.parent for path in paths} == {runner._RUNTIME_ROOT}
    assert {path.name for path in paths} == {
        "telegram-checkpoint.sqlite3",
        "task-runtime.sqlite3",
        "telegram-state.sqlite3",
        "business-notes.sqlite3",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", ["worker", "voice"] )
async def test_failed_startup_probe_prevents_control_polling_and_announcement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_stage: str
) -> None:
    from src.voice import VoiceTranscriptionError
    from src.workers.codex_cli import CodexCliError

    startup_events: list[str] = []

    class Secret:
        def get_secret_value(self) -> str:
            return "test-token"

    class Api:
        closed = False

        def __init__(self, **values: object) -> None:
            pass

        async def get_me(self) -> SimpleNamespace:
            return SimpleNamespace(bot_id=1, username="Nobusspacebot")

        async def aclose(self) -> None:
            self.closed = True

    class Runtime:
        async def probe_worker(self) -> None:
            startup_events.append("worker_probe")
            if failure_stage == "worker":
                raise CodexCliError("worker_timeout")

    class Transcriber:
        def __init__(self, **values: object) -> None:
            assert values["local_files_only"] is True
            assert values["beam_size"] == 8
            assert values["patience"] == 1.2
            assert values["condition_on_previous_text"] is True
            assert "PROстранство" in str(values["initial_prompt"])
            assert "Nobus Space" in str(values["hotwords"])
            startup_events.append("voice_constructed")

        async def warmup(self) -> None:
            startup_events.append("voice_warmup")
            raise VoiceTranscriptionError("voice model unavailable")

    executable = tmp_path / "codex.exe"
    executable.touch()
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    api_instances: list[Api] = []
    control_constructed = False
    polling_constructed = False
    reported_stages: list[str] = []

    def api_factory(**values: object) -> Api:
        instance = Api(**values)
        api_instances.append(instance)
        return instance

    def forbidden_control(*args: object, **kwargs: object) -> object:
        nonlocal control_constructed
        control_constructed = True
        raise AssertionError("control must not be constructed after failed probe")

    def forbidden_polling(*args: object, **kwargs: object) -> object:
        nonlocal polling_constructed
        polling_constructed = True
        raise AssertionError("polling must not start after failed probe")

    monkeypatch.setattr(
        runner,
        "read_generic_credential",
        lambda target: SimpleNamespace(username="@Nobusspacebot", secret=Secret()),
    )
    monkeypatch.setattr(runner, "_required_codex_executable", lambda: executable)
    monkeypatch.setattr(runner, "_required_executable", lambda name: executable)
    monkeypatch.setattr(runner, "_validated_worktree", lambda: worktree)
    monkeypatch.setattr(runner, "NobusMemory", lambda path: object())
    monkeypatch.setattr(runner, "_CODEX_TEMP", tmp_path / "codex-temp")
    binding_path = tmp_path / "telegram-bindings.local.json"
    binding_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(runner, "_BINDING_PATH", binding_path)
    monkeypatch.setattr(
        runner,
        "TelegramBindingConfig",
        SimpleNamespace(
            model_validate=lambda value: SimpleNamespace(
                bindings=(SimpleNamespace(purpose="owner_private"),)
            )
        ),
    )
    monkeypatch.setattr(runner, "TelegramBotApi", api_factory)
    monkeypatch.setattr(runner.httpx, "AsyncHTTPTransport", lambda **values: object())
    monkeypatch.setattr(
        runner,
        "load_telegram_bindings",
        lambda *args, **kwargs: {(1, 1): object()},
    )
    monkeypatch.setattr(
        runner, "SQLitePollingCheckpointStore", lambda *args, **kwargs: object()
    )
    telegram_state = object()
    monkeypatch.setattr(
        runner, "SQLiteTelegramState", lambda *args, **kwargs: telegram_state
    )
    monkeypatch.setattr(
        runner,
        "DurableTelegramActionStore",
        lambda value: object() if value is telegram_state else None,
    )
    monkeypatch.setattr(runner, "InMemoryTelegramActionStore", lambda: object())
    monkeypatch.setattr(runner, "PollingCheckpointUpdateIdStore", lambda: object())
    monkeypatch.setattr(runner, "TelegramGateway", lambda **values: object())
    monkeypatch.setattr(
        runner,
        "_task_destinations",
        lambda bindings: ({"owner": "sha256:" + "d" * 64}, {}),
    )
    monkeypatch.setattr(
        runner, "build_gate5a4_runtime", lambda **values: Runtime()
    )
    monkeypatch.setattr(runner, "FasterWhisperTranscriber", Transcriber)
    monkeypatch.setattr(runner, "ProductTelegramControlPlane", forbidden_control)
    monkeypatch.setattr(runner, "TelegramPollingBoundary", forbidden_polling)

    expected = CodexCliError if failure_stage == "worker" else VoiceTranscriptionError
    with pytest.raises(expected) as caught:
        await runner._run(
            SimpleNamespace(
                bootstrap_next_offset=None,
                once=False,
                timeout=30,
                announce=True,
            ),
            report_stage=reported_stages.append,
        )

    if failure_stage == "worker":
        assert caught.value.code == "worker_timeout"
        assert startup_events == ["worker_probe"]
        assert reported_stages[-1] == "worker_probe"
    else:
        assert startup_events == [
            "worker_probe",
            "voice_constructed",
            "voice_warmup",
        ]
        assert reported_stages[-1] == "voice_warmup"
    assert not control_constructed
    assert not polling_constructed
    assert len(api_instances) == 1
    assert api_instances[0].closed

def test_runtime_layout_is_portable_and_defaults_to_current_root(
    tmp_path: Path,
) -> None:
    root = Path(tmp_path.anchor) / "portable" / "checkout"

    owner, orchestrator, live = runner._runtime_layout(root)

    assert owner == root
    assert orchestrator == root.parent
    assert live == root.parent / "Code" / "worktrees" / "telegram-live"


def test_runtime_layout_discovers_canonical_named_ancestors(
    tmp_path: Path,
) -> None:
    owner = tmp_path / "АГЕНТ"
    orchestrator = owner / "PROстранство" / "ОРКЕСТРАТОР"
    root = orchestrator / "Code" / "worktrees" / "telegram-live"
    root.mkdir(parents=True)

    discovered_owner, discovered_orchestrator, live = runner._runtime_layout(root)

    assert discovered_owner == owner
    assert discovered_orchestrator == orchestrator
    assert live == root
