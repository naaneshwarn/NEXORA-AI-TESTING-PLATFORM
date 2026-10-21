"""Shared pytest fixtures for the backend suite (Work Packages B and D).

This file is the single merge point of the two independent work packages:

* **Work Package B (Rajath / environments)** — guarantees the test suite never
  talks to a real Docker daemon by accident.  The Phase 2 contract test drives
  the real FastAPI app via ``TestClient(app)``; with WP-B in place,
  ``POST /api/v1/environments`` schedules real provisioning in the background.
  On a machine where Docker runs, that would create (and potentially leak) a
  real container.  ``_docker_free_environment_manager`` installs a
  deterministic, Docker-free provider for the process-wide environment manager
  so unit/contract tests stay hermetic.  The only tests that touch the real
  daemon are the explicitly marked live integration tests in
  ``test_environment_docker_integration.py``, which opt in via their own
  provider instance.

* **Work Package D (Rahul / workflow)** — isolates the workflow subsystem's
  durable run-context store into a temporary directory so tests never write
  into the repository and always start from a clean snapshot, and silences
  workflow logging noise during the run.

Nothing here changes production behaviour: it only adjusts the manager used by
the in-process API and the workflow store's target directory during tests.
"""

from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

import pytest

from app.integrations.environment.docker_provider import (
    ContainerSpec,
    DEFAULT_INTERNAL_PORT,
)

# Make ``app`` importable when pytest is invoked from the repository root.
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# --------------------------------------------------------------------------- #
# Work Package B — Docker-free environment manager                             #
# --------------------------------------------------------------------------- #
class _NoopDockerProvider:
    """A provider that provisions nothing and never touches Docker.

    It reports Docker as *unavailable* so provisioning transitions to a
    deterministic ``failed`` state (with a safe message) instead of inventing a
    ready environment — mirroring the real "Docker not running" behaviour and
    keeping tests honest.
    """

    def available(self) -> bool:
        return False

    def create(self, spec: ContainerSpec) -> tuple[str, str]:  # pragma: no cover - never reached
        raise AssertionError("test provider must not create containers")

    def is_running(self, container_id: str) -> bool:
        return False

    def container_status(self, container_id: str) -> str | None:
        return None

    def host_port(self, container_id: str, internal_port: int = DEFAULT_INTERNAL_PORT) -> int | None:
        return None

    def exec_command(
        self, container_id: str, command: list[str], *, input_text: str | None = None
    ) -> tuple[int, str, str]:
        return 1, "", "no container in test provider"

    def wait_for_ready(
        self, container_id: str, *, database: str, username: str, timeout_seconds: float = 30.0, poll_interval: float = 0.5
    ) -> bool:
        return False

    def stop(self, container_id: str) -> bool:
        return True

    def remove(self, container_id: str, *, force: bool = True) -> bool:
        return False


@pytest.fixture(autouse=True)
def _docker_free_environment_manager():
    """Force the API's environment manager to a Docker-free provider for tests.

    Autouse so every test is hermetic.  Tests that need a *specific* fake can
    still override the manager themselves; tests that need the real daemon use
    ``DockerProvider`` directly (the live integration tests).
    """
    from app.api.routes import environments as env_routes
    from app.integrations.environment.manager import EnvironmentManager

    env_routes.set_manager(EnvironmentManager(provider=_NoopDockerProvider()))
    try:
        yield
    finally:
        env_routes.set_manager(None)


# --------------------------------------------------------------------------- #
# Work Package D — isolated, quiet workflow state                              #
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True, scope="session")
def _isolate_workflow_state():
    """Redirect the durable run-context store to a throwaway temp directory."""
    import app.workflow.service as service
    import app.workflow.runtime as runtime

    tmp = Path(tempfile.mkdtemp(prefix="nexora-wf-test-"))
    # Point the store at an isolated path and reset cached singletons.
    service._CONTEXT_STORE = runtime.RunContextStore(tmp / "run_contexts.json")
    service.RUN_CONTEXTS.clear()
    # Reduce log noise for the test run.
    logging.getLogger("nexora").setLevel(logging.CRITICAL)

    yield

    logging.getLogger("nexora").setLevel(logging.NOTSET)
