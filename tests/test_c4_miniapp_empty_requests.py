"""Proxy-framed empty requests must reach authentication, never bypass it."""

import pytest
from fastapi.testclient import TestClient

from src.transport.miniapp import create_miniapp_app
from tests.test_c4_miniapp_recovery import COOKIE
from tests.test_miniapp import ORIGIN, core, headers, signed_init_data


def framed(client, method, path, *, body=(), extra=None):
    return client.request(method, path, headers={**headers(), **(extra or {})},
                          content=iter(body))


def test_empty_chunked_recovery_bootstrap_rotation_and_read(tmp_path):
    service = core(tmp_path)
    app = create_miniapp_app(service, allowed_host="testserver", allowed_origin=ORIGIN)
    with TestClient(app, base_url=ORIGIN) as client:
        # A fresh WebView has no cookie: 401 allows the JS Telegram auth step.
        unauthenticated = framed(client, "POST", "/api/session/recover")
        assert unauthenticated.request.headers["transfer-encoding"] == "chunked"
        assert "content-length" not in unauthenticated.request.headers
        assert unauthenticated.status_code == 401
        auth = client.post("/api/session", content=signed_init_data(),
                           headers={**headers(), "Content-Type": "text/plain"})
        assert auth.status_code == 200
        first = auth.json()["access_token"]
        cookie = client.cookies.get(COOKIE)
        recovered = framed(client, "POST", "/api/session/recover")
        assert recovered.status_code == 200
        second = recovered.json()["access_token"]
        assert second != first and client.cookies.get(COOKIE) != cookie
        assert framed(client, "GET", "/api/tasks", extra=headers(second)).status_code == 200
        assert framed(client, "GET", "/api/tasks", extra=headers(first)).status_code == 401
        assert framed(client, "POST", "/api/session/recover",
                      extra={"Cookie": f"{COOKIE}={cookie}"}).status_code == 401


@pytest.mark.parametrize("body,extra", [
    ((b"x",), {}),
    ((b"", b"x"), {}),
    ((), {"Content-Length": "1"}),
    ((), {"Content-Length": "0", "Transfer-Encoding": "chunked"}),
    ((), {"Transfer-Encoding": "gzip"}),
    ((), {"Transfer-Encoding": "gzip, chunked"}),
])
def test_invalid_framing_or_body_does_not_rotate_cookie(tmp_path, body, extra):
    service = core(tmp_path)
    grant = service.authenticate(signed_init_data())
    app = create_miniapp_app(service, allowed_host="testserver", allowed_origin=ORIGIN)
    cookie = {"Cookie": f"{COOKIE}={grant.recovery_token}"}
    with TestClient(app, base_url=ORIGIN) as client:
        assert framed(client, "POST", "/api/session/recover", body=body,
                      extra={**cookie, **extra}).status_code == 400
        assert framed(client, "POST", "/api/session/recover", extra=cookie).status_code == 200


def test_chunked_requests_keep_origin_and_no_body_boundaries(tmp_path):
    service = core(tmp_path)
    grant = service.authenticate(signed_init_data())
    app = create_miniapp_app(service, allowed_host="testserver", allowed_origin=ORIGIN)
    with TestClient(app, base_url=ORIGIN) as client:
        assert framed(client, "POST", "/api/session/recover",
                      extra={"Origin": "https://foreign.example",
                             "Cookie": f"{COOKIE}={grant.recovery_token}"}).status_code == 403
        for path in ("/api/tasks", "/api/requests/c4-unknown-request-00000001"):
            assert framed(client, "GET", path, body=(b"x",),
                          extra=headers(grant.access_token)).status_code == 400
        path = "/api/requests/c4-unknown-request-00000001/cancel"
        assert framed(client, "POST", path, body=(b"x",),
                      extra=headers(grant.access_token)).status_code == 400
        assert framed(client, "POST", path).status_code == 401
