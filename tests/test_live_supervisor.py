from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "run_nobus_space_live.py"


def _module() -> object:
    spec = importlib.util.spec_from_file_location("run_nobus_space_live", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_supervisor_binds_one_local_core_to_exact_public_route() -> None:
    module = _module()

    assert module.WORKTREE == Path(__file__).parents[1]
    assert module.RUNNER == module.WORKTREE / "scripts" / "run_telegram_mvp1.py"
    assert module.PUBLIC_ORIGIN == "https://app.nobusspace.com"
    assert module.RELAY_TARGET == "nobus-relay@76.13.9.125"
    assert module.REVERSE_BINDING == "127.0.0.1:18765:127.0.0.1:8765"
    assert "token" not in SCRIPT.read_text(encoding="utf-8").lower()


def test_live_supervisor_readiness_uses_exact_host(monkeypatch: object) -> None:
    module = _module()
    observed: dict[str, object] = {}

    class Response:
        status = 200

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        @staticmethod
        def read(_: int) -> bytes:
            return b'{"status":"ready"}'

    def open_request(request: object, *, timeout: int) -> Response:
        observed["url"] = request.full_url
        observed["host"] = request.get_header("Host")
        observed["timeout"] = timeout
        return Response()

    monkeypatch.setattr(module.urllib.request, "urlopen", open_request)

    assert module.ready() is True
    assert observed == {
        "url": "http://127.0.0.1:8765/readyz",
        "host": "app.nobusspace.com",
        "timeout": 2,
    }
