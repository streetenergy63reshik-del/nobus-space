"""Probe real Codex authentication, process control, JSONL, and sentinel."""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from pathlib import Path
from uuid import uuid4


_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from src.contracts import TaskContract
from src.workers.asyncio_spawner import AsyncioProcessSpawner
from src.workers.codex_cli import CodexCliAdapter, CodexCliError, build_worker_env
from src.workers.windows_job import WindowsJobLauncher


_SENTINEL = "NOBUS_CODEX_READONLY_OK"


async def _run(executable: Path, workspace: Path) -> None:
    temp_root = workspace / ".tmp"
    temp_root.mkdir(exist_ok=True)
    git = shutil.which("git")
    if git is None:
        raise CodexCliError("worker_configuration_invalid")
    system_root = Path(os.environ["SYSTEMROOT"])
    worker_env = build_worker_env(
        codex_home=Path.home() / ".codex",
        system_root=system_root,
        temp_root=temp_root,
        workspace_root=workspace,
        path_entries=(
            system_root / "System32",
            system_root / "System32" / "WindowsPowerShell" / "v1.0",
            Path(git).parent,
        ),
    )
    launcher = WindowsJobLauncher(
        workspace_root=workspace,
        target_executable=executable,
        worker_env=worker_env,
    )
    spawner = AsyncioProcessSpawner(
        workspace_root=workspace,
        executable=executable,
        spawn=launcher,
        tree_killer=launcher.kill_tree,
        worker_env=worker_env,
    )
    adapter = CodexCliAdapter(
        workspace_root=workspace,
        executable=executable,
        spawner=spawner,
        max_timeout_seconds=120,
        cleanup_timeout=10,
        worker_env=worker_env,
    )
    result = await adapter.execute(
        TaskContract(
            task_id=uuid4(),
            idempotency_key="live-codex-readonly-probe",
            ingress_digest="sha256:" + "0" * 64,
            tenant_id="local-probe",
            source="local-probe",
            instruction=(
                "Do not use tools, browse, read files, or modify files. "
                f"Return exactly {_SENTINEL} and nothing else."
            ),
            allowed_paths=(str(workspace),),
            permissions=("repo.read", "process.run_allowlisted"),
            risk="low",
            acceptance_criteria=(f"The final answer is exactly {_SENTINEL}.",),
            timeout_seconds=120,
            quality_profile="live-codex-readonly-probe@1",
        )
    )
    if result.message != _SENTINEL:
        raise CodexCliError("worker_protocol_error")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=_ROOT)
    arguments = parser.parse_args()
    if os.name != "nt":
        print("Codex CLI live probe: FAIL (unsupported_platform)")
        return 1
    try:
        executable = arguments.executable.resolve(strict=True)
        workspace = arguments.workspace.resolve(strict=True)
        asyncio.run(_run(executable, workspace))
    except CodexCliError as error:
        print(f"Codex CLI live probe: FAIL ({error.code})")
        return 1
    except (OSError, RuntimeError, TypeError, ValueError):
        print("Codex CLI live probe: FAIL (unexpected)")
        return 1
    print("Codex CLI live probe: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
