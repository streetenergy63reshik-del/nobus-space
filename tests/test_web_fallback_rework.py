from __future__ import annotations

import asyncio
import time
from pathlib import Path

import httpx
import pytest

from src.application.network_tools import (
    NetworkBoundaryError,
    SafeSourceVerifier,
    _pinned_https_get,
    _read_pinned_response,
)
from src.contracts import TaskContract
from src.workers.codex_cli import (
    CodexCliAdapter,
    CodexCliError,
    CodexCliResult,
    ProcessOutput,
)
from src.workers.codex_sdk import ResilientCodexAdapter
from tests.test_codex_cli import (
    FakeProcess,
    FakeSpawner,
    make_contract,
    worker_files,
)


@pytest.mark.asyncio
async def test_production_research_profile_uses_web_with_owner_projection(
    worker_files: tuple[Path, Path, Path],
) -> None:
    workspace, allowed, executable = worker_files
    owner = workspace.parent / "owner"
    owner.mkdir()
    output = (
        b'{"type":"thread.started","thread_id":"thread"}\n'
        b'{"type":"turn.started"}\n'
        b'{"type":"item.started","item":{"id":"web","type":"web_search",'
        b'"query":"","action":{"type":"other"}}}\n'
        b'{"type":"item.completed","item":{"id":"web","type":"web_search",'
        b'"query":"official source","action":{"type":"search",'
        b'"query":"official source"}}}\n'
        b'{"type":"item.completed","item":{"id":"answer","type":'
        b'"agent_message","text":"https://example.com"}}\n'
        b'{"type":"turn.completed","usage":{"input_tokens":1,'
        b'"output_tokens":1}}\n'
    )
    spawner = FakeSpawner(
        FakeProcess(output=ProcessOutput(output, b"", 0))
    )
    adapter = CodexCliAdapter(
        workspace_root=workspace,
        executable=executable,
        spawner=spawner,
        owner_read_root=owner,
    )

    await adapter.execute(
        make_contract(
            allowed,
            permissions=(
                "model.inference",
                "owner.library.read",
                "web.search",
            ),
        )
    )

    assert 'web_search="live"' in spawner.call["argv"]
    assert b'"owner_library":' in spawner.process.stdin


@pytest.mark.asyncio
async def test_pinned_get_cancellation_does_not_wait_for_tls_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = asyncio.Event()

    class Writer:
        closed = False

        def get_extra_info(self, name):
            return ("93.184.216.34", 443)

        def write(self, value):
            return None

        async def drain(self):
            return None

        def close(self):
            self.closed = True

        async def wait_closed(self):
            await asyncio.Event().wait()

    reader = asyncio.StreamReader()
    writer = Writer()

    async def open_connection(**kwargs):
        entered.set()
        return reader, writer

    monkeypatch.setattr(asyncio, "open_connection", open_connection)
    task = asyncio.create_task(
        _pinned_https_get(
            "https://example.com/article",
            frozenset({"93.184.216.34"}),
        )
    )
    await entered.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=0.1)
    assert writer.closed


@pytest.mark.asyncio
async def test_pinned_response_rejects_ambiguous_te_and_content_length() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(
        b"HTTP/1.1 200 OK\r\n"
        b"Transfer-Encoding: chunked\r\n"
        b"Content-Length: 5\r\n\r\n"
        b"0\r\n\r\n"
    )
    reader.feed_eof()

    with pytest.raises(NetworkBoundaryError):
        await _read_pinned_response(reader)


@pytest.mark.asyncio
async def test_source_verifier_rejects_redirect_to_private() -> None:
    public = [(None, None, None, None, ("93.184.216.34", 443))]
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                302, headers={"location": "https://127.0.0.1/private"}
            )
        )
    )
    verifier = SafeSourceVerifier(
        client=client, resolver=lambda *args, **kwargs: public
    )

    assert not await verifier.verify("https://example.com/start", "safe source content from page")
    await client.aclose()


@pytest.mark.asyncio
async def test_source_verifier_pins_the_resolved_public_address() -> None:
    public = [(None, None, None, None, ("93.184.216.34", 443))]
    resolver_calls = 0
    fetch_calls: list[tuple[str, frozenset[str]]] = []

    def resolver(*args, **kwargs):
        nonlocal resolver_calls
        resolver_calls += 1
        return public

    async def pinned_fetcher(url: str, addresses: frozenset[str]):
        fetch_calls.append((url, addresses))
        return type(
            "Response",
            (),
            {
                "status_code": 200,
                "headers": {},
                "content": b"safe source content from page",
            },
        )()

    verifier = SafeSourceVerifier(
        resolver=resolver,
        pinned_fetcher=pinned_fetcher,
    )

    assert await verifier.verify(
        "https://example.com/article",
        "safe source content from page",
    )
    assert resolver_calls == 1
    assert fetch_calls == [
        (
            "https://example.com/article",
            frozenset({"93.184.216.34"}),
        )
    ]


@pytest.mark.asyncio
async def test_source_verifier_rejects_url_control_characters() -> None:
    verifier = SafeSourceVerifier(
        resolver=lambda *args, **kwargs: [
            (None, None, None, None, ("93.184.216.34", 443))
        ]
    )

    assert not await verifier.verify(
        "https://example.com/article\r\nX-Test: injected",
        "safe source content from page",
    )


@pytest.mark.asyncio
async def test_source_verifier_rejects_unconfirmed_status() -> None:
    public = [(None, None, None, None, ("93.184.216.34", 443))]
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(403)
        )
    )
    verifier = SafeSourceVerifier(
        client=client, resolver=lambda *args, **kwargs: public
    )

    assert not await verifier.verify("https://example.com/blocked", "safe source content from page")
    await client.aclose()


@pytest.mark.asyncio
async def test_source_verifier_requires_quote_from_the_fetched_page() -> None:
    public = [(None, None, None, None, ("93.184.216.34", 443))]
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                content=b"this page contains different words",
            )
        )
    )
    verifier = SafeSourceVerifier(
        client=client,
        resolver=lambda *args, **kwargs: public,
    )

    assert not await verifier.verify(
        "https://example.com/article",
        "safe source content from page",
    )
    await client.aclose()


@pytest.mark.asyncio
async def test_source_verifier_rejects_encoded_bodies() -> None:
    public = [(None, None, None, None, ("93.184.216.34", 443))]
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-encoding": "gzip"},
                content=b"safe source content from page",
            )
        )
    )
    verifier = SafeSourceVerifier(
        client=client,
        resolver=lambda *args, **kwargs: public,
    )

    assert not await verifier.verify(
        "https://example.com/article",
        "safe source content from page",
    )
    await client.aclose()


@pytest.mark.asyncio
async def test_cancellation_during_source_verification_propagates(
    worker_files: tuple[Path, Path, Path],
) -> None:
    entered = asyncio.Event()

    class Primary:
        async def execute(self, contract: TaskContract):
            raise CodexCliError("worker_failed")

        async def close(self) -> None:
            return None

    class Fallback:
        async def execute(self, contract: TaskContract):
            return CodexCliResult(
                message='{"answer":"https://example.com [source_quote: safe source content from page]"}',
                web_search_observed=True,
            )

    class Verifier:
        async def verify(self, url: str, quote: str) -> bool:
            entered.set()
            await asyncio.Event().wait()
            return True

    _, allowed, _ = worker_files
    contract = make_contract(
        allowed,
        permissions=("model.inference", "web.search"),
    )
    adapter = ResilientCodexAdapter(Primary(), Fallback(), Verifier())
    task = asyncio.create_task(adapter.execute(contract))
    await entered.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.parametrize(
    "address",
    (
        "100.64.0.1",
        "::ffff:100.64.0.1",
        "224.0.0.1",
        "239.255.255.250",
        "ff02::1",
        "::ffff:224.0.0.1",
    ),
)
@pytest.mark.asyncio
async def test_source_verifier_rejects_cgnat(address: str) -> None:
    resolver = lambda *args, **kwargs: [
        (None, None, None, None, (address, 443))
    ]
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"safe source content from page")
        )
    )
    verifier = SafeSourceVerifier(client=client, resolver=resolver)

    assert not await verifier.verify("https://example.com/article", "safe source content from page")
    await client.aclose()


@pytest.mark.asyncio
async def test_source_verifier_dns_does_not_block_event_loop() -> None:
    def resolver(*args, **kwargs):
        time.sleep(0.1)
        return [(None, None, None, None, ("93.184.216.34", 443))]

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"safe source content from page")
        )
    )
    verifier = SafeSourceVerifier(client=client, resolver=resolver)
    verification = asyncio.create_task(
        verifier.verify("https://example.com/article", "safe source content from page")
    )
    await asyncio.sleep(0.01)

    assert not verification.done()
    assert await verification
    await client.aclose()


@pytest.mark.asyncio
async def test_fallback_verifies_at_most_eight_unique_candidates(
    worker_files: tuple[Path, Path, Path],
) -> None:
    class Primary:
        async def execute(self, contract):
            raise CodexCliError("worker_failed")

        async def close(self):
            return None

    class Fallback:
        async def execute(self, contract):
            urls = " ".join(
                f"https://source{index}.example/article [source_quote: safe source content from page]"
                for index in range(20)
            )
            return CodexCliResult(
                message='{"answer":"' + urls + '"}',
                web_search_observed=True,
            )

    class Verifier:
        def __init__(self):
            self.urls = []

        async def verify(self, url, quote):
            self.urls.append(url)
            return False

    _, allowed, _ = worker_files
    contract = make_contract(
        allowed,
        permissions=("model.inference", "web.search"),
    )
    verifier = Verifier()
    result = await ResilientCodexAdapter(
        Primary(), Fallback(), verifier
    ).execute(contract)

    assert result.source_urls == ()
    assert len(verifier.urls) == 8


@pytest.mark.asyncio
async def test_fallback_requires_completed_web_search_trace(
    worker_files: tuple[Path, Path, Path],
) -> None:
    class Primary:
        async def execute(self, contract):
            raise CodexCliError("worker_failed")

        async def close(self):
            return None

    class Fallback:
        async def execute(self, contract):
            return CodexCliResult(
                message='{"answer":"https://example.com [source_quote: safe source content from page]"}'
            )

    class Verifier:
        async def verify(self, url, quote):
            raise AssertionError("untraced URL must not be fetched")

    _, allowed, _ = worker_files
    contract = make_contract(
        allowed,
        permissions=("model.inference", "web.search"),
    )
    result = await ResilientCodexAdapter(
        Primary(), Fallback(), Verifier()
    ).execute(contract)

    assert result.source_urls == ()