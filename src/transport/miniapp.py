"""Thin same-origin FastAPI boundary for the Telegram Mini App."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Sequence
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import ClientDisconnect

from src.application.miniapp import (
    MiniAppAuthenticationError,
    MiniAppCoreUnavailableError,
    MiniAppSessionGrant,
    MiniAppTaskArtifactDownload,
    MiniAppTaskConflictError,
    MiniAppTaskCreation,
    MiniAppTaskDetail,
    MiniAppTaskEvent,
    MiniAppTaskNotFoundError,
    MiniAppTaskMaterial,
    MiniAppTaskRequestError,
    MiniAppTaskResult,
    MiniAppTaskSummary,
)
from src.application.semantic_admission import (
    SemanticClarificationRejected,
    SemanticClarificationRequired,
)


_UNAVAILABLE = "Nobus Space временно недоступен"
_SAFE_READ_METHODS = frozenset({"GET", "HEAD"})
_AUTHORITY_HEADERS = frozenset(
    {
        "x-actor",
        "x-capabilities",
        "x-owner-id",
        "x-risk",
        "x-role",
        "x-route",
        "x-tenant-id",
    }
)


class MiniAppCoreBoundary(Protocol):
    def authenticate(self, raw_init_data: str) -> MiniAppSessionGrant: ...

    def list_tasks(
        self, bearer: str, *, limit: int
    ) -> Sequence[MiniAppTaskSummary]: ...

    def task_detail(self, bearer: str, task_id: UUID) -> MiniAppTaskDetail: ...

    def task_result(
        self, bearer: str, task_id: UUID, *, result_revision: int
    ) -> MiniAppTaskResult: ...

    def task_artifact(
        self,
        bearer: str,
        task_id: UUID,
        artifact_id: UUID,
        *,
        result_revision: int,
    ) -> MiniAppTaskArtifactDownload: ...

    def task_events(
        self, bearer: str, task_id: UUID, *, limit: int
    ) -> Sequence[MiniAppTaskEvent]: ...

    async def create_task(
        self,
        bearer: str,
        instruction: str,
        idempotency_key: str,
        *,
        display_title: str | None = None,
        clarification_token: str | None = None,
        material: MiniAppTaskMaterial | None = None,
    ) -> MiniAppTaskCreation: ...


def create_miniapp_app(
    core: MiniAppCoreBoundary,
    *,
    allowed_host: str,
    allowed_origin: str,
    max_init_data_bytes: int = 4096,
    max_task_request_bytes: int = 16_384,
    init_data_read_timeout_seconds: float = 5.0,
    readiness: Callable[[], None] | None = None,
) -> FastAPI:
    """Create a stateless boundary; every authority decision stays in Core."""
    host = allowed_host.strip() if isinstance(allowed_host, str) else ""
    origin = allowed_origin.strip() if isinstance(allowed_origin, str) else ""
    if not host or any(character in host for character in "/*"):
        raise ValueError("allowed_host must be exact")
    parsed_origin = urlsplit(origin)
    local_http = parsed_origin.scheme == "http" and host == "127.0.0.1"
    if (
        (parsed_origin.scheme != "https" and not local_http)
        or parsed_origin.hostname != host
        or parsed_origin.path
        or parsed_origin.query
        or parsed_origin.fragment
        or parsed_origin.username is not None
        or parsed_origin.password is not None
    ):
        raise ValueError(
            "allowed_origin must be an exact HTTPS origin or loopback HTTP origin"
        )
    try:
        if parsed_origin.port is not None and not 1 <= parsed_origin.port <= 65535:
            raise ValueError
    except ValueError:
        raise ValueError("allowed_origin is invalid") from None
    if (
        isinstance(max_init_data_bytes, bool)
        or not isinstance(max_init_data_bytes, int)
        or not 256 <= max_init_data_bytes <= 8192
    ):
        raise ValueError("max_init_data_bytes is invalid")
    if (
        isinstance(init_data_read_timeout_seconds, bool)
        or not isinstance(init_data_read_timeout_seconds, (int, float))
        or not 0 < init_data_read_timeout_seconds <= 30
    ):
        raise ValueError("init_data_read_timeout_seconds is invalid")
    if (
        isinstance(max_task_request_bytes, bool)
        or not isinstance(max_task_request_bytes, int)
        or not 2_048 <= max_task_request_bytes <= 32_768
    ):
        raise ValueError("max_task_request_bytes is invalid")

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[host])

    @app.middleware("http")
    async def secure_boundary(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if len(request.scope.get("query_string", b"")) > 512:
            response = JSONResponse({"detail": "invalid_request"}, status_code=400)
        elif any(name in request.headers for name in _AUTHORITY_HEADERS):
            response = JSONResponse({"detail": "invalid_request"}, status_code=400)
        elif request.url.path.startswith("/api/"):
            if request.method in _SAFE_READ_METHODS and not await _body_is_empty(
                request,
                timeout_seconds=float(init_data_read_timeout_seconds),
            ):
                response = _invalid_request()
            else:
                request_origin = request.headers.get("origin")
                if request_origin != origin and not (
                    request.method in _SAFE_READ_METHODS and request_origin is None
                ):
                    response = JSONResponse(
                        {"detail": "forbidden"}, status_code=403
                    )
                else:
                    response = await call_next(request)
        else:
            response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' https://telegram.org; "
            "style-src 'self'; connect-src 'self'; img-src 'self' data:; "
            "object-src 'none'; base-uri 'none'; "
            "frame-ancestors https://web.telegram.org https://*.telegram.org"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path.startswith("/api/") or request.url.path in {
            "/healthz",
            "/readyz",
        }:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/healthz")
    async def health() -> object:
        return {"status": "ok"}

    @app.get("/readyz")
    async def ready() -> object:
        try:
            if readiness is not None:
                readiness()
        except Exception:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return {"status": "ready"}

    @app.post("/api/session")
    async def create_session(request: Request) -> object:
        if request.query_params:
            return _invalid_request()
        media_type = request.headers.get("content-type", "").split(";", 1)[0]
        if media_type.strip().lower() != "text/plain":
            return JSONResponse({"detail": "unsupported_media_type"}, status_code=415)
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                parsed_content_length = int(content_length)
                if parsed_content_length < 0:
                    return _invalid_request()
                if parsed_content_length > max_init_data_bytes:
                    return JSONResponse({"detail": "request_too_large"}, status_code=413)
            except ValueError:
                return _invalid_request()
        try:
            raw = await _read_bounded_body(
                request,
                max_bytes=max_init_data_bytes,
                timeout_seconds=float(init_data_read_timeout_seconds),
            )
        except _RequestBodyTooLarge:
            return JSONResponse({"detail": "request_too_large"}, status_code=413)
        except TimeoutError:
            return JSONResponse({"detail": "request_timeout"}, status_code=408)
        if not raw:
            return _invalid_request()
        try:
            init_data = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return _invalid_request()
        try:
            return core.authenticate(init_data)
        except MiniAppAuthenticationError:
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        except Exception:
            return _core_unavailable()

    @app.get("/api/tasks")
    async def list_tasks(request: Request) -> object:
        if not _query_is(request, allowed="limit"):
            return _invalid_request()
        try:
            bearer = _bearer(request)
            raw_limit = request.query_params.get("limit", "20")
            if not raw_limit.isascii() or not raw_limit.isdigit():
                return _invalid_request()
            limit = int(raw_limit)
            if not 1 <= limit <= 50:
                return _invalid_request()
            return {"tasks": list(core.list_tasks(bearer, limit=limit))}
        except MiniAppAuthenticationError:
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        except MiniAppCoreUnavailableError:
            return _core_unavailable()
        except Exception:
            return _core_unavailable()

    @app.post("/api/tasks", status_code=202)
    async def create_task(request: Request) -> object:
        if request.query_params:
            return _invalid_request()
        content_types = request.headers.getlist("content-type")
        if len(content_types) != 1:
            return _invalid_request()
        content_type = content_types[0]
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type not in {"application/json", "multipart/form-data"}:
            return JSONResponse({"detail": "unsupported_media_type"}, status_code=415)
        request_ids = request.headers.getlist("idempotency-key")
        if len(request_ids) != 1:
            return _invalid_request()
        content_length = request.headers.get("content-length")
        if len(request.headers.getlist("content-length")) > 1:
            return _invalid_request()
        if content_length is not None:
            try:
                parsed_content_length = int(content_length)
                if parsed_content_length < 0:
                    return _invalid_request()
                if parsed_content_length > max_task_request_bytes:
                    return JSONResponse(
                        {"detail": "request_too_large"}, status_code=413
                    )
            except ValueError:
                return _invalid_request()
        try:
            raw = await _read_bounded_body(
                request,
                max_bytes=max_task_request_bytes,
                timeout_seconds=float(init_data_read_timeout_seconds),
            )
        except _RequestBodyTooLarge:
            return JSONResponse({"detail": "request_too_large"}, status_code=413)
        except TimeoutError:
            return JSONResponse({"detail": "request_timeout"}, status_code=408)
        except ClientDisconnect:
            return _invalid_request()
        try:
            if content_length is not None and len(raw) != parsed_content_length:
                raise ValueError
            material = None
            if media_type == "multipart/form-data":
                payload, material = _multipart_task_payload(raw, content_type)
            else:
                payload = json.loads(
                    raw.decode("utf-8", errors="strict"),
                    object_pairs_hook=_unique_object,
                )
            if (
                not isinstance(payload, dict)
                or "instruction" not in payload
                or not set(payload).issubset(
                    {"clarification_token", "display_title", "instruction"}
                )
            ):
                raise ValueError
            instruction = payload["instruction"]
            display_title = payload.get("display_title")
            clarification_token = payload.get("clarification_token")
            if not isinstance(instruction, str) or (
                display_title is not None and not isinstance(display_title, str)
            ) or (
                clarification_token is not None
                and not isinstance(clarification_token, str)
            ):
                raise ValueError
        except (UnicodeError, ValueError, json.JSONDecodeError):
            return _invalid_request()
        try:
            options = {"display_title": display_title}
            if clarification_token is not None:
                options["clarification_token"] = clarification_token
            if material is not None:
                options["material"] = material
            result = await core.create_task(
                _bearer(request), instruction, request_ids[0], **options
            )
            return JSONResponse(result.model_dump(mode="json"), status_code=202)
        except MiniAppAuthenticationError:
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        except MiniAppTaskRequestError:
            return _invalid_request()
        except SemanticClarificationRequired as error:
            return JSONResponse(
                {
                    "detail": "clarification_required",
                    "question": error.question,
                    "clarification_token": error.token,
                },
                status_code=409,
            )
        except SemanticClarificationRejected:
            return JSONResponse(
                {"detail": "clarification_invalid"}, status_code=409
            )
        except MiniAppTaskConflictError:
            return JSONResponse({"detail": "request_conflict"}, status_code=409)
        except MiniAppCoreUnavailableError:
            return _core_unavailable()
        except Exception:
            return _core_unavailable()

    @app.get("/api/tasks/{task_id}")
    async def task_detail(request: Request, task_id: str) -> object:
        if request.query_params:
            return _invalid_request()
        try:
            parsed_task_id = UUID(task_id)
        except (TypeError, ValueError):
            return _task_not_found()
        try:
            return core.task_detail(_bearer(request), parsed_task_id)
        except MiniAppAuthenticationError:
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        except MiniAppTaskNotFoundError:
            return _task_not_found()
        except MiniAppCoreUnavailableError:
            return _core_unavailable()
        except Exception:
            return _core_unavailable()

    @app.get("/api/tasks/{task_id}/result")
    async def task_result(request: Request, task_id: str) -> object:
        if not _query_is(request, allowed="revision"):
            return _invalid_request()
        try:
            parsed_task_id = UUID(task_id)
            raw_revision = request.query_params.get("revision", "")
            if not raw_revision.isascii() or not raw_revision.isdigit():
                return _invalid_request()
            revision = int(raw_revision)
            if not 1 <= revision <= 2_147_483_647:
                return _invalid_request()
        except (TypeError, ValueError):
            return _task_not_found()
        try:
            return core.task_result(
                _bearer(request),
                parsed_task_id,
                result_revision=revision,
            )
        except MiniAppAuthenticationError:
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        except MiniAppTaskNotFoundError:
            return _task_not_found()
        except MiniAppCoreUnavailableError:
            return _core_unavailable()
        except Exception:
            return _core_unavailable()

    @app.get("/api/tasks/{task_id}/events")
    async def task_events(request: Request, task_id: str) -> object:
        if not _query_is(request, allowed="limit"):
            return _invalid_request()
        try:
            parsed_task_id = UUID(task_id)
            raw_limit = request.query_params.get("limit", "20")
            if not raw_limit.isascii() or not raw_limit.isdigit():
                return _invalid_request()
            limit = int(raw_limit)
            if not 1 <= limit <= 50:
                return _invalid_request()
        except (TypeError, ValueError):
            return _task_not_found()
        try:
            return {
                "events": list(
                    core.task_events(_bearer(request), parsed_task_id, limit=limit)
                )
            }
        except MiniAppAuthenticationError:
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        except MiniAppTaskNotFoundError:
            return _task_not_found()
        except MiniAppCoreUnavailableError:
            return _core_unavailable()
        except Exception:
            return _core_unavailable()

    @app.get("/api/tasks/{task_id}/artifacts/{artifact_id}")
    async def task_artifact(
        request: Request, task_id: str, artifact_id: str
    ) -> Response:
        if not _query_is(request, allowed="revision"):
            return _invalid_request()
        try:
            parsed_task_id = UUID(task_id)
            parsed_artifact_id = UUID(artifact_id)
            raw_revision = request.query_params.get("revision", "")
            if not raw_revision.isascii() or not raw_revision.isdigit():
                return _invalid_request()
            revision = int(raw_revision)
            if not 1 <= revision <= 2_147_483_647:
                return _invalid_request()
        except (TypeError, ValueError):
            return _task_not_found()
        try:
            download = core.task_artifact(
                _bearer(request),
                parsed_task_id,
                parsed_artifact_id,
                result_revision=revision,
            )
        except MiniAppAuthenticationError:
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        except MiniAppTaskNotFoundError:
            return _task_not_found()
        except MiniAppCoreUnavailableError:
            return _core_unavailable()
        except Exception:
            return _core_unavailable()
        artifact = download.artifact
        return Response(
            content=download.content,
            media_type=artifact.media_type,
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{artifact.filename}"'
                ),
                "ETag": f'"{artifact.content_digest[7:]}"',
            },
        )

    static_root = Path(__file__).with_name("miniapp_static")
    app.mount("/", StaticFiles(directory=static_root, html=True), name="miniapp")
    return app


class _RequestBodyTooLarge(Exception):
    pass


async def _read_bounded_body(
    request: Request, *, max_bytes: int, timeout_seconds: float
) -> bytes:
    body = bytearray()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    stream = request.stream()
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError
        try:
            # A fresh await keeps middleware cancellation scopes from consuming
            # the total timeout after a successfully received initial chunk.
            chunk = await asyncio.wait_for(anext(stream), timeout=remaining)
        except StopAsyncIteration:
            return bytes(body)
        if len(body) + len(chunk) > max_bytes:
            raise _RequestBodyTooLarge
        body.extend(chunk)


async def _body_is_empty(request: Request, *, timeout_seconds: float) -> bool:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) != 0:
                return False
        except ValueError:
            return False
    if "transfer-encoding" in request.headers:
        return False
    try:
        await _read_bounded_body(
            request,
            max_bytes=0,
            timeout_seconds=timeout_seconds,
        )
    except (_RequestBodyTooLarge, TimeoutError):
        return False
    return True


def _bearer(request: Request) -> str:
    value = request.headers.get("authorization", "")
    parts = value.split(" ")
    if len(parts) != 2 or parts[0] != "Bearer" or not 32 <= len(parts[1]) <= 128:
        raise MiniAppAuthenticationError("unauthorized")
    return parts[1]


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _multipart_task_payload(
    raw: bytes, content_type: str
) -> tuple[dict[str, object], MiniAppTaskMaterial]:
    """Parse the bounded two-part form without disk files or an upload service."""
    if len(content_type) > 200 or "\r" in content_type or "\n" in content_type:
        raise ValueError("invalid multipart")
    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + content_type.encode("ascii") + b"\r\n\r\n" + raw
    )
    boundary = message.get_boundary()
    if (
        not isinstance(boundary, str)
        or re.fullmatch(r"[0-9A-Za-z'()+_,./:=?-]{1,70}", boundary) is None
        or len(message.get_params()) != 2
        or message.get_params()[1][0].lower() != "boundary"
        or not message.is_multipart()
        or message.preamble is not None
        or message.epilogue not in {None, ""}
    ):
        raise ValueError("invalid multipart")
    marker = boundary.encode("ascii")
    if not raw.startswith(b"--" + marker + b"\r\n") or not (
        raw.endswith(b"\r\n--" + marker + b"--\r\n")
        or raw.endswith(b"\r\n--" + marker + b"--")
    ):
        raise ValueError("incomplete multipart")
    parts = {}
    for part in message.iter_parts():
        if (
            part.is_multipart()
            or sorted(name.lower() for name in part.keys())
            != ["content-disposition", "content-type"]
            or part.get_content_disposition() != "form-data"
        ):
            raise ValueError("invalid multipart part")
        name = part.get_param("name", header="content-disposition")
        if name not in {"metadata", "material"} or name in parts:
            raise ValueError("invalid multipart part")
        disposition = part.get_params(header="content-disposition")
        expected = ["form-data", "name"] + (["filename"] if name == "material" else [])
        if sorted(key.lower() for key, _ in disposition) != sorted(expected):
            raise ValueError("invalid multipart disposition")
        mime = "application/json" if name == "metadata" else "text/plain"
        type_params = part.get_params()
        if (
            part.get_content_type() != mime
            or len(type_params) > 2
            or (len(type_params) == 2 and type_params[1] != ("charset", "utf-8"))
            or (name == "material" and len(type_params) != 2)
        ):
            raise ValueError("invalid multipart media type")
        parts[name] = part
    if set(parts) != {"metadata", "material"} or any(
        item.defects or any(getattr(value, "defects", ()) for value in item.values())
        for item in message.walk()
    ):
        raise ValueError("invalid multipart")
    payload = json.loads(
        parts["metadata"].get_payload(decode=True).decode("utf-8", errors="strict"),
        object_pairs_hook=_unique_object,
    )
    if not isinstance(payload, dict) or "material" not in payload:
        raise ValueError("invalid multipart metadata")
    metadata = payload.pop("material")
    if not isinstance(metadata, dict) or set(metadata) != {
        "filename", "media_type", "size", "content_digest"
    }:
        raise ValueError("invalid material metadata")
    material = MiniAppTaskMaterial(
        **metadata,
        text=parts["material"].get_payload(decode=True).decode("utf-8", errors="strict"),
    )
    if material.filename != parts["material"].get_filename():
        raise ValueError("invalid material filename")
    material.checked_instruction("")
    return payload, material


def _query_is(request: Request, *, allowed: str) -> bool:
    keys = list(request.query_params.keys())
    return not keys or (keys == [allowed] and len(request.query_params.getlist(allowed)) == 1)


def _invalid_request() -> JSONResponse:
    return JSONResponse({"detail": "invalid_request"}, status_code=400)


def _task_not_found() -> JSONResponse:
    return JSONResponse({"detail": "task_not_found"}, status_code=404)


def _core_unavailable() -> JSONResponse:
    return JSONResponse({"detail": _UNAVAILABLE}, status_code=503)
