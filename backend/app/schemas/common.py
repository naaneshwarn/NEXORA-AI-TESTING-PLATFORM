from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error explanation")
    details: dict[str, Any] = Field(default_factory=dict, description="Additional context or validation errors")


class ApiEnvelope(BaseModel, Generic[T]):
    success: bool = Field(default=True, description="Indicates whether the request was successful")
    data: T | None = Field(default=None, description="Response payload data when successful")
    error: ErrorDetail | dict[str, Any] | None = Field(default=None, description="Error detail if request failed")


class ErrorEnvelope(BaseModel):
    success: bool = Field(default=False, description="Always false for error envelopes")
    data: None = Field(default=None, description="Null data payload on error")
    error: ErrorDetail = Field(..., description="Structured error details")


class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="Overall service status")
    service: str = Field(default="nexora", description="Service identifier")
    environment: str = Field(default="development", description="Current deployment environment")
    version: str = Field(default="0.1.0", description="API version")

