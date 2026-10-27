"""Cross-cutting ASGI middleware: observability, security headers, auth.

Both middlewares are *pure* ASGI (not ``BaseHTTPMiddleware``) so they pass
Server-Sent Events and other streaming responses through untouched — the SSE
trace stream would otherwise risk being buffered or broken by a wrapping
layer.

Registration order in ``app.main`` (Starlette: the middleware added last is
outermost):

    ObservabilityMiddleware  (security headers + request log, outermost)
      └── CORSMiddleware     (answers preflight OPTIONS before auth runs)
            └── AuthMiddleware  (edge-level API-key enforcement)
              └── application
"""

from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable, Iterable

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.core.auth import (
    OPEN_PATHS,
    authenticate_token,
    extract_token_from_headers,
    requires_auth,
)

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]

_logger = logging.getLogger("nexora.http")

# Response headers applied to every HTTP response (including error responses).
SECURITY_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"cross-origin-resource-policy", b"same-origin"),
    (b"permissions-policy", b"geolocation=(), microphone=(), camera=()"),
)


def _path_is_chatty(path: str) -> bool:
    """Health/schema/readiness probes poll constantly — keep them out of the log."""
    if path in OPEN_PATHS:
        return True
    return path.endswith("/readiness")


def _envelope_for(exc: HTTPException) -> JSONResponse:
    """Render an HTTPException with the platform's standard error envelope."""
    detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
    message = detail.get("message", "Request failed")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": f"http_{exc.status_code}",
                "message": message,
                "details": detail,
            },
        },
    )


class ObservabilityMiddleware:
    """Attach security headers to every response and log completed requests."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        method: str = scope.get("method", "GET")
        client = scope.get("client") or ("-", 0)
        started = time.perf_counter()
        status_code: int | None = None

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers: list[tuple[bytes, bytes]] = message.setdefault("headers", [])
                existing = {name.lower() for name, _ in headers}
                for name, value in SECURITY_HEADERS:
                    if name not in existing:
                        headers.append((name, value))
            await send(message)

        def log_outcome(outcome_status: int, *, failed: bool = False) -> None:
            if _path_is_chatty(path):
                return
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            level = logging.WARNING if failed or outcome_status >= 500 else logging.INFO
            _logger.log(
                level,
                "%s %s -> %s (%.2f ms) client=%s:%s",
                method,
                path,
                outcome_status,
                duration_ms,
                client[0],
                client[1],
            )

        try:
            await self.app(scope, receive, send_wrapper)
        except BaseException:
            log_outcome(status_code or 500, failed=True)
            raise
        else:
            log_outcome(status_code or 200)


class AuthMiddleware:
    """Enforce API-key authentication at the edge for protected requests.

    Runs after CORS (so preflights are answered without a credential challenge)
    and before the router.  Rejections use the same error envelope as the
    application's exception handlers, so clients cannot tell whether a 401 came
    from the middleware or from a route dependency.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        method: str = scope.get("method", "GET")

        if requires_auth(method, path):
            headers = {name.lower(): value for name, value in scope.get("headers", [])}
            token = extract_token_from_headers(headers)
            try:
                authenticate_token(token, enforce=True)
            except HTTPException as exc:
                response = _envelope_for(exc)
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


def security_headers_for(status_code: int) -> Iterable[tuple[str, str]]:
    """Test helper: the header set applied to a response of ``status_code``."""
    _ = status_code
    return [(name.decode(), value.decode()) for name, value in SECURITY_HEADERS]
