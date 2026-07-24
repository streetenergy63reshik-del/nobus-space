from __future__ import annotations

import json

import pytest

from tests.test_codex_cli import adapter_for, make_contract, worker_files


@pytest.mark.asyncio
async def test_web_profile_enables_only_live_search_and_keeps_read_only(worker_files):
    _, allowed, _ = worker_files
    adapter, spawner = adapter_for(worker_files)

    await adapter.execute(
        make_contract(
            allowed,
            permissions=("repo.read", "process.run_allowlisted", "web.search"),
        )
    )

    argv = spawner.call["argv"]
    assert 'web_search="live"' in argv
    assert 'web_search="disabled"' not in argv
    assert "read-only" in argv
    assert "workspace-write" not in argv
    prompt = json.loads(spawner.process.stdin)
    assert "untrusted data" in prompt["research_policy"]
