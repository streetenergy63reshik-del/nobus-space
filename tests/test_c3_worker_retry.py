"""C3 model retry: one identity, bounded generations and no effect authority."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from openai_codex.errors import (
    InvalidParamsError,
    InvalidRequestError,
    MethodNotFoundError,
    ParseError,
)

from src.core.policy import task_contract_digest
from src.workers.codex_cli import CodexCliError, CodexCliResult
from src.workers.codex_sdk import CodexSdkAdapter, ResilientCodexAdapter
from tests.test_codex_sdk import _Client, _Thread, _Turn, _contract, _paths


class _NoFallback:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, contract):
        self.calls += 1
        raise AssertionError("non-web must never reach the CLI fallback")

    async def verify(self, url, quote):
        raise AssertionError("non-web must never verify web sources")


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ("worker_start_failed", "worker_failed"))
async def test_non_web_transient_retry_keeps_exact_contract(tmp_path, code):
    class Primary:
        def __init__(self):
            self.calls = []

        async def execute(self, contract):
            self.calls.append(contract)
            if len(self.calls) == 1:
                raise CodexCliError(code)
            return CodexCliResult(message='{"answer":"ready"}')

    contract = _contract(tmp_path)
    digest = task_contract_digest(contract)
    primary, forbidden = Primary(), _NoFallback()
    result = await ResilientCodexAdapter(primary, forbidden, forbidden).execute(contract)
    assert result.message == '{"answer":"ready"}'
    assert len(primary.calls) == 2
    assert all(value is contract for value in primary.calls)
    assert all(task_contract_digest(value) == digest for value in primary.calls)
    assert forbidden.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "calls"),
    (
        ("worker_failed", 2),
        ("worker_start_failed", 2),
        ("worker_protocol_error", 1),
        ("worker_forbidden", 1),
        ("worker_configuration_invalid", 1),
        ("worker_timeout", 1),
        ("worker_output_too_large", 1),
        ("worker_context_unavailable", 1),
    ),
)
async def test_non_web_retry_closed_failure_policy(tmp_path, code, calls):
    class Primary:
        count = 0

        async def execute(self, contract):
            self.count += 1
            raise CodexCliError(code)

    primary, forbidden = Primary(), _NoFallback()
    with pytest.raises(CodexCliError) as failure:
        await ResilientCodexAdapter(primary, forbidden, forbidden).execute(_contract(tmp_path))
    assert failure.value.code == code
    assert primary.count == calls
    assert forbidden.calls == 0


@pytest.mark.asyncio
async def test_non_web_retry_uses_fresh_sdk_generation(tmp_path):
    class FailedTurn(_Turn):
        async def run(self):
            raise RuntimeError("synthetic transport interruption")

    class FailedThread(_Thread):
        async def turn(self, prompt, **kwargs):
            return FailedTurn("late stale output must be ignored")

    class FailedClient(_Client):
        async def thread_start(self, **kwargs):
            self.start_values.append(kwargs)
            return FailedThread("failed", self.response)

    owner, workspace, home, temp = _paths(tmp_path)
    failed, recovered = FailedClient(), _Client()
    clients = iter((failed, recovered))
    primary = CodexSdkAdapter(
        workspace_root=workspace, owner_root=owner, codex_home=home,
        temp_root=temp, client_factory=lambda _: next(clients),
    )
    forbidden = _NoFallback()
    wrapper = ResilientCodexAdapter(primary, forbidden, forbidden)
    contract = _contract(workspace).model_copy(update={"quality_profile": "gate-c1-semantic-no-effect@1"})
    assert primary.generation_available is False
    result = await wrapper.execute(contract)
    assert json.loads(result.message) == {"answer": "ok"}
    assert failed.closed and recovered.entered
    assert len(failed.start_values) == len(recovered.start_values) == 1
    assert failed.start_values[0] == recovered.start_values[0]
    assert wrapper.generation_available is True
    await primary._invalidate_client(recovered)
    assert wrapper.generation_available is False
    await primary.close()
    assert wrapper.generation_available is False
    assert forbidden.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", (ParseError, InvalidRequestError, MethodNotFoundError, InvalidParamsError))
@pytest.mark.parametrize("stage", ("start", "turn"))
async def test_typed_permanent_sdk_error_is_not_transient(tmp_path, error_type, stage):
    error = error_type(-32600, "synthetic rejected request")

    class FailedTurn(_Turn):
        async def run(self):
            raise error

    class FailedThread(_Thread):
        async def turn(self, prompt, **kwargs):
            return FailedTurn("unused")

    class Client(_Client):
        async def thread_start(self, **kwargs):
            self.start_values.append(kwargs)
            if stage == "start":
                raise error
            return FailedThread("permanent", self.response)

    owner, workspace, home, temp = _paths(tmp_path)
    client = Client()
    primary = CodexSdkAdapter(
        workspace_root=workspace, owner_root=owner, codex_home=home,
        temp_root=temp, client_factory=lambda _: client,
    )
    forbidden = _NoFallback()
    with pytest.raises(CodexCliError) as failure:
        await ResilientCodexAdapter(primary, forbidden, forbidden).execute(_contract(workspace))
    assert failure.value.code == "worker_protocol_error"
    assert "synthetic" not in str(failure.value)
    assert len(client.start_values) == 1
    assert forbidden.calls == 0
    await primary.close()


@pytest.mark.asyncio
async def test_retry_deadline_is_shared_and_rejects_late_result(monkeypatch):
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(
        "src.workers.codex_sdk.asyncio.get_running_loop",
        lambda: SimpleNamespace(time=lambda: clock.now),
    )

    class Primary:
        calls = 0

        async def execute(self, contract):
            self.calls += 1
            if self.calls == 1:
                clock.now = 0.03
                raise CodexCliError("worker_failed")
            clock.now = 0.06
            return CodexCliResult(message='{"answer":"late"}')

    # Fractional time is a test-only clock fixture; production contracts use seconds.
    contract = SimpleNamespace(permissions=("model.inference",), conversation_ref=None, timeout_seconds=0.05)
    primary, forbidden = Primary(), _NoFallback()
    with pytest.raises(CodexCliError) as failure:
        await ResilientCodexAdapter(primary, forbidden, forbidden).execute(contract)
    assert failure.value.code == "worker_timeout"
    assert primary.calls == 2


@pytest.mark.asyncio
async def test_cancellation_is_not_retried():
    started = asyncio.Event()

    class Primary:
        calls = 0

        async def execute(self, contract):
            self.calls += 1
            started.set()
            await asyncio.Event().wait()

    primary, forbidden = Primary(), _NoFallback()
    contract = SimpleNamespace(permissions=("model.inference",), conversation_ref=None, timeout_seconds=10)
    execution = asyncio.create_task(ResilientCodexAdapter(primary, forbidden, forbidden).execute(contract))
    await started.wait()
    execution.cancel()
    with pytest.raises(asyncio.CancelledError):
        await execution
    assert primary.calls == 1
    assert forbidden.calls == 0


@pytest.mark.asyncio
async def test_previous_web_context_is_bound_to_tenant(tmp_path):
    class Primary:
        calls = []

        async def execute(self, contract):
            self.calls.append(contract)
            return CodexCliResult(message='{"answer":"ready"}')

    primary, forbidden = Primary(), _NoFallback()
    wrapper = ResilientCodexAdapter(primary, forbidden, forbidden)
    original = _contract(tmp_path, conversation_ref="telegram:" + "a" * 40)
    wrapper.remember_delivered(original, CodexCliResult(message="synthetic tenant A answer", source_urls=("https://example.com",)))
    await wrapper.execute(original.model_copy(update={"tenant_id": "tenant-b"}))
    assert "synthetic tenant A answer" not in primary.calls[-1].instruction
    await wrapper.execute(original)
    assert "synthetic tenant A answer" in primary.calls[-1].instruction


@pytest.mark.asyncio
async def test_late_abandoned_generation_output_cannot_replace_fresh_result(tmp_path, monkeypatch):
    late = asyncio.Event()
    old_tasks = []
    monkeypatch.setattr("src.workers.codex_sdk._CONTROL_TIMEOUT_SECONDS", 0.01)

    class LateTurn(_Turn):
        async def run(self):
            old_tasks.append(asyncio.current_task())
            while not late.is_set():
                try:
                    await late.wait()
                except asyncio.CancelledError:
                    pass
            return SimpleNamespace(final_response='{"answer":"stale"}')

        async def interrupt(self):
            pass  # The old generation ignores interrupt and repeated cancellation.

    class LateThread(_Thread):
        async def turn(self, prompt, **kwargs):
            return LateTurn("unused")

    class LateClient(_Client):
        async def thread_start(self, **kwargs):
            return LateThread("abandoned", self.response)

    owner, workspace, home, temp = _paths(tmp_path)
    old, fresh = LateClient(), _Client()
    clients = iter((old, fresh))
    primary = CodexSdkAdapter(workspace_root=workspace, owner_root=owner,
        codex_home=home, temp_root=temp, client_factory=lambda _: next(clients))
    contract = _contract(workspace).model_copy(update={"timeout_seconds": 0.2})
    try:
        with pytest.raises(CodexCliError) as failure:
            await primary.execute(contract)
        assert failure.value.code == "worker_timeout"
        assert old.closed and not old_tasks[0].done()
        # Explicit second invocation represents generation recovery. The retry
        # policy above still never retries a timeout automatically.
        result = await primary.execute(contract)
        assert json.loads(result.message) == {"answer": "ok"}
        late.set()
        abandoned = await old_tasks[0]
        assert json.loads(abandoned.final_response) == {"answer": "stale"}
        assert json.loads(result.message) == {"answer": "ok"}
        assert primary._client is fresh
        assert all(client is fresh for client, _ in primary._threads.values())
    finally:
        late.set()
        await asyncio.gather(*old_tasks, return_exceptions=True)
        await primary.close()
