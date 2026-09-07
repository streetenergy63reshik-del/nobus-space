"""Deterministic C4 harness checks: no model, ASR, Telegram or external HTTP."""

import json
import sqlite3
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from src.application.miniapp import MiniAppCore
from src.storage import SQLiteStore
from tests.gate_c3.budget import Budget as C3Budget
from tests.gate_c4 import budget, product_smoke as smoke
from tests.gate_c4.server import candidate_server


def test_c4_uses_one_distinct_fixed_ledger_and_accepted_accounting():
    assert budget.Budget is C3Budget
    assert budget.LIMITS == {"model": (64, 5400.0), "asr": (20, 1200.0)}
    assert budget.ledger_path().as_posix().endswith(
        "/mvp1-closure-c4-frontend-journey/.runtime/c4/execution-budget.sqlite3")
    assert smoke.MODEL.as_posix().endswith(
        "/mvp1-closure-c2-voice-parity/.runtime/asr-qualification/faster-whisper-small/models")


def test_c4_aggregate_reservations_include_cleanup_and_never_reset(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    ledger = budget.Budget(path)
    n = ledger.reserve("model", "direct_text", "compiler", "a" * 64, 180)
    ledger.mark_turn(n)
    ledger.finish(n, 1, "RETURNED")
    ledger.add_cleanup(n, 2)
    reopened = budget.Budget(path)
    assert reopened.snapshot()["resources"]["model"]["charged_seconds"] == 3
    reopened.hold_cleanup_failure(n)
    with pytest.raises(RuntimeError, match="unfinished_budget_reservation"):
        ledger.reserve("asr", "direct_voice", "native_inference", "b" * 64, 190)


def test_ledger_reads_git_unicode_path_as_utf8(tmp_path, monkeypatch):
    common = tmp_path / "ОРКЕСТРАТОР" / ".git"

    def output(*args, **kwargs):
        assert kwargs["encoding"] == "utf-8"
        return str(common)

    monkeypatch.setattr(budget.subprocess, "check_output", output)
    assert budget.ledger_path().is_relative_to(common.parent)


def test_source_guard_rejects_other_roots_and_cache(tmp_path):
    with pytest.raises(RuntimeError, match="run_must_stay_in_c4"):
        smoke.bind_sources(smoke.ROOT / "outside-c4", tmp_path)
    with pytest.raises(RuntimeError, match="model_must_be_pinned_c2_cache"):
        smoke.bind_sources((smoke.C4 / "guard").resolve(), tmp_path)


def test_freeze_guard_rejects_dirty_or_different_revision(monkeypatch):
    monkeypatch.setattr(smoke, "git", lambda *args: "b" * 40)
    with pytest.raises(RuntimeError, match="candidate_not_exact_clean_freeze"):
        smoke.assert_frozen({"candidate_revision": "a" * 40, "c4_sources": {}})
    monkeypatch.setattr(smoke, "git", lambda *args: "a" * 40 if args[0] == "rev-parse" else " M src/example.py")
    with pytest.raises(RuntimeError, match="candidate_not_exact_clean_freeze"):
        smoke.assert_frozen({"candidate_revision": "a" * 40, "c4_sources": {}})


@pytest.mark.asyncio
async def test_inspect_never_starts_product_or_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(smoke, "bind_sources", lambda *args: {"synthetic": True})
    monkeypatch.setattr(smoke, "ledger_path", lambda: tmp_path / "ledger.sqlite3")
    monkeypatch.setattr(smoke, "build_runtime", lambda *args: pytest.fail("inspection started product"))
    args = SimpleNamespace(run=tmp_path, model=tmp_path, scenario="direct_text", phase="inspect")
    await smoke.run(args)
    receipt = json.loads((tmp_path / "direct_text/inspect.json").read_text("utf-8"))
    assert receipt["inference"] is False
    assert receipt["budget"]["resources"]["model"]["reserved_calls"] == 0
    assert receipt["budget"]["resources"]["asr"]["reserved_calls"] == 0


@pytest.mark.asyncio
async def test_real_execution_requires_opt_in_before_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(smoke, "bind_sources", lambda *args: {"synthetic": True})
    monkeypatch.setattr(smoke, "ledger_path", lambda: tmp_path / "ledger.sqlite3")
    monkeypatch.setattr(smoke, "build_runtime", lambda *args: pytest.fail("unauthorized runtime"))
    args = SimpleNamespace(run=tmp_path, model=tmp_path, scenario="direct_text", phase="run", authorized_run=False)
    with pytest.raises(RuntimeError, match="explicit_authorized_run_required"):
        await smoke.run(args)


@pytest.mark.asyncio
async def test_frozen_primary_checks_bytes_before_reservation(tmp_path, monkeypatch):
    def changed(_binding):
        raise RuntimeError("source_changed_since_run_started")

    monkeypatch.setattr(smoke, "assert_frozen", changed)
    ledger = budget.Budget(tmp_path / "ledger.sqlite3")
    primary = SimpleNamespace(execute=lambda *args: pytest.fail("changed source started provider"))
    counted = smoke.FrozenPrimary(primary, ledger, budget.TurnBudget(ledger), "direct_text", "a" * 64, source_binding={})
    with pytest.raises(RuntimeError, match="source_changed"):
        await counted.execute(None)
    assert ledger.snapshot()["resources"]["model"]["reserved_calls"] == 0


@pytest.mark.asyncio
async def test_runtime_construction_and_close_do_not_start_inference(tmp_path, monkeypatch):
    monkeypatch.setattr(smoke.old, "cli_status", lambda *args: "CHATGPT")
    monkeypatch.setattr(smoke.c3, "CleanupObservedClient", lambda *args: pytest.fail("construction started SDK"))
    args = SimpleNamespace(codex_home=tmp_path / "empty-home", scenario="direct_text", diagnostic_repeat=False)
    args.codex_home.mkdir()
    ledger = budget.Budget(tmp_path / "ledger.sqlite3")
    runtime, state, api, control, counted, core, clock = smoke.build_runtime(args, tmp_path, {}, ledger)
    try:
        assert runtime._store.list_tasks(smoke.old.TENANT) == ()
        assert state.queue_counts() == (0, 0)
        assert counted.clients == []
    finally:
        await control.close()
        await runtime.close()
    assert ledger.snapshot()["resources"]["model"]["reserved_calls"] == 0
    assert ledger.snapshot()["resources"]["asr"]["reserved_calls"] == 0


@pytest.mark.asyncio
async def test_loopback_serves_exact_candidate_and_real_session_rotation(tmp_path):
    clock = smoke.Clock()
    core = MiniAppCore(store=SQLiteStore(tmp_path / "tasks.sqlite3"), bot_token=smoke.BOT_TOKEN,
        owner_user_id=smoke.old.USER, tenant_id=smoke.old.TENANT, clock=clock,
        session_ttl=timedelta(seconds=120))
    async with candidate_server(core) as origin:
        async with httpx.AsyncClient(base_url=origin, trust_env=False) as client:
            journey = smoke.HttpJourney(client, clock)
            await journey.authenticate()
            old_cookie = client.cookies.get("nobus_miniapp_recovery")
            response = await journey.request("GET", "/")
            assert response.content == (smoke.ROOT / "src/transport/miniapp_static/index.html").read_bytes()
            for name in ("app.js", "styles.css"):
                response = await journey.request("GET", "/" + name)
                assert response.content == (smoke.ROOT / "src/transport/miniapp_static" / name).read_bytes()
            await journey.expire_and_recover()
            assert client.cookies.get("nobus_miniapp_recovery") != old_cookie
            assert (await journey.request("GET", "/api/tasks")).json() == {"tasks": []}
            await journey.request("GET", "/api/requests/c4-unknown-request-0001", expected=404)
            # The synthetic signer is a local test input, not live initData proof.
            assert all("token" not in row and "headers" not in row for row in journey.receipts)


def test_synthetic_fixtures_preserve_text_voice_material_parity():
    assert smoke.fixture("direct_text") == smoke.fixture("direct_voice")
    assert smoke.fixture("direct_text") == smoke.fixture("telegram_text")
    assert "telegram_text" in smoke.TELEGRAM_SCENARIOS
    assert smoke.fixture("transform_text") == smoke.fixture("transform_voice")
    assert "не надо" in smoke.fixture("transform_voice")
    with pytest.raises(RuntimeError, match="scenario_not_authorized"):
        smoke.fixture("private")


@pytest.mark.asyncio
@pytest.mark.parametrize("corruption", (None, "local_file", "part_digest", "receipt_digest", "missing_part", "outbox", "alias"))
async def test_actual_store_delivery_http_alias_and_corruption(tmp_path, monkeypatch, corruption):
    """Real sealed-result recovery and delivery; no SDK, inference or fake Core."""
    from tests import test_c3_result_recovery as sealed

    monkeypatch.setattr(smoke.old, "TENANT", "tenant-a")
    # A long Unicode answer stays within the accepted 3400-codepoint cap.
    monkeypatch.setattr(sealed, "ANSWER", "Синтетическая последовательность: " + "𝛼" * 3200)
    runtime = sealed.runtime(tmp_path)
    prepared, incoming, task = await sealed.seal(runtime)
    assert await runtime.recover_prepared(prepared, incoming) is False
    state = smoke.old.SQLiteTelegramState(tmp_path / "telegram.sqlite3")
    api = smoke.LocalTransport(tmp_path)
    sender = smoke.old.TelegramStatusSender(api, {"tenant-a": (sealed.DESTINATION, smoke.old.USER)}, technical_details=False)
    delivered = await runtime.deliver_pending("tenant-a", sender)
    assert len(delivered) == 1 and delivered[0].status.value == "acked"
    immutable = smoke.old.artifact_for_message(delivered[0])
    assert immutable is not None
    assert immutable.filename == f"nobus-result-{task.id}.txt"
    assert [row["filename"] for row in api.rows if row["kind"] == "document"] == ["nobus-result.txt"]
    clock = smoke.Clock()
    core = MiniAppCore(store=runtime._store, bot_token=smoke.BOT_TOKEN,
        owner_user_id=smoke.old.USER, tenant_id="tenant-a", clock=clock)
    async with candidate_server(core) as origin, httpx.AsyncClient(base_url=origin, trust_env=False) as client:
        journey = smoke.HttpJourney(client, clock)
        await journey.authenticate()
        result = await smoke.compare_result(journey, runtime, state, api, tmp_path, str(task.id))
        assert result["artifact_id"] == str(immutable.artifact_id)
        assert result["artifact_digest"] == immutable.content_digest
        assert result["confirmed_parts"] >= 2  # Complete text plus the one document.
        parts = runtime._store.read_delivery_parts("tenant-a", delivered[0].message_id)
        assert all(receipt is not None and receipt.part_id == part.part_id for part, receipt in parts)
        assert {part.manifest_digest for part, _ in parts} == {result["delivery_manifest_digest"]}
        await journey.request("GET", f"/api/tasks/{task.id}/artifacts/{uuid4()}?revision={task.result_revision}", expected=404)
        if corruption is None:
            before = list(api.rows)
            assert await runtime.deliver_pending("tenant-a", sender) == ()
            assert api.rows == before
            return
        if corruption == "local_file":
            (tmp_path / "artifacts/nobus-result.txt").write_bytes(b"corrupt")
        elif corruption == "alias":
            next(row for row in api.rows if row["kind"] == "document")["filename"] = immutable.filename
        else:
            with sqlite3.connect(tmp_path / "tasks.sqlite3") as db:
                if corruption in {"part_digest", "receipt_digest"}:
                    db.execute(f"UPDATE outbox_delivery_parts SET {corruption}='bad'")
                elif corruption == "missing_part":
                    db.execute("DELETE FROM outbox_delivery_parts WHERE part_index=0")
                else:
                    raw = json.loads(db.execute("SELECT message_json FROM outbox_messages").fetchone()[0])
                    raw["user_message"] = "corrupt"
                    db.execute("UPDATE outbox_messages SET message_json=?", (json.dumps(raw),))
        # Corrupt authoritative or received bytes cannot produce a PASS receipt.
        with pytest.raises(RuntimeError):
            await smoke.compare_result(journey, runtime, state, api, tmp_path, str(task.id))
        if corruption == "outbox":
            response = await journey.request("GET", f"/api/tasks/{task.id}/artifacts/{immutable.artifact_id}?revision={task.result_revision}", expected=503)
            assert response.json()["detail"] == "Nobus Space временно недоступен"
        elif corruption in {"part_digest", "receipt_digest", "missing_part"}:
            # Delivery evidence is required for this smoke's PASS, but a damaged
            # Telegram receipt does not invalidate independently bound file bytes.
            response = await journey.request("GET", f"/api/tasks/{task.id}/artifacts/{immutable.artifact_id}?revision={task.result_revision}")
            assert response.content == immutable.content_bytes()
