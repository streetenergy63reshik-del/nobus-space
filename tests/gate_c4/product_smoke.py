"""Opt-in C4 HTTP/Core smoke with real inference and synthetic Telegram transport.

This is NOT browser or live Telegram acceptance. Import/inspect never starts
SDK, ASR, or HTTP. All candidates share the one C4 ledger, including retries.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx

from tests.gate_c3 import product_smoke as c3
from tests.gate_c4.budget import Budget, TurnBudget, ledger_path
from tests.gate_c4.server import candidate_server
from src.application.durable_telegram_state import execution_lease
from src.application.miniapp import MiniAppCore
from src.contracts.models import canonical_json_digest
from src.storage.outbox import delivery_parts

old = c3.old
C4 = ledger_path().parent
C2 = C4.parents[2] / "mvp1-closure-c2-voice-parity"
MODEL = C2 / ".runtime/asr-qualification/faster-whisper-small/models"
AUDIO = C2 / ".runtime/c2/synthetic-audio"
BOT_TOKEN = "911001:c4-synthetic-only-not-a-telegram-bot"
SCENARIOS = ("direct_text", "telegram_text", "transform_text", "direct_voice", "transform_voice", "clarification", "unavailable")
TELEGRAM_SCENARIOS = frozenset({"telegram_text", "direct_voice", "transform_voice"})
CLARIFICATION_ANSWER = "Нужны три пункта плана проверки проекта; каждый пункт — конкретное действие. Исходный материал не требуется."


def fixture(scenario):
    if scenario not in SCENARIOS:
        raise RuntimeError("scenario_not_authorized")
    if scenario.startswith("direct_") or scenario == "telegram_text":
        return c3.fixture("direct_text")
    if scenario.startswith("transform_"):
        return next(row["text"] for row in json.loads(old.FIXTURES.read_text("utf-8"))["cases"] if row["id"] == "transform")
    if scenario == "clarification":
        # The accepted C1 real-provider ambiguity fixture, now followed by an answer.
        return "Подготовь это в подходящем виде."
    return "Создай событие в Google Calendar на завтра в 12:00 с названием Синтетическая проверка."


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def assert_frozen(binding):
    if git("rev-parse", "HEAD") != binding["candidate_revision"] or git("status", "--porcelain", "--untracked-files=normal"):
        raise RuntimeError("candidate_not_exact_clean_freeze")
    if any(old.digest(ROOT / path) != digest for path, digest in binding["c4_sources"].items()):
        raise RuntimeError("source_changed_since_run_started")


def bind_sources(runroot, model):
    if not runroot.is_relative_to(C4.resolve()) or runroot == C4.resolve():
        raise RuntimeError("run_must_stay_in_c4")
    if model != MODEL.resolve():
        raise RuntimeError("model_must_be_pinned_c2_cache")
    from scripts.run_telegram_mvp1 import _VOICE_MODEL_FILES
    if any(old.digest(model / name) != expected for name, expected in _VOICE_MODEL_FILES.items()):
        raise RuntimeError("pinned_asr_digest_mismatch")
    paths = git("ls-files", "src", "scripts", "tests/gate_c2", "tests/gate_c3", "tests/gate_c4").splitlines()
    binding = old.source_binding(model)
    binding.update(
        candidate_revision=git("rev-parse", "HEAD"), candidate_tree=git("rev-parse", "HEAD^{tree}"),
        c4_sources={path: old.digest(ROOT / path) for path in paths},
        c4_runner_sha256=old.digest(__file__),
        c4_budget_sha256=old.digest(ROOT / "tests/gate_c4/budget.py"),
        c4_server_sha256=old.digest(ROOT / "tests/gate_c4/server.py"),
        c4_fixtures={name: hashlib.sha256(fixture(name).encode()).hexdigest() for name in SCENARIOS},
        c4_clarification_answer_sha256=hashlib.sha256(CLARIFICATION_ANSWER.encode()).hexdigest(),
        c4_audio={name: old.digest(AUDIO / f"{name}.wav") for name in ("direct", "transform")},
        profile={"model": old.MODEL, "reasoning": "high", "tier": "fast", "tools": False},
        scope="actual_loopback_http_core_worker_synthetic_telegram_not_live_or_browser",
    )
    runroot.mkdir(parents=True, exist_ok=True)
    path = runroot / "source-binding.json"
    if path.exists() and json.loads(path.read_text("utf-8")) != binding:
        raise RuntimeError("source_changed_since_run_started")
    if not path.exists():
        old.write(path, binding)
    return binding


class FrozenPrimary(c3.BudgetedPrimary):
    def __init__(self, *args, source_binding, **kwargs):
        super().__init__(*args, **kwargs)
        self.source_binding = source_binding

    async def _call(self, *args, **kwargs):
        assert_frozen(self.source_binding)
        return await super()._call(*args, **kwargs)

    async def start(self):
        await self.bootstrap()


class FrozenVoice(c3.BudgetedVoice):
    def __init__(self, *args, source_binding):
        super().__init__(*args)
        self.source_binding = source_binding

    async def transcribe_audio(self, *args, **kwargs):
        assert_frozen(self.source_binding)
        return await super().transcribe_audio(*args, **kwargs)


class LocalTransport(old.LocalTransport):
    async def edit_message_text(self, chat_id, message_id, text):
        if chat_id != old.USER or not any(row["kind"] == "message" for row in self.rows):
            raise RuntimeError("foreign_progress_edit")
        self.append("edit", message_id=message_id, text=text)


class Clock:
    def __init__(self):
        self.offset = timedelta()

    def __call__(self):
        return datetime.now(UTC) + self.offset


def signed_init_data(now):
    fields = {"auth_date": str(int(now.timestamp())), "query_id": "c4-" + str(time.time_ns()),
              "user": json.dumps({"id": old.USER, "first_name": "Synthetic"}, separators=(",", ":"))}
    check = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    return urlencode([*fields.items(), ("hash", hmac.new(secret, check.encode(), hashlib.sha256).hexdigest())])


class HttpJourney:
    def __init__(self, client, clock, receipt_path=None):
        self.client, self.clock = client, clock
        self.receipt_path = receipt_path
        self.token = None
        self.receipts = []

    async def request(self, method, path, expected=200, **kwargs):
        headers = {"Origin": str(self.client.base_url).rstrip("/")}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        headers.update(kwargs.pop("headers", {}))
        response = await self.client.request(method, path, headers=headers, **kwargs)
        self.receipts.append({"method": method, "path": path, "status": response.status_code, "expected": expected})
        if self.receipt_path is not None:
            old.write(self.receipt_path, self.receipts)
        if response.status_code != expected:
            raise RuntimeError("unexpected_candidate_http_status")
        return response

    async def authenticate(self):
        response = await self.request("POST", "/api/session", content=signed_init_data(self.clock()),
                                      headers={"Content-Type": "text/plain"})
        self.token = response.json()["access_token"]

    async def recover(self):
        self.token = (await self.request("POST", "/api/session/recover")).json()["access_token"]

    async def expire_and_recover(self):
        previous = self.token
        self.clock.offset += timedelta(seconds=121)
        await self.request("GET", "/api/tasks", expected=401)
        await self.recover()
        current, self.token = self.token, previous
        await self.request("GET", "/api/tasks", expected=401)
        self.token = current
        await self.request("GET", "/api/tasks")


def build_runtime(args, folder, binding, ledger):
    workspace, temp = folder / "workspace", folder / "workspace/temp"
    temp.mkdir(parents=True, exist_ok=True)
    if old.cli_status(args.codex_home, workspace) != "CHATGPT":
        raise RuntimeError("existing_chatgpt_login_not_verified")
    state = old.SQLiteTelegramState(folder / "telegram.sqlite3")
    actions = old.DurableTelegramActionStore(state)
    gateway = old.TelegramGateway(actor_bindings={(old.USER, old.USER): old.ActorBinding(
        tenant_id=old.TENANT, actor_identity="telegram:c4-synthetic-owner", role="owner", auth_context_ref=old.AUTH)},
        update_id_store=old.PollingCheckpointUpdateIdStore(), callback_token_store=actions)
    audio = AUDIO / ("transform.wav" if args.scenario == "transform_voice" else "direct.wav")
    api = LocalTransport(folder, audio if args.scenario.endswith("_voice") else None)
    runtime = old.build_gate5a4_runtime(gateway=gateway, sqlite_path=folder / "tasks.sqlite3",
        destination_refs={old.TENANT: old.DEST}, worktree=workspace,
        codex_executable=old.bundled_codex_path(), git_executable=shutil.which("git"), python_executable=sys.executable,
        codex_home=args.codex_home, system_root=os.environ.get("SystemRoot", "C:/Windows"), temp_root=temp,
        path_entries=(Path(sys.executable).parent, Path(shutil.which("git")).parent),
        owner_read_root=None, project_context=None, nobus_memory=None)
    turns = TurnBudget(ledger)
    binding_digest = canonical_json_digest(binding)[7:]
    primary = runtime._worker._primary
    counted = FrozenPrimary(primary, ledger, turns, args.scenario, binding_digest,
                            args.diagnostic_repeat, source_binding=binding)

    def factory(config):
        client = c3.CleanupObservedClient(config, turns, args.scenario, folder)
        counted.clients.append(client)
        return client

    primary._client_factory = factory
    runtime._worker._primary = counted
    voice = FrozenVoice(MODEL.resolve(), ledger, args.scenario, binding_digest, source_binding=binding)
    control = old.DurableProductTelegramControlPlane(gateway, api, task_runtime=runtime,
        task_confirmations=old.DurableTaskConfirmationStore(state), patch_confirmations=old.DurablePatchConfirmationStore(state),
        action_store=actions, voice_service=old.ObservedVoice(voice, folder, "admit"),
        semantic_admission=old.ObservedAdmission(runtime, folder), semantic_clarifications=old.DurableSemanticClarificationStore(state),
        enable_semantic_admission=True, enable_extended_routes=False, execution_concurrency=2, telegram_state=state,
        task_tenants=(old.TENANT,), task_status_sender=old.TelegramStatusSender(api, {old.TENANT: (old.DEST, old.USER)}, technical_details=False))
    clock = Clock()
    core = MiniAppCore(store=runtime._store, task_admission=control, bot_token=BOT_TOKEN,
                       owner_user_id=old.USER, tenant_id=old.TENANT, clock=clock)
    # A controlled scheduler cut makes ACK-loss lookup and the voice preview
    # observable before a real worker can consume the durable queue.
    control._c4_start = control.start

    async def admission_barrier():
        return None

    control.start = admission_barrier
    return runtime, state, api, control, counted, core, clock


async def voice_admit(control, state, api, runtime, folder, ledger, scenario):
    # Scheduling fault injection only: retain real durable admission, ASR and
    # confirmation paths while proving zero compiler/tasks before confirmation.
    original_start = control.start

    async def barrier():
        return None

    control.start = barrier
    checkpoint = old.SQLitePollingCheckpointStore(folder / "polling.sqlite3", consumer_id="c4-product-smoke", lease_duration_seconds=240)
    polling = old.TelegramPollingBoundary(api, control.handle, checkpoint)
    before = ledger.snapshot()["resources"]["model"]
    try:
        await old.poll_update(api, polling, old.update(None, api.audio))
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
        if runtime._store.list_tasks(old.TENANT) or ledger.snapshot()["resources"]["model"] != before:
            raise RuntimeError("task_or_model_before_confirmation")
        # Accepted C2 confirmation is an exact reply to the original voice.
        await old.poll_update(api, polling, old.update("да", reply=True))
    finally:
        control.start = original_start
    return polling


async def wait_result(journey, runtime, control):
    seen = []
    async with asyncio.timeout(900):
        while True:
            control.assert_healthy()
            items = (await journey.request("GET", "/api/tasks")).json()["tasks"]
            if len(items) > 1:
                raise RuntimeError("duplicate_task")
            if items:
                item = items[0]
                if not seen or seen[-1] != item["status"]:
                    seen.append(item["status"])
                if item["terminal"]:
                    if item["status"] != "ready":
                        raise RuntimeError("task_did_not_complete")
                    await control.deliver_pending()
                    return item["task_id"], seen
            await asyncio.sleep(0.25)


def ready_delivery(runtime, state, api, folder, task_id):
    """Read immutable authority and every receipt, then compare transport bytes.

    C3's helper is unchanged: its UUID-bearing external filename predates C4.
    The display alias changes neither artifact identity nor delivery manifest.
    """
    store = runtime._store
    snapshots = store.list_tasks(old.TENANT)
    if len(snapshots) != 1 or str(snapshots[0].projection.task_id) != task_id:
        raise RuntimeError("one_authoritative_task_not_proven")
    snapshot = snapshots[0]
    projection = snapshot.projection
    message = store.read_verified_answer(old.TENANT, projection.task_id,
        task_revision=snapshot.revision, task_projection_digest=snapshot.snapshot_digest,
        contract_digest=projection.contract_digest, result_revision=projection.result_revision,
        result_digest=projection.result_digest)
    if message is None or message.status.value != "acked":
        raise RuntimeError("one_ready_outbox_not_proven")
    receipts = store.read_outbox_receipts(old.TENANT, message.message_id)
    if sum(row.receipt_type.value == "ack" for row in receipts) != 1:
        raise RuntimeError("one_ready_ack_not_proven")
    artifact = old.artifact_for_message(message)
    if artifact is None:
        raise RuntimeError("ready_artifact_binding_missing")
    chunks = old._status_message_chunks(old._status_text(message, technical_details=False))
    expected_parts = delivery_parts(message, tuple(
        [("text", chunk.encode("utf-8")) for chunk in chunks] + [("document", artifact.content_bytes())]))
    actual_parts = store.read_delivery_parts(old.TENANT, message.message_id)
    if tuple(part for part, _ in actual_parts) != expected_parts or any(receipt is None for _, receipt in actual_parts):
        raise RuntimeError("ready_part_receipts_not_proven")
    documents = [row for row in api.rows if row["kind"] == "document"]
    if len(documents) != 1 or documents[0]["filename"] != "nobus-result.txt" or documents[0]["sha256"] != artifact.content_digest[7:]:
        raise RuntimeError("one_ready_document_not_proven")
    if (folder / "artifacts/nobus-result.txt").read_bytes() != artifact.content_bytes():
        raise RuntimeError("ready_artifact_bytes_mismatch")
    # The full ordered terminal answer appears once; earlier progress is allowed.
    rendered = [row["text"] if row["kind"] == "message" else None for row in api.rows
                if row["kind"] == "document" or (row["kind"] == "message" and row["text"] in chunks)]
    if rendered != [*chunks, None]:
        raise RuntimeError("ready_delivery_order_or_count_differ")
    with sqlite3.connect(state.path) as db:
        if db.execute("SELECT COUNT(*) FROM telegram_jobs WHERE kind NOT IN ('voice','draft','miniapp_draft')").fetchone()[0]:
            raise RuntimeError("unexpected_effect_job")
    return snapshot, message, artifact, expected_parts


async def compare_result(journey, runtime, state, api, folder, task_id):
    snapshot, message, bound_artifact, parts = ready_delivery(runtime, state, api, folder, task_id)
    detail = (await journey.request("GET", f"/api/tasks/{task_id}")).json()
    result = (await journey.request("GET", f"/api/tasks/{task_id}/result?revision={detail['result_revision']}")).json()
    artifact = result["artifact"]
    if artifact is None:
        raise RuntimeError("http_artifact_missing")
    if artifact != {"artifact_id": str(bound_artifact.artifact_id), "filename": "nobus-result.txt",
                    "media_type": bound_artifact.media_type, "size": bound_artifact.size,
                    "content_digest": bound_artifact.content_digest}:
        raise RuntimeError("http_artifact_binding_differ")
    response = await journey.request("GET", f"/api/tasks/{task_id}/artifacts/{artifact['artifact_id']}?revision={result['result_revision']}")
    digest = "sha256:" + hashlib.sha256(response.content).hexdigest()
    if digest != artifact["content_digest"] or len(response.content) != artifact["size"]:
        raise RuntimeError("http_artifact_digest_mismatch")
    if response.content != (folder / "artifacts" / artifact["filename"]).read_bytes():
        raise RuntimeError("telegram_http_artifact_bytes_differ")
    # Strict decoding proves that the received TXT opens, not only its metadata.
    if result["answer"] != message.user_message or result["answer"] != response.content.decode("utf-8", errors="strict"):
        raise RuntimeError("http_artifact_answer_differ")
    if (str(snapshot.projection.task_id) != result["task_id"] or snapshot.revision != result["task_revision"]
        or snapshot.projection.result_revision != result["result_revision"] or snapshot.projection.result_digest != result["result_digest"]):
        raise RuntimeError("http_result_revision_differ")
    await journey.request("GET", f"/api/tasks/{task_id}/events")
    return {"task_id": task_id, "result_revision": result["result_revision"], "result_digest": result["result_digest"],
            "artifact_id": str(bound_artifact.artifact_id), "artifact_digest": digest,
            "artifact_size": len(response.content), "artifact_opened_utf8": True,
            "delivery_manifest_digest": parts[0].manifest_digest, "confirmed_parts": len(parts),
            "telegram_transport": "synthetic", "http_transport": "actual_loopback_tcp"}


async def exercise(args, folder, runtime, state, api, control, counted, core, clock, ledger):
    async with candidate_server(core) as origin, httpx.AsyncClient(base_url=origin, timeout=600, trust_env=False) as client:
        journey = HttpJourney(client, clock, folder / f"http-{time.time_ns()}-{args.phase}.json")
        await journey.authenticate()
        html = await journey.request("GET", "/")
        if html.content != (ROOT / "src/transport/miniapp_static/index.html").read_bytes():
            raise RuntimeError("candidate_static_html_differ")
        for name in ("app.js", "styles.css"):
            content = await journey.request("GET", "/" + name)
            if content.content != (ROOT / "src/transport/miniapp_static" / name).read_bytes():
                raise RuntimeError("candidate_static_asset_differ")
        request_id = "c4-" + args.scenario + "-intent-0001"
        if args.phase == "run":
            if runtime._store.list_tasks(old.TENANT) or state.queue_counts() != (0, 0):
                raise RuntimeError("run_requires_unused_scenario")
            if args.scenario.endswith("_voice"):
                await voice_admit(control, state, api, runtime, folder, ledger, args.scenario)
            elif args.scenario == "telegram_text":
                checkpoint = old.SQLitePollingCheckpointStore(folder / "polling.sqlite3", consumer_id="c4-product-smoke", lease_duration_seconds=240)
                polling = old.TelegramPollingBoundary(api, control.handle, checkpoint)
                await old.poll_update(api, polling, old.update(fixture(args.scenario)))
            else:
                expected = 409 if args.scenario in {"clarification", "unavailable"} else 202
                response = await journey.request("POST", "/api/tasks", expected=expected,
                    headers={"Idempotency-Key": request_id}, json={"instruction": fixture(args.scenario)})
                if args.scenario == "unavailable":
                    if response.json().get("detail") != "capability_unavailable" or runtime._store.list_tasks(old.TENANT):
                        raise RuntimeError("unavailable_not_proven")
                    lookup = (await journey.request("GET", "/api/requests/" + request_id)).json()
                    if lookup["state"] != "not_accepted":
                        raise RuntimeError("unavailable_request_state_differ")
                    return {"unavailable": True, "http": journey.receipts}
                if args.scenario == "clarification":
                    question = response.json()
                    if question.get("detail") != "clarification_required" or not question.get("question"):
                        raise RuntimeError("clarification_not_proven")
                    lookup = (await journey.request("GET", "/api/requests/" + request_id)).json()
                    if lookup["state"] != "clarification" or lookup["question"] != question["question"]:
                        raise RuntimeError("clarification_recovery_differ")
                    await journey.recover()
                    request_id = "c4-clarification-answer-0001"
                    await journey.request("POST", "/api/tasks", expected=202, headers={"Idempotency-Key": request_id},
                        json={"instruction": CLARIFICATION_ANSWER, "clarification_token": question["clarification_token"]})
                # Discard create response as an ACK-loss fault. Core lookup is the
                # sole source of identity after reload; no new POST is issued.
                before = ledger.snapshot()
                journey.token = None
                await journey.recover()
                lookup = (await journey.request("GET", "/api/requests/" + request_id)).json()
                if lookup["state"] != "accepted" or not lookup["task_id"]:
                    raise RuntimeError("ack_loss_reconciliation_failed")
                if ledger.snapshot() != before:
                    raise RuntimeError("lookup_started_model")
            control.start = control._c4_start
            await counted.bootstrap()
            await control.start()
            await journey.expire_and_recover()
            task_id, progress = await wait_result(journey, runtime, control)
        else:
            before = c3.product_snapshot(runtime, state, folder)
            before_budget = ledger.snapshot()
            await journey.recover()
            items = (await journey.request("GET", "/api/tasks")).json()["tasks"]
            if len(items) != 1:
                raise RuntimeError("replay_requires_one_completed_task")
            task_id, progress = items[0]["task_id"], []
            if args.scenario not in TELEGRAM_SCENARIOS:
                if args.scenario == "clarification":
                    request_id = "c4-clarification-answer-0001"
                lookup = (await journey.request("GET", "/api/requests/" + request_id)).json()
                if lookup.get("task_id") != task_id:
                    raise RuntimeError("restart_request_identity_differ")
            if c3.product_snapshot(runtime, state, folder) != before or ledger.snapshot() != before_budget:
                raise RuntimeError("read_recovery_repeated_work")
        result = await compare_result(journey, runtime, state, api, folder, task_id)
        result.update(progress=progress, http=journey.receipts)
        return result


async def run(args):
    binding = bind_sources(args.run.resolve(), args.model.resolve())
    ledger = Budget(ledger_path())
    folder = args.run.resolve() / args.scenario
    folder.mkdir(exist_ok=True)
    if args.phase == "inspect":
        old.write(folder / "inspect.json", {"binding": binding, "budget": ledger.snapshot(), "inference": False})
        return
    if not args.authorized_run:
        raise RuntimeError("explicit_authorized_run_required")
    assert_frozen(binding)
    runtime, state, api, control, counted, core, clock = build_runtime(args, folder, binding, ledger)
    before, status, cleanup, result = ledger.snapshot(), "FAILED", [], None
    try:
        async with asyncio.timeout(1200):
            result = await exercise(args, folder, runtime, state, api, control, counted, core, clock, ledger)
        assert_frozen(binding)
        status = "LOCAL_HTTP_CORE_COMPLETED"
    finally:
        for name, close in (("control", control.close), ("runtime", runtime.close)):
            started = time.monotonic()
            try:
                async with asyncio.timeout(45):
                    await close()
                cleanup.append({"component": name, "closed": True})
            except BaseException:
                cleanup.append({"component": name, "closed": False})
                if counted.last_reservation is not None:
                    ledger.hold_cleanup_failure(counted.last_reservation)
            else:
                if counted.last_reservation is not None:
                    ledger.add_cleanup(counted.last_reservation, time.monotonic() - started)
        old.write(folder / f"phase-{time.time_ns()}-{args.phase}.json", {
            "scenario": args.scenario, "phase": args.phase, "status": status, "process_id": os.getpid(),
            "binding": binding, "budget_before": before, "budget_after": ledger.snapshot(), "cleanup": cleanup,
            "result": result, "snapshot": c3.product_snapshot(runtime, state, folder),
            "browser_acceptance": False, "live_telegram_acceptance": False, "quality_rubric": "PENDING_INDEPENDENT_REVIEW",
        })
        if not all(row["closed"] for row in cleanup):
            raise RuntimeError("cleanup_not_verified")
    print(json.dumps({"status": status, "scenario": args.scenario, "phase": args.phase, "budget": ledger.snapshot()}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    parser.add_argument("--phase", choices=("inspect", "run", "replay"), default="inspect")
    parser.add_argument("--codex-home", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=MODEL)
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
