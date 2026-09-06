"""Opt-in C3 product smoke; invoke phases in separate processes for restart proof.

No inference occurs on import or in inspect. The fixed C3 ledger is shared by
all scenarios/run folders and never resets when source bytes change.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.gate_c2 import product_smoke as old
from tests.gate_c3.budget import Budget, TurnBudget
from src.contracts.models import canonical_json_digest
from src.application.durable_telegram_state import execution_lease

C3 = ROOT / ".runtime/c3"
LEDGER = C3 / "execution-budget.sqlite3"
C2 = ROOT.parent / "mvp1-closure-c2-voice-parity"
SCENARIOS = ("direct_text", "direct_voice", "material_text")


def fixture(scenario):
    if scenario not in SCENARIOS:
        raise RuntimeError("scenario_not_authorized")
    if scenario.startswith("direct_"):
        values = json.loads((ROOT / "tests/gate_c2/dataset.json").read_text("utf-8"))
        return next(row["text"] for row in values["cases"] if row["id"] == "direct")
    values = json.loads(old.FIXTURES.read_text("utf-8"))
    return next(row["text"] for row in values["cases"] if row["id"] == "transform_correction")


def bind_sources(runroot, model, audio):
    if not runroot.is_relative_to(C3.resolve()) or runroot == C3.resolve():
        raise RuntimeError("run_must_stay_in_c3")
    if model != (C2 / ".runtime/asr-qualification/faster-whisper-small/models").resolve():
        raise RuntimeError("model_must_be_pinned_c2_cache")
    if audio is not None and audio != (C2 / ".runtime/c2/synthetic-audio/direct.wav").resolve():
        raise RuntimeError("audio_must_be_synthetic_c2_direct")
    from scripts.run_telegram_mvp1 import _VOICE_MODEL_FILES
    if any(old.digest(model / name) != expected for name, expected in _VOICE_MODEL_FILES.items()):
        raise RuntimeError("pinned_asr_digest_mismatch")
    binding = old.source_binding(model)
    binding.update(c3_runner_sha256=old.digest(__file__),
        c3_budget_sha256=old.digest(ROOT / "tests/gate_c3/budget.py"),
        c3_fixture_text={name: hashlib.sha256(fixture(name).encode()).hexdigest() for name in SCENARIOS},
        c3_direct_audio_sha256=old.digest(C2 / ".runtime/c2/synthetic-audio/direct.wav"),
        profile={"model": old.MODEL, "reasoning": "high", "tier": "fast", "tools": False})
    runroot.mkdir(parents=True, exist_ok=True)
    path = runroot / "source-binding.json"
    if path.exists() and json.loads(path.read_text("utf-8")) != binding:
        raise RuntimeError("source_changed_since_run_started")
    if not path.exists():
        old.write(path, binding)
    return binding


class CleanupObservedClient(old.GuardedClient):
    """Retain failed physical-close evidence even if SDK startup suppresses it."""
    def __init__(self, *args):
        super().__init__(*args)
        self.cleanup_unproven = False

    async def close(self):
        self.cleanup_unproven = True
        await super().close()
        self.cleanup_unproven = False


class BudgetedPrimary:
    def __init__(self, real, ledger, turn_budget, scenario, binding, diagnostic=False):
        self.real, self.ledger, self.turn_budget = real, ledger, turn_budget
        self.scenario, self.binding, self.diagnostic = scenario, binding, diagnostic
        self.lock = asyncio.Lock()
        self.last_reservation = None
        self.clients = []

    def __getattr__(self, name):
        return getattr(self.real, name)

    async def _call(self, kind, method, *args, **kwargs):
        async with self.lock:
            number = self.ledger.reserve("model", self.scenario, kind, self.binding, 180,
                diagnostic=self.diagnostic)
            self.last_reservation = number
            self.diagnostic = False
            self.turn_budget.active = number
            started, status = time.monotonic(), "FAILED"
            try:
                # Existing SDK cancellation drains its affected generation. The
                # reservation includes 60 seconds beyond this request deadline.
                async with asyncio.timeout(120):
                    value = await method(*args, **kwargs)
                status = "RETURNED"
                return value
            except BaseException as error:
                status = getattr(error, "code", type(error).__name__)
                raise
            finally:
                self.turn_budget.active = None
                self.ledger.finish(number, time.monotonic() - started, status)
                retired = getattr(self.real, "_retired_clients", {})
                outcomes = getattr(self.real, "_retired_outcomes", {})
                if (any(outcomes.get(identity) is not True for identity in retired)
                    or any(client.cleanup_unproven for client in self.clients)):
                    self.ledger.hold_cleanup_failure(number)

    async def execute(self, contract):
        return await self._call("downstream", self.real.execute, contract)

    async def compile_semantic(self, *args, **kwargs):
        return await self._call("compiler", self.real.compile_semantic, *args, **kwargs)

    async def bootstrap(self):
        """Open/validate the local SDK generation without creating a model turn."""
        if self.real.generation_available:
            return

        async def start():
            client = await self.real._client_instance()
            await self.real._release_client(client)

        await self._call("startup", start)


class BudgetedVoice:
    def __init__(self, model, ledger, scenario, binding):
        self.model, self.ledger, self.scenario, self.binding = model, ledger, scenario, binding

    async def transcribe_audio(self, audio, *, max_chars):
        number = self.ledger.reserve("asr", self.scenario, "native_inference", self.binding, 190)
        started, status = time.monotonic(), "FAILED"
        from scripts.run_telegram_mvp1 import _build_voice_transcriber
        engine = None
        try:
            engine = _build_voice_transcriber(self.model)
            result = await engine.transcribe_audio(audio, max_chars=max_chars)
            status = "RETURNED"
            return result
        finally:
            try:
                if engine is not None:
                    await engine.close()
            except BaseException:
                self.ledger.hold_cleanup_failure(number)
                raise
            self.ledger.finish(number, time.monotonic() - started, status)

    async def close(self):
        return None


def product_snapshot(runtime, state, folder):
    with sqlite3.connect(state.path) as db:
        jobs = db.execute("SELECT kind,status,task_id FROM telegram_jobs ORDER BY job_id").fetchall()
    return {"tasks": [x.projection.model_dump(mode="json") for x in runtime._store.list_tasks(old.TENANT)],
        "jobs": jobs, "outbox": old.outbox_projection(folder)}


async def run(args):
    runroot, model = args.run.resolve(), args.model.resolve()
    audio = args.audio.resolve() if args.audio else None
    if args.scenario == "direct_voice" and audio is None:
        raise RuntimeError("synthetic_audio_required")
    binding = bind_sources(runroot, model, audio)
    binding_digest = canonical_json_digest(binding)[7:]
    ledger = Budget(LEDGER)
    folder = runroot / args.scenario
    folder.mkdir(exist_ok=True)
    if args.phase == "inspect":
        old.write(folder / "inspect.json", {"binding": binding, "budget": ledger.snapshot(), "inference": False})
        return
    if not args.authorized_run:
        raise RuntimeError("explicit_authorized_run_required")
    workspace, temp = folder / "workspace", folder / "workspace/temp"
    temp.mkdir(parents=True, exist_ok=True)
    if old.cli_status(args.codex_home, workspace) != "CHATGPT":
        raise RuntimeError("existing_chatgpt_login_not_verified")
    state = old.SQLiteTelegramState(folder / "telegram.sqlite3")
    actions = old.DurableTelegramActionStore(state)
    gateway = old.TelegramGateway(actor_bindings={(old.USER, old.USER): old.ActorBinding(
        tenant_id=old.TENANT, actor_identity="telegram:c3-synthetic-owner", role="owner", auth_context_ref=old.AUTH)},
        update_id_store=old.PollingCheckpointUpdateIdStore(), callback_token_store=actions)
    api = old.LocalTransport(folder, audio)
    runtime = old.build_gate5a4_runtime(gateway=gateway, sqlite_path=folder / "tasks.sqlite3",
        destination_refs={old.TENANT: old.DEST}, worktree=workspace,
        codex_executable=old.bundled_codex_path(), git_executable=shutil.which("git"), python_executable=sys.executable,
        codex_home=args.codex_home, system_root=os.environ.get("SystemRoot", "C:/Windows"), temp_root=temp,
        path_entries=(Path(sys.executable).parent, Path(shutil.which("git")).parent),
        owner_read_root=None, project_context=None, nobus_memory=None)
    turn_budget = TurnBudget(ledger)
    primary = runtime._worker._primary
    counted_primary = BudgetedPrimary(primary, ledger, turn_budget, args.scenario, binding_digest, args.diagnostic_repeat)

    def client_factory(config):
        client = CleanupObservedClient(config, turn_budget, args.scenario, folder)
        counted_primary.clients.append(client)
        return client

    primary._client_factory = client_factory
    runtime._worker._primary = counted_primary
    engine = BudgetedVoice(model, ledger, args.scenario, binding_digest)
    service = old.ObservedVoice(engine, folder, args.phase)
    control = old.DurableProductTelegramControlPlane(gateway, api, task_runtime=runtime,
        task_confirmations=old.DurableTaskConfirmationStore(state), patch_confirmations=old.DurablePatchConfirmationStore(state), action_store=actions,
        voice_service=service, semantic_admission=old.ObservedAdmission(runtime, folder),
        semantic_clarifications=old.DurableSemanticClarificationStore(state), enable_semantic_admission=True,
        enable_extended_routes=False, execution_concurrency=2, telegram_state=state,
        task_tenants=(old.TENANT,), task_status_sender=old.TelegramStatusSender(api, {old.TENANT: (old.DEST, old.USER)}, technical_details=False))
    checkpoint = old.SQLitePollingCheckpointStore(folder / "polling.sqlite3", consumer_id="c3-product-smoke", lease_duration_seconds=240)
    polling = old.TelegramPollingBoundary(api, control.handle, checkpoint)
    original = old.update(None, audio) if args.scenario == "direct_voice" else old.update(fixture(args.scenario))
    before, status, cleanup = ledger.snapshot(), "FAILED", []
    try:
        async with asyncio.timeout(240):
            if args.phase == "admit":
                await old.poll_update(api, polling, original)
                if args.scenario == "direct_voice":
                    job = state.claim(lease_owner=control._lease_owner, lease_seconds=60)
                    if job is None or job.kind != "voice":
                        raise RuntimeError("voice_not_durable_before_asr")
                    marker = execution_lease.set((state, job, control._lease_owner))
                    try:
                        await control._execute_voice_with_lease(job)
                    finally:
                        execution_lease.reset(marker)
                    saved = state.read_voice(tenant_id=job.tenant_id, task_id=job.task_id)
                    if saved is None or saved.payload.get("stage") != "waiting":
                        raise RuntimeError("voice_preview_not_durable")
                    if runtime._store.list_tasks(old.TENANT) or ledger.snapshot()["resources"]["model"] != before["resources"]["model"]:
                        raise RuntimeError("task_or_model_before_confirmation")
            elif args.phase == "confirm":
                if args.scenario != "direct_voice":
                    raise RuntimeError("confirmation_requires_voice")
                await old.poll_update(api, polling, old.update("да", reply=True))
                job = state.claim(lease_owner=control._lease_owner, lease_seconds=60)
                if job is None or job.kind != "voice":
                    raise RuntimeError("confirmed_voice_not_durable")
                marker = execution_lease.set((state, job, control._lease_owner))
                try:
                    await control._durable_voice.run(job)
                finally:
                    execution_lease.reset(marker)
                with sqlite3.connect(state.path) as db:
                    if db.execute("SELECT COUNT(*) FROM telegram_jobs WHERE kind='draft' AND status='pending'").fetchone()[0] != 1:
                        raise RuntimeError("voice_to_draft_restart_barrier_missing")
            elif args.phase in {"drain", "replay"}:
                await counted_primary.bootstrap()
                original_snapshot = product_snapshot(runtime, state, folder)
                original_budget = ledger.snapshot()
                original_transport = list(api.rows)
                if args.phase == "replay":
                    await old.poll_update(api, polling, original)
                    if args.scenario == "direct_voice":
                        await old.poll_update(api, polling, old.update("да", reply=True))
                await control.start()
                while state.queue_counts() != (0, 0):
                    control.assert_healthy()
                    await asyncio.sleep(0.15)
                await control.deliver_pending()
                if args.phase == "replay":
                    if product_snapshot(runtime, state, folder) != original_snapshot or ledger.snapshot() != original_budget:
                        raise RuntimeError("restart_replay_repeated_task_result_or_model")
                    if any(row["kind"] in {"message", "document"} for row in api.rows[len(original_transport):]):
                        raise RuntimeError("restart_replay_repeated_delivery")
                tasks = runtime._store.list_tasks(old.TENANT)
                if len(tasks) != 1 or tasks[0].projection.status.value != "answered":
                    raise RuntimeError("one_authoritative_result_not_proven")
                old.assert_ready_delivery(folder, api, state)
            status = "PHASE_COMPLETED"
    finally:
        for name, close in (("control", control.close), ("runtime", runtime.close)):
            close_started = time.monotonic()
            try:
                async with asyncio.timeout(45):
                    await close()
                cleanup.append({"component": name, "closed": True})
            except BaseException:
                cleanup.append({"component": name, "closed": False})
                if name == "runtime" and counted_primary.last_reservation is not None:
                    ledger.hold_cleanup_failure(counted_primary.last_reservation)
            else:
                if name == "runtime" and counted_primary.last_reservation is not None:
                    ledger.add_cleanup(counted_primary.last_reservation, time.monotonic() - close_started)
        old.write(folder / f"phase-{time.time_ns()}-{args.phase}.json", {
            "scenario": args.scenario, "phase": args.phase, "process_id": os.getpid(), "status": status,
            "binding": binding, "budget_before": before, "budget_after": ledger.snapshot(),
            "snapshot": product_snapshot(runtime, state, folder), "cleanup": cleanup,
            "restart_kind": "controlled_separate_phase_process", "quality_rubric": "PENDING_INDEPENDENT_REVIEW"})
        if not all(row["closed"] for row in cleanup):
            raise RuntimeError("cleanup_not_verified")
    print(json.dumps({"scenario": args.scenario, "phase": args.phase, "status": status, "budget": ledger.snapshot()}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    parser.add_argument("--phase", choices=("inspect", "admit", "confirm", "drain", "replay"), default="inspect")
    parser.add_argument("--codex-home", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--authorized-run", action="store_true")
    parser.add_argument("--diagnostic-repeat", action="store_true")
    try:
        asyncio.run(run(parser.parse_args()))
    except BaseException as error:
        code = str(error) if isinstance(error, RuntimeError) and re.fullmatch("[a-z_]{1,100}", str(error)) else None
        print(json.dumps({"status": "FAILED", "error_type": type(error).__name__, "safe_code": code}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
