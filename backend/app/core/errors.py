from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette import status


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
                {"errors": exc.errors()},
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
