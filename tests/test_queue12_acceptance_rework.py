from __future__ import annotations

import json
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest

from scripts.check_telegram_health import check
from src.application.durable_telegram_state import SQLiteTelegramState
from src.application.network_commands import NetworkCommandRunner
from src.workers.asyncio_spawner import _ARGV_PROFILES
from src.workers.codex_cli import _WEB_ARGV


APPROVAL = "telegram-owner-confirmation:sha256:" + "a" * 64


def _codec():
    return (
        lambda value: json.dumps(value, sort_keys=True).encode(),
        lambda value: json.loads(value),
    )


def _network_runner(tmp_path: Path) -> tuple[NetworkCommandRunner, Path, Path]:
    root = tmp_path / "workspace"
    (root / ".git").mkdir(parents=True)
    config = root / ".git" / "config"
    config.write_text(
        '[remote "origin"]\n\turl = https://example.com/repo.git\n',
        encoding="utf-8",
    )
    requirements = root / "requirements.txt"
    requirements.write_text(
        "demo==1.0 --hash=sha256:" + "a" * 64 + "\n",
        encoding="utf-8",
    )
    git = tmp_path / "git.exe"
    python = tmp_path / "python.exe"
    git.touch()
    python.touch()
    return (
        NetworkCommandRunner(
            workspace_root=root,
            git_executable=git,
            python_executable=python,
        ),
        config,
        requirements,
    )


def test_web_profile_is_wired_to_asyncio_process_boundary() -> None:
    assert _WEB_ARGV in _ARGV_PROFILES


def test_configure_profile_requires_explicit_apply_without_external_call() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        (
            str(root / ".venv" / "Scripts" / "python.exe"),
            str(root / "scripts" / "configure_telegram_profile.py"),
        ),
        cwd=root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=15,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert result.returncode == 2
    assert b"--apply" in result.stderr


def test_network_git_binds_exact_https_destination_and_disables_rewrites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner, config, _ = _network_runner(tmp_path)
    proposal = runner.propose_git_fetch(
        repository_directory=".", remote="origin", revision="main"
    )
    assert proposal.destination == "https://example.com/repo.git"
    assert proposal.argv[-2:] == ("https://example.com/repo.git", "main")
    captured: dict[str, object] = {}

    def fake_run(argv, **options):
        captured["argv"] = argv
        captured["env"] = options["env"]
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner.run(proposal, approval_ref=APPROVAL)
    assert captured["argv"][-2:] == (
        "https://example.com/repo.git",
        "main",
    )
    assert captured["env"]["GIT_CONFIG_NOSYSTEM"] == "1"
    assert captured["env"]["GIT_CONFIG_GLOBAL"]

    config.write_text(
        '[include]\n\tpath = ../outside\n'
        '[remote "origin"]\n\turl = https://example.com/repo.git\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="forbidden settings"):
        runner.propose_git_fetch(
            repository_directory=".", remote="origin", revision="main"
        )


@pytest.mark.parametrize(
    "content",
    [
        "-r nested.txt\n",
        "--constraint constraints.txt\n",
        "-e .\n",
        "demo @ https://example.com/demo.whl\n",
        "./local.whl\n",
        "demo==1.0\n",
        "demo==1.0 --hash=sha256:" + "a" * 64 + " \\\n"
        " --hash=sha256:" + "b" * 64,
    ],
)
def test_pip_rejects_nested_mutable_or_local_inputs(
    tmp_path: Path, content: str
) -> None:
    runner, _, requirements = _network_runner(tmp_path)
    requirements.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="nested or mutable"):
        runner.propose_pip_install(
            repository_directory=".",
            requirement_file="requirements.txt",
        )


def test_legacy_job_schema_migrates_and_effect_can_be_enqueued(
    tmp_path: Path,
) -> None:
    database = tmp_path / "telegram-state.sqlite3"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            """CREATE TABLE telegram_jobs (
                job_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL CHECK(kind IN ('draft','patch')),
                tenant_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                binding_digest TEXT NOT NULL,
                payload_digest TEXT NOT NULL,
                payload BLOB NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','leased')),
                attempt_count INTEGER NOT NULL,
                lease_id TEXT,
                lease_owner TEXT,
                lease_expires_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(tenant_id,task_id,kind)
            )"""
        )
    encode, decode = _codec()
    state = SQLiteTelegramState(database, encode=encode, decode=decode)
    task_id = uuid4()
    state.enqueue(
        kind="effect",
        tenant_id="owner",
        task_id=task_id,
        binding_digest="sha256:" + "a" * 64,
        payload={"task": str(task_id)},
    )
    with closing(sqlite3.connect(database)) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(telegram_jobs)")
        }
        sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='telegram_jobs'"
        ).fetchone()[0]
    assert "failure_code" in columns
    assert "'effect'" in sql
    assert "'failed'" in sql


def test_poison_job_moves_to_dead_letter_and_does_not_block_fifo(
    tmp_path: Path,
) -> None:
    encode, decode = _codec()
    state = SQLiteTelegramState(
        tmp_path / "telegram-state.sqlite3",
        encode=encode,
        decode=decode,
    )
    first_id, second_id = uuid4(), uuid4()
    for task_id in (first_id, second_id):
        state.enqueue(
            kind="draft",
            tenant_id="owner",
            task_id=task_id,
            binding_digest="sha256:" + task_id.hex.ljust(64, "0"),
            payload={"task": str(task_id)},
        )
    owner = uuid4()
    first = state.claim(lease_owner=owner)
    assert first is not None and first.task_id == first_id
    state.fail(first, lease_owner=owner, failure_code="runtime_job_failed")
    second = state.claim(lease_owner=owner)
    assert second is not None and second.task_id == second_id
    assert state.dead_letter_count() == 1


def test_health_rejects_known_database_with_unrelated_schema(tmp_path: Path) -> None:
    checkpoint = tmp_path / "telegram-checkpoint.sqlite3"
    database = tmp_path / "task-runtime.sqlite3"
    telegram_state = tmp_path / "telegram-state.sqlite3"
    business_notes = tmp_path / "business-notes.sqlite3"
    from src.application.business_notes import SQLiteBusinessNotes
    from src.storage.sqlite_store import SQLiteStore
    from src.transport.telegram.sqlite_checkpoint import (
        SQLitePollingCheckpointStore,
    )

    SQLitePollingCheckpointStore(checkpoint, consumer_id="nobus-space-bot")
    SQLiteStore(database)
    SQLiteTelegramState(telegram_state)
    SQLiteBusinessNotes(business_notes)
    database.unlink()
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("CREATE TABLE marker(value INTEGER)")
    result = check((checkpoint, database, telegram_state, business_notes))
    assert result["status"] == "FAIL"
    assert result["databases"][database.name] == "unavailable"


def test_git_fetch_url_rejects_query_and_fragment(
    tmp_path: Path,
) -> None:
    runner, config, _ = _network_runner(tmp_path)
    for url in (
        "https://example.com/repo.git?token=secret",
        "https://example.com/repo.git#branch",
    ):
        config.write_text(
            f'[remote "origin"]\n\turl = {url}\n',
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="git remote URL is not approved"):
            runner.propose_git_fetch(
                repository_directory=".",
                remote="origin",
                revision="main",
            )


@pytest.mark.skipif(__import__("os").name != "nt", reason="Windows DPAPI")
def test_real_runtime_schema_backup_restore_roundtrip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import restore_telegram_runtime
    from scripts.backup_telegram_runtime import backup
    from scripts.check_telegram_health import check
    from src.application.business_notes import SQLiteBusinessNotes
    from src.storage.sqlite_store import SQLiteStore
    from src.transport.telegram import TextMessage
    from src.transport.telegram.sqlite_checkpoint import (
        SQLitePollingCheckpointStore,
    )

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    checkpoint = runtime / "telegram-checkpoint.sqlite3"
    task_runtime = runtime / "task-runtime.sqlite3"
    telegram_state = runtime / "telegram-state.sqlite3"
    business_notes = runtime / "business-notes.sqlite3"
    SQLitePollingCheckpointStore(checkpoint, consumer_id="nobus-space-bot")
    SQLiteStore(task_runtime)
    SQLiteTelegramState(telegram_state)
    notes_store = SQLiteBusinessNotes(business_notes)
    notes_store.append(
        TextMessage(
            update_id=1,
            tenant_id="synthetic-test",
            actor_identity="telegram:test",
            actor_role="owner",
            auth_context_ref="sha256:" + "b" * 64,
            user_id=1,
            chat_id=-1001,
            message_thread_id=7,
            binding_purpose="business_notes",
            message_id=1,
            text="Synthetic restore marker.",
        )
    )

    manifest = backup(
        (checkpoint, task_runtime, telegram_state, business_notes),
        tmp_path / "backup",
    )
    for database in (
        checkpoint,
        task_runtime,
        telegram_state,
        business_notes,
    ):
        database.unlink()
    monkeypatch.setattr(restore_telegram_runtime, "RUNTIME", runtime)
    restore_telegram_runtime.restore(manifest, approval_ref=APPROVAL)
    assert check(
        (checkpoint, task_runtime, telegram_state, business_notes)
    )["status"] == "PASS"
    restored = SQLiteBusinessNotes(business_notes).recent(
        tenant_id="synthetic-test",
        chat_id=-1001,
        thread_id=7,
    )
    assert [note.text for note in restored] == ["Synthetic restore marker."]


def test_network_rejects_credential_proxy_and_header_config(
    tmp_path: Path,
) -> None:
    for forbidden in (
        "[credential]\n\thelper = !calc.exe\n",
        "[http]\n\tproxy = https://proxy.example\n",
        '[http "https://example.com"]\n\textraHeader = Authorization: secret\n',
        "[core]\n\tsshCommand = helper.exe\n",
        "[extensions]\n\tworktreeConfig = true\n",
    ):
        runner, config, _ = _network_runner(tmp_path / str(abs(hash(forbidden))))
        config.write_text(
            forbidden
            + '[remote "origin"]\n\turl = https://example.com/repo.git\n',
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="forbidden settings"):
            runner.propose_git_fetch(
                repository_directory=".",
                remote="origin",
                revision="main",
            )


def test_pip_isolated_config_is_exactly_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, _, _ = _network_runner(tmp_path)
    proposal = runner.propose_pip_install(
        repository_directory=".",
        requirement_file="requirements.txt",
    )
    assert proposal.argv[:4] == ("-m", "pip", "--isolated", "install")
    assert proposal.destination == "https://pypi.org/simple"
    assert proposal.argv[proposal.argv.index("--index-url") + 1] == proposal.destination
    captured: dict[str, object] = {}

    def fake_run(argv, **options):
        captured["argv"] = argv
        captured["env"] = options["env"]
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner.run(proposal, approval_ref=APPROVAL)
    assert captured["env"]["PIP_CONFIG_FILE"] == __import__("os").devnull
    assert captured["env"]["PYTHONNOUSERSITE"] == "1"
