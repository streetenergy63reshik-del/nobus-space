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
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import uvicorn
from codex_cli_bin import bundled_codex_path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
from src.application.durable_confirmations import (  # noqa: E402
    DurablePatchConfirmationStore,
    DurableTaskConfirmationStore,
    DurableTelegramActionStore,
)
from src.application.durable_product import DurableProductTelegramControlPlane  # noqa: E402
from src.application.durable_telegram_state import SQLiteTelegramState  # noqa: E402
from src.application.miniapp import MiniAppCore, MiniAppTaskAdmission  # noqa: E402
from src.application.nobus_memory import NobusMemory  # noqa: E402
from src.application.runtime_maintenance import (  # noqa: E402
    recover_interrupted_restore,
)
from src.application.task_confirmation import (  # noqa: E402
    MAX_TASK_INSTRUCTION_LENGTH,
)
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
from src.transport.miniapp import create_miniapp_app  # noqa: E402
from src.storage import SQLiteStore  # noqa: E402
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
    "Telegram и Nobus Space. "
    "Термины: MCP, idempotency key, L1, L2, L3, L4 и субагент."
)
_VOICE_HOTWORDS = (
    "Nobus Space Нобус Спейс PROстранство Codex Telegram Wildberries Ozon "
    "MCP idempotency оркестратор субагент"
)
_POLLING_LEASE_SECONDS = 240
_CHECKPOINT_PATH = _RUNTIME_ROOT / "telegram-checkpoint.sqlite3"
_TASK_RUNTIME_PATH = _RUNTIME_ROOT / "task-runtime.sqlite3"
_TELEGRAM_STATE_PATH = _RUNTIME_ROOT / "telegram-state.sqlite3"
_PROJECT_CONTEXT_PATH = ROOT / "docs" / "11-Контекст-продукта.md"
_NOBUS_MEMORY_ROOT = _OWNER_READ_ROOT / "Nobus memory"
_RUN_STAGES = frozenset(
    {
        "credentials",
        "local_preflight",
        "telegram_identity",
        "bindings",
        "runtime_stores",
        "core_runtime",
        "worker_probe",
        "voice_warmup",
        "rate_limit_provider",
        "control_construction",
        "control_start",
        "miniapp_core",
        "miniapp_server",
        "polling",
    }
)



class _MiniAppServer:
    def __init__(self, app: object, *, host: str, port: int) -> None:
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="warning",
            access_log=False,
            server_header=False,
        )
        self._server = uvicorn.Server(config)
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("miniapp server lifecycle is invalid")
        self._task = asyncio.create_task(
            self._server.serve(), name="nobus-miniapp-server"
        )
        try:
            async with asyncio.timeout(15):
                while not self._server.started:
                    if self._task.done():
                        await self._task
                        raise RuntimeError("miniapp server failed to start")
                    await asyncio.sleep(0.01)
        except TimeoutError:
            await self.close()
            raise RuntimeError("miniapp server failed to start") from None

    def assert_healthy(self) -> None:
        task = self._task
        if task is None or task.done():
            error = None
            if task is not None and not task.cancelled():
                error = task.exception()
            raise RuntimeError("miniapp server stopped") from error

    async def close(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        self._server.should_exit = True
        try:
            async with asyncio.timeout(15):
                await task
        except TimeoutError:
            self._server.force_exit = True
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise RuntimeError("miniapp server failed to stop") from None


def _miniapp_endpoint(values: argparse.Namespace) -> tuple[str, int, str, str]:
    bind = getattr(values, "miniapp_bind", "127.0.0.1")
    port = getattr(values, "miniapp_port", 8765)
    origin = getattr(values, "miniapp_origin", None) or f"http://127.0.0.1:{port}"
    host = urlsplit(origin).hostname or ""
    if bind != "127.0.0.1" or type(port) is not int or not 1024 <= port <= 65535:
        raise RuntimeError("miniapp endpoint is invalid")
    if not host:
        raise RuntimeError("miniapp endpoint is invalid")
    return bind, port, origin, host


def _create_miniapp_server(
    *,
    store: SQLiteStore,
    task_admission: MiniAppTaskAdmission,
    bot_token: str,
    owner_user_id: int,
    tenant_id: str,
    values: argparse.Namespace,
) -> _MiniAppServer:
    core = MiniAppCore(
        store=store,
        task_admission=task_admission,
        bot_token=bot_token,
        owner_user_id=owner_user_id,
        tenant_id=tenant_id,
    )
    bind, port, origin, host = _miniapp_endpoint(values)

    def readiness() -> None:
        task_admission.assert_healthy()
        store.list_tasks(tenant_id, limit=1)

    app = create_miniapp_app(
        core,
        allowed_host=host,
        allowed_origin=origin,
        readiness=readiness,
    )
    return _MiniAppServer(app, host=bind, port=port)


def _assert_product_healthy(
    control: ProductTelegramControlPlane,
    miniapp_server: _MiniAppServer | None,
) -> None:
    control.assert_healthy()
    if miniapp_server is not None:
        miniapp_server.assert_healthy()


def _load_project_context() -> str:
    try:
        content = _PROJECT_CONTEXT_PATH.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        raise RuntimeError("project context is unavailable") from None
    if not content or len(content) > 16_000 or "\x00" in content:
        raise RuntimeError("project context is invalid")
    return content


async def _run(
    values: argparse.Namespace,
    *,
    report_stage: Callable[[str], None] = lambda stage: None,
) -> dict[str, object]:
    report_stage("credentials")
    credential = read_generic_credential(_CREDENTIAL_TARGET)
    if credential.username.casefold() != f"@{_EXPECTED_USERNAME}".casefold():
        raise CredentialStoreError("credential_unavailable")
    report_stage("local_preflight")
    executable = _required_codex_executable()
    git = _required_executable("git")
    python = Path(sys.executable).resolve(strict=True)
    worktree = _validated_worktree()
    _CODEX_TEMP.mkdir(parents=True, exist_ok=True)
    system_root = Path(os.environ["SYSTEMROOT"]).resolve(strict=True)
    nobus_memory = NobusMemory(_NOBUS_MEMORY_ROOT)

    control: ProductTelegramControlPlane | None = None
    miniapp_server: _MiniAppServer | None = None
    runtime = None
    bot_token = credential.secret.get_secret_value()
    api = TelegramBotApi(
        token=bot_token,
        transport=httpx.AsyncHTTPTransport(retries=0, trust_env=False),
        request_timeout=60,
    )
    try:
        report_stage("telegram_identity")
        identity = await api.get_me()
        if identity.username.casefold() != _EXPECTED_USERNAME.casefold():
            raise TelegramBotApiError("telegram_protocol_error")
        report_stage("bindings")
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
        report_stage("runtime_stores")
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
        report_stage("core_runtime")
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
        report_stage("worker_probe")
        await runtime.probe_worker()
        report_stage("voice_warmup")
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
        report_stage("rate_limit_provider")
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
        report_stage("control_construction")
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
            enable_extended_routes=False,
            execution_concurrency=GATE5A4_EXECUTION_CONCURRENCY,
            telegram_state=telegram_state,
            task_tenants=destination_refs,
            task_status_sender=TelegramStatusSender(
                api, sender_destinations, technical_details=False
            ),
        )
        report_stage("control_start")
        await control.start()
        if not values.once:
            report_stage("miniapp_core")
            miniapp_server = _create_miniapp_server(
                store=runtime.miniapp_store,
                task_admission=control,
                bot_token=bot_token,
                owner_user_id=owner_binding.user_id,
                tenant_id=owner_binding.tenant_id,
                values=values,
            )
            report_stage("miniapp_server")
            await miniapp_server.start()

        async def handle_with_binding(update: dict[str, object]) -> bool:
            return await control.handle(update)

        report_stage("polling")
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
                health_check=lambda: _assert_product_healthy(
                    control, miniapp_server
                ),
            )
            _assert_product_healthy(control, miniapp_server)
            while True:
                acknowledged += await _poll_with_unavailable_backoff(
                    polling, api, bindings, control=control,
                    timeout=values.timeout, announce=False,
                    health_check=lambda: _assert_product_healthy(
                        control, miniapp_server
                    ),
                )
                _assert_product_healthy(control, miniapp_server)
        _assert_product_healthy(control, miniapp_server)
        return {
            "status": "PASS",
            "mode": "once" if values.once else "serve",
            "announced": bool(values.announce),
            "acknowledged": acknowledged,
        }
    finally:
        try:
            if miniapp_server is not None:
                await miniapp_server.close()
        finally:
            try:
                if control is not None:
                    await control.close()
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


def _required_executable(name: str) -> Path:
    value = shutil.which(name)
    if value is None:
        raise RuntimeError("required executable is unavailable")
    return Path(value).resolve(strict=True)


def _validated_worktree() -> Path:
    root = _WORKTREE.resolve(strict=True)
    current_is_isolated = (
        root == ROOT
        and root.parent.name.casefold() == "worktrees"
        and (root / ".git").is_file()
    )
    if not root.is_dir() or (root == ROOT and not current_is_isolated):
        raise RuntimeError("isolated worktree is unavailable")
    return root


def _stage_failure_code(stage: str) -> str:
    if stage not in _RUN_STAGES:
        return "telegram_mvp1_failed"
    return f"telegram_mvp1_{stage}_failed"


def main() -> int:
    result: dict[str, object] | None = None
    failure = ""
    stage = ""

    def report_stage(value: str) -> None:
        nonlocal stage
        stage = value

    try:
        with WindowsNamedMutex():
            recover_interrupted_restore(_RUNTIME_ROOT)
            result = asyncio.run(_run(_arguments(), report_stage=report_stage))
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
        failure = _stage_failure_code(stage)
    if result is None:
        result = {"status": "FAIL", "code": failure or "telegram_mvp1_failed"}
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return 0 if result["status"] in {"PASS", "STOPPED", "ALREADY_RUNNING"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
