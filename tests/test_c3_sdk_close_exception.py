"""A physical close exception must not become success through a later no-op."""
import asyncio
from types import SimpleNamespace

import pytest
from openai_codex import AsyncCodex
from src.workers import codex_sdk
from tests.test_codex_sdk import _paths


@pytest.mark.asyncio
async def test_physical_close_exception_is_not_erased_by_noop_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(codex_sdk, '_CONTROL_TIMEOUT_SECONDS', .02)
    owner, workspace, home, temp = _paths(tmp_path)
    process = SimpleNamespace(terminated=False)
    def broken_stdin_close():
        raise RuntimeError('synthetic failure before process termination')
    process.stdin = SimpleNamespace(close=broken_stdin_close)
    process.terminate = process.kill = lambda: setattr(process, 'terminated', True)
    process.wait = lambda **kwargs: None
    client = AsyncCodex()
    client._client._sync._proc = process
    adapter = codex_sdk.CodexSdkAdapter(workspace_root=workspace, owner_root=owner,
        codex_home=home, temp_root=temp, client_factory=lambda _: client)
    adapter._client = client
    try:
        result = await asyncio.wait_for(asyncio.gather(adapter.close(), return_exceptions=True), .5)
        assert isinstance(result[0], codex_sdk.CodexCliError), 'physical close exception was erased by a later no-op close'
        assert result[0].code == 'worker_failed'
        assert not process.terminated
        assert id(client) in adapter._retired_clients
        with pytest.raises(codex_sdk.CodexCliError):
            await adapter.close()
    finally:
        process.terminate()
