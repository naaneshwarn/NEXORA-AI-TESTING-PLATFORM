from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiEnvelope(BaseModel, Generic[T]):
    success: bool = True
    data: T | None = None
    error: dict[str, Any] | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    success: bool = False
    error: ErrorDetail


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "nexora"
    environment: str = "development"
    version: str = "0.1.0"
