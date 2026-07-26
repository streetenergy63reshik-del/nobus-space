"""Contract tests for the persistent official Codex SDK boundary."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from openai_codex.generated.v2_all import (
    OpenPageWebSearchAction,
    SearchWebSearchAction,
    ThreadItem,
    WebSearchAction,
    WebSearchThreadItem,
)

from src.contracts import RiskLevel, TaskContract
from src.workers.codex_cli import CodexCliError, CodexCliResult
from src.workers.codex_sdk import CodexSdkAdapter, ResilientCodexAdapter


class _Turn:
    def __init__(self, response: str) -> None:
        self._response = response
        self.interrupted = False

    async def run(self):
        return SimpleNamespace(final_response=self._response)

    async def interrupt(self) -> None:
        self.interrupted = True


class _Thread:
    def __init__(self, thread_id: str, response: str) -> None:
        self.id = thread_id
        self.name: str | None = None
        self._response = response
        self.turns: list[dict[str, object]] = []

    async def turn(self, prompt: str, **values: object) -> _Turn:
        self.turns.append({"prompt": prompt, **values})
        return _Turn(self._response)

    async def set_name(self, name: str) -> None:
        self.name = name


class _Client:
    def __init__(
        self,
        response: str = '{"kind":"answer","answer":"ok","summary":null,"patch":null,"paths":null}',
        listed: tuple[object, ...] = (),
    ) -> None:
        self.response = response
        self.listed = listed
        self.started: list[_Thread] = []
        self.start_values: list[dict[str, object]] = []
        self.resumed: list[_Thread] = []
        self.closed = False
        self.entered = False

    async def __aenter__(self):
        self.entered = True
        return self

    async def thread_list(self, **_: object):
        return SimpleNamespace(data=list(self.listed), next_cursor=None)

    async def thread_start(self, **values: object) -> _Thread:
        thread = _Thread(f"started-{len(self.started)}", self.response)
        self.started.append(thread)
        self.start_values.append(values)
        return thread

    async def thread_resume(self, thread_id: str, **_: object) -> _Thread:
        thread = _Thread(thread_id, self.response)
        self.resumed.append(thread)
        return thread

    async def close(self) -> None:
        self.closed = True


def _paths(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    owner = tmp_path / "owner"
    workspace = owner / "project"
    home = tmp_path / "codex-home"
    temp = tmp_path / "temp"
    for path in (workspace, home, temp):
        path.mkdir(parents=True)
    return owner, workspace, home, temp


def _contract(
    workspace: Path,
    *,
    source: str = "telegram:one",
    conversation_ref: str | None = None,
    permissions: tuple[str, ...] = ("model.inference",),
) -> TaskContract:
    return TaskContract(
        task_id=uuid4(),
        idempotency_key=uuid4().hex,
        ingress_digest="sha256:" + "0" * 64,
        tenant_id="owner",
        source=source,
        conversation_ref=conversation_ref,
        instruction="Ответь кратко.",
        allowed_paths=(str(workspace),),
        permissions=permissions,
        risk=RiskLevel.LOW,
        acceptance_criteria=("Return a useful answer.",),
        timeout_seconds=5,
        quality_profile="answer@1",
    )


@pytest.mark.asyncio
async def test_sdk_starts_persistent_named_thread_and_validates_result(
    tmp_path: Path,
) -> None:
    owner, workspace, home, temp = _paths(tmp_path)
    client = _Client('{"kind":"answer","answer":"Готово","summary":null,"patch":null,"paths":null}')
    adapter = CodexSdkAdapter(
        workspace_root=workspace,
        owner_root=owner,
        codex_home=home,
        temp_root=temp,
        client_factory=lambda _: client,
    )

    result = await adapter.execute(_contract(workspace))

    assert json.loads(result.message) == {"answer": "Готово"}
    assert client.entered is True
    assert len(client.started) == 1
    assert client.started[0].name is not None
    assert client.started[0].name.startswith("nobus:")
    assert len(client.started[0].turns) == 1


@pytest.mark.asyncio
async def test_sdk_reuses_thread_in_process(tmp_path: Path) -> None:
    owner, workspace, home, temp = _paths(tmp_path)
    client = _Client()
    adapter = CodexSdkAdapter(
        workspace_root=workspace,
        owner_root=owner,
        codex_home=home,
        temp_root=temp,
        client_factory=lambda _: client,
    )
    contract = _contract(workspace)

    await adapter.execute(contract)
    await adapter.execute(contract.model_copy(update={"task_id": uuid4()}))

    assert len(client.started) == 1
    assert len(client.started[0].turns) == 2


@pytest.mark.asyncio
async def test_sdk_web_turns_use_fresh_ephemeral_threads(tmp_path: Path) -> None:
    owner, workspace, home, temp = _paths(tmp_path)
    client = _Client()
    adapter = CodexSdkAdapter(
        workspace_root=workspace,
        owner_root=owner,
        codex_home=home,
        temp_root=temp,
        client_factory=lambda _: client,
    )
    contract = _contract(
        workspace,
        permissions=("model.inference", "web.search"),
    )

    await adapter.execute(contract)
    await adapter.execute(contract)

    assert len(client.started) == 2
    assert all(value["ephemeral"] is True for value in client.start_values)
    assert all(thread.name is None for thread in client.started)
    assert not client.resumed


@pytest.mark.asyncio
async def test_sdk_resumes_named_persistent_thread_after_restart(
    tmp_path: Path,
) -> None:
    owner, workspace, home, temp = _paths(tmp_path)
    contract = _contract(workspace)
    name = CodexSdkAdapter._session_name(contract, workspace)
    listed = SimpleNamespace(name=name, id="saved", ephemeral=False)
    client = _Client(listed=(listed,))
    adapter = CodexSdkAdapter(
        workspace_root=workspace,
        owner_root=owner,
        codex_home=home,
        temp_root=temp,
        client_factory=lambda _: client,
    )

    await adapter.execute(contract)

    assert not client.started
    assert [thread.id for thread in client.resumed] == ["saved"]


@pytest.mark.asyncio
async def test_sdk_isolates_sources_into_distinct_threads(tmp_path: Path) -> None:
    owner, workspace, home, temp = _paths(tmp_path)
    client = _Client()
    adapter = CodexSdkAdapter(
        workspace_root=workspace,
        owner_root=owner,
        codex_home=home,
        temp_root=temp,
        client_factory=lambda _: client,
    )

    await adapter.execute(_contract(workspace, source="telegram:chat-a"))
    await adapter.execute(_contract(workspace, source="telegram:chat-b"))

    assert len(client.started) == 2
    assert client.started[0].name != client.started[1].name


def test_sdk_isolates_conversations_without_overloading_trust_source(
    tmp_path: Path,
) -> None:
    _, workspace, _, _ = _paths(tmp_path)
    first = _contract(
        workspace,
        source="telegram",
        conversation_ref="telegram:" + "a" * 40,
    )
    second = _contract(
        workspace,
        source="telegram",
        conversation_ref="telegram:" + "b" * 40,
    )

    assert first.source == second.source == "telegram"
    assert CodexSdkAdapter._session_name(
        first, workspace
    ) != CodexSdkAdapter._session_name(second, workspace)


def test_sdk_session_identity_includes_capabilities(tmp_path: Path) -> None:
    _, workspace, _, _ = _paths(tmp_path)
    plain = _contract(workspace)
    web = _contract(
        workspace,
        permissions=("model.inference", "web.search"),
    )

    assert CodexSdkAdapter._session_name(
        plain, workspace
    ) != CodexSdkAdapter._session_name(web, workspace)


@pytest.mark.asyncio
async def test_sdk_rejects_invalid_final_protocol(tmp_path: Path) -> None:
    owner, workspace, home, temp = _paths(tmp_path)
    client = _Client('{"kind":"answer","answer":"ok","extra":true}')
    adapter = CodexSdkAdapter(
        workspace_root=workspace,
        owner_root=owner,
        codex_home=home,
        temp_root=temp,
        client_factory=lambda _: client,
    )

    with pytest.raises(CodexCliError, match="invalid output"):
        await adapter.execute(_contract(workspace))


@pytest.mark.asyncio
async def test_sdk_invalidates_failed_app_server_before_retry(
    tmp_path: Path,
) -> None:
    class FailingTurn(_Turn):
        async def run(self):
            raise RuntimeError("transport failed")

    class FailingThread(_Thread):
        async def turn(self, prompt: str, **values: object) -> FailingTurn:
            self.turns.append({"prompt": prompt, **values})
            return FailingTurn(self._response)

    class FailingClient(_Client):
        async def thread_start(self, **values: object) -> FailingThread:
            thread = FailingThread("failed", self.response)
            self.started.append(thread)
            self.start_values.append(values)
            return thread

    owner, workspace, home, temp = _paths(tmp_path)
    failed = FailingClient()
    recovered = _Client()
    clients = iter((failed, recovered))
    adapter = CodexSdkAdapter(
        workspace_root=workspace,
        owner_root=owner,
        codex_home=home,
        temp_root=temp,
        client_factory=lambda _: next(clients),
    )

    with pytest.raises(CodexCliError, match="worker failed"):
        await adapter.execute(_contract(workspace))
    result = await adapter.execute(
        _contract(workspace).model_copy(update={"task_id": uuid4()})
    )

    assert failed.closed is True
    assert recovered.entered is True
    assert json.loads(result.message) == {"answer": "ok"}


@pytest.mark.asyncio
async def test_resilient_adapter_falls_back_only_for_web_transport_failure(
    tmp_path: Path,
) -> None:
    class Verifier:
        async def verify(self, url: str, quote: str) -> bool:
            return url == "https://example.com"

        async def aclose(self) -> None:
            return None

    class Worker:
        def __init__(self, result=None, error: str | None = None) -> None:
            self.result = result
            self.error = error
            self.calls: list[TaskContract] = []

        async def execute(self, contract: TaskContract):
            self.calls.append(contract)
            if self.error is not None:
                raise CodexCliError(self.error)
            return self.result

        async def close(self) -> None:
            return None

    _, workspace, _, _ = _paths(tmp_path)
    contract = _contract(workspace).model_copy(
        update={
            "permissions": (
                "model.inference",
                "owner.library.read",
                "web.search",
            )
        }
    )
    recovered = CodexCliResult(
        message='{"kind":"answer","answer":"ok https://example.com [source_quote: safe source content from page]","summary":null,"patch":null,"paths":null}',
        web_search_observed=True,
    )
    primary = Worker(error="worker_failed")
    fallback = Worker(result=recovered)
    adapter = ResilientCodexAdapter(primary, fallback, Verifier())

    result = await adapter.execute(contract)
    assert result == recovered.model_copy(
        update={
            "message": (
                '{"kind":"answer","answer":"ok https://example.com","summary":null,"patch":null,"paths":null}'
            ),
            "fallback_used": True,
            "source_urls": ("https://example.com",),
        }
    )
    adapter.remember_delivered(contract, result)
    assert primary.calls == [contract]
    assert fallback.calls[0].permissions == contract.permissions

    non_web = contract.model_copy(update={"permissions": ("model.inference",)})
    with pytest.raises(CodexCliError, match="worker failed"):
        await adapter.execute(non_web)
    assert len(fallback.calls) == 1


@pytest.mark.asyncio
async def test_resilient_adapter_verifies_cited_fallback_urls(
    tmp_path: Path,
) -> None:
    class Primary:
        async def execute(self, contract):
            raise CodexCliError("worker_failed")

        async def close(self):
            return None

    class Fallback:
        async def execute(self, contract):
            return CodexCliResult(
                message='{"answer":"https://example.com [source_quote: safe source content from page] https://spoof.invalid [source_quote: spoof source content from page]"}',
                web_search_observed=True,
            )

    class Verifier:
        async def verify(self, url, quote):
            return url == "https://example.com"

    _, workspace, _, _ = _paths(tmp_path)
    contract = _contract(workspace).model_copy(
        update={
            "permissions": (
                "model.inference",
                "owner.library.read",
                "web.search",
            )
        }
    )
    result = await ResilientCodexAdapter(
        Primary(), Fallback(), Verifier()
    ).execute(contract)

    assert result.source_urls == ("https://example.com",)


@pytest.mark.asyncio
async def test_resilient_adapter_uses_each_transport_once(tmp_path: Path) -> None:
    class Worker:
        def __init__(self, result):
            self.result = result
            self.calls = 0

        async def execute(self, contract):
            self.calls += 1
            return self.result

        async def close(self):
            return None

    class Verifier:
        async def verify(self, url, quote):
            return True

    _, workspace, _, _ = _paths(tmp_path)
    contract = _contract(workspace).model_copy(
        update={"permissions": ("model.inference", "web.search")}
    )
    primary = Worker(CodexCliResult(message='{"answer":"no source"}'))
    fallback = Worker(
        CodexCliResult(
            message='{"answer":"https://example.com [source_quote: safe source content from page]"}',
            web_search_observed=True,
        )
    )
    result = await ResilientCodexAdapter(
        primary, fallback, Verifier()
    ).execute(contract)

    assert result.source_urls == ("https://example.com",)
    assert primary.calls == fallback.calls == 1


@pytest.mark.asyncio
async def test_resilient_adapter_carries_fallback_context_to_next_turn(
    tmp_path: Path,
) -> None:
    class Primary:
        def __init__(self):
            self.calls = []

        async def execute(self, contract):
            self.calls.append(contract)
            if len(self.calls) == 1:
                raise CodexCliError("worker_failed")
            return CodexCliResult(message='{"answer":"follow-up"}')

        async def close(self):
            return None

    class Fallback:
        async def execute(self, contract):
            return CodexCliResult(
                message='{"answer":"research https://example.com [source_quote: safe source content from page]"}',
                web_search_observed=True,
            )

    class Verifier:
        async def verify(self, url, quote):
            return True

    _, workspace, _, _ = _paths(tmp_path)
    reference = "telegram:" + "c" * 40
    first = _contract(workspace).model_copy(
        update={
            "permissions": ("model.inference", "web.search"),
            "conversation_ref": reference,
        }
    )
    primary = Primary()
    adapter = ResilientCodexAdapter(primary, Fallback(), Verifier())
    result = await adapter.execute(first)
    adapter.remember_delivered(first, result)
    second = first.model_copy(
        update={"task_id": uuid4(), "instruction": "continue"}
    )
    await adapter.execute(second)

    assert "previous_verified_web_answer" in primary.calls[1].instruction
    assert "research https://example.com" in primary.calls[1].instruction
    assert primary.calls[1].instruction.endswith("continue")


@pytest.mark.asyncio
async def test_resilient_adapter_remembers_delivered_primary_web_once(
    tmp_path: Path,
) -> None:
    class Primary:
        def __init__(self):
            self.calls = []

        async def execute(self, contract):
            self.calls.append(contract)
            if len(self.calls) == 1:
                return CodexCliResult(
                    message='{"answer":"accepted primary answer"}',
                    source_urls=("https://example.com",),
                )
            return CodexCliResult(message='{"answer":"follow-up"}')

        async def close(self):
            return None

    class Fallback:
        async def execute(self, contract):
            raise AssertionError("verified primary must not use fallback")

    class Verifier:
        async def verify(self, url, quote):
            raise AssertionError("verified primary source is SDK-owned evidence")

    _, workspace, _, _ = _paths(tmp_path)
    reference = "telegram:" + "d" * 40
    first = _contract(workspace).model_copy(
        update={
            "permissions": ("model.inference", "web.search"),
            "conversation_ref": reference,
        }
    )
    primary = Primary()
    adapter = ResilientCodexAdapter(primary, Fallback(), Verifier())
    result = await adapter.execute(first)
    adapter.remember_delivered(first, result)
    second = first.model_copy(
        update={
            "task_id": uuid4(),
            "instruction": "continue",
            "permissions": ("model.inference",),
        }
    )
    await adapter.execute(second)

    instruction = primary.calls[1].instruction
    assert instruction.count("previous_verified_web_answer") == 2
    assert instruction.count("accepted primary answer") == 1
    assert instruction.endswith("continue")


@pytest.mark.asyncio
async def test_resilient_adapter_does_not_remember_unverified_fallback(
    tmp_path: Path,
) -> None:
    class Primary:
        def __init__(self):
            self.calls = []

        async def execute(self, contract):
            self.calls.append(contract)
            if len(self.calls) == 1:
                raise CodexCliError("worker_failed")
            return CodexCliResult(message='{"answer":"follow-up"}')

        async def close(self):
            return None

    class Fallback:
        async def execute(self, contract):
            return CodexCliResult(
                message='{"answer":"unverified https://spoof.invalid [source_quote: spoof source content from page]"}',
                web_search_observed=True,
            )

    class Verifier:
        async def verify(self, url, quote):
            return False

    _, workspace, _, _ = _paths(tmp_path)
    reference = "telegram:" + "u" * 40
    first = _contract(workspace).model_copy(
        update={
            "permissions": ("model.inference", "web.search"),
            "conversation_ref": reference,
        }
    )
    primary = Primary()
    adapter = ResilientCodexAdapter(primary, Fallback(), Verifier())
    result = await adapter.execute(first)
    assert result.source_urls == ()

    second = first.model_copy(
        update={"task_id": uuid4(), "instruction": "continue"}
    )
    await adapter.execute(second)

    assert primary.calls[1].instruction == "continue"


@pytest.mark.asyncio
async def test_failed_generation_drains_parallel_peer_before_close(
    tmp_path: Path,
) -> None:
    peer_started = asyncio.Event()
    release_peer = asyncio.Event()

    class PeerTurn(_Turn):
        async def run(self):
            peer_started.set()
            await release_peer.wait()
            return SimpleNamespace(final_response=self._response)

    class FailingTurn(_Turn):
        async def run(self):
            await peer_started.wait()
            raise RuntimeError("transport failed")

    class PeerThread(_Thread):
        async def turn(self, prompt: str, **values: object) -> PeerTurn:
            self.turns.append({"prompt": prompt, **values})
            return PeerTurn(self._response)

    class FailingThread(_Thread):
        async def turn(self, prompt: str, **values: object) -> FailingTurn:
            self.turns.append({"prompt": prompt, **values})
            return FailingTurn(self._response)

    class ParallelClient(_Client):
        async def thread_start(self, **values: object) -> _Thread:
            thread: _Thread
            if not self.started:
                thread = PeerThread("peer", self.response)
            else:
                thread = FailingThread("failing", self.response)
            self.started.append(thread)
            self.start_values.append(values)
            return thread

    owner, workspace, home, temp = _paths(tmp_path)
    failed = ParallelClient()
    recovered = _Client()
    clients = iter((failed, recovered))
    adapter = CodexSdkAdapter(
        workspace_root=workspace,
        owner_root=owner,
        codex_home=home,
        temp_root=temp,
        client_factory=lambda _: next(clients),
    )
    peer = asyncio.create_task(
        adapter.execute(_contract(workspace, source="telegram:peer"))
    )
    await asyncio.wait_for(peer_started.wait(), timeout=1)

    with pytest.raises(CodexCliError, match="worker failed"):
        await adapter.execute(_contract(workspace, source="telegram:failing"))
    assert failed.closed is False

    release_peer.set()
    result = await peer
    assert json.loads(result.message) == {"answer": "ok"}
    assert failed.closed is True

    recovered_result = await adapter.execute(
        _contract(workspace, source="telegram:recovered")
    )
    assert recovered.entered is True
    assert json.loads(recovered_result.message) == {"answer": "ok"}


@pytest.mark.asyncio
async def test_unclean_interrupt_retires_client_before_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StuckTurn:
        async def run(self):
            await asyncio.Event().wait()

        async def interrupt(self) -> None:
            raise RuntimeError("interrupt failed")

    class StuckThread(_Thread):
        async def turn(self, prompt: str, **values: object) -> StuckTurn:
            self.turns.append({"prompt": prompt, **values})
            return StuckTurn()

    class StuckClient(_Client):
        async def thread_start(self, **values: object) -> StuckThread:
            thread = StuckThread("stuck", self.response)
            self.started.append(thread)
            self.start_values.append(values)
            return thread

    monkeypatch.setattr("src.workers.codex_sdk._CONTROL_TIMEOUT_SECONDS", 0.01)
    owner, workspace, home, temp = _paths(tmp_path)
    stuck = StuckClient()
    recovered = _Client()
    clients = iter((stuck, recovered))
    adapter = CodexSdkAdapter(
        workspace_root=workspace,
        owner_root=owner,
        codex_home=home,
        temp_root=temp,
        max_timeout_seconds=1,
        client_factory=lambda _: next(clients),
    )

    with pytest.raises(CodexCliError, match="timed out"):
        await adapter.execute(
            _contract(workspace).model_copy(update={"timeout_seconds": 1})
        )
    assert stuck.closed is True

    result = await adapter.execute(
        _contract(workspace).model_copy(update={"timeout_seconds": 1})
    )
    assert recovered.entered is True
    assert json.loads(result.message) == {"answer": "ok"}


@pytest.mark.asyncio
async def test_cancellation_during_timeout_cleanup_propagates(
    tmp_path: Path,
) -> None:
    interrupt_started = asyncio.Event()
    release_interrupt = asyncio.Event()

    class SlowCleanupTurn:
        async def run(self):
            await asyncio.Event().wait()

        async def interrupt(self) -> None:
            interrupt_started.set()
            await release_interrupt.wait()

    class SlowCleanupThread(_Thread):
        async def turn(self, prompt: str, **values: object) -> SlowCleanupTurn:
            self.turns.append({"prompt": prompt, **values})
            return SlowCleanupTurn()

    class SlowCleanupClient(_Client):
        async def thread_start(self, **values: object) -> SlowCleanupThread:
            thread = SlowCleanupThread("slow-cleanup", self.response)
            self.started.append(thread)
            self.start_values.append(values)
            return thread

    owner, workspace, home, temp = _paths(tmp_path)
    client = SlowCleanupClient()
    adapter = CodexSdkAdapter(
        workspace_root=workspace,
        owner_root=owner,
        codex_home=home,
        temp_root=temp,
        max_timeout_seconds=1,
        client_factory=lambda _: client,
    )
    execution = asyncio.create_task(
        adapter.execute(
            _contract(workspace).model_copy(update={"timeout_seconds": 1})
        )
    )
    await asyncio.wait_for(interrupt_started.wait(), timeout=2)
    execution.cancel()
    await asyncio.sleep(0)
    execution.cancel()
    release_interrupt.set()

    with pytest.raises(asyncio.CancelledError):
        await execution


@pytest.mark.asyncio
async def test_failed_client_enter_is_closed(tmp_path: Path) -> None:
    class EnterFailureClient(_Client):
        async def __aenter__(self):
            self.entered = True
            raise RuntimeError("start failed")

    owner, workspace, home, temp = _paths(tmp_path)
    client = EnterFailureClient()
    adapter = CodexSdkAdapter(
        workspace_root=workspace,
        owner_root=owner,
        codex_home=home,
        temp_root=temp,
        client_factory=lambda _: client,
    )

    with pytest.raises(CodexCliError, match="could not be started"):
        await adapter.execute(_contract(workspace))

    assert client.closed is True




@pytest.mark.asyncio
async def test_repeated_cancellation_cannot_interrupt_release_drain(
    tmp_path: Path,
) -> None:
    turn_started = asyncio.Event()
    release_turn = asyncio.Event()
    close_started = asyncio.Event()
    release_close = asyncio.Event()

    class ActiveTurn(_Turn):
        async def run(self):
            turn_started.set()
            await release_turn.wait()
            return SimpleNamespace(final_response=self._response)

    class ActiveThread(_Thread):
        async def turn(self, prompt: str, **values: object) -> ActiveTurn:
            self.turns.append({"prompt": prompt, **values})
            return ActiveTurn(self._response)

    class SlowCloseClient(_Client):
        async def thread_start(self, **values: object) -> ActiveThread:
            thread = ActiveThread("active", self.response)
            self.started.append(thread)
            self.start_values.append(values)
            return thread

        async def close(self) -> None:
            close_started.set()
            await release_close.wait()
            self.closed = True

    owner, workspace, home, temp = _paths(tmp_path)
    client = SlowCloseClient()
    adapter = CodexSdkAdapter(
        workspace_root=workspace,
        owner_root=owner,
        codex_home=home,
        temp_root=temp,
        client_factory=lambda _: client,
    )
    execution = asyncio.create_task(adapter.execute(_contract(workspace)))
    await asyncio.wait_for(turn_started.wait(), timeout=1)
    closing = asyncio.create_task(adapter.close())
    await asyncio.sleep(0)
    release_turn.set()
    await asyncio.wait_for(close_started.wait(), timeout=1)

    execution.cancel()
    await asyncio.sleep(0)
    execution.cancel()
    release_close.set()

    with pytest.raises(asyncio.CancelledError):
        await execution
    await closing
    assert client.closed is True


@pytest.mark.asyncio
async def test_cancelled_client_enter_is_closed(tmp_path: Path) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    class SlowEnterClient(_Client):
        async def __aenter__(self):
            entered.set()
            await release.wait()
            return self

    owner, workspace, home, temp = _paths(tmp_path)
    client = SlowEnterClient()
    adapter = CodexSdkAdapter(
        workspace_root=workspace,
        owner_root=owner,
        codex_home=home,
        temp_root=temp,
        client_factory=lambda _: client,
    )
    execution = asyncio.create_task(adapter.execute(_contract(workspace)))
    await asyncio.wait_for(entered.wait(), timeout=1)

    execution.cancel()
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await execution
    assert client.closed is True


@pytest.mark.asyncio
async def test_deferred_close_failure_is_reported(
    tmp_path: Path,
) -> None:
    turn_started = asyncio.Event()
    release_turn = asyncio.Event()

    class ActiveTurn(_Turn):
        async def run(self):
            turn_started.set()
            await release_turn.wait()
            return SimpleNamespace(final_response=self._response)

    class ActiveThread(_Thread):
        async def turn(self, prompt: str, **values: object) -> ActiveTurn:
            self.turns.append({"prompt": prompt, **values})
            return ActiveTurn(self._response)

    class FailingCloseClient(_Client):
        def __init__(self) -> None:
            super().__init__()
            self.close_calls = 0

        async def thread_start(self, **values: object) -> ActiveThread:
            thread = ActiveThread("active", self.response)
            self.started.append(thread)
            self.start_values.append(values)
            return thread

        async def close(self) -> None:
            self.close_calls += 1
            raise RuntimeError("close failed")

    owner, workspace, home, temp = _paths(tmp_path)
    client = FailingCloseClient()
    adapter = CodexSdkAdapter(
        workspace_root=workspace,
        owner_root=owner,
        codex_home=home,
        temp_root=temp,
        client_factory=lambda _: client,
    )
    execution = asyncio.create_task(adapter.execute(_contract(workspace)))
    await asyncio.wait_for(turn_started.wait(), timeout=1)
    closing = asyncio.create_task(adapter.close())
    await asyncio.sleep(0)
    release_turn.set()

    assert json.loads((await execution).message) == {"answer": "ok"}
    with pytest.raises(CodexCliError, match="worker failed"):
        await closing
    assert client.close_calls == 2


@pytest.mark.asyncio
async def test_sdk_close_stops_app_server(tmp_path: Path) -> None:
    owner, workspace, home, temp = _paths(tmp_path)
    client = _Client()
    adapter = CodexSdkAdapter(
        workspace_root=workspace,
        owner_root=owner,
        codex_home=home,
        temp_root=temp,
        client_factory=lambda _: client,
    )
    await adapter.execute(_contract(workspace))

    await adapter.close()

    assert client.closed is True



@pytest.mark.asyncio
async def test_concurrent_close_calls_share_one_physical_close(
    tmp_path: Path,
) -> None:
    class NonReentrantClient(_Client):
        def __init__(self) -> None:
            super().__init__()
            self.close_calls = 0
            self.overlap = 0
            self.closing = False

        async def close(self) -> None:
            self.close_calls += 1
            if self.closing:
                self.overlap += 1
            self.closing = True
            await asyncio.sleep(0.01)
            self.closing = False
            self.closed = True

    owner, workspace, home, temp = _paths(tmp_path)
    client = NonReentrantClient()
    adapter = CodexSdkAdapter(
        workspace_root=workspace,
        owner_root=owner,
        codex_home=home,
        temp_root=temp,
        client_factory=lambda _: client,
    )
    await adapter.execute(_contract(workspace))

    await asyncio.gather(adapter.close(), adapter.close())

    assert client.closed is True
    assert client.close_calls == 1
    assert client.overlap == 0




@pytest.mark.asyncio
async def test_cancelled_close_cannot_cancel_shared_physical_close(
    tmp_path: Path,
) -> None:
    close_started = asyncio.Event()
    release_close = asyncio.Event()

    class SlowCloseClient(_Client):
        def __init__(self) -> None:
            super().__init__()
            self.close_calls = 0
            self.close_cancelled = 0

        async def close(self) -> None:
            self.close_calls += 1
            close_started.set()
            try:
                await release_close.wait()
            except asyncio.CancelledError:
                self.close_cancelled += 1
                raise
            self.closed = True

    owner, workspace, home, temp = _paths(tmp_path)
    client = SlowCloseClient()
    adapter = CodexSdkAdapter(
        workspace_root=workspace,
        owner_root=owner,
        codex_home=home,
        temp_root=temp,
        client_factory=lambda _: client,
    )
    await adapter.execute(_contract(workspace))
    first = asyncio.create_task(adapter.close())
    await asyncio.wait_for(close_started.wait(), timeout=1)

    first.cancel()
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first

    second = asyncio.create_task(adapter.close())
    release_close.set()
    await second

    assert client.closed is True
    assert client.close_calls == 1
    assert client.close_cancelled == 0


@pytest.mark.asyncio
async def test_concurrent_close_calls_share_one_failure_outcome(
    tmp_path: Path,
) -> None:
    class FailingNonReentrantClient(_Client):
        def __init__(self) -> None:
            super().__init__()
            self.close_calls = 0
            self.overlap = 0
            self.closing = False

        async def close(self) -> None:
            self.close_calls += 1
            if self.closing:
                self.overlap += 1
            self.closing = True
            await asyncio.sleep(0.01)
            self.closing = False
            raise RuntimeError("close failed")

    owner, workspace, home, temp = _paths(tmp_path)
    client = FailingNonReentrantClient()
    adapter = CodexSdkAdapter(
        workspace_root=workspace,
        owner_root=owner,
        codex_home=home,
        temp_root=temp,
        client_factory=lambda _: client,
    )
    await adapter.execute(_contract(workspace))

    outcomes = await asyncio.gather(
        adapter.close(), adapter.close(), return_exceptions=True
    )

    assert all(isinstance(outcome, CodexCliError) for outcome in outcomes)
    assert [outcome.code for outcome in outcomes] == [
        "worker_failed",
        "worker_failed",
    ]
    assert client.close_calls == 2
    assert client.overlap == 0


@pytest.mark.asyncio
async def test_idle_close_failure_retries_and_reports_error(
    tmp_path: Path,
) -> None:
    class FailingCloseClient(_Client):
        def __init__(self) -> None:
            super().__init__()
            self.close_calls = 0

        async def close(self) -> None:
            self.close_calls += 1
            raise RuntimeError("close failed")

    owner, workspace, home, temp = _paths(tmp_path)
    client = FailingCloseClient()
    adapter = CodexSdkAdapter(
        workspace_root=workspace,
        owner_root=owner,
        codex_home=home,
        temp_root=temp,
        client_factory=lambda _: client,
    )
    await adapter.execute(_contract(workspace))

    with pytest.raises(CodexCliError, match="worker failed"):
        await adapter.close()

    assert client.close_calls == 2


@pytest.mark.asyncio
async def test_sdk_interrupts_and_drains_timed_out_turn(tmp_path: Path) -> None:
    class BlockingTurn:
        def __init__(self) -> None:
            self.release = __import__("asyncio").Event()
            self.interrupted = False

        async def run(self):
            await self.release.wait()
            return SimpleNamespace(final_response=None)

        async def interrupt(self) -> None:
            self.interrupted = True
            self.release.set()

    class BlockingThread(_Thread):
        def __init__(self) -> None:
            super().__init__("blocking", "")
            self.blocking_turn = BlockingTurn()

        async def turn(self, prompt: str, **values: object):
            self.turns.append({"prompt": prompt, **values})
            return self.blocking_turn

    class BlockingClient(_Client):
        def __init__(self) -> None:
            super().__init__()
            self.thread = BlockingThread()

        async def thread_start(self, **_: object):
            self.started.append(self.thread)
            return self.thread

    owner, workspace, home, temp = _paths(tmp_path)
    client = BlockingClient()
    adapter = CodexSdkAdapter(
        workspace_root=workspace,
        owner_root=owner,
        codex_home=home,
        temp_root=temp,
        max_timeout_seconds=1,
        client_factory=lambda _: client,
    )
    timed = _contract(workspace).model_copy(update={"timeout_seconds": 1})

    with pytest.raises(CodexCliError, match="timed out"):
        await adapter.execute(timed)

    assert client.thread.blocking_turn.interrupted is True


@pytest.mark.asyncio
async def test_sdk_rejects_repeated_thread_list_cursor(tmp_path: Path) -> None:
    class RepeatingCursorClient(_Client):
        async def thread_list(self, **_: object):
            return SimpleNamespace(data=[], next_cursor="same")

    owner, workspace, home, temp = _paths(tmp_path)
    client = RepeatingCursorClient()
    adapter = CodexSdkAdapter(
        workspace_root=workspace,
        owner_root=owner,
        codex_home=home,
        temp_root=temp,
        client_factory=lambda _: client,
    )

    with pytest.raises(CodexCliError, match="could not be started"):
        await adapter.execute(_contract(workspace))

def test_sdk_extracts_only_urls_opened_by_web_search() -> None:
    items = [
        ThreadItem(
            root=WebSearchThreadItem(
                id="open",
                query="open",
                type="webSearch",
                action=WebSearchAction(
                    root=OpenPageWebSearchAction(
                        type="openPage", url="https://openai.com/news"
                    )
                ),
            )
        ),
        ThreadItem(
            root=WebSearchThreadItem(
                id="search",
                query="ignored",
                type="webSearch",
                action=WebSearchAction(
                    root=SearchWebSearchAction(type="search", query="ignored")
                ),
            )
        ),
        SimpleNamespace(
            root=SimpleNamespace(
                type="webSearch",
                action=SimpleNamespace(url="https://spoof.invalid"),
            )
        ),
    ]

    assert CodexSdkAdapter._web_source_urls(items) == (
        "https://openai.com/news",
    )

@pytest.mark.asyncio
async def test_sdk_rejects_unsupported_mixed_permission_profile(
    tmp_path: Path,
) -> None:
    workspace, _, home, temp = _paths(tmp_path)
    adapter = CodexSdkAdapter(
        workspace_root=workspace,
        owner_root=workspace,
        codex_home=home,
        temp_root=temp,
    )
    contract = _contract(workspace).model_copy(
        update={
            "permissions": (
                "model.inference",
                "repo.read",
                "web.search",
            )
        }
    )

    with pytest.raises(CodexCliError, match="not allowed"):
        await adapter.execute(contract)
