"""Bounded Google HTTP transport shared by owner-only integrations."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Iterable


_CONNECT_TIMEOUT_SECONDS = 15
_REQUEST_TIMEOUT_SECONDS = 60
_API_RETRIES = 2


class _TimeoutSession:
    """Lazily create a requests.Session with a mandatory default timeout."""

    def __new__(cls):
        import requests

        class Session(requests.Session):
            def request(self, method: str, url: str, **values: Any):
                values.setdefault(
                    "timeout",
                    (_CONNECT_TIMEOUT_SECONDS, _REQUEST_TIMEOUT_SECONDS),
                )
                return super().request(method, url, **values)

        return Session()


def load_service(
    token_path: Path,
    *,
    api: str,
    version: str,
    required_scopes: Iterable[str],
    any_scope: bool = False,
) -> Any:
    """Load one authenticated Google service with bounded refresh and I/O."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    scopes = tuple(required_scopes)
    credentials = Credentials.from_authorized_user_file(str(token_path))
    if any_scope:
        granted = set(
            getattr(credentials, "granted_scopes", None)
            or getattr(credentials, "scopes", None)
            or ()
        )
        allowed = bool(granted.intersection(scopes))
    else:
        allowed = credentials.has_scopes(scopes)
    if not allowed:
        raise RuntimeError("google_credentials_scope_mismatch")
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request(session=_TimeoutSession()))
    if not credentials.valid:
        raise RuntimeError("google_credentials_invalid")
    from google_auth_httplib2 import AuthorizedHttp
    from googleapiclient.discovery import build
    from googleapiclient.http import HttpRequest
    import httplib2

    class RetryingHttpRequest(HttpRequest):
        def execute(self, http=None, num_retries: int = 0):
            return super().execute(http=http, num_retries=num_retries)

    transport = AuthorizedHttp(
        credentials,
        http=httplib2.Http(timeout=_REQUEST_TIMEOUT_SECONDS),
    )
    return build(
        api,
        version,
        http=transport,
        cache_discovery=False,
        requestBuilder=RetryingHttpRequest,
    )


def execute_request(request: Any, *, retries: int = 0) -> Any:
    """Execute a request; callers opt in to retries only for safe reads."""
    if type(retries) is not int or not 0 <= retries <= _API_RETRIES:
        raise ValueError("google_request_retries_invalid")
    execute = getattr(request, "execute", None)
    if not callable(execute):
        raise RuntimeError("google_request_invalid")
    try:
        parameters = inspect.signature(execute).parameters.values()
    except (TypeError, ValueError):
        parameters = ()
    supports_retries = any(
        parameter.name == "num_retries"
        or parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )
    return execute(num_retries=retries) if supports_retries else execute()
