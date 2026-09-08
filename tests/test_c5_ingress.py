"""C5 bounds use only synthetic Core/HTTP and disposable loopback sockets."""
from __future__ import annotations

import asyncio
import socket

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from starlette.responses import Response

from src.transport.miniapp import BoundedH11Protocol, _ResourceBoundary, create_miniapp_app
from tests.test_miniapp import RecordingCore, ORIGIN, headers, signed_init_data


def app(**options):
    return create_miniapp_app(RecordingCore(), allowed_host="testserver", allowed_origin=ORIGIN, **options)


def test_absent_readiness_is_unavailable_while_liveness_is_alive():
    with TestClient(app()) as client:
        assert client.get('/healthz').status_code == 200
        assert client.get('/readyz').status_code == 503


@pytest.mark.parametrize('bad_headers,code', [
    ([("host", "testserver:444")], 400),
    ([("origin", ORIGIN), ("origin", "https://foreign.example")], 400),
    ([("content-length", "0"), ("transfer-encoding", "chunked")], 400),
    ([("content-type", "text/plain"), ("content-type", "application/json")], 400),
    ([("x-padding", "x" * 16384)], 431),
    ([(f"x-{i}", "x") for i in range(65)], 431),
])
def test_ambiguous_or_oversized_headers_fail_before_core(bad_headers, code):
    with TestClient(app()) as client:
        response = client.post('/api/session', headers=bad_headers)
    assert response.status_code == code
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert 'includeSubDomains' not in str(response.headers)


def test_forwarded_headers_never_repair_a_foreign_host_or_origin():
    with TestClient(app()) as client:
        response = client.get('/healthz', headers={'Host': 'foreign.example', 'X-Forwarded-Host': 'testserver'})
        assert response.status_code == 400
        response = client.post('/api/session', content=signed_init_data(), headers={
            'Content-Type': 'text/plain', 'Origin': 'https://foreign.example',
            'X-Forwarded-Host': 'testserver', 'X-Forwarded-Proto': 'https'})
        assert response.status_code == 403


def test_method_path_query_and_auth_burst_have_closed_responses():
    with TestClient(app()) as client:
        assert client.options('/api/tasks').status_code == 405
        assert client.get('/' + 'x' * 513).status_code == 400
        assert client.get('/healthz?' + 'x' * 513).status_code == 400
        responses = [client.post('/api/session', content=signed_init_data(), headers={
            **headers(), 'Content-Type': 'text/plain'}) for _ in range(11)]
    assert [r.status_code for r in responses] == [200] * 10 + [429]
    assert responses[-1].headers['retry-after'] == '2'


@pytest.mark.asyncio
async def test_busy_requests_do_not_form_an_unbounded_queue(monkeypatch):
    gate, entered = asyncio.Event(), asyncio.Event()
    count = 0
    async def downstream(scope, receive, send):
        nonlocal count
        count += 1
        entered.set()
        await gate.wait()
        await Response('ok')(scope, receive, send)
    guarded = _ResourceBoundary(downstream, authority='testserver')
    monkeypatch.setattr(guarded, 'MAX_ACTIVE', 2)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=guarded), base_url=ORIGIN) as client:
        first = asyncio.create_task(client.get('/'))
        await entered.wait()
        entered.clear()
        second = asyncio.create_task(client.get('/'))
        await entered.wait()
        assert (await client.get('/')).status_code == 503
        assert count == 2
        gate.set()
        assert [r.status_code for r in await asyncio.gather(first, second)] == [200, 200]
    assert guarded.active == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['timeout', 'oversized', 'exception'])
async def test_total_timeout_large_response_and_exceptions_are_safe_unknown(monkeypatch, failure):
    async def downstream(scope, receive, send):
        if failure == 'timeout':
            await asyncio.Event().wait()
        if failure == 'exception':
            raise RuntimeError('synthetic-private-marker\r\nforged-log')
        await Response(b'x' * (1024 * 1024 + 1))(scope, receive, send)
    guarded = _ResourceBoundary(downstream, authority='testserver')
    monkeypatch.setattr(guarded, 'TOTAL_SECONDS', .02)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=guarded), base_url=ORIGIN) as client:
        response = await client.post('/api/tasks')
    assert response.status_code == 503
    assert 'request_timeout' not in response.text
    assert 'private' not in response.text and 'forged' not in response.text
    assert guarded.active == 0


@pytest.mark.asyncio
async def test_real_loopback_slow_headers_close_and_normal_request_survives(monkeypatch):
    monkeypatch.setattr(BoundedH11Protocol, 'HEADER_SECONDS', .08)
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    configured = create_miniapp_app(RecordingCore(), allowed_host='127.0.0.1',
                                  allowed_origin=f'http://127.0.0.1:{port}', readiness=lambda: None)
    config = uvicorn.Config(configured, http=BoundedH11Protocol, ws='none', proxy_headers=False,
                            access_log=False, log_level='critical', lifespan='off',
                            limit_concurrency=16, backlog=32, h11_max_incomplete_event_size=16384)
    server = uvicorn.Server(config)
    serving = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(3):
            while not server.started:
                await asyncio.sleep(.005)
            reader, writer = await asyncio.open_connection('127.0.0.1', port)
            writer.write(b'GET /healthz HTTP/1.1\r\nHost: ')
            await writer.drain()
            assert await reader.read() == b''
            writer.close()
            await writer.wait_closed()
            async with httpx.AsyncClient(trust_env=False) as client:
                response = await client.get(f'http://127.0.0.1:{port}/healthz')
                assert response.status_code == 200
    finally:
        server.should_exit = True
        await asyncio.wait_for(serving, 3)
        listener.close()
