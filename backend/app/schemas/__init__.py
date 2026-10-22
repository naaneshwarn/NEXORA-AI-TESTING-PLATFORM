"""Shared API schema definitions for the NEXORA backend."""

from app.schemas.agent import AgentConfig, AgentRegistrationResponse
from app.schemas.common import ApiEnvelope, ErrorDetail, ErrorEnvelope, HealthResponse
from app.schemas.environment import SyntheticEnvironment, SyntheticEnvironmentRequest
from app.schemas.evaluation import EvaluationResult, EvaluationSubmission, ReportSummary
from app.schemas.events import ExecutionEvent, ToolCallTrace
from app.schemas.test_run import ExecutionStatus, RunCreateRequest, RunDetail, ScenarioConfig

__all__ = [
    "AgentConfig",
    "AgentRegistrationResponse",
    "ApiEnvelope",
    "ErrorDetail",
    "ErrorEnvelope",
    "HealthResponse",
    "SyntheticEnvironment",
    "SyntheticEnvironmentRequest",
    "EvaluationResult",
    "EvaluationSubmission",
    "ReportSummary",
    "ExecutionEvent",
    "ToolCallTrace",
    "ExecutionStatus",
    "RunCreateRequest",
    "RunDetail",
    "ScenarioConfig",
]
