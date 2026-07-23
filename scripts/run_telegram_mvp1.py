"""Run the owner-bound Telegram MVP-1 with a read-only Codex patch worker."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_telegram_control import (  # noqa: E402
    _BINDING_PATH,
    _CHECKPOINT_PATH,
    _CREDENTIAL_TARGET,
    _EXPECTED_USERNAME,
    _TASK_RUNTIME_PATH,
    _arguments,
    _bootstrap_checkpoint,
    _poll_once_and_announce,
    _poll_with_unavailable_backoff,
    _task_destinations,
)
from src.application.gate5a4 import build_gate5a4_runtime  # noqa: E402
from src.application.patch_confirmation import InMemoryPatchConfirmationStore  # noqa: E402
from src.application.task_confirmation import (  # noqa: E402
    MAX_TASK_INSTRUCTION_LENGTH,
    InMemoryTaskConfirmationStore,
)
from src.application.telegram_actions import InMemoryTelegramActionStore  # noqa: E402
from src.application.telegram_product import ProductTelegramControlPlane  # noqa: E402
from src.security.windows_credentials import (  # noqa: E402
    CredentialStoreError,
    read_generic_credential,
)
from src.transport.telegram import PollingCheckpointUpdateIdStore, TelegramGateway  # noqa: E402
from src.transport.telegram.bindings import (  # noqa: E402
    TelegramBindingError,
    load_telegram_bindings,
)
from src.transport.telegram.bot_api import (  # noqa: E402
    TelegramBotApi,
    TelegramBotApiError,
    TelegramPollingBoundary,
    TelegramStatusSender,
)
from src.transport.telegram.sqlite_checkpoint import (  # noqa: E402
    SQLitePollingCheckpointError,
    SQLitePollingCheckpointStore,
)
from src.voice import FasterWhisperTranscriber, VoicePreviewService  # noqa: E402


_WORKTREE = ROOT.parent / "worktrees" / "telegram-live"
_RUNTIME_ROOT = ROOT / ".runtime"
_CODEX_TEMP = _WORKTREE / ".runtime" / "codex-tmp"
_VOICE_MODEL_ROOT = _RUNTIME_ROOT / "voice-models"
_VOICE_TEMP_ROOT = _RUNTIME_ROOT / "voice-temp"
_POLLING_LEASE_SECONDS = 240


async def _run(values: argparse.Namespace) -> dict[str, object]:
    credential = read_generic_credential(_CREDENTIAL_TARGET)
    if credential.username.casefold() != f"@{_EXPECTED_USERNAME}".casefold():
        raise CredentialStoreError("credential_unavailable")
    executable = _required_codex_executable()
    git = _required_executable("git")
    python = (ROOT / ".venv" / "Scripts" / "python.exe").resolve(strict=True)
    worktree = _validated_worktree()
    _CODEX_TEMP.mkdir(parents=True, exist_ok=True)
    system_root = Path(os.environ["SYSTEMROOT"]).resolve(strict=True)

    api = TelegramBotApi(
        token=credential.secret.get_secret_value(),
        transport=httpx.AsyncHTTPTransport(retries=0, trust_env=False),
        request_timeout=60,
    )
    try:
        identity = await api.get_me()
        if identity.username.casefold() != _EXPECTED_USERNAME.casefold():
            raise TelegramBotApiError("telegram_protocol_error")
        bindings = load_telegram_bindings(
            _BINDING_PATH,
            expected_bot_id=identity.bot_id,
            expected_bot_username=identity.username,
            expected_tenant_id="owner",
            expected_actor_identity="telegram:owner",
            expected_role="owner",
        )
        checkpoint = SQLitePollingCheckpointStore(
            _CHECKPOINT_PATH,
            consumer_id="nobusspacebot-owner",
            lease_duration_seconds=_POLLING_LEASE_SECONDS,
        )
        if values.bootstrap_next_offset is not None:
            _bootstrap_checkpoint(checkpoint, values.bootstrap_next_offset)
        action_store = InMemoryTelegramActionStore()
        gateway = TelegramGateway(
            actor_bindings=bindings,
            update_id_store=PollingCheckpointUpdateIdStore(),
            callback_token_store=action_store,
        )
        destination_refs, sender_destinations = _task_destinations(bindings)
        runtime = build_gate5a4_runtime(
            gateway=gateway,
            sqlite_path=_TASK_RUNTIME_PATH,
            destination_refs=destination_refs,
            worktree=worktree,
            codex_executable=executable,
            git_executable=git,
            python_executable=python,
            codex_home=Path.home() / ".codex",
            system_root=system_root,
            temp_root=_CODEX_TEMP,
            path_entries=(
                system_root / "System32",
                system_root / "System32" / "WindowsPowerShell" / "v1.0",
                executable.parent,
                git.parent,
            ),
        )
        await runtime.probe_worker()
        voice_transcriber = FasterWhisperTranscriber(
            model_size="base",
            device="cpu",
            compute_type="int8",
            download_root=_VOICE_MODEL_ROOT,
            local_files_only=True,
        )
        await voice_transcriber.warmup()
        control = ProductTelegramControlPlane(
            gateway,
            api,
            task_runtime=runtime,
            task_confirmations=InMemoryTaskConfirmationStore(),
            patch_confirmations=InMemoryPatchConfirmationStore(),
            action_store=action_store,
            voice_service=VoicePreviewService(
                voice_transcriber,
                temp_root=_VOICE_TEMP_ROOT,
                max_bytes=10 * 1024 * 1024,
                max_transcript_length=MAX_TASK_INSTRUCTION_LENGTH,
            ),
            task_tenants=destination_refs,
            task_status_sender=TelegramStatusSender(
                api, sender_destinations, technical_details=False
            ),
        )
        polling = TelegramPollingBoundary(api, control.handle, checkpoint)
        if values.once:
            acknowledged = await _poll_once_and_announce(
                polling, api, bindings, control=control,
                timeout=values.timeout, announce=values.announce,
            )
        else:
            acknowledged = await _poll_with_unavailable_backoff(
                polling, api, bindings, control=control,
                timeout=values.timeout, announce=values.announce,
            )
            while True:
                acknowledged += await _poll_with_unavailable_backoff(
                    polling, api, bindings, control=control,
                    timeout=values.timeout, announce=False,
                )
        return {
            "status": "PASS",
            "mode": "once" if values.once else "serve",
            "announced": bool(values.announce),
            "acknowledged": acknowledged,
        }
    finally:
        await api.aclose()


def _extension_version(executable: Path) -> tuple[int, ...]:
    match = re.fullmatch(
        r"openai\.chatgpt-(.+)-win32-x64",
        executable.parents[2].name,
    )
    return tuple(int(value) for value in re.findall(r"\d+", match.group(1))) if match else ()

def _required_codex_executable(home: Path | None = None) -> Path:
    """Select an installed CLI that can actually start, preferring VS Code bundles."""
    candidates: list[Path] = []
    extension_root = (home or Path.home()) / ".vscode" / "extensions"
    try:
        candidates.extend(
            sorted(
                extension_root.glob(
                    "openai.chatgpt-*-win32-x64/bin/windows-x86_64/codex.exe"
                ),
                key=_extension_version,
                reverse=True,
            )
        )
    except OSError:
        pass
    discovered = shutil.which("codex.exe") or shutil.which("codex")
    if discovered is not None:
        candidates.append(Path(discovered))

    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
            key = str(resolved).casefold()
            if key in seen or not resolved.is_file():
                continue
            seen.add(key)
            options: dict[str, object] = {
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "timeout": 10,
                "check": False,
                "shell": False,
                "env": {
                    "PATH": os.environ.get("PATH", ""),
                    "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
                },
            }
            if os.name == "nt":
                options["creationflags"] = subprocess.CREATE_NO_WINDOW
            result = subprocess.run((str(resolved), "--version"), **options)
            if (
                result.returncode == 0
                and isinstance(result.stdout, bytes)
                and b"codex-cli" in result.stdout.lower()
                and len(result.stdout) <= 4096
                and len(result.stderr) <= 4096
            ):
                return resolved
        except (OSError, RuntimeError, subprocess.SubprocessError):
            continue
    raise RuntimeError("working Codex CLI is unavailable")


def _required_executable(name: str) -> Path:
    value = shutil.which(name)
    if value is None:
        raise RuntimeError("required executable is unavailable")
    return Path(value).resolve(strict=True)


def _validated_worktree() -> Path:
    root = _WORKTREE.resolve(strict=True)
    if not root.is_dir() or root == ROOT:
        raise RuntimeError("isolated worktree is unavailable")
    return root


def main() -> int:
    result: dict[str, object] | None = None
    failure = ""
    try:
        result = asyncio.run(_run(_arguments()))
    except KeyboardInterrupt:
        result = {"status": "STOPPED"}
    except CredentialStoreError as error:
        failure = error.code
    except TelegramBindingError as error:
        failure = error.code
    except TelegramBotApiError as error:
        failure = error.code
    except SQLitePollingCheckpointError:
        failure = "telegram_checkpoint_failed"
    except Exception:
        failure = "telegram_mvp1_failed"
    if result is None:
        result = {"status": "FAIL", "code": failure or "telegram_mvp1_failed"}
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return 0 if result["status"] in {"PASS", "STOPPED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
