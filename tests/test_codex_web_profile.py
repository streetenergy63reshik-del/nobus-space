from __future__ import annotations

import json

import pytest

from src.workers import CodexCliError, ProcessOutput
from tests.test_codex_cli import (
    FakeProcess,
    adapter_for,
    make_contract,
    worker_files,
)

@pytest.mark.asyncio
async def test_web_profile_enables_only_live_search_and_keeps_read_only(worker_files):
    _, allowed, _ = worker_files
    output = (
        b'{"type":"thread.started","thread_id":"thread"}\n'
        b'{"type":"turn.started"}\n'
        b'{"type":"item.started","item":{"id":"item_0","type":"web_search","id":"call-1","query":"","action":{"type":"other"}}}\n'
        b'{"type":"item.completed","item":{"id":"item_0","type":"web_search","id":"call-1","query":"official source","action":{"type":"search","query":"official source"}}}\n'
        b'{"type":"item.completed","item":{"id":"answer","type":"agent_message","text":"done"}}\n'
        b'{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}\n'
    )
    adapter, spawner = adapter_for(
        worker_files, FakeProcess(output=ProcessOutput(output, b"", 0))
    )

    await adapter.execute(
        make_contract(
            allowed,
            permissions=("model.inference", "web.search"),
        )
    )

    argv = spawner.call["argv"]
    assert 'web_search="live"' in argv
    assert 'web_search="disabled"' not in argv
    assert "features.shell_tool=false" in argv
    assert "features.shell_snapshot=false" in argv
    assert "read-only" in argv
    assert "workspace-write" not in argv
    prompt = json.loads(spawner.process.stdin)
    assert "untrusted data" in prompt["research_policy"]


@pytest.mark.asyncio
async def test_web_profile_accepts_only_bounded_web_search_events(
    worker_files,
) -> None:
    _, allowed, _ = worker_files
    output = (
        b'{"type":"thread.started","thread_id":"thread"}\n'
        b'{"type":"turn.started"}\n'
        b'{"type":"item.started","item":{"id":"web-1","type":"web_search",'
        b'"query":"official source","action":{"type":"search",'
        b'"query":"official source"}}}\n'
        b'{"type":"item.completed","item":{"id":"web-1","type":"web_search",'
        b'"query":"official source","action":{"type":"search",'
        b'"query":"official source"}}}\n'
        b'{"type":"item.completed","item":{"id":"answer","type":'
        b'"agent_message","text":"done"}}\n'
        b'{"type":"turn.completed","usage":{"input_tokens":1,'
        b'"output_tokens":1}}\n'
    )
    adapter, _ = adapter_for(
        worker_files,
        FakeProcess(output=ProcessOutput(output, b"", 0)),
    )

    result = await adapter.execute(
        make_contract(
            allowed,
            permissions=["model.inference", "web.search"],
        )
    )

    assert result.message == "done"


@pytest.mark.asyncio
async def test_web_profile_does_not_self_attest_source_urls(worker_files) -> None:
    _, allowed, _ = worker_files
    output = (
        b'{"type":"thread.started","thread_id":"thread"}\n'
        b'{"type":"turn.started"}\n'
        b'{"type":"item.completed","item":{"id":"search","type":"web_search",'
        b'"query":"official source","action":{"type":"search",'
        b'"query":"official source"}}}\n'
        b'{"type":"item.completed","item":{"id":"open","type":"web_search",'
        b'"query":"official source","action":{"type":"open_page",'
        b'"url":"https://example.com/source"}}}\n'
        b'{"type":"item.completed","item":{"id":"answer","type":'
        b'"agent_message","text":"https://example.com/source"}}\n'
        b'{"type":"turn.completed","usage":{"input_tokens":1,'
        b'"output_tokens":1}}\n'
    )
    adapter, _ = adapter_for(
        worker_files,
        FakeProcess(output=ProcessOutput(output, b"", 0)),
    )

    result = await adapter.execute(
        make_contract(
            allowed,
            permissions=["model.inference", "web.search"],
        )
    )

    assert result.source_urls == ()


@pytest.mark.asyncio
async def test_web_profile_accepts_current_completed_other_and_cited_source(
    worker_files,
) -> None:
    _, allowed, _ = worker_files
    output = (
        b'{"type":"thread.started","thread_id":"thread"}\n'
        b'{"type":"turn.started"}\n'
        b'{"type":"item.started","item":{"id":"web-1","type":"web_search",'
        b'"query":"","action":{"type":"other"}}}\n'
        b'{"type":"item.completed","item":{"id":"web-1","type":"web_search",'
        b'"query":"official source","action":{"type":"search",'
        b'"query":"official source"}}}\n'
        b'{"type":"item.started","item":{"id":"web-2","type":"web_search",'
        b'"query":"","action":{"type":"other"}}}\n'
        b'{"type":"item.completed","item":{"id":"web-2","type":"web_search",'
        b'"query":"official source","action":{"type":"other"}}}\n'
        b'{"type":"item.completed","item":{"id":"answer","type":'
        b'"agent_message","text":"Source: https://example.com/current"}}\n'
        b'{"type":"turn.completed","usage":{"input_tokens":1,'
        b'"output_tokens":1}}\n'
    )
    adapter, _ = adapter_for(
        worker_files,
        FakeProcess(output=ProcessOutput(output, b"", 0)),
    )

    result = await adapter.execute(
        make_contract(
            allowed,
            permissions=["model.inference", "web.search"],
        )
    )

    assert result.source_urls == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "item",
    [
        '{"id":"mcp","type":"mcp_tool_call"}',
        '{"id":"file","type":"file_change"}',
    ],
)
async def test_web_profile_rejects_non_web_tool_items(
    worker_files, item: str
) -> None:
    _, allowed, _ = worker_files
    output = (
        '{"type":"thread.started","thread_id":"thread"}\n'
        '{"type":"turn.started"}\n'
        f'{{"type":"item.completed","item":{item}}}\n'
        '{"type":"item.completed","item":{"id":"answer","type":'
        '"agent_message","text":"done"}}\n'
        '{"type":"turn.completed","usage":{"input_tokens":1,'
        '"output_tokens":1}}\n'
    ).encode("utf-8")
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
