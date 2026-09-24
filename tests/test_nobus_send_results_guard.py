from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from ops.windows.nobus_send_results_guard import (
    DeliveryOwnerGuardError,
    assert_skill_delivery_allowed,
)
from src.application.desktop_bridge_state import BridgeRequestStatus, SQLiteDesktopBridgeState

OLD_SENDER_SHA = "595f4db569519d1bb545b16320dbf8aabee3277d46263fe3f0d3efa04476a4df"
NEW_SENDER_SHA = "d38d9809dda89a088eb9e4415f4a834bb47d58cc804b14fa2fa9cc523c9d9f2e"


_GUARD_PRELUDE = (
    "    if args.send:\n"
    "        try:\n"
    "            from nobus_send_results_guard import (\n"
    "                DeliveryOwnerGuardError,\n"
    "                assert_skill_delivery_allowed,\n"
    "            )\n"
    "            assert_skill_delivery_allowed(\n"
    "                settings_path=Path.home() / \".codex\" / \"nobus-task-notifier.json\",\n"
    "                codex_thread_id=os.environ.get(\"CODEX_THREAD_ID\"),\n"
    "            )\n"
    "        except ImportError:\n"
    "            fail(\"bridge_owner_guard_unavailable\")\n"
    "        except DeliveryOwnerGuardError as error:\n"
    "            fail(str(error))\n"
)


def _old_sender_bytes(source: Path) -> bytes:
    installed = source.read_bytes()
    digest = hashlib.sha256(installed).hexdigest()
    if digest == OLD_SENDER_SHA:
        return installed
    assert digest == NEW_SENDER_SHA, "Installed skill drifted beyond the approved pair"
    normalized = installed.replace(b"\r\n", b"\n").decode("utf-8")
    assert normalized.count(_GUARD_PRELUDE) == 1
    assert normalized.count("import json\nimport os\nimport re\n") == 1
    original = normalized.replace(_GUARD_PRELUDE, "").replace(
        "import json\nimport os\nimport re\n", "import json\nimport re\n",
    ).encode("utf-8")
    assert hashlib.sha256(original).hexdigest() == OLD_SENDER_SHA
    return original


def _configured(tmp_path: Path) -> tuple[Path, Path]:
    state = tmp_path / "bridge.sqlite3"
    with closing(sqlite3.connect(state)) as connection:
        connection.execute(
            "CREATE TABLE desktop_bridge_requests "
            "(desktop_thread_id TEXT, status TEXT, operation TEXT, updated_at TEXT)"
        )
    settings = tmp_path / "notifier.json"
    settings.write_text(json.dumps({"bridge_state_path": str(state)}), encoding="utf-8")
    return settings, state


def test_active_bridge_turn_blocks_skill_but_unrelated_and_completed_tasks_work(tmp_path: Path) -> None:
    settings, state = _configured(tmp_path)
    bridge_thread, ordinary_thread = str(uuid4()), str(uuid4())
    with closing(sqlite3.connect(state)) as connection:
        connection.execute(
            "INSERT INTO desktop_bridge_requests VALUES (?,?,?,?)",
            (bridge_thread, "running", "continue", datetime.now(UTC).isoformat()),
        )
        connection.commit()
    with pytest.raises(DeliveryOwnerGuardError, match="bridge_delivery_owned"):
        assert_skill_delivery_allowed(settings_path=settings, codex_thread_id=bridge_thread)
    assert_skill_delivery_allowed(settings_path=settings, codex_thread_id=ordinary_thread)
    with closing(sqlite3.connect(state)) as connection:
        connection.execute(
            "UPDATE desktop_bridge_requests SET status='delivered' WHERE desktop_thread_id=?",
            (bridge_thread,),
        )
        connection.commit()
    assert_skill_delivery_allowed(settings_path=settings, codex_thread_id=bridge_thread)


def test_unbound_create_bootstrap_blocks_parallel_skill_send(tmp_path: Path) -> None:
    settings, state = _configured(tmp_path)
    with closing(sqlite3.connect(state)) as connection:
        connection.execute(
            "INSERT INTO desktop_bridge_requests VALUES (NULL,'dispatching','create',?)",
            (datetime.now(UTC).isoformat(),),
        )
        connection.commit()
    with pytest.raises(DeliveryOwnerGuardError, match="bridge_delivery_owned"):
        assert_skill_delivery_allowed(settings_path=settings, codex_thread_id=str(uuid4()))
    with closing(sqlite3.connect(state)) as connection:
        connection.execute("UPDATE desktop_bridge_requests SET updated_at=?", (
            (datetime.now(UTC) - timedelta(minutes=3)).isoformat(),
        ))
        connection.commit()
    assert_skill_delivery_allowed(settings_path=settings, codex_thread_id=str(uuid4()))


def test_configured_but_unreadable_bridge_state_fails_closed(tmp_path: Path) -> None:
    settings, state = _configured(tmp_path)
    state.unlink()
    with pytest.raises(DeliveryOwnerGuardError, match="bridge_owner_state_unavailable"):
        assert_skill_delivery_allowed(settings_path=settings, codex_thread_id=str(uuid4()))


def test_absent_bridge_configuration_keeps_legacy_skill_available(tmp_path: Path) -> None:
    assert_skill_delivery_allowed(
        settings_path=tmp_path / "missing.json", codex_thread_id=str(uuid4())
    )
    assert_skill_delivery_allowed(
        settings_path=tmp_path / "missing.json", codex_thread_id=None
    )


def test_configured_bridge_requires_verified_codex_thread_identity(tmp_path: Path) -> None:
    settings, _ = _configured(tmp_path)
    with pytest.raises(DeliveryOwnerGuardError, match="codex_thread_identity_missing"):
        assert_skill_delivery_allowed(settings_path=settings, codex_thread_id=None)


def test_guard_reads_real_bridge_state_schema_without_writer(tmp_path: Path) -> None:
    state = tmp_path / "telegram-state.sqlite3"
    bridge = SQLiteDesktopBridgeState(
        state, encode=lambda item: json.dumps(item).encode(),
        decode=lambda item: json.loads(item),
    )
    request_id, thread_id = uuid4(), str(uuid4())
    bridge.create_request(
        request_id=request_id, ingress_key="sha256:" + "a" * 64,
        tenant_id="owner", author_user_id=41,
        author_identity="telegram:member:41", chat_id=-1001, topic_id=7,
        source_message_id=12, operation="continue", project_name="project",
        payload={"instruction": "test"},
    )
    bridge.bind_desktop(
        request_id, thread_id=thread_id, turn_id="turn-1",
        client_message_id=f"nobus:{request_id}", status=BridgeRequestStatus.RUNNING,
    )
    settings = tmp_path / "notifier.json"
    settings.write_text(json.dumps({"bridge_state_path": str(state)}), encoding="utf-8")
    with pytest.raises(DeliveryOwnerGuardError, match="bridge_delivery_owned"):
        assert_skill_delivery_allowed(settings_path=settings, codex_thread_id=thread_id)


def test_patch_blocks_installed_skill_path_before_artifact_or_network_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = Path.home() / ".codex" / "skills" / "nobus-send-results" / "scripts"
    if not (source / "send_result.py").is_file():
        pytest.skip("The separate installed skill is unavailable")
    stage = tmp_path / "skill"
    scripts = stage / "scripts"
    scripts.mkdir(parents=True)
    for name in ("send_result.py", "telegram_delivery_runtime.py"):
        shutil.copyfile(source / name, scripts / name)
    repo_root = Path(__file__).parents[1]
    patch = repo_root / "docs/gates/mvp2/m2-desktop/send-results-bridge-owner.patch"
    digest = hashlib.sha256((scripts / "send_result.py").read_bytes()).hexdigest()
    if digest == OLD_SENDER_SHA:
        original = (scripts / "send_result.py").read_text(encoding="utf-8")
        assert original.count("import json\nimport re\n") == 1
        assert original.count("async def deliver(args: argparse.Namespace) -> None:\n") == 1
        patched = original.replace(
            "import json\nimport re\n", "import json\nimport os\nimport re\n",
        ).replace(
            "async def deliver(args: argparse.Namespace) -> None:\n",
            "async def deliver(args: argparse.Namespace) -> None:\n" + _GUARD_PRELUDE,
        )
        result = patched.replace("\n", "\r\n").encode("utf-8")
        assert hashlib.sha256(result).hexdigest() == NEW_SENDER_SHA
        (scripts / "send_result.py").write_bytes(result)
    else:
        assert digest == NEW_SENDER_SHA, "Installed skill drifted beyond the approved pair"
    shutil.copyfile(repo_root / "ops/windows/nobus_send_results_guard.py",
                    scripts / "nobus_send_results_guard.py")
    spec = importlib.util.spec_from_file_location("isolated_send_result", scripts / "send_result.py")
    assert spec is not None and spec.loader is not None
    sender = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sender)

    settings, state = _configured(tmp_path)
    thread_id = str(uuid4())
    with closing(sqlite3.connect(state)) as connection:
        connection.execute("INSERT INTO desktop_bridge_requests VALUES (?,?,?,?)", (
            thread_id, "running", "continue", datetime.now(UTC).isoformat(),
        ))
        connection.commit()
    config = tmp_path / ".codex"
    config.mkdir()
    shutil.copyfile(settings, config / "nobus-task-notifier.json")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("CODEX_THREAD_ID", thread_id)
    args = argparse.Namespace(send=True, file=str(tmp_path / "not-read.txt"),
                              project_root=str(tmp_path), destination="owner_private",
                              expect_sha256=None)
    with pytest.raises(sender.DeliveryError, match="bridge_delivery_owned"):
        asyncio.run(sender.deliver(args))


def test_installer_atomic_replace_on_fake_skill_home(tmp_path: Path) -> None:
    source = Path.home() / ".codex" / "skills" / "nobus-send-results" / "scripts" / "send_result.py"
    if not source.is_file():
        pytest.skip("The separate installed skill is unavailable")
    fake_home = tmp_path / "fake-home"
    target_dir = fake_home / ".codex/skills/nobus-send-results/scripts"
    target_dir.mkdir(parents=True)
    target = target_dir / "send_result.py"
    repo_root = Path(__file__).parents[1]
    installer = repo_root / "ops/windows/Install-NobusSendResultsGuard.ps1"
    patch = repo_root / "docs/gates/mvp2/m2-desktop/send-results-bridge-owner.patch"
    target.write_bytes(_old_sender_bytes(source))
    environment = os.environ.copy()
    environment["USERPROFILE"] = str(fake_home)
    command = [
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", str(installer), "-SourceRoot", str(repo_root),
    ]
    installed = subprocess.run(command, env=environment, capture_output=True,
                               text=True, encoding="utf-8", check=False)
    assert installed.returncode == 0, installed.stderr
    assert "INSTALLED backup=" in installed.stdout
    assert hashlib.sha256(target.read_bytes()).hexdigest() == (
        "d38d9809dda89a088eb9e4415f4a834bb47d58cc804b14fa2fa9cc523c9d9f2e"
    )
    assert hashlib.sha256((target_dir / "nobus_send_results_guard.py").read_bytes()).hexdigest() == (
        "e20cd35d1d09fc5c90ee91fe37bf80b4057de86ab4bb9e117d2ae0f0e6e6fe20"
    )
    repeated = subprocess.run(command, env=environment, capture_output=True,
                              text=True, encoding="utf-8", check=False)
    assert repeated.returncode == 0
    assert "ALREADY_INSTALLED" in repeated.stdout
