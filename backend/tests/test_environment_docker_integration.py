"""Optional live Docker integration test (Rajath — Work Package B).

This test exercises the **real** :class:`DockerProvider` against a running Docker
Engine.  It is skipped automatically when Docker is not available, so the default
test run stays green on machines without Docker (CI, reviewers, offline devs).

Prerequisites to actually run it:
- Docker Engine running and reachable (`docker version` succeeds).
- The Python `docker` SDK installed (`pip install docker`).
- Network access to pull `postgres:16-alpine` the first time.

Guidelines honoured here:
- Only resources this platform creates are used; the container carries the
  platform owner label and is force-removed in teardown.
- No broad host mounts; the default port bind is loopback-only.
- The test never asserts a *fabricated* state: it inspects the container.

Run explicitly with::

    pytest tests/test_environment_docker_integration.py -v -m docker

or simply let it skip::

    pytest tests/test_environment_docker_integration.py -v
"""

from __future__ import annotations

import shutil

import pytest

from app.integrations.environment import database_seed
from app.integrations.environment.docker_provider import (
    ConnectionInfo,
    ContainerSpec,
    DockerProvider,
)
from app.integrations.environment.manager import EnvironmentManager
from app.schemas.environment import SyntheticEnvironmentRequest

pytestmark = pytest.mark.docker


def _docker_available() -> bool:
    """Return True only if the daemon actually answers (never assume)."""
    if shutil.which("docker") is None:
        # The CLI may be absent while the SDK can still reach a remote daemon.
        pass
    try:
        from docker.errors import DockerException  # noqa: F401
    except Exception:  # pragma: no cover - SDK not installed
        return False
    return DockerProvider().available()


_DOCKER_READY = _docker_available()

skip_reason = (
    "Docker Engine is not available. Start Docker Desktop/daemon to run the "
    "live environment integration test. Unit tests cover the same lifecycle with "
    "a mocked provider (tests/test_environment_service.py)."
)


@pytest.mark.skipif(not _DOCKER_READY, reason=skip_reason)
def test_provision_seed_and_destroy_real_postgres() -> None:
    """Full happy path against a real PostgreSQL container."""
    provider = DockerProvider()
    manager = EnvironmentManager(
        provider=provider,
        ready_timeout_seconds=60.0,
        poll_interval=1.0,
    )
    request = SyntheticEnvironmentRequest(
        environment_type="postgres",
        label="integration-postgres",
        config={"database": "nexora_it", "image": "postgres:16-alpine"},
    )

    try:
        result = manager.provision(request, environment_id="env-it-live")
        env = result.environment

        # Provisioning must have genuinely succeeded against the real daemon.
        assert result.ok is True, env.metadata.get("error")
        assert env.status == "ready"
        assert env.metadata["lifecycle"] == "ready"
        assert env.metadata["container_id"]

        # The container must actually be running — inspected, not assumed.
        assert provider.is_running(env.metadata["container_id"]) is True

        # Verify the synthetic seed is queryable from inside the container.
        code, out, err = provider.exec_command(
            env.metadata["container_id"],
            [
                "psql",
                "-U",
                "nexora",
                "-d",
                "nexora_it",
                "-tAc",
                f"SELECT count(*) FROM {database_seed.SCHEMA_NAME}.{database_seed.LEADS_TABLE};",
            ],
        )
        assert code == 0, err
        assert out.strip() == str(len(database_seed.SEED_LEADS))

        # Reset must return the environment to its deterministic seed.
        reset = manager.reset(env)
        assert reset.status == "ready"

        # Teardown: cleanup removes only the container we created.
        destroyed = manager.cleanup_environment(reset)
        assert destroyed.metadata["cleanup"] == "removed"
        assert provider.is_running(destroyed.metadata["container_id"]) is False
    finally:
        # Safety net: never leave an owned container behind on failure.
        provider.close()


@pytest.mark.skipif(not _DOCKER_READY, reason=skip_reason)
def test_repeated_cleanup_is_safe_against_real_docker() -> None:
    """Removing an already-removed container must not raise."""
    provider = DockerProvider()
    manager = EnvironmentManager(provider=provider, ready_timeout_seconds=60.0, poll_interval=1.0)
    request = SyntheticEnvironmentRequest(
        environment_type="postgres",
        label="integration-cleanup",
        config={"database": "nexora_it2"},
    )

    try:
        env = manager.provision(request, environment_id="env-it-cleanup").environment
        first = manager.cleanup_environment(env)
        second = manager.cleanup_environment(first)
        assert second.metadata["lifecycle"] == "destroyed"
    finally:
        provider.close()


@pytest.mark.skipif(not _DOCKER_READY, reason=skip_reason)
def test_default_binding_is_loopback_only() -> None:
    """The container's DB port must be bound to loopback, not 0.0.0.0."""
    provider = DockerProvider()
    spec = ContainerSpec(environment_id="env-it-bind", expose_publicly=False)
    ports = DockerProvider._ports(spec)  # static helper, no daemon needed
    host_ip, host_port = ports[f"{spec.internal_port}/tcp"]
    assert host_ip == "127.0.0.1"
    assert host_port is None  # ephemeral


def test_connection_info_dsn_shape() -> None:
    """A pure unit check that also documents the DSN the platform produces."""
    info = ConnectionInfo(
        host="127.0.0.1",
        port=55432,
        database="nexora",
        username="nexora",
        password="p",
        container_id="cid",
        container_name="nexora-env-x",
        image="postgres:16-alpine",
    )
    assert info.dsn() == "postgresql://nexora:p@127.0.0.1:55432/nexora"
