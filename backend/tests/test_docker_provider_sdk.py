"""Docker-SDK-level unit tests for :class:`DockerProvider` (Rajath — WP-B).

These tests replace the **Python Docker SDK client** with a faithful fake and
exercise the *real* provider code (config building, container creation, exec
with/without stdin, readiness polling, stop/remove).  They need no Docker daemon.

Why this file exists (and why it matters):
    The provider-level fake in ``test_environment_service.py`` substitutes the
    whole :class:`DockerProvider`, so it cannot catch bugs in the provider's own
    use of the SDK.  A live run once exposed exactly that: the real
    ``Container.exec_run`` does **not** accept an ``input=`` parameter, so stdin
    seeding silently failed while the provider-level fake "passed".  Here we fake
    the SDK at the same seam the provider actually calls, so the contract is
    enforced without Docker.

The fake mirrors the real SDK shapes we depend on:
- ``client.ping()``
- ``client.containers.run(**kwargs) -> Container`` / ``.get(id)``
- ``client.api.exec_create(...)`` / ``.exec_start(socket=True)`` / ``.exec_inspect(...)``
- ``Container.exec_run(cmd, demux=True) -> ExecResult(exit_code, output)``
- ``Container.reload()``, ``.ports``, ``.status``, ``.stop()``, ``.remove()``
"""

from __future__ import annotations

from typing import Any

import pytest

from app.integrations.environment.docker_provider import (
    DockerProvider,
    DockerUnavailableError,
    OWNER_LABEL,
    OWNER_VALUE,
    ProvisionError,
)
from app.integrations.environment.manager import EnvironmentManager
from app.schemas.environment import SyntheticEnvironmentRequest

# ---------------------------------------------------------------------------
# Faithful fake SDK
# ---------------------------------------------------------------------------


class FakeExecResult:
    """Mirror of ``docker.models.containers.ExecResult`` (a NamedTuple)."""

    def __init__(self, exit_code: int, output: Any) -> None:
        self.exit_code = exit_code
        self.output = output


class FakeSocket:
    """Mimics the POSIX socket wrapper shape (``_sock`` + ``read``)."""

    class _Inner:
        def __init__(self) -> None:
            self.sent = b""
            self._reply = b""
            self._closed = False

        def sendall(self, data: bytes) -> None:
            self.sent += data

        def shutdown(self, how: int) -> None:  # noqa: ARG002
            self._closed = True

        def recv(self, _n: int) -> bytes:
            # Emit the prepared reply once, then EOF.
            out, self._reply = self._reply, b""
            return out

    def __init__(self, reply: bytes = b"") -> None:
        self._sock = FakeSocket._Inner()
        self._sock._reply = reply

    def read(self) -> bytes:
        return self._sock._reply


class FakeContainer:
    def __init__(self, container_id: str, name: str, *, status: str = "running") -> None:
        self.id = container_id
        self.name = name
        self.status = status
        self.ports: dict[str, Any] = {}
        self.removed = False
        self.stopped = False
        self.exec_calls: list[Any] = []
        # Default exec reply: success, no output.
        self.next_exit_code: int = 0
        self.next_output: Any = (b"", b"")
        # For stdin-based execs (ExecApiMixin path).
        self.stdin_received: list[bytes] = []

    def reload(self) -> None:
        pass

    def exec_run(self, cmd: list[str], demux: bool = False, **kwargs: Any) -> FakeExecResult:
        # Enforce the real SDK contract: exec_run must NOT receive an 'input' kwarg.
        if "input" in kwargs:
            raise TypeError("exec_run() got an unexpected keyword argument 'input'")
        if "stdin" in kwargs and kwargs["stdin"]:
            raise TypeError("FakeContainer: stdin exec must go through the api client")
        self.exec_calls.append(("exec_run", cmd, demux))
        return FakeExecResult(self.next_exit_code, self.next_output)

    def stop(self, timeout: int = 10) -> None:  # noqa: ARG002
        self.stopped = True
        self.status = "exited"

    def remove(self, force: bool = True, v: bool = False) -> None:  # noqa: ARG002
        if self.removed:
            raise RuntimeError("container already removed")
        self.removed = True
        self.status = "removed"


class FakeContainers:
    def __init__(self, client: "FakeDockerClient") -> None:
        self._client = client

    def run(self, **kwargs: Any) -> FakeContainer:
        self._client.run_kwargs.append(kwargs)
        if self._client.run_error is not None:
            raise self._client.run_error
        name = kwargs["name"]
        container = FakeContainer(f"cid-{name}", name)
        # Model the ephemeral port binding the daemon would assign.
        for spec_port in (kwargs.get("ports") or {}):
            container.ports[spec_port] = [{"HostIp": "127.0.0.1", "HostPort": "55432"}]
        self._client.created[name] = container
        return container

    def get(self, container_id: str) -> FakeContainer:
        for container in self._client.created.values():
            if container.id == container_id or container.name == container_id:
                if container.removed:
                    raise RuntimeError("No such container")
                return container
        raise RuntimeError("No such container")


class FakeExecApi:
    def __init__(self, client: "FakeDockerClient") -> None:
        self._client = client

    def exec_create(self, container: str, cmd: list[str], stdin: bool = False, **_: Any) -> dict[str, str]:
        self._client.exec_create_calls.append((container, cmd, stdin))
        return {"Id": f"exec-{len(self._client.exec_create_calls)}"}

    def exec_start(self, exec_id: str, socket: bool = False, demux: bool = False) -> Any:
        self._client.exec_start_calls.append((exec_id, socket, demux))
        return FakeSocket(reply=b"")

    def exec_inspect(self, exec_id: str) -> dict[str, Any]:
        return {"ExitCode": self._client.stdin_exit_code}


class FakeDockerClient:
    """A fake ``docker.DockerClient`` covering only the provider's surface."""

    def __init__(self, *, ping_ok: bool = True, stdin_exit_code: int = 0) -> None:
        self._ping_ok = ping_ok
        self.stdin_exit_code = stdin_exit_code
        self.created: dict[str, FakeContainer] = {}
        self.run_kwargs: list[dict[str, Any]] = []
        self.exec_create_calls: list[Any] = []
        self.exec_start_calls: list[Any] = []
        self.run_error: Exception | None = None
        self.closed = False
        self.api = FakeExecApi(self)

    @property
    def containers(self) -> FakeContainers:
        return FakeContainers(self)

    @property
    def networks(self) -> Any:
        return {}

    def ping(self) -> bool:
        return self._ping_ok

    def close(self) -> None:
        self.closed = True


def _provider(**kwargs: Any) -> tuple[DockerProvider, FakeDockerClient]:
    client = FakeDockerClient(**kwargs)
    return DockerProvider(client=client), client


# ---------------------------------------------------------------------------
# Client management / availability
# ---------------------------------------------------------------------------


def test_available_reflects_real_ping() -> None:
    provider, _ = _provider(ping_ok=True)
    assert provider.available() is True

    provider_down, _ = _provider(ping_ok=False)
    assert provider_down.available() is False


def test_lazy_client_import_reports_unavailable_when_sdk_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "docker":
            raise ImportError("no docker")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    provider = DockerProvider()
    # available() must swallow the missing SDK and report unavailable, not raise.
    assert provider.available() is False


# ---------------------------------------------------------------------------
# Container creation: configuration actually reaches the SDK
# ---------------------------------------------------------------------------


def test_create_passes_configuration_to_sdk() -> None:
    provider, client = _provider()
    spec = EnvironmentManager(provider=provider).build_spec(
        "env-x",
        SyntheticEnvironmentRequest(
            environment_type="postgres",
            label="cfg",
            config={
                "database": "mydb",
                "username": "myuser",
                "password": "mypw",
                "image": "postgres:15-alpine",
                "network": "nexora-net",
                "nano_cpus": 250_000_000,
                "mem_limit": 128 * 1024 * 1024,
            },
        ),
    )

    container_id, name = provider.create(spec)

    assert name == "nexora-env-env-x"
    assert container_id == "cid-nexora-env-env-x"
    kwargs = client.run_kwargs[-1]
    assert kwargs["image"] == "postgres:15-alpine"
    assert kwargs["network"] == "nexora-net"
    assert kwargs["nano_cpus"] == 250_000_000
    assert kwargs["mem_limit"] == 128 * 1024 * 1024
    env = kwargs["environment"]
    assert env["POSTGRES_DB"] == "mydb"
    assert env["POSTGRES_USER"] == "myuser"
    assert env["POSTGRES_PASSWORD"] == "mypw"


def test_create_labels_are_ownership_tags() -> None:
    provider, client = _provider()
    spec = EnvironmentManager(provider=provider).build_spec(
        "env-owned", SyntheticEnvironmentRequest(environment_type="postgres", label="x")
    )
    provider.create(spec)
    labels = client.run_kwargs[-1]["labels"]
    assert labels[OWNER_LABEL] == OWNER_VALUE
    assert labels["nexora.environment_id"] == "env-owned"
    assert labels["nexora.engine"] == "postgres"


def test_create_binds_loopback_by_default() -> None:
    provider, client = _provider()
    spec = EnvironmentManager(provider=provider).build_spec(
        "env-lb", SyntheticEnvironmentRequest(environment_type="postgres", label="x")
    )
    provider.create(spec)
    ports = client.run_kwargs[-1]["ports"]
    host_ip, host_port = ports["5432/tcp"]
    assert host_ip == "127.0.0.1"
    assert host_port is None


def test_create_normalizes_sdk_failure() -> None:
    provider, client = _provider()
    client.run_error = RuntimeError("daemon exploded")
    spec = EnvironmentManager(provider=provider).build_spec(
        "env-boom", SyntheticEnvironmentRequest(environment_type="postgres", label="x")
    )
    with pytest.raises(ProvisionError):
        provider.create(spec)


# ---------------------------------------------------------------------------
# exec: the real contract that the live run exposed
# ---------------------------------------------------------------------------


def test_exec_without_stdin_returns_decoded_output() -> None:
    provider, client = _provider()
    spec = EnvironmentManager(provider=provider).build_spec(
        "env-exec", SyntheticEnvironmentRequest(environment_type="postgres", label="x")
    )
    cid, _ = provider.create(spec)
    client.created["nexora-env-env-exec"].next_exit_code = 0
    client.created["nexora-env-env-exec"].next_output = (b"hello", b"")

    code, out, err = provider.exec_command(cid, ["pg_isready"])

    assert (code, out, err) == (0, "hello", "")


def test_exec_with_stdin_uses_low_level_api_not_exec_run() -> None:
    """stdin seeding must NOT call exec_run(input=...) — the real SDK rejects it."""
    provider, client = _provider(stdin_exit_code=0)
    spec = EnvironmentManager(provider=provider).build_spec(
        "env-stdin", SyntheticEnvironmentRequest(environment_type="postgres", label="x")
    )
    cid, _ = provider.create(spec)

    code, _out, _err = provider.exec_command(
        cid, ["psql", "-f", "-"], input_text="SELECT 1;"
    )

    assert code == 0
    # The low-level exec API must have been used.
    assert len(client.exec_create_calls) == 1
    assert client.exec_create_calls[0][2] is True  # stdin=True
    assert client.exec_start_calls[-1][1] is True  # socket=True
    # And the container's exec_run must NOT have been given an input kwarg.
    for call in client.created["nexora-env-env-stdin"].exec_calls:
        assert "input" not in call


def test_exec_with_stdin_propagates_nonzero_exit() -> None:
    provider, client = _provider(stdin_exit_code=3)
    spec = EnvironmentManager(provider=provider).build_spec(
        "env-badseed", SyntheticEnvironmentRequest(environment_type="postgres", label="x")
    )
    cid, _ = provider.create(spec)

    code, _out, _err = provider.exec_command(cid, ["psql", "-f", "-"], input_text="BAD SQL;")

    assert code == 3


# ---------------------------------------------------------------------------
# Inspection / readiness / stop / remove
# ---------------------------------------------------------------------------


def test_is_running_inspects_status() -> None:
    provider, client = _provider()
    spec = EnvironmentManager(provider=provider).build_spec(
        "env-run", SyntheticEnvironmentRequest(environment_type="postgres", label="x")
    )
    cid, _ = provider.create(spec)
    assert provider.is_running(cid) is True
    client.created["nexora-env-env-run"].status = "exited"
    assert provider.is_running(cid) is False


def test_is_running_false_for_unknown_container() -> None:
    provider, _ = _provider()
    assert provider.is_running("cid-does-not-exist") is False


def test_host_port_resolves_ephemeral_binding() -> None:
    provider, _ = _provider()
    spec = EnvironmentManager(provider=provider).build_spec(
        "env-port", SyntheticEnvironmentRequest(environment_type="postgres", label="x")
    )
    cid, _ = provider.create(spec)
    assert provider.host_port(cid, 5432) == 55432


def test_wait_for_ready_returns_true_when_query_succeeds() -> None:
    provider, _ = _provider()
    spec = EnvironmentManager(provider=provider).build_spec(
        "env-ready", SyntheticEnvironmentRequest(environment_type="postgres", label="x")
    )
    cid, _ = provider.create(spec)
    assert provider.wait_for_ready(cid, database="nexora", username="nexora", poll_interval=0.0) is True


def test_wait_for_ready_issues_real_query_not_just_pg_isready() -> None:
    """Readiness must verify a real query, not merely pg_isready.

    ``pg_isready`` can report success while PostgreSQL is still starting up, which
    caused intermittent seeding failures against real Docker.  The provider now
    issues a real ``SELECT 1`` and requires it to succeed.
    """
    provider, client = _provider()
    spec = EnvironmentManager(provider=provider).build_spec(
        "env-ready2", SyntheticEnvironmentRequest(environment_type="postgres", label="x")
    )
    cid, _ = provider.create(spec)
    provider.wait_for_ready(cid, database="nexora", username="nexora", poll_interval=0.0)

    commands = [call[1] for call in client.created["nexora-env-env-ready2"].exec_calls]
    flat = [" ".join(c) for c in commands]
    assert any("SELECT 1" in c for c in flat), f"expected a SELECT 1 probe, got {flat}"
    assert not any(c[:1] == ["pg_isready"] for c in commands), "pg_isready alone is not a readiness proof"


def test_wait_for_ready_returns_false_when_query_fails() -> None:
    provider, client = _provider()
    spec = EnvironmentManager(provider=provider).build_spec(
        "env-noready", SyntheticEnvironmentRequest(environment_type="postgres", label="x")
    )
    cid, _ = provider.create(spec)
    # Make the real query fail (e.g. server still starting up).
    client.created["nexora-env-env-noready"].next_exit_code = 2
    assert provider.wait_for_ready(cid, database="nexora", username="nexora", timeout_seconds=0.0, poll_interval=0.0) is False


def test_wait_for_ready_returns_false_when_not_running() -> None:
    provider, client = _provider()
    spec = EnvironmentManager(provider=provider).build_spec(
        "env-notready", SyntheticEnvironmentRequest(environment_type="postgres", label="x")
    )
    cid, _ = provider.create(spec)
    client.created["nexora-env-env-notready"].status = "exited"
    assert provider.wait_for_ready(cid, database="nexora", username="nexora", poll_interval=0.0) is False


def test_stop_verifies_container_exited() -> None:
    provider, _ = _provider()
    spec = EnvironmentManager(provider=provider).build_spec(
        "env-stop", SyntheticEnvironmentRequest(environment_type="postgres", label="x")
    )
    cid, _ = provider.create(spec)
    assert provider.stop(cid) is True
    assert provider.is_running(cid) is False


def test_remove_is_idempotent_for_unknown_container() -> None:
    provider, _ = _provider()
    assert provider.remove("cid-missing") is False


def test_remove_marks_container_removed() -> None:
    provider, client = _provider()
    spec = EnvironmentManager(provider=provider).build_spec(
        "env-rm", SyntheticEnvironmentRequest(environment_type="postgres", label="x")
    )
    cid, _ = provider.create(spec)
    assert provider.remove(cid) is True
    assert client.created["nexora-env-env-rm"].removed is True
    # Second removal: the container is gone => False, never raises.
    assert provider.remove(cid) is False


# ---------------------------------------------------------------------------
# Mocked tests never claim a real container was created
# ---------------------------------------------------------------------------


def test_mocked_provider_never_asserts_real_containers() -> None:
    """A mocked run must report ids from the fake, never a real daemon id."""
    provider, client = _provider()
    spec = EnvironmentManager(provider=provider).build_spec(
        "env-fake", SyntheticEnvironmentRequest(environment_type="postgres", label="x")
    )
    cid, _ = provider.create(spec)
    assert cid == "cid-nexora-env-env-fake"
    # No real client/daemon was involved; only the injected fake recorded calls.
    assert client.run_kwargs, "the fake client should have recorded the create call"
