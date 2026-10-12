from __future__ import annotations

from typing import Any, Callable

from pydantic import ValidationError

from app.core.store import (
    create_crm_lead,
    delete_crm_lead,
    get_crm_lead,
    list_crm_leads,
    update_crm_lead,
)
from app.schemas.crm import CRMLeadCreate

_CRM_WRITABLE_FIELDS = ("name", "email", "company", "status")


class ToolNotFoundError(ValueError):
    """Raised when the requested synthetic tool is not registered."""


class ToolExecutionError(RuntimeError):
    """Raised when a registered synthetic tool fails to execute."""


def _require_lead_id(parameters: dict[str, Any]) -> str:
    lead_id = parameters.get("lead_id") or parameters.get("id")
    if not lead_id:
        raise ValueError("Parameter 'lead_id' is required.")
    return str(lead_id)


def _crm_list_leads(parameters: dict[str, Any]) -> list[dict[str, Any]]:
    return list_crm_leads()


def _crm_get_lead(parameters: dict[str, Any]) -> dict[str, Any]:
    lead_id = _require_lead_id(parameters)
    lead = get_crm_lead(lead_id)
    if lead is None:
        raise ToolExecutionError(f"Lead '{lead_id}' was not found.")
    return lead


def _crm_create_lead(parameters: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = CRMLeadCreate(**parameters)
    except ValidationError as exc:
        raise ToolExecutionError(f"Invalid CRM lead payload: {exc}") from exc
    return create_crm_lead(payload.model_dump())


def _crm_update_lead(parameters: dict[str, Any]) -> dict[str, Any]:
    lead_id = _require_lead_id(parameters)
    if get_crm_lead(lead_id) is None:
        raise ToolExecutionError(f"Lead '{lead_id}' was not found.")
    update = {key: parameters[key] for key in _CRM_WRITABLE_FIELDS if key in parameters}
    if not update:
        raise ValueError("At least one of 'name', 'email', 'company', or 'status' must be provided.")
    return update_crm_lead(lead_id, update)


def _crm_delete_lead(parameters: dict[str, Any]) -> dict[str, Any]:
    lead_id = _require_lead_id(parameters)
    if get_crm_lead(lead_id) is None:
        raise ToolExecutionError(f"Lead '{lead_id}' was not found.")
    delete_crm_lead(lead_id)
    return {"lead_id": lead_id, "deleted": True}


# Aliases keep the registry friendly to dotted and snake_case tool names.
TOOL_REGISTRY: dict[str, Callable[[dict[str, Any]], Any]] = {
    "list_crm_leads": _crm_list_leads,
    "crm.list_leads": _crm_list_leads,
    "get_crm_lead": _crm_get_lead,
    "crm.get_lead": _crm_get_lead,
    "create_crm_lead": _crm_create_lead,
    "crm.create_lead": _crm_create_lead,
    "update_crm_lead": _crm_update_lead,
    "crm.update_lead": _crm_update_lead,
    "delete_crm_lead": _crm_delete_lead,
    "crm.delete_lead": _crm_delete_lead,
}


def execute_synthetic_tool(tool_name: str, parameters: dict[str, Any] | None = None) -> Any:
    """Execute a synthetic tool by name against the in-memory store."""
    handler = TOOL_REGISTRY.get(tool_name)
    if handler is None:
        raise ToolNotFoundError(f"Unknown synthetic tool '{tool_name}'.")
    return handler(parameters or {})
