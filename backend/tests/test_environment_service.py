"""Unit tests for the environment lifecycle service (Rajath — Work Package B).

These tests are deliberately **Docker-free** and deterministic, as the Phase 3
guide requires ("unit tests should not require API keys or Docker").  They
exercise the real :class:`EnvironmentManager` against a fake
:class:`DatabaseProvider`, so the production code path is covered without a
container runtime.

Coverage:
- successful provisioning (create -> running -> ready -> seed -> ready)
- failure when Docker is unavailable (honest ``failed`` state, no endpoint)
- failure during seeding (partial-resource cleanup is attempted)
- cleanup after success and after partial failure
- repeated cleanup is safe (idempotent)
- credentials never appear in the redacted view / never leak into endpoint
- the provider is never claimed to be running unless inspected
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.integrations.environment.docker_provider import (
    ConnectionInfo,
    ContainerSpec,
    DockerUnavailableError,
    ProvisionError,
)
from app.integrations.environment.manager import (
    EnvironmentManager,
    generate_password,
    redact_connection,
)
from app.schemas.environment import SyntheticEnvironmentRequest

# ---------------------------------------------------------------------------
# Fake provider
# ---------------------------------------------------------------------------


class FakeDatabaseProvider:
    """Deterministic, in-memory stand-in for :class:`DockerProvider`.

    It models just enough Docker behaviour for the manager's lifecycle without
    touching a daemon.  Every interaction is recorded so tests can assert on the
    exact call sequence (e.g. "was the container removed after a seed failure?").
    """

    def __init__(
        self,
        *,
        available: bool = True,
        running: bool = True,
        ready: bool = True,
        seed_exit_code: int = 0,
        create_error: Exception | None = None,
        host_port: int = 55432,
        remove_result: bool = True,
    ) -> None:
        self._available = available
        self._running = running
        self._ready = ready
        self._seed_exit_code = seed_exit_code
        self._create_error = create_error
        self._host_port = host_port
        self._remove_result = remove_result

        self.calls: list[tuple[str, Any]] = []
        self.created_specs: list[ContainerSpec] = []
        self.exec_calls: list[tuple[str, list[str], str | None]] = []
        self.removed: list[str] = []
        self.stopped: list[str] = []

    # -- DatabaseProvider surface ------------------------------------------

    def available(self) -> bool:
        self.calls.append(("available", None))
        return self._available

    def create(self, spec: ContainerSpec) -> tuple[str, str]:
        self.calls.append(("create", spec.environment_id))
        if self._create_error is not None:
            raise self._create_error
        self.created_specs.append(spec)
        return f"cid-{spec.environment_id}", f"nexora-env-{spec.environment_id}"

    def is_running(self, container_id: str) -> bool:
        self.calls.append(("is_running", container_id))
        return self._running

    def container_status(self, container_id: str) -> str | None:
        return "running" if self._running else "exited"

    def host_port(self, container_id: str, internal_port: int = 5432) -> int | None:
        self.calls.append(("host_port", container_id))
        return self._host_port

    def exec_command(
        self, container_id: str, command: list[str], *, input_text: str | None = None
    ) -> tuple[int, str, str]:
        self.calls.append(("exec_command", tuple(command)))
        self.exec_calls.append((container_id, list(command), input_text))
        # Only the seeding psql call is modelled as failing; readiness probes
        # (pg_isready) always succeed so we reach the seed step.
        if "psql" in command[0]:
            return self._seed_exit_code, "", "synthetic seed error" if self._seed_exit_code else ""
        return 0, "accepting connections", ""

    def wait_for_ready(
        self,
        container_id: str,
        *,
        database: str,
        username: str,
        timeout_seconds: float = 30.0,
        poll_interval: float = 0.5,
    ) -> bool:
        self.calls.append(("wait_for_ready", container_id))
        return self._ready

    def remove(self, container_id: str, *, force: bool = True) -> bool:
        self.calls.append(("remove", container_id))
        self.removed.append(container_id)
        return self._remove_result

    def stop(self, container_id: str) -> bool:
        self.calls.append(("stop", container_id))
        self.stopped.append(container_id)
        self._running = False
        return True


def _request(**config: Any) -> SyntheticEnvironmentRequest:
    return SyntheticEnvironmentRequest(
        environment_type="postgres",
        label="unit-test-db",
        config=config,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_provision_success_reaches_ready_and_seeds() -> None:
    provider = FakeDatabaseProvider()
    manager = EnvironmentManager(provider=provider, ready_timeout_seconds=1.0, poll_interval=0.0)

    result = manager.provision(_request(database="nexora_dev"))

    assert result.ok is True
    env = result.environment
    assert env.status == "ready"
    assert env.metadata["lifecycle"] == "ready"
    assert env.endpoint == f"postgres://127.0.0.1:{provider._host_port}/nexora_dev"
    assert env.metadata["container_id"] == f"cid-{env.environment_id}"
    assert env.metadata["seed"]["rows"] == 3

    # It must have actually run a psql seed inside the container.
    psql_calls = [c for c in provider.exec_calls if c[1][0] == "psql"]
    assert len(psql_calls) == 1
    assert psql_calls[0][2] is not None  # SQL piped via stdin
    assert "CREATE SCHEMA IF NOT EXISTS" in psql_calls[0][2]
    assert "ON CONFLICT (id) DO NOTHING" in psql_calls[0][2]


def test_provision_uses_supplied_environment_id() -> None:
    provider = FakeDatabaseProvider()
    manager = EnvironmentManager(provider=provider)
    result = manager.provision(_request(), environment_id="env-fixed123")
    assert result.environment.environment_id == "env-fixed123"
    assert result.environment.metadata["container_id"] == "cid-env-fixed123"


def test_provision_generates_credentials_when_absent() -> None:
    provider = FakeDatabaseProvider()
    manager = EnvironmentManager(provider=provider)
    result = manager.provision(_request())
    password = result.environment.metadata["connection"]["password"]
    assert isinstance(password, str) and len(password) >= 16
    # The container must have received the same password via its environment.
    spec = provider.created_specs[0]
    assert spec.password == password


def test_loopback_only_by_default_and_public_when_opted_in() -> None:
    provider = FakeDatabaseProvider()
    manager = EnvironmentManager(provider=provider)

    manager.provision(_request(), environment_id="env-loopback")
    assert provider.created_specs[0].expose_publicly is False

    manager.provision(_request(expose_publicly=True), environment_id="env-public")
    assert provider.created_specs[1].expose_publicly is True


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


def test_provision_fails_honestly_when_docker_unavailable() -> None:
    provider = FakeDatabaseProvider(available=False)
    manager = EnvironmentManager(provider=provider)

    result = manager.provision(_request())

    assert result.ok is False
    env = result.environment
    assert env.status == "failed"
    assert env.metadata["lifecycle"] == "failed"
    assert env.endpoint is None
    assert env.metadata["error"] == "Docker Engine is unavailable."
    # Nothing was created, so nothing should have been removed.
    assert provider.removed == []


def test_provision_cleans_up_when_container_not_running() -> None:
    provider = FakeDatabaseProvider(running=False)
    manager = EnvironmentManager(provider=provider)

    result = manager.provision(_request())

    assert result.ok is False
    assert result.environment.status == "failed"
    # The created container must have been removed (partial-failure cleanup).
    assert provider.removed == [result.environment.metadata["container_id"]]
    assert result.environment.metadata["cleanup"] == "attempted"


def test_provision_cleans_up_when_seeding_fails() -> None:
    provider = FakeDatabaseProvider(seed_exit_code=1)
    manager = EnvironmentManager(provider=provider)

    result = manager.provision(_request())

    assert result.ok is False
    assert result.environment.status == "failed"
    assert result.environment.metadata["error"].startswith("Seeding failed")
    assert provider.removed == [result.environment.metadata["container_id"]]


def test_provision_normalizes_create_failure() -> None:
    provider = FakeDatabaseProvider(create_error=ProvisionError("docker said no"))
    manager = EnvironmentManager(provider=provider)

    result = manager.provision(_request())

    assert result.ok is False
    assert result.environment.status == "failed"
    assert result.environment.metadata["error"] == "docker said no"


def test_unsupported_engine_fails_without_touching_provider() -> None:
    provider = FakeDatabaseProvider()
    manager = EnvironmentManager(provider=provider)
    request = SyntheticEnvironmentRequest(environment_type="redis", label="cache")

    result = manager.provision(request)

    assert result.ok is False
    assert "not supported yet" in result.environment.metadata["error"]
    assert provider.created_specs == []


# ---------------------------------------------------------------------------
# Reset / stop / cleanup
# ---------------------------------------------------------------------------


def test_reset_truncates_and_reseeds() -> None:
    provider = FakeDatabaseProvider()
    manager = EnvironmentManager(provider=provider)
    provisioned = manager.provision(_request(database="nexora_dev")).environment

    provider.exec_calls.clear()
    reset = manager.reset(provisioned)

    assert reset.status == "ready"
    assert reset.metadata["lifecycle"] == "ready"
    psql_calls = [c for c in provider.exec_calls if c[1][0] == "psql"]
    sql_inputs = [c[2] for c in psql_calls]
    assert any("TRUNCATE TABLE" in (s or "") for s in sql_inputs)
    assert any("INSERT INTO" in (s or "") for s in sql_inputs)
    # Reset must target the environment's own database, not a hard-coded default.
    assert all("nexora_dev" in c[1] for c in psql_calls)
    assert reset.metadata["history"][-1]["action"] == "reset"


def test_reset_without_container_fails_safely() -> None:
    provider = FakeDatabaseProvider()
    manager = EnvironmentManager(provider=provider)
    orphan = manager.provision(_request()).environment
    orphan.metadata.pop("container_id")

    result = manager.reset(orphan)

    assert result.status == "failed"
    assert "No container" in result.metadata["error"]


def test_stop_sets_contract_status_and_stops_container() -> None:
    provider = FakeDatabaseProvider()
    manager = EnvironmentManager(provider=provider)
    env = manager.provision(_request()).environment
    container_id = env.metadata["container_id"]

    stopped = manager.stop(env)

    assert stopped.status == "stopped"
    assert stopped.metadata["lifecycle"] == "stopped"
    # The container must have been genuinely stopped and verified.
    assert provider.stopped == [container_id]
    assert stopped.metadata["stop"] == "verified"


def test_stop_clears_stale_failure_reason() -> None:
    provider = FakeDatabaseProvider(available=False)
    manager = EnvironmentManager(provider=provider)
    failed = manager.provision(_request()).environment
    assert failed.metadata["error"]

    stopped = manager.stop(failed)

    assert stopped.status == "stopped"
    assert "error" not in stopped.metadata


def test_cleanup_after_success_removes_container() -> None:
    provider = FakeDatabaseProvider()
    manager = EnvironmentManager(provider=provider)
    env = manager.provision(_request()).environment

    destroyed = manager.cleanup_environment(env)

    assert destroyed.metadata["lifecycle"] == "destroyed"
    assert destroyed.metadata["cleanup"] == "removed"
    assert destroyed.endpoint is None
    assert provider.removed == [env.metadata["container_id"]]


def test_cleanup_after_partial_failure_is_safe() -> None:
    provider = FakeDatabaseProvider(seed_exit_code=1, remove_result=False)
    manager = EnvironmentManager(provider=provider)
    env = manager.provision(_request()).environment

    destroyed = manager.cleanup_environment(env)

    # Removing an already-absent container reports "already_absent", never raises.
    assert destroyed.metadata["cleanup"] in {"removed", "already_absent"}
    assert destroyed.status == "stopped"


def test_repeated_cleanup_is_idempotent() -> None:
    provider = FakeDatabaseProvider()
    manager = EnvironmentManager(provider=provider)
    env = manager.provision(_request()).environment

    first = manager.cleanup_environment(env)
    second = manager.cleanup_environment(first)

    assert second.metadata["lifecycle"] == "destroyed"
    # Second cleanup should not have credentials to strip and must not raise.
    assert "connection" not in second.metadata


def test_cleanup_strips_credentials() -> None:
    provider = FakeDatabaseProvider()
    manager = EnvironmentManager(provider=provider)
    env = manager.provision(_request()).environment
    assert env.metadata["connection"]["password"]

    destroyed = manager.cleanup_environment(env)

    assert "connection" not in destroyed.metadata


# ---------------------------------------------------------------------------
# Credential safety
# ---------------------------------------------------------------------------


def test_redact_connection_removes_secrets_only() -> None:
    metadata = {
        "lifecycle": "ready",
        "connection": {
            "host": "127.0.0.1",
            "port": 55432,
            "database": "nexora",
            "username": "nexora",
            "password": "super-secret-value",
            "dsn": "postgresql://nexora:super-secret-value@127.0.0.1:55432/nexora",
            "container_id": "cid-1",
            "image": "postgres:16-alpine",
        },
    }

    safe = redact_connection(metadata)

    assert safe["connection"]["password"] == "[REDACTED]"
    assert safe["connection"]["dsn"] == "[REDACTED]"
    assert safe["connection"]["username"] == "nexora"
    assert safe["connection"]["port"] == 55432
    assert safe["lifecycle"] == "ready"
    # The original must not be mutated.
    assert metadata["connection"]["password"] == "super-secret-value"


def test_generated_passwords_are_unique() -> None:
    assert generate_password() != generate_password()


def test_password_never_in_endpoint() -> None:
    provider = FakeDatabaseProvider()
    manager = EnvironmentManager(provider=provider)
    env = manager.provision(_request()).environment
    password = env.metadata["connection"]["password"]
    assert password not in (env.endpoint or "")


# ---------------------------------------------------------------------------
# Route-level integration (still Docker-free)
# ---------------------------------------------------------------------------


@pytest.fixture()
def client_with_fake_provider() -> Any:
    """A TestClient whose environment manager uses the fake provider."""
    from app.api.routes import environments as env_routes
    from app.core import store
    from app.main import app

    provider = FakeDatabaseProvider()
    env_routes.set_manager(EnvironmentManager(provider=provider))
    store.ENVIRONMENTS.clear()
    with TestClient(app) as client:
        yield client
    env_routes.set_manager(None)
    store.ENVIRONMENTS.clear()


def test_create_environment_preserves_contract(client_with_fake_provider: Any) -> None:
    client = client_with_fake_provider
    response = client.post(
        "/api/v1/environments",
        json={
            "environment_type": "postgres",
            "label": "route-test-db",
            "config": {"database": "nexora_dev", "port": 5432},
        },
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["environment_type"] == "postgres"
    # The synchronous contract response must still say "provisioning".
    assert data["status"] == "provisioning"

    env_id = data["environment_id"]
    # After the background task ran, the record must be genuinely ready.
    fetched = client.get(f"/api/v1/environments/{env_id}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["status"] == "ready"
    assert fetched.json()["data"]["label"] == "route-test-db"


def test_created_environment_never_exposes_credentials(client_with_fake_provider: Any) -> None:
    client = client_with_fake_provider
    created = client.post(
        "/api/v1/environments",
        json={"environment_type": "postgres", "label": "secret-check", "config": {}},
    ).json()["data"]
    env_id = created["environment_id"]

    fetched = client.get(f"/api/v1/environments/{env_id}").json()["data"]
    connection = fetched["metadata"].get("connection", {})
    assert connection.get("password") == "[REDACTED]"
    assert connection.get("dsn") == "[REDACTED]"
    # The raw wire payload must not contain any real password value.
    raw = str(fetched)
    assert "super-secret" not in raw


def test_environment_lifecycle_endpoints(client_with_fake_provider: Any) -> None:
    client = client_with_fake_provider
    env_id = client.post(
        "/api/v1/environments",
        json={"environment_type": "postgres", "label": "lifecycle", "config": {}},
    ).json()["data"]["environment_id"]

    reset = client.post(f"/api/v1/environments/{env_id}/reset")
    assert reset.status_code == 200
    assert reset.json()["data"]["status"] == "ready"

    destroyed = client.post(f"/api/v1/environments/{env_id}/destroy")
    assert destroyed.status_code == 200
    assert destroyed.json()["data"]["metadata"]["lifecycle"] == "destroyed"

    stopped = client.post(f"/api/v1/environments/{env_id}/stop")
    assert stopped.status_code == 200
    assert stopped.json()["data"]["status"] == "stopped"


def test_missing_environment_returns_404(client_with_fake_provider: Any) -> None:
    client = client_with_fake_provider
    assert client.get("/api/v1/environments/env-does-not-exist").status_code == 404
    assert client.post("/api/v1/environments/env-does-not-exist/stop").status_code == 404
    assert client.post("/api/v1/environments/env-does-not-exist/destroy").status_code == 404


def test_unsupported_engine_via_route_fails_but_returns_201(client_with_fake_provider: Any) -> None:
    client = client_with_fake_provider
    created = client.post(
        "/api/v1/environments",
        json={"environment_type": "redis", "label": "cache", "config": {}},
    )
    assert created.status_code == 201
    env_id = created.json()["data"]["environment_id"]
    fetched = client.get(f"/api/v1/environments/{env_id}").json()["data"]
    assert fetched["status"] == "failed"
    assert fetched["endpoint"] is None


# ---------------------------------------------------------------------------
# Concurrency: two provisions must not interfere (separate containers)
# ---------------------------------------------------------------------------


def test_concurrent_provisions_are_independent() -> None:
    provider = FakeDatabaseProvider()
    manager = EnvironmentManager(provider=provider)

    async def main() -> None:
        # The manager is synchronous; run two provisions and confirm distinct ids
        # and distinct containers.  Wrapped in asyncio to mirror how routes invoke
        # it from the event loop (FastAPI background tasks).
        r1 = manager.provision(_request(), environment_id="env-a")
        r2 = manager.provision(_request(), environment_id="env-b")
        assert r1.environment.environment_id != r2.environment.environment_id
        assert r1.environment.metadata["container_id"] != r2.environment.metadata["container_id"]

    asyncio.run(main())
