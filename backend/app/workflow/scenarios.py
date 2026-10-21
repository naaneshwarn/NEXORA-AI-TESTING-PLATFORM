"""Deterministic scenario registry (Rahul / Work Package D).

A scenario declares what a workflow run should do, which synthetic tool it
may call, which record fields the agent summary must reflect, and which
markers count as invented ("hallucinated") facts.  Expected results live here
— never in the agent-visible prompt — as required by the Phase 3 guide.

All built-in scenarios run against the synthetic CRM tool registry and need
no LLM credentials, network access, or Docker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.core.store import create_crm_lead, list_crm_leads

AgentBehavior = Literal["correct", "hallucinated", "error", "timeout"]

# Deterministic synthetic lead used when a run does not pin a specific record.
SEED_LEAD_EMAIL = "seed.lead@nexora.test"
SEED_LEAD = {
    "name": "Synthetic Seed Lead",
    "email": SEED_LEAD_EMAIL,
    "company": "NEXORA Synthetic Labs",
    "status": "qualified",
}


@dataclass(frozen=True)
class ScenarioDefinition:
    """Immutable definition of one executable test scenario."""

    scenario_id: str
    description: str
    goal: str
    tool_name: str
    summary_fields: tuple[str, ...] = ("name", "email", "status")
    agent_behavior: AgentBehavior = "correct"
    forbidden_markers: tuple[str, ...] = ()
    default_timeout_seconds: float = 10.0


def _scenarios() -> dict[str, ScenarioDefinition]:
    return {
        scenario.scenario_id: scenario
        for scenario in (
            ScenarioDefinition(
                scenario_id="crm-read-customer-summary",
                description="Retrieve one synthetic CRM lead and summarize only the returned fields.",
                goal="Retrieve one synthetic customer and accurately summarize returned fields.",
                tool_name="get_crm_lead",
            ),
            ScenarioDefinition(
                scenario_id="crm-read-customer-hallucination",
                description="Same lookup, but the mock agent invents an unsupported account tier.",
                goal="Detect invented customer details that are absent from the source record.",
                tool_name="get_crm_lead",
                agent_behavior="hallucinated",
                forbidden_markers=("platinum-vip",),
            ),
            ScenarioDefinition(
                scenario_id="crm-read-customer-agent-failure",
                description="The mock agent backend fails deterministically during the lookup.",
                goal="Produce a useful failed-run report when the target agent errors.",
                tool_name="get_crm_lead",
                agent_behavior="error",
            ),
        )
    }


SCENARIOS: dict[str, ScenarioDefinition] = _scenarios()


def get_scenario(scenario_id: str) -> ScenarioDefinition | None:
    return SCENARIOS.get(scenario_id)


def is_registered_scenario(scenario_id: str) -> bool:
    return scenario_id in SCENARIOS


def list_scenario_ids() -> list[str]:
    return sorted(SCENARIOS)


def ensure_seed_lead() -> dict[str, Any]:
    """Idempotently create (or reuse) the deterministic demo lead.

    The lead is synthetic by construction; this function never reads from or
    writes to anything outside the in-memory store.
    """
    for lead in list_crm_leads():
        if lead.get("email") == SEED_LEAD_EMAIL:
            return lead
    return create_crm_lead(dict(SEED_LEAD))
