"""Installed SDK ownership regression with an inert subprocess factory."""
import asyncio
import threading
from types import SimpleNamespace

import pytest
from openai_codex import AsyncCodex
from openai_codex import client as sdk_client
from src.workers import codex_sdk
from tests.test_codex_sdk import _paths


@pytest.mark.asyncio
@pytest.mark.parametrize('hung_initialize', (False, True))
@pytest.mark.parametrize('caller_cancel', (False, True))
async def test_late_physical_start_is_quarantined_and_automatically_closed(
    tmp_path, monkeypatch, hung_initialize, caller_cancel
):
    monkeypatch.setattr(codex_sdk, '_CONTROL_TIMEOUT_SECONDS', .02)
    owner, workspace, home, temp = _paths(tmp_path)
    entered, release, finished, terminated = (threading.Event() for _ in range(4))
    process = SimpleNamespace(stdin=None)
    process.terminate = terminated.set
    process.kill = terminated.set
    process.wait = lambda **kwargs: None
    starts, clients = [], []

    def inert_popen(*args, **kwargs):
        starts.append('start')
        entered.set()
        if not release.wait(3):
            raise RuntimeError('synthetic startup control expired')
        return process

    def blocked_initialize():
        if not terminated.wait(3):
            raise RuntimeError('synthetic process still alive')
        raise RuntimeError('synthetic closed transport')

    monkeypatch.setattr(sdk_client.subprocess, 'Popen', inert_popen)
    def factory(config):
        config.launch_args_override = ('synthetic-no-process',)
        client = AsyncCodex(config)
        client._client._sync._start_stderr_drain_thread = lambda: None
        client._client._sync._start_reader_thread = finished.set
        if hung_initialize:
            client._client._sync.initialize = blocked_initialize
        clients.append(client)
        return client

    adapter = codex_sdk.CodexSdkAdapter(workspace_root=workspace, owner_root=owner,
        codex_home=home, temp_root=temp, client_factory=factory)
    caller = asyncio.create_task(adapter.start())
    assert await asyncio.to_thread(entered.wait, 1)
    try:
        if caller_cancel:
            caller.cancel()
        with pytest.raises(asyncio.CancelledError if caller_cancel else codex_sdk.CodexCliError):
            await asyncio.wait_for(caller, 1)
        assert not adapter.generation_available and adapter._closed
        assert adapter._retired_clients and adapter._client_users
        with pytest.raises(codex_sdk.CodexCliError):
            await adapter.start()
        assert starts == ['start']
        with pytest.raises(codex_sdk.CodexCliError):
            await asyncio.wait_for(adapter.close(), 1)
        release.set()
        assert await asyncio.to_thread(finished.wait, 1)
        assert await asyncio.to_thread(terminated.wait, 1)
        await asyncio.wait_for(asyncio.gather(*tuple(adapter._startup_cleanup)), 1)
        assert not adapter._client_users
        assert all(adapter._retired_outcomes.values())
        assert all(event.is_set() for event in adapter._retired_events.values())
        assert not adapter.generation_available
        # The earlier failed close remains a truthful sticky failure.
        with pytest.raises(codex_sdk.CodexCliError):
            await adapter.close()
    finally:
        release.set()
        await asyncio.to_thread(finished.wait, 1)
        await asyncio.gather(caller, return_exceptions=True)
        for client in clients:
            await client.close()
        await asyncio.gather(*tuple(adapter._startup_cleanup), return_exceptions=True)
