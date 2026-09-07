"""Independent L3 startup regressions plus shutdown ownership boundaries."""
import asyncio
from types import SimpleNamespace

import pytest

from src.workers import codex_sdk
from tests.test_codex_sdk import _paths, _Client
from tests.test_c3_shutdown import _control


def primary(tmp_path, client):
    owner, workspace, home, temp = _paths(tmp_path)
    return codex_sdk.CodexSdkAdapter(workspace_root=workspace, owner_root=owner,
        codex_home=home, temp_root=temp, client_factory=lambda _: client)


@pytest.mark.asyncio
async def test_control_close_owns_pending_initialization(tmp_path, monkeypatch):
    from src.application import durable_product
    monkeypatch.setattr(durable_product, '_CLEANUP_SECONDS', 0.02)
    monkeypatch.setattr(durable_product, '_SHUTDOWN_SECONDS', 0.02)
    entered, release = asyncio.Event(), asyncio.Event()
    class InitializingClient(_Client):
        async def __aenter__(self):
            entered.set()
            await release.wait()
            return await super().__aenter__()
    client = InitializingClient()
    adapter = primary(tmp_path, client)
    control = _control(tmp_path)
    control._product_runtime._worker = codex_sdk.ResilientCodexAdapter(adapter,
        SimpleNamespace(execute=lambda *args: None), SimpleNamespace(verify=lambda *args: None))
    caller = asyncio.create_task(control.start())
    await asyncio.wait_for(entered.wait(), 1)
    try:
        await asyncio.wait_for(control.close(), 1)
        assert control._start_task.done(), 'shutdown reported success while owned SDK startup is still live'
        assert not adapter.generation_available
    finally:
        release.set()
        await asyncio.gather(caller, return_exceptions=True)
        await adapter.close()


@pytest.mark.asyncio
async def test_cancelled_start_caller_does_not_orphan_shared_startup(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()
    class InitializingClient(_Client):
        async def __aenter__(self):
            entered.set()
            await release.wait()
            return await super().__aenter__()
    client = InitializingClient()
    adapter = primary(tmp_path, client)
    control = _control(tmp_path)
    control._product_runtime._worker = adapter
    first = asyncio.create_task(control.start())
    await entered.wait()
    second = asyncio.create_task(control.start())
    first.cancel()
    await asyncio.gather(first, return_exceptions=True)
    assert not control._start_task.done()
    await control.close()
    await asyncio.gather(second, return_exceptions=True)
    assert control._start_task.cancelled() and client.closed
    release.set()
    await control.start()
    assert control._execution_workers == () and not adapter.generation_available
    await adapter.close()


@pytest.mark.asyncio
async def test_resistant_startup_marks_shutdown_failure_and_never_reopens(tmp_path, monkeypatch):
    from contextlib import suppress
    from src.application import durable_product
    monkeypatch.setattr(durable_product, '_SHUTDOWN_SECONDS', 0.02)
    entered, release = asyncio.Event(), asyncio.Event()
    async def resistant_start():
        entered.set()
        while not release.is_set():
            with suppress(asyncio.CancelledError):
                await release.wait()
    control = _control(tmp_path)
    control._product_runtime._worker = SimpleNamespace(start=resistant_start, generation_available=False)
    caller = asyncio.create_task(control.start())
    await entered.wait()
    try:
        with pytest.raises(RuntimeError, match='did not close safely'):
            await asyncio.wait_for(control.close(), 1)
        assert control._closed and control._close_failed
        assert control._start_task in control._cleanup_pending
        with pytest.raises(RuntimeError, match='unavailable'):
            control.assert_healthy()
    finally:
        release.set()
        await asyncio.gather(caller, return_exceptions=True)
    assert control._execution_workers == ()
    await control.start()
    assert control._execution_workers == ()


@pytest.mark.asyncio
async def test_failed_startup_cleanup_is_retained_and_blocks_new_generation(tmp_path, monkeypatch):
    monkeypatch.setattr(codex_sdk, '_CONTROL_TIMEOUT_SECONDS', 0.02)
    release = asyncio.Event()
    class BrokenClient(_Client):
        async def __aenter__(self):
            await release.wait()
            return self
        async def close(self):
            raise RuntimeError('synthetic cleanup failure')
    client = BrokenClient()
    adapter = primary(tmp_path, client)
    with pytest.raises(codex_sdk.CodexCliError) as failure:
        await asyncio.wait_for(adapter.start(), 1)
    assert failure.value.code == 'worker_start_failed'
    assert not adapter.generation_available and adapter._closed
    assert adapter._retired_clients[id(client)] is client
    with pytest.raises(codex_sdk.CodexCliError) as failure:
        await adapter.start()
    assert failure.value.code == 'worker_start_failed'
    with pytest.raises(codex_sdk.CodexCliError) as failure:
        await asyncio.wait_for(adapter.close(), 1)
    assert failure.value.code == 'worker_failed'
    release.set()
    await asyncio.gather(*tuple(adapter._startup_cleanup))
    assert adapter._retired_outcomes[id(client)] is False


@pytest.mark.asyncio
async def test_sdk_initialization_has_control_deadline(tmp_path, monkeypatch):
    monkeypatch.setattr(codex_sdk, '_CONTROL_TIMEOUT_SECONDS', 0.02)
    entered, release = asyncio.Event(), asyncio.Event()
    class InitializingClient(_Client):
        async def __aenter__(self):
            entered.set()
            await release.wait()
            return await super().__aenter__()
    client = InitializingClient()
    adapter = primary(tmp_path, client)
    caller = asyncio.create_task(adapter.start())
    await asyncio.wait_for(entered.wait(), 1)
    try:
        done, pending = await asyncio.wait({caller}, timeout=0.2)
        assert not pending, 'local SDK protocol initialization has no bounded control deadline'
        assert caller.exception() is not None
        assert client.closed
    finally:
        release.set()
        await asyncio.gather(caller, return_exceptions=True)
        await adapter.close()


@pytest.mark.asyncio
async def test_concurrent_start_shares_generation_and_cancelled_caller(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()
    starts = []
    class InitializingClient(_Client):
        async def __aenter__(self):
            starts.append('initialize')
            entered.set()
            await release.wait()
            return await super().__aenter__()
    client = InitializingClient()
    adapter = primary(tmp_path, client)
    control = _control(tmp_path)
    control._product_runtime._worker = codex_sdk.ResilientCodexAdapter(adapter,
        SimpleNamespace(execute=lambda *args: None), SimpleNamespace(verify=lambda *args: None))
    first = asyncio.create_task(control.start())
    await asyncio.wait_for(entered.wait(), 1)
    second = asyncio.create_task(control.start())
    first.cancel()
    try:
        with pytest.raises(asyncio.CancelledError):
            await first
        assert not control._start_task.done()
        release.set()
        await asyncio.wait_for(second, 1)
        control.assert_healthy()
        assert starts == ['initialize']
        assert len(control._execution_workers) == 1
        assert client.start_values == []
    finally:
        release.set()
        await asyncio.gather(first, second, return_exceptions=True)
        await control.close()
        await adapter.close()


@pytest.mark.asyncio
async def test_late_start_does_not_reopen_closed_control(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()
    class InitializingClient(_Client):
        async def __aenter__(self):
            entered.set()
            await release.wait()
            return await super().__aenter__()
    client = InitializingClient()
    adapter = primary(tmp_path, client)
    control = _control(tmp_path)
    control._product_runtime._worker = codex_sdk.ResilientCodexAdapter(adapter,
        SimpleNamespace(execute=lambda *args: None), SimpleNamespace(verify=lambda *args: None))
    caller = asyncio.create_task(control.start())
    await asyncio.wait_for(entered.wait(), 1)
    try:
        await asyncio.wait_for(control.close(), 1)
        release.set()
        await asyncio.wait_for(asyncio.gather(caller, return_exceptions=True), 1)
        assert control._closed and not control._execution_workers
        with pytest.raises(RuntimeError):
            control.assert_healthy()
        await control.start()
        assert not control._execution_workers
    finally:
        release.set()
        await asyncio.gather(caller, return_exceptions=True)
        await adapter.close()
