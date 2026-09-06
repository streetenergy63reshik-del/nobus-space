"""Remote acceptance and local receipt loss with synthetic durable effect state."""
from __future__ import annotations

import sqlite3

import httpx
import pytest

from src.application.network_commands import NetworkCommandProposal
from src.application.product_effects import ProductEffectKind, ProductEffectService, _network_payload
from tests.test_product_effects import _service, _vault


@pytest.mark.asyncio
async def test_remote_effect_acceptance_before_receipt_recovers_unknown_without_replay(tmp_path, monkeypatch):
    class ProcessLoss(BaseException):
        pass
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    service = _service(tmp_path, client)
    remote = tmp_path / "synthetic-remote.sqlite3"
    with sqlite3.connect(remote) as db:
        db.execute("CREATE TABLE accepted (effect TEXT PRIMARY KEY)")
    proposal = NetworkCommandProposal(tool="git-fetch", argv=("synthetic",),
        working_directory="synthetic", input_digest="sha256:" + "a" * 64,
        source="synthetic", destination="synthetic", digest="sha256:" + "b" * 64)
    token = service._vault.issue(kind=ProductEffectKind.NETWORK, tenant_id="owner", user_id=7, chat_id=7,
        payload=_network_payload(proposal), idempotency_key="sha256:" + "c" * 64)
    calls = []
    def accepted_then_lost(proposal, *, approval_ref):
        calls.append(proposal.digest)
        with sqlite3.connect(remote) as db:
            db.execute("INSERT INTO accepted VALUES (?)", (proposal.digest,))
        raise ProcessLoss()
    monkeypatch.setattr(service._network, "run", accepted_then_lost)
    parameters = dict(expected_kind=ProductEffectKind.NETWORK, approve=True, tenant_id="owner",
                      user_id=7, chat_id=7, approval_ref="telegram-owner-confirmation:sha256:" + "d" * 64)
    try:
        with pytest.raises(ProcessLoss):
            await service.resolve(token, **parameters)
        binding = service._vault.read(token, tenant_id="owner", user_id=7, chat_id=7)
        assert binding.state == "executing" and binding.result is None
        for _ in range(2):
            restarted = ProductEffectService(vault=_vault(tmp_path / "effects.sqlite3"),
                workspace=service._workspace, downloader=service._downloader,
                quarantine=service._quarantine, network_runner=service._network)
            outcome = await restarted.resolve(token, **parameters)
            assert "ручной проверки" in outcome.message
            assert "повторный запуск заблокирован" in outcome.message
            assert restarted._vault.read(token, tenant_id="owner", user_id=7, chat_id=7).state == "unknown"
        with sqlite3.connect(remote) as db:
            assert db.execute("SELECT count(*) FROM accepted").fetchone()[0] == 1
        assert calls == [proposal.digest]
        with pytest.raises(ValueError):
            await restarted.resolve(token, **dict(parameters, tenant_id="foreign"))
    finally:
        await client.aclose()
