"""Synthetic API integration package (Prajwal / Work Package C).

Houses the reusable pieces of the emulated external surface the agents are
tested against:

* :mod:`~app.integrations.synthetic_api.faults` — deterministic fault-injection
  query contract shared by the CRM read endpoints.
* :mod:`~app.integrations.synthetic_api.repository` — the lead repository the
  CRM routes and tool registry are served from.
* :mod:`~app.integrations.synthetic_api.schemas` — capability descriptor
  models describing the synthetic surface (protocols, tools, fault ranges).
* :mod:`~app.integrations.synthetic_api.app` — the router that publishes that
  self-description under ``GET /api/v1/synthetic``.
"""

from app.integrations.synthetic_api.app import create_synthetic_api_router
from app.integrations.synthetic_api.faults import (
    InjectError,
    SimulatedLatencyMs,
    apply_fault_injection,
)
from app.integrations.synthetic_api.repository import LeadRepository, lead_repository
from app.integrations.synthetic_api.schemas import (
    AuthenticationSpec,
    FaultInjectionSpec,
    RedactionSpec,
    SyntheticAPIDescriptor,
)

__all__ = [
    "create_synthetic_api_router",
    "InjectError",
    "SimulatedLatencyMs",
    "apply_fault_injection",
    "LeadRepository",
    "lead_repository",
    "AuthenticationSpec",
    "FaultInjectionSpec",
    "RedactionSpec",
    "SyntheticAPIDescriptor",
]
