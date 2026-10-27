"""Lead repository for the synthetic CRM surface (WP-C).

Routes and tool handlers go through this repository instead of touching the
store directly, giving the synthetic API one seam where validation, (future)
paging/filtering and observability can live without spreading across the
codebase.  It delegates to the shared in-memory store, so repository and store
views are always identical.
"""

from __future__ import annotations

from typing import Any

from app.core.store import (
    create_crm_lead,
    delete_crm_lead,
    get_crm_lead,
    list_crm_leads,
    update_crm_lead,
)


class LeadRepository:
    """CRUD access to the synthetic CRM lead collection."""

    def create(self, lead_data: dict[str, Any]) -> dict[str, Any]:
        return create_crm_lead(lead_data)

    def get(self, lead_id: str) -> dict[str, Any] | None:
        return get_crm_lead(lead_id)

    def list(self) -> list[dict[str, Any]]:
        return list_crm_leads()

    def exists(self, lead_id: str) -> bool:
        return get_crm_lead(lead_id) is not None

    def update(self, lead_id: str, lead_data: dict[str, Any]) -> dict[str, Any]:
        return update_crm_lead(lead_id, lead_data)

    def delete(self, lead_id: str) -> None:
        delete_crm_lead(lead_id)

    def clear(self) -> None:
        """Remove every lead (used by contract tests and reset tooling)."""
        for lead_id in list(list_crm_leads()):
            delete_crm_lead(lead_id["id"])


# Process-wide repository used by the CRM routes.
lead_repository = LeadRepository()
