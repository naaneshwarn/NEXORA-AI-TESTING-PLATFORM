"""Shared pytest fixtures (Rajath — Work Package B).

Purpose
-------
Guarantee that the *test suite never talks to a real Docker daemon by accident*.

The Phase 2 contract test ``test_api_contracts.py::test_environment_and_evaluation_contract``
drives the real FastAPI app via ``TestClient(app)``.  With Work Package B in
place, ``POST /api/v1/environments`` schedules real provisioning in the
background.  On a machine where Docker is running, that path would create a real
container — an unwanted side effect that can also leak a container when the test
only calls ``/stop`` (stop != remove).

This conftest installs a deterministic, Docker-free provider for the process-wide
environment manager for the duration of the test session, so:

- unit/contract tests are hermetic and need no Docker (guide rule);
- no real container is created by ordinary tests;
- the only tests that touch the real daemon are the explicitly marked live
  integration tests in ``test_environment_docker_integration.py``, which opt in
  via their own provider instance.

Nothing here changes production behaviour: it only replaces the manager used by
the in-process API during tests.
"""

from __future__ import annotations

import pytest

from app.integrations.environment.docker_provider import (
    ContainerSpec,
    DEFAULT_INTERNAL_PORT,
)


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
