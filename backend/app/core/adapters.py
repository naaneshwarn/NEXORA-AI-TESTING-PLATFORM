from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, ClassVar
from uuid import uuid4

from pydantic import BaseModel, Field


class AgentToolRequest(BaseModel):
    """Protocol-agnostic representation of an inbound agent tool call."""

    call_id: str = Field(..., min_length=1)
    tool_name: str = Field(..., min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    agent_id: str | None = None


class AgentToolResponse(BaseModel):
    """Protocol-agnostic representation of the outcome of a tool call."""

    call_id: str = Field(..., min_length=1)
    success: bool
    data: Any | None = None
    error: dict[str, Any] | None = None
    execution_time_ms: float = Field(..., ge=0)


class UnknownProtocolError(ValueError):
    """Raised when no adapter is registered for the requested protocol."""


def _coerce_parameters(value: Any, *, source: str) -> dict[str, Any]:
    """Normalize a tool parameter payload into a plain ``dict``.

    Accepts an already-decoded object, a blank value, or a JSON-encoded object
    string (the shape OpenAI function calling commonly returns).
    """
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        if not value.strip():
            return {}
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"'{source}' must be a JSON object or an object-encoded string.") from exc
        if not isinstance(decoded, dict):
            raise ValueError(f"'{source}' must decode to a JSON object.")
        return decoded
    raise ValueError(f"'{source}' must be a JSON object.")


def _first_present(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return None


class BaseProtocolAdapter(ABC):
    """Translate between a wire protocol and the unified agent tool models."""

    protocol_type: ClassVar[str] = "base"

    @abstractmethod
    def parse_request(self, raw_payload: dict[str, Any]) -> AgentToolRequest:
        """Normalize an inbound protocol payload into an ``AgentToolRequest``."""

    @abstractmethod
    def format_response(self, response: AgentToolResponse) -> dict[str, Any]:
        """Serialize an ``AgentToolResponse`` back into the wire protocol shape."""


class RESTProtocolAdapter(BaseProtocolAdapter):
    """Adapter for standard REST/OpenAPI JSON tool-call payloads."""

    protocol_type = "rest"

    def parse_request(self, raw_payload: dict[str, Any]) -> AgentToolRequest:
        if not isinstance(raw_payload, dict):
            raise ValueError("REST payload must be a JSON object.")

        tool_name = _first_present(raw_payload, ("tool_name", "tool", "name"))
        if not tool_name:
            raise ValueError("REST payload must include 'tool_name'.")

        call_id = _first_present(raw_payload, ("call_id", "id")) or f"call-{uuid4().hex[:8]}"
        parameters = _coerce_parameters(
            _first_present(raw_payload, ("parameters", "params", "arguments")),
            source="parameters",
        )

        return AgentToolRequest(
            call_id=str(call_id),
            tool_name=str(tool_name),
            parameters=parameters,
            agent_id=_first_present(raw_payload, ("agent_id",)),
        )

    def format_response(self, response: AgentToolResponse) -> dict[str, Any]:
        return response.model_dump()


class OpenAIFunctionAdapter(BaseProtocolAdapter):
    """Adapter for OpenAI / LangChain function-calling tool messages."""

    protocol_type = "openai"

    def parse_request(self, raw_payload: dict[str, Any]) -> AgentToolRequest:
        if not isinstance(raw_payload, dict):
            raise ValueError("OpenAI payload must be a JSON object.")

        function = _first_present(raw_payload, ("function", "function_call"))
        if not isinstance(function, dict):
            raise ValueError("OpenAI payload must include a 'function' object.")

        tool_name = function.get("name")
        if not tool_name:
            raise ValueError("OpenAI function payload must include 'function.name'.")

        call_id = _first_present(raw_payload, ("call_id", "id", "tool_call_id")) or f"call-{uuid4().hex[:8]}"
        parameters = _coerce_parameters(function.get("arguments"), source="function.arguments")

        return AgentToolRequest(
            call_id=str(call_id),
            tool_name=str(tool_name),
            parameters=parameters,
            agent_id=_first_present(raw_payload, ("agent_id",)),
        )

    def format_response(self, response: AgentToolResponse) -> dict[str, Any]:
        content = json.dumps(
            {
                "success": response.success,
                "data": response.data,
                "error": response.error,
                "execution_time_ms": response.execution_time_ms,
            },
            default=str,
        )
        return {
            "role": "tool",
            "tool_call_id": response.call_id,
            "content": content,
        }


class AdapterFactory:
    """Registry that resolves a protocol name to a concrete adapter instance."""

    _registry: ClassVar[dict[str, type[BaseProtocolAdapter]]] = {}

    @classmethod
    def register(cls, protocol_type: str, adapter_cls: type[BaseProtocolAdapter]) -> None:
        cls._registry[protocol_type.strip().lower()] = adapter_cls

    @classmethod
    def get_adapter(cls, protocol_type: str | None) -> BaseProtocolAdapter:
        key = (protocol_type or "rest").strip().lower() or "rest"
        adapter_cls = cls._registry.get(key)
        if adapter_cls is None:
            supported = ", ".join(sorted(cls._registry))
            raise UnknownProtocolError(
                f"Unsupported protocol '{protocol_type}'. Supported protocols: {supported}."
            )
        return adapter_cls()

    @classmethod
    def supported_protocols(cls) -> list[str]:
        """Every registered protocol name (used by the capability descriptor)."""
        return sorted(cls._registry)


AdapterFactory.register("rest", RESTProtocolAdapter)
AdapterFactory.register("openai", OpenAIFunctionAdapter)
AdapterFactory.register("openai_function", OpenAIFunctionAdapter)
AdapterFactory.register("function", OpenAIFunctionAdapter)
AdapterFactory.register("langchain", OpenAIFunctionAdapter)
