"""Contract tests for the persistent official Codex SDK boundary."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.contracts import RiskLevel, TaskContract
from src.workers.codex_cli import CodexCliError
from src.workers.codex_sdk import CodexSdkAdapter


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
        self.resumed: list[_Thread] = []
        self.closed = False
        self.entered = False

    async def __aenter__(self):
        self.entered = True
        return self

    async def thread_list(self, **_: object):
        return SimpleNamespace(data=list(self.listed), next_cursor=None)

    async def thread_start(self, **_: object) -> _Thread:
        thread = _Thread(f"started-{len(self.started)}", self.response)
        self.started.append(thread)
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
    permissions: tuple[str, ...] = ("model.inference",),
) -> TaskContract:
    return TaskContract(
        task_id=uuid4(),
        idempotency_key=uuid4().hex,
        ingress_digest="sha256:" + "0" * 64,
        tenant_id="owner",
        source=source,
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
