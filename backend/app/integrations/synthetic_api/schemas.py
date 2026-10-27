"""Capability descriptors for the synthetic API (WP-C)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FaultInjectionSpec(BaseModel):
    """One advertised fault-injection knob."""

    parameter: str
    type: str = "integer"
    minimum: int
    maximum: int
    description: str


class AuthenticationSpec(BaseModel):
    """How the synthetic surface authenticates callers (never the keys)."""

    modes: list[str] = Field(default_factory=list)
    active_mode: str = "off"
    keys_configured: bool = False
    header: str = "X-API-Key"
    bearer_header: str = "Authorization"
    sentinels: dict[str, str] = Field(default_factory=dict)


class RedactionSpec(BaseModel):
    """Redaction guarantees applied to telemetry."""

    enabled: bool = True
    marker: str = "[REDACTED]"
    sensitive_keys: list[str] = Field(default_factory=list)


class SyntheticAPIDescriptor(BaseModel):
    """Self-description of the emulated API surface served to agents."""

    name: str
    version: str
    protocols: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    fault_injection: list[FaultInjectionSpec] = Field(default_factory=list)
    authentication: AuthenticationSpec = Field(default_factory=AuthenticationSpec)
    redaction: RedactionSpec = Field(default_factory=RedactionSpec)
    endpoints: dict[str, str] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)
