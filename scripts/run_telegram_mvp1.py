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
from codex_cli_bin import bundled_codex_path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.bind_business_notes import (  # noqa: E402
    _atomic_write as _write_binding_config,
    _candidate as _business_notes_candidate,
    _v2_config as _business_notes_v2_config,
)
from scripts.run_telegram_control import (  # noqa: E402
    _BINDING_PATH,
    _CREDENTIAL_TARGET,
    _EXPECTED_USERNAME,
    _arguments,
    _bootstrap_checkpoint,
    _poll_once_and_announce,
    _poll_with_unavailable_backoff,
    _task_destinations,
)
from src.application.gate5a4 import (  # noqa: E402
    GATE5A4_EXECUTION_CONCURRENCY,
    build_gate5a4_runtime,
)
from src.application.business_notes import (
    BusinessNotesService,
    SQLiteBusinessNotes,
)
from src.application.durable_confirmations import (  # noqa: E402
    DurablePatchConfirmationStore,
    DurableTaskConfirmationStore,
    DurableTelegramActionStore,
)
from src.application.durable_product import DurableProductTelegramControlPlane  # noqa: E402
from src.application.durable_telegram_state import SQLiteTelegramState  # noqa: E402
from src.application.nobus_memory import NobusMemory  # noqa: E402
from src.application.owner_files import OwnerFileService  # noqa: E402
from src.application.runtime_maintenance import (  # noqa: E402
    recover_interrupted_restore,
)
from src.application.owner_workspace import EdgePdfRenderer, OwnerWorkspace  # noqa: E402
from src.application.network_commands import NetworkCommandRunner  # noqa: E402
from src.application.network_tools import Quarantine, SafeDownloader  # noqa: E402
from src.application.product_effects import (  # noqa: E402
    DurableProductEffectVault,
    ProductEffectService,
)
from src.application.task_confirmation import (  # noqa: E402
    MAX_TASK_INSTRUCTION_LENGTH,
    InMemoryTaskConfirmationStore,
)
from src.application.patch_confirmation import InMemoryPatchConfirmationStore  # noqa: E402
from src.application.telegram_actions import InMemoryTelegramActionStore  # noqa: E402
from src.application.telegram_product import ProductTelegramControlPlane  # noqa: E402
from src.application.windows_singleton import (  # noqa: E402
    RunnerAlreadyActive,
    WindowsNamedMutex,
)
from src.security.windows_credentials import (  # noqa: E402
    CredentialStoreError,
    read_generic_credential,
)
from src.transport.telegram import PollingCheckpointUpdateIdStore, TelegramGateway  # noqa: E402
from src.transport.telegram.bindings import (  # noqa: E402
    TelegramBindingConfig,
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
from src.integrations import (  # noqa: E402
    GoogleCalendarClient,
    GoogleDriveClient,
    GoogleTasksClient,
)
from src.voice import FasterWhisperTranscriber, VoicePreviewService  # noqa: E402
from src.workers.codex_limits import build_codex_rate_limit_client  # noqa: E402


def _named_ancestor(start: Path, name: str) -> Path | None:
    expected = name.casefold()
    for candidate in (start, *start.parents):
        if candidate.name.casefold() == expected:
            return candidate
    return None


def _runtime_layout(root: Path) -> tuple[Path, Path, Path]:
    owner_root = _named_ancestor(root, "АГЕНТ") or root
    orchestrator_root = _named_ancestor(root, "ОРКЕСТРАТОР") or root.parent
    live_worktree = (
        root
        if root.parent.name.casefold() == "worktrees"
        else orchestrator_root / "Code" / "worktrees" / "telegram-live"
    )
    return owner_root, orchestrator_root, live_worktree


_OWNER_READ_ROOT, _ORCHESTRATOR_ROOT, _WORKTREE = _runtime_layout(ROOT)
_RUNTIME_ROOT = ROOT / ".runtime"
_CODEX_TEMP = _WORKTREE / ".runtime" / "codex-tmp"
_VOICE_MODEL_ROOT = _RUNTIME_ROOT / "voice-models"
_VOICE_TEMP_ROOT = _RUNTIME_ROOT / "voice-temp"
_VOICE_INITIAL_PROMPT = (
    "Нобус Спейс — личный оркестратор. Компания называется PROстранство, "
    "про пространство. Маркетплейсы Wildberries и Ozon. Используются Codex, "
    "Telegram, Google Drive, Google Calendar и Google Tasks. "
    "Термины: MCP, idempotency key, L1, L2, L3, L4, субагент, Nobus Memory."
)
_VOICE_HOTWORDS = (
    "Nobus Space Нобус Спейс PROстранство Codex Telegram Wildberries Ozon "
    "Google Drive Google Calendar Google Tasks MCP idempotency оркестратор "
    "субагент Nobus Memory Нобус память"
)
_POLLING_LEASE_SECONDS = 240
_CHECKPOINT_PATH = _RUNTIME_ROOT / "telegram-checkpoint.sqlite3"
_TASK_RUNTIME_PATH = _RUNTIME_ROOT / "task-runtime.sqlite3"
_TELEGRAM_STATE_PATH = _RUNTIME_ROOT / "telegram-state.sqlite3"
_BUSINESS_NOTES_PATH = _RUNTIME_ROOT / "business-notes.sqlite3"
_PROJECT_CONTEXT_PATH = ROOT / "docs" / "11-Контекст-продукта.md"
_NOBUS_MEMORY_ROOT = _OWNER_READ_ROOT / "Nobus memory"
_ARTIFACT_SNAPSHOT_ROOT = _RUNTIME_ROOT / "artifact-snapshots"
_OWNER_WRITE_ROOT = _ORCHESTRATOR_ROOT / "NOBUS SPACE BOT"
_QUARANTINE_ROOT = _OWNER_WRITE_ROOT / "Загрузки"
_GOOGLE_CALENDAR_TOKEN = (
    _ORCHESTRATOR_ROOT / "Интеграции/google_api_integration/token.json"
)



def _load_project_context() -> str:
    try:
        content = _PROJECT_CONTEXT_PATH.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        raise RuntimeError("project context is unavailable") from None
    if not content or len(content) > 16_000 or "\x00" in content:
        raise RuntimeError("project context is invalid")
    return content


async def _run(values: argparse.Namespace) -> dict[str, object]:
    credential = read_generic_credential(_CREDENTIAL_TARGET)
    if credential.username.casefold() != f"@{_EXPECTED_USERNAME}".casefold():
        raise CredentialStoreError("credential_unavailable")
    executable = _required_codex_executable()
    git = _required_executable("git")
    python = (ROOT / ".venv" / "Scripts" / "python.exe").resolve(strict=True)
    worktree = _validated_worktree()
    _CODEX_TEMP.mkdir(parents=True, exist_ok=True)
    _ARTIFACT_SNAPSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    system_root = Path(os.environ["SYSTEMROOT"]).resolve(strict=True)
    nobus_memory = NobusMemory(_NOBUS_MEMORY_ROOT)

    control: ProductTelegramControlPlane | None = None
    product_effects: ProductEffectService | None = None
    runtime = None
    api = TelegramBotApi(
        token=credential.secret.get_secret_value(),
        transport=httpx.AsyncHTTPTransport(retries=0, trust_env=False),
        request_timeout=60,
    )
    try:
        identity = await api.get_me()
        if identity.username.casefold() != _EXPECTED_USERNAME.casefold():
            raise TelegramBotApiError("telegram_protocol_error")
        binding_config = TelegramBindingConfig.model_validate(
            json.loads(_BINDING_PATH.read_text(encoding="utf-8"))
        )
        owner_binding = next(
            item
            for item in binding_config.bindings
            if item.purpose == "owner_private"
        )
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
        telegram_state = SQLiteTelegramState(_TELEGRAM_STATE_PATH)
        action_store = DurableTelegramActionStore(telegram_state)
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
            owner_read_root=_OWNER_READ_ROOT,
            project_context=_load_project_context(),
            nobus_memory=nobus_memory,
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
            language="ru",
            beam_size=8,
            patience=1.2,
            vad_filter=True,
            condition_on_previous_text=True,
            initial_prompt=_VOICE_INITIAL_PROMPT,
            hotwords=_VOICE_HOTWORDS,
        )
        await voice_transcriber.warmup()
        limit_provider = build_codex_rate_limit_client(
            workspace_root=worktree,
            executable=executable,
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
        calendar = GoogleCalendarClient(_GOOGLE_CALENDAR_TOKEN)
        google_tasks = GoogleTasksClient(_GOOGLE_CALENDAR_TOKEN)
        google_drive = GoogleDriveClient(_GOOGLE_CALENDAR_TOKEN)
        product_effects = ProductEffectService(
            vault=DurableProductEffectVault(telegram_state),
            workspace=OwnerWorkspace(
                _OWNER_WRITE_ROOT,
                snapshot_root=_ARTIFACT_SNAPSHOT_ROOT,
                pdf_renderer=EdgePdfRenderer(
                    _required_edge_executable(),
                    temp_root=_CODEX_TEMP,
                ),
            ),
            downloader=SafeDownloader(),
            quarantine=Quarantine(_QUARANTINE_ROOT),
            network_runner=NetworkCommandRunner(
                workspace_root=_OWNER_READ_ROOT,
                git_executable=git,
                python_executable=python,
            ),
            calendar=calendar,
            google_tasks=google_tasks,
            google_drive=google_drive,
        )
        control = DurableProductTelegramControlPlane(
            gateway,
            api,
            task_runtime=runtime,
            task_confirmations=DurableTaskConfirmationStore(telegram_state),
            patch_confirmations=DurablePatchConfirmationStore(telegram_state),
            action_store=action_store,
            voice_service=VoicePreviewService(
                voice_transcriber,
                temp_root=_VOICE_TEMP_ROOT,
                max_bytes=10 * 1024 * 1024,
                max_transcript_length=MAX_TASK_INSTRUCTION_LENGTH,
            ),
            limit_provider=limit_provider,
            owner_files=OwnerFileService(_OWNER_READ_ROOT),
            product_effects=product_effects,
            calendar_planner=runtime,
            calendar_service=calendar,
            google_tasks_planner=runtime,
            google_tasks_service=google_tasks,
            google_drive_planner=runtime,
            google_drive_service=google_drive,
            business_notes=BusinessNotesService(
                SQLiteBusinessNotes(_BUSINESS_NOTES_PATH)
            ),
            nobus_memory=nobus_memory,
            execution_concurrency=GATE5A4_EXECUTION_CONCURRENCY,
            telegram_state=telegram_state,
            task_tenants=destination_refs,
            task_status_sender=TelegramStatusSender(
                api, sender_destinations, technical_details=False
            ),
        )
        await control.start()

        async def handle_with_binding(update: dict[str, object]) -> bool:
            nonlocal binding_config
            selected = _business_notes_candidate(
                [update], owner_user_id=owner_binding.user_id
            )
            if selected is None:
                return await control.handle(update)
            update_id, chat_id = selected
            existing = next(
                (
                    item
                    for item in binding_config.bindings
                    if item.purpose == "business_notes"
                ),
                None,
            )
            if existing is not None:
                if existing.chat_id == chat_id:
                    await api.send_message(
                        owner_binding.chat_id,
                        "✅ «Заметки бизнеса» уже подключены.",
                    )
                return True
            updated = _business_notes_v2_config(
                binding_config, update_id=update_id, chat_id=chat_id
            )
            _write_binding_config(_BINDING_PATH, updated)
            reloaded = load_telegram_bindings(
                _BINDING_PATH,
                expected_bot_id=updated.bot_id,
                expected_bot_username=updated.bot_username,
                expected_tenant_id=owner_binding.tenant_id,
                expected_actor_identity=owner_binding.actor_identity,
                expected_role=owner_binding.role,
            )
            gateway.replace_actor_bindings(reloaded)
            binding_config = updated
            await api.send_message(
                owner_binding.chat_id,
                "✅ «Заметки бизнеса» подключены. Новые сообщения и темы доступны Nobus.",
            )
            return True

        polling = TelegramPollingBoundary(api, handle_with_binding, checkpoint)
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
            control.assert_healthy()
            while True:
                acknowledged += await _poll_with_unavailable_backoff(
                    polling, api, bindings, control=control,
                    timeout=values.timeout, announce=False,
                )
                control.assert_healthy()
        control.assert_healthy()
        return {
            "status": "PASS",
            "mode": "once" if values.once else "serve",
            "announced": bool(values.announce),
            "acknowledged": acknowledged,
        }
    finally:
        try:
            if control is not None:
                await control.close()
            elif product_effects is not None:
                await product_effects.close()
        finally:
            try:
                if runtime is not None:
                    closer = getattr(runtime, "close", None)
                    if callable(closer):
                        await closer()
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
    candidates: list[Path] = (
        [bundled_codex_path()]
        if home is None
        else []
    )
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


def _required_edge_executable() -> Path:
    candidates = (
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    )
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
            if resolved.is_file():
                return resolved
        except OSError:
            continue
    raise RuntimeError("local PDF renderer is unavailable")


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
        with WindowsNamedMutex():
            recover_interrupted_restore(_RUNTIME_ROOT)
            result = asyncio.run(_run(_arguments()))
    except RunnerAlreadyActive:
        result = {"status": "ALREADY_RUNNING"}
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
    return 0 if result["status"] in {"PASS", "STOPPED", "ALREADY_RUNNING"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
