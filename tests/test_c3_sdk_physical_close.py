"""Actual installed SDK close offloading; inert synthetic process only."""
import asyncio
import threading
from types import SimpleNamespace

import pytest
from openai_codex import AsyncCodex
from src.workers import codex_sdk
from tests.test_codex_sdk import _paths


@pytest.mark.asyncio
async def test_physical_close_timeout_cannot_be_cleared_by_noop_second_close(tmp_path, monkeypatch):
    monkeypatch.setattr(codex_sdk, '_CONTROL_TIMEOUT_SECONDS', .02)
    owner, workspace, home, temp = _paths(tmp_path)
    entered, release, terminated = (threading.Event() for _ in range(3))
    def close_stdin():
        entered.set()
        if not release.wait(3):
            raise RuntimeError('probe close release failed')
    process=SimpleNamespace(stdin=SimpleNamespace(close=close_stdin))
    process.terminate=process.kill=terminated.set
    process.wait=lambda **kwargs: None
    client=AsyncCodex()
    # Exact SDK post-start process state, with all operating-system effects inert.
    client._client._sync._proc=process
    adapter=codex_sdk.CodexSdkAdapter(workspace_root=workspace,owner_root=owner,
        codex_home=home,temp_root=temp,client_factory=lambda _: client)
    adapter._client=client
    caller=asyncio.create_task(adapter.close())
    assert await asyncio.to_thread(entered.wait,1)
    try:
        result=await asyncio.wait_for(asyncio.gather(caller,return_exceptions=True),.5)
        assert isinstance(result[0],codex_sdk.CodexCliError), 'adapter.close falsely succeeded while physical close thread is stuck before terminate'
        assert result[0].code=='worker_failed'
        assert not terminated.is_set()
        assert id(client) in adapter._retired_clients
    finally:
        release.set()
        assert await asyncio.to_thread(terminated.wait,1)
        await asyncio.gather(caller,return_exceptions=True)
