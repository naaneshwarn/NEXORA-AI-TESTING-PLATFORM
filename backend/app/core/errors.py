from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette import status

from app.core.config import settings

logger = logging.getLogger("nexora.errors")


class NEXORAException(Exception):
    """Base exception for NEXORA platform errors."""

    def __init__(
        self,
        message: str,
        code: str = "nexora_error",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(NEXORAException):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            code="not_found",
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class ConflictError(NEXORAException):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            code="conflict",
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class ValidationError(NEXORAException):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            code="validation_error",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class BadStateError(NEXORAException):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            code="invalid_state_transition",
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )


class ServiceUnavailableError(NEXORAException):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            code="service_unavailable",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=details,
        )


def _error_payload(code: str, message: str, details: Any | None = None) -> dict[str, Any]:
    return {
        "success": False,
        "data": None,
        "error": {
            "code": code,
            "message": message,
            "details": details if details is not None else {},
        },
    }


_STATUS_TO_CODE = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "unauthorized",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "validation_error",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "internal_server_error",
    status.HTTP_503_SERVICE_UNAVAILABLE: "service_unavailable",
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        logger.warning("Validation error on %s %s: %s", request.method, request.url.path, exc.errors())
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_payload(
                "validation_error",
                "Request validation failed",
                {"errors": exc.errors()},
            ),
        )

    @app.exception_handler(NEXORAException)
    async def handle_nexora_exception(request: Request, exc: NEXORAException) -> JSONResponse:
        logger.warning(
            "Application error [%s] on %s %s: %s",
            exc.code,
            request.method,
            request.url.path,
            exc.message,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict):
            detail_dict = exc.detail
            message = detail_dict.get("message", "Request failed")
            code = detail_dict.get("code") or _STATUS_TO_CODE.get(exc.status_code, f"http_{exc.status_code}")
            details = detail_dict.get("details", detail_dict)
        else:
            message = str(exc.detail) if exc.detail else "Request failed"
            code = _STATUS_TO_CODE.get(exc.status_code, f"http_{exc.status_code}")
            details = {}

        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(code, message, details),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unexpected error on %s %s: %s", request.method, request.url.path, exc)
        # Never leak raw stack traces or internal details in production
        details = {} if settings.app_env.lower() == "production" else {"type": type(exc).__name__}
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_payload(
                "internal_server_error",
                "An unexpected error occurred.",
                details,
            ),
        )

