"""Deterministic fault injection for the synthetic API (WP-C).

The parameters exist solely to exercise agent resiliency — timeouts, rate
limiting and server failures — against the emulated surface, never real
infrastructure.  Behaviour is deterministic and side-effect free: a fault is
evaluated *before* any store operation, so an injected failure can never
corrupt synthetic data.

The same contract is reused by every read endpoint that opts in, and is
advertised through ``GET /api/v1/synthetic`` so tooling can discover it.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import HTTPException, Query

# Shared fault-injection query parameters.
SimulatedLatencyMs = Annotated[
    int | None,
    Query(
        ge=0,
        le=60_000,
        description="Inject a synthetic delay (in milliseconds) before responding.",
    ),
]
InjectError = Annotated[
    int | None,
    Query(
        ge=400,
        le=599,
        description="Simulate an HTTP error status (e.g. 429 rate limit, 500 server error).",
    ),
]

# Advertised ranges (mirrored in the OpenAPI metadata above; kept as constants
# so the capability descriptor cannot drift from the query constraints).
LATENCY_RANGE_MS = (0, 60_000)
ERROR_CODE_RANGE = (400, 599)


async def apply_fault_injection(
    simulated_latency_ms: int | None,
    inject_error: int | None,
) -> None:
    """Apply deterministic fault injection for agent resiliency testing.

    Raises immediately when ``inject_error`` is set (matching the reference
    behaviour), otherwise introduces a non-blocking latency so the event loop
    stays free to service concurrent requests.
    """
    if inject_error is not None:
        raise HTTPException(
            status_code=inject_error,
            detail={"message": f"Simulated fault triggered with error code {inject_error}"},
        )

    if simulated_latency_ms:
        await asyncio.sleep(simulated_latency_ms / 1000.0)
