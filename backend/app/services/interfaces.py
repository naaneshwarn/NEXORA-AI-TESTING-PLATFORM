from __future__ import annotations

"""Integration interfaces coordinating NEXORA platform modules across team members.

Module assignments:
- Naaneshwar: FastAPI core, API contracts, routing, and integration coordination.
- Rajath: Docker lifecycle, synthetic database provisioning (Postgres, MySQL, Mongo, Redis, Neo4j).
- Prajwal: Target-agent adapters, protocol wrappers, synthetic API simulation.
- Rahul: LangGraph workflow orchestration, simulated user execution, evaluation, and reporting.
"""

from typing import Any, Protocol, runtime_checkable

from app.schemas.agent import AgentConfig
from app.schemas.environment import SyntheticEnvironment
from app.schemas.evaluation import ReportSummary
from app.schemas.events import ExecutionEvent
from app.schemas.test_run import RunDetail, ScenarioConfig


@runtime_checkable
class DockerLifecycleProtocol(Protocol):
    """Interface for Rajath's Docker lifecycle and synthetic database module."""

    def provision_environment(
        self,
        environment_type: str,
        label: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Provisions a synthetic environment or container and returns runtime metadata."""
        ...

    def stop_environment(self, environment_id: str) -> bool:
        """Stops and deprovisions an active synthetic environment."""
        ...

    def check_health(self, environment_id: str) -> dict[str, Any]:
        """Checks the connectivity and health of the provisioned container."""
        ...


@runtime_checkable
class AgentAdapterProtocol(Protocol):
    """Interface for Prajwal's target-agent adapter and protocol wrapper module."""

    def invoke_agent(
        self,
        agent: AgentConfig,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Invokes a registered AI agent via its configured protocol or mock provider."""
        ...

    def ping(self, agent: AgentConfig) -> bool:
        """Verifies reachability of the target agent endpoint."""
        ...


@runtime_checkable
class WorkflowOrchestratorProtocol(Protocol):
    """Interface for Rahul's LangGraph workflow orchestration module."""

    def start_run(
        self,
        run: RunDetail,
        scenario: ScenarioConfig | None = None,
    ) -> str:
        """Triggers the LangGraph workflow for the given test run and returns workflow execution ID."""
        ...

    def cancel_workflow(self, run_id: str) -> bool:
        """Cancels an active LangGraph workflow execution."""
        ...


@runtime_checkable
class EvaluatorProtocol(Protocol):
    """Interface for Rahul's evaluation and reporting module."""

    def evaluate_test_run(
        self,
        run: RunDetail,
        events: list[ExecutionEvent],
    ) -> ReportSummary:
        """Computes benchmark metrics, scores, and findings from run execution traces."""
        ...


# --- Deterministic Mock Implementations for Development ---

class MockDockerLifecycle:
    """Deterministic local mock for environment lifecycle when Docker daemon is not active."""

    def provision_environment(
        self,
        environment_type: str,
        label: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        # Does not pretend a real container was launched; records honest metadata
        return {
            "status": "provisioning",
            "endpoint": None,
            "provider": "mock-docker-lifecycle",
            "note": "Docker daemon integration pending Rajath's module integration.",
        }

    def stop_environment(self, environment_id: str) -> bool:
        return True

    def check_health(self, environment_id: str) -> dict[str, Any]:
        return {"status": "ok", "provider": "mock-docker-lifecycle"}


class MockAgentAdapter:
    """Deterministic local mock for agent execution when external LLM endpoints are not configured."""

    def invoke_agent(
        self,
        agent: AgentConfig,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "agent_id": agent.agent_id,
            "response": f"Mock response for agent '{agent.name}' (role: {agent.role}) to input: {message[:60]}",
            "provider": "mock-agent-adapter",
            "tokens_used": 42,
        }

    def ping(self, agent: AgentConfig) -> bool:
        return True


class MockWorkflowOrchestrator:
    """Deterministic local mock for test-run workflow orchestration."""

    def start_run(
        self,
        run: RunDetail,
        scenario: ScenarioConfig | None = None,
    ) -> str:
        return f"wf-mock-{run.run_id}"

    def cancel_workflow(self, run_id: str) -> bool:
        return True


class MockEvaluator:
    """Deterministic local mock for evaluation reports."""

    def evaluate_test_run(
        self,
        run: RunDetail,
        events: list[ExecutionEvent],
    ) -> dict[str, Any]:
        return {
            "run_id": run.run_id,
            "score": 100.0 if run.state == "passed" else 0.0,
            "summary": f"Evaluation mock summary for run {run.run_id}.",
            "metrics": {"total_events": float(len(events))},
        }
