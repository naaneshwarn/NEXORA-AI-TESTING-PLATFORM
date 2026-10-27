"""Synthetic API surface router (WP-C).

Publishes a machine-readable self-description of the emulated API at
``GET /api/v1/synthetic`` so agents, contract tests and humans can discover
what the platform can be tested against: supported wire protocols, the tool
registry, the fault-injection ranges and the redaction/authentication
contract.  A companion ``GET /api/v1/synthetic/tools`` returns just the tool
names for quick wiring checks.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.adapters import AdapterFactory
from app.core.auth import (
    FORBIDDEN_TOKEN,
    INVALID_TOKEN,
    VALID_AUTH_MODES,
    configured_api_keys,
    resolve_auth_mode,
    verify_optional_auth,
)
from app.core.config import settings
from app.core.redaction import REDACTED, SENSITIVE_KEYS
from app.core.tools import TOOL_REGISTRY
from app.integrations.synthetic_api.faults import (
    ERROR_CODE_RANGE,
    LATENCY_RANGE_MS,
)
from app.integrations.synthetic_api.schemas import (
    AuthenticationSpec,
    FaultInjectionSpec,
    RedactionSpec,
    SyntheticAPIDescriptor,
)
from app.schemas.common import ApiEnvelope

_SYNTHETIC_API_VERSION = "1.0.0"


def build_descriptor() -> SyntheticAPIDescriptor:
    """Compose the live capability descriptor from the current process state."""
    keys_configured = bool(configured_api_keys())
    return SyntheticAPIDescriptor(
        name="NEXORA Synthetic CRM API",
        version=_SYNTHETIC_API_VERSION,
        protocols=AdapterFactory.supported_protocols(),
        tools=sorted(TOOL_REGISTRY),
        fault_injection=[
            FaultInjectionSpec(
                parameter="simulated_latency_ms",
                minimum=LATENCY_RANGE_MS[0],
                maximum=LATENCY_RANGE_MS[1],
                description="Non-blocking synthetic delay applied before the response.",
            ),
            FaultInjectionSpec(
                parameter="inject_error",
                minimum=ERROR_CODE_RANGE[0],
                maximum=ERROR_CODE_RANGE[1],
                description="Deterministic HTTP error status returned instead of the result.",
            ),
        ],
        authentication=AuthenticationSpec(
            modes=sorted(VALID_AUTH_MODES),
            active_mode=resolve_auth_mode(),
            keys_configured=keys_configured,
            sentinels={"401": INVALID_TOKEN, "403": FORBIDDEN_TOKEN},
        ),
        redaction=RedactionSpec(
            enabled=True,
            marker=REDACTED,
            sensitive_keys=sorted(SENSITIVE_KEYS),
        ),
        endpoints={
            "describe": f"{settings.api_prefix}/synthetic",
            "tools": f"{settings.api_prefix}/synthetic/tools",
            "execute": f"{settings.api_prefix}/synthetic/agent/execute/{{protocol}}",
            "leads": f"{settings.api_prefix}/leads",
        },
    )


def create_synthetic_api_router() -> APIRouter:
    """Build the router exposing the synthetic API's self-description."""
    router = APIRouter(tags=["synthetic-api"])

    @router.get("/synthetic", response_model=ApiEnvelope[SyntheticAPIDescriptor])
    async def describe_synthetic_api(
        auth_info: dict = Depends(verify_optional_auth),
    ) -> ApiEnvelope[SyntheticAPIDescriptor]:
        """Describe protocols, tools, fault ranges, auth mode and redaction."""
        return ApiEnvelope(success=True, data=build_descriptor())

    @router.get("/synthetic/tools", response_model=ApiEnvelope[list[str]])
    async def list_synthetic_tools(
        auth_info: dict = Depends(verify_optional_auth),
    ) -> ApiEnvelope[list[str]]:
        """List the tool names agents can call on the synthetic surface."""
        return ApiEnvelope(success=True, data=sorted(TOOL_REGISTRY))

    return router
