from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette import status

# Errors returned by validation are JSON-serialized verbatim.  Pydantic echoes
# the offending input back in each error's ``input`` field, and for a
# non-JSON body (e.g. ``text/plain``) that value is raw ``bytes`` — which
# ``json.dumps`` cannot encode.  Without sanitizing, the 422 handler itself
# raises ``TypeError`` and the client sees a misleading 500.  We coerce any
# non-JSON-serializable value to a safe, human-readable placeholder so the
# contract (a well-formed 422 envelope) always holds.
_MAX_ECHO_BYTES = 256


def _safe_json_value(value: Any) -> Any:
    """Return a JSON-serializable stand-in for an arbitrary value."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (bytes, bytearray)):
        try:
            text = bytes(value).decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - never let serialization raise
            return f"<{len(value)} bytes>"
        if len(text) > _MAX_ECHO_BYTES:
            text = text[:_MAX_ECHO_BYTES] + "…"
        return text
    if isinstance(value, dict):
        return {str(k): _safe_json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_json_value(v) for v in value]
    return str(value)


def _error_payload(code: str, message: str, details: Any | None = None) -> dict[str, Any]:
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
    }


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_payload(
                "validation_error",
                "Request validation failed",
                {"errors": _safe_json_value(exc.errors())},
            ),
        )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(
                f"http_{exc.status_code}",
                detail.get("message", "Request failed") if isinstance(detail, dict) else str(exc.detail),
                detail if isinstance(detail, dict) else {"message": str(exc.detail)},
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_payload(
                "internal_server_error",
                "An unexpected error occurred.",
                {"type": type(exc).__name__},
            ),
        )
