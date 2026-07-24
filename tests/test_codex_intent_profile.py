from __future__ import annotations

import pytest

from src.workers import CodexCliError, ProcessOutput
from tests.test_codex_cli import (
    FakeProcess,
    adapter_for,
    make_contract,
    worker_files,
)

@pytest.mark.asyncio
async def test_intent_profile_disables_every_available_tool_family(
    worker_files,
) -> None:
    _, allowed, _ = worker_files
    adapter, spawner = adapter_for(worker_files)

    result = await adapter.execute(
        make_contract(
            allowed,
            instruction="Return one intent JSON object.",
            permissions=["model.inference"],
        )
    )

    assert result.message == "done"
    argv = spawner.call["argv"]
    assert "features.shell_tool=false" in argv
    assert "features.shell_snapshot=false" in argv
    assert "features.multi_agent=false" in argv
    assert "features.apps=false" in argv
    assert "features.goals=false" in argv
    assert "features.hooks=false" in argv
    assert "features.remote_plugin=false" in argv
    assert 'web_search="disabled"' in argv
    assert "mcp_servers={}" in argv
    assert 'approval_policy="never"' in argv
    assert argv[-3:] == ("--sandbox", "read-only", "-")

@pytest.mark.asyncio
async def test_intent_profile_rejects_any_reported_tool_event(
    worker_files,
) -> None:
    _, allowed, _ = worker_files
    output = (
        b'{"type":"thread.started","thread_id":"thread"}\n'
        b'{"type":"turn.started"}\n'
        b'{"type":"item.completed","item":{"id":"tool","type":'
        b'"command_execution","command":"dir","aggregated_output":"",'
        b'"exit_code":0,"status":"completed"}}\n'
        b'{"type":"item.completed","item":{"id":"answer","type":'
        b'"agent_message","text":"done"}}\n'
        b'{"type":"turn.completed","usage":{"input_tokens":1,'
        b'"output_tokens":1}}\n'
    )
    adapter, _ = adapter_for(
        worker_files,
        FakeProcess(output=ProcessOutput(output, b"", 0)),
    )

    with pytest.raises(CodexCliError, match="invalid output"):
        await adapter.execute(
            make_contract(
                allowed,
                permissions=["model.inference"],
            )
        )


@pytest.mark.asyncio
async def test_web_profile_rejects_any_reported_shell_event(
    worker_files,
) -> None:
    _, allowed, _ = worker_files
    output = (
        b'{"type":"thread.started","thread_id":"thread"}\n'
        b'{"type":"turn.started"}\n'
        b'{"type":"item.completed","item":{"id":"tool","type":'
        b'"command_execution","command":"dir","aggregated_output":"",'
        b'"exit_code":0,"status":"completed"}}\n'
        b'{"type":"item.completed","item":{"id":"answer","type":'
        b'"agent_message","text":"done"}}\n'
        b'{"type":"turn.completed","usage":{"input_tokens":1,'
        b'"output_tokens":1}}\n'
    )
    adapter, _ = adapter_for(
        worker_files,
        FakeProcess(output=ProcessOutput(output, b"", 0)),
    )

    with pytest.raises(CodexCliError, match="invalid output"):
        await adapter.execute(
            make_contract(
                allowed,
                permissions=["model.inference", "web.search"],
            )
        )
