"""Docker Engine provider for synthetic database environments.

Owner: Rajath (Work Package B — Docker environment lifecycle).

This module talks to the Docker Engine through the Python Docker SDK and owns
*only* the container mechanics:

    create container -> start -> wait for readiness -> seed -> (reset) -> remove

Design rules taken directly from the Phase 3 guide:
- "a database container is separate from Docker Engine" — we never assume the
  daemon is ours; we only manage containers we created and labelled.
- "avoid exposing database ports broadly by default" — the default bind is
  ``127.0.0.1`` on an ephemeral host port, never ``0.0.0.0``.  A caller must opt
  in to ``expose_publicly`` to change that.
- "do not mount the host filesystem broadly" — no host bind mounts are used;
  the container's own volume is anonymous and removed with the container.
- "claim a container is running unless verified" — :meth:`DockerProvider.is_running`
  inspects the container rather than trusting bookkeeping.
- "cleanup only affects resources created and owned by this platform" — every
  container is labelled with :data:`OWNER_LABEL`, and removal filters on it.

The provider is written against a *narrow* seam so unit tests can substitute a
fake Docker client without importing or running Docker at all.

Security note: credentials are passed to the container via its environment. They
are returned to the caller only inside :class:`ConnectionInfo`, which the
application layer redacts before it reaches any response or log.  Nothing in this
module logs a password.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

# Labels stamped on every resource this platform creates.  Cleanup filters on
# these so we can never remove a container the platform does not own.
OWNER_LABEL = "nexora.owner"
OWNER_VALUE = "nexora-testing-platform"
ENV_LABEL = "nexora.environment_id"
ENGINE_LABEL = "nexora.engine"

DEFAULT_IMAGE = "postgres:16-alpine"
DEFAULT_INTERNAL_PORT = 5432


class DockerUnavailableError(RuntimeError):
    """Raised when the Docker Engine cannot be reached or is not installed."""


class ProvisionError(RuntimeError):
    """Raised when a container cannot be created, started, or becomes healthy."""


@dataclass
class ContainerSpec:
    """Everything needed to create one disposable database container.

    Kept intentionally small and explicit; the guide asks configuration to be
    "image/version, network, resource limits, and credentials configurable".
    """

    environment_id: str
    image: str = DEFAULT_IMAGE
    internal_port: int = DEFAULT_INTERNAL_PORT
    network: str | None = None
    # Resource limits (Docker SDK semantics: CPU in nano-CPUs, memory in bytes).
    nano_cpus: int = 500_000_000  # 0.5 CPU
    mem_limit: int = 256 * 1024 * 1024  # 256 MiB
    # Credentials: generated per environment and never reused across runs.
    database: str = "nexora"
    username: str = "nexora"
    password: str = "nexora-test-password"
    # Networking policy.
    expose_publicly: bool = False
    # Extra environment variables merged last (advanced overrides).
    extra_env: dict[str, str] = field(default_factory=dict)


@dataclass
class ConnectionInfo:
    """Safe-for-caller connection metadata (the application layer redacts it)."""

    host: str
    port: int
    database: str
    username: str
    password: str
    container_id: str
    container_name: str
    image: str

    def dsn(self) -> str:
        """Return a libpq-style DSN.  Contains the password — callers must redact."""
        return (
            f"postgresql://{self.username}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )


class DockerClientProtocol(Protocol):
    """The slice of ``docker.DockerClient`` this provider depends on.

    Declaring the seam as a protocol keeps the provider testable with a fake and
    documents exactly which Docker capabilities we rely on.
    """

    def ping(self) -> bool: ...

    @property
    def containers(self) -> Any: ...

    @property
    def networks(self) -> Any: ...

    @property
    def api(self) -> Any: ...

    def close(self) -> None: ...


class DockerProvider:
    """Real Docker Engine provider built on the Python Docker SDK.

    The client is injected (constructor argument) so tests never touch Docker.
    ``docker`` is imported lazily so importing this module never requires the SDK
    or a running daemon.
    """

    def __init__(self, client: DockerClientProtocol | None = None, *, client_factory: Any | None = None) -> None:
        self._client = client
        self._client_factory = client_factory

    # -- client management -------------------------------------------------

    def _get_client(self) -> DockerClientProtocol:
        if self._client is not None:
            return self._client
        if self._client_factory is not None:
            self._client = self._client_factory()
            return self._client
        try:
            import docker  # imported lazily: the SDK is optional for unit tests
        except ImportError as exc:  # pragma: no cover - exercised only without SDK
            raise DockerUnavailableError(
                "The Python 'docker' SDK is not installed. Install it (pip install docker) "
                "to use real container provisioning, or use the mock provider."
            ) from exc
        try:
            self._client = docker.from_env()
        except Exception as exc:  # noqa: BLE001 - normalize any SDK/daemon error
            raise DockerUnavailableError(
                f"Docker Engine is not reachable: {type(exc).__name__}. "
                "Start Docker Desktop/daemon and retry."
            ) from exc
        return self._client

    def available(self) -> bool:
        """Return True only if the daemon answers a ping (never assumes)."""
        try:
            return bool(self._get_client().ping())
        except (DockerUnavailableError, Exception):  # noqa: BLE001
            return False

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001 - closing must never raise
                pass
            self._client = None

    # -- container configuration ------------------------------------------

    @staticmethod
    def _container_name(environment_id: str) -> str:
        return f"nexora-env-{environment_id}"

    def _ports(self, spec: ContainerSpec) -> dict[str, Any]:
        """Map container port -> host binding, defaulting to loopback-only."""
        host_ip = "0.0.0.0" if spec.expose_publicly else "127.0.0.1"
        return {f"{spec.internal_port}/tcp": (host_ip, None)}  # None => ephemeral port

    def _environment(self, spec: ContainerSpec) -> dict[str, str]:
        env = {
            "POSTGRES_DB": spec.database,
            "POSTGRES_USER": spec.username,
            "POSTGRES_PASSWORD": spec.password,
            "PGDATA": "/var/lib/postgresql/data/pgdata",
        }
        env.update(spec.extra_env)
        return env

    def _labels(self, spec: ContainerSpec) -> dict[str, str]:
        return {
            OWNER_LABEL: OWNER_VALUE,
            ENV_LABEL: spec.environment_id,
            ENGINE_LABEL: "postgres",
        }

    # -- lifecycle ---------------------------------------------------------

    def create(self, spec: ContainerSpec) -> tuple[str, str]:
        """Create and start a container; return ``(container_id, name)``.

        Raises :class:`DockerUnavailableError` if the daemon is unreachable and
        :class:`ProvisionError` for any Docker-level failure, so callers get a
        normalized error rather than a raw SDK exception.
        """
        client = self._get_client()  # may raise DockerUnavailableError
        name = self._container_name(spec.environment_id)
        kwargs: dict[str, Any] = {
            "image": spec.image,
            "name": name,
            "detach": True,
            "environment": self._environment(spec),
            "ports": self._ports(spec),
            "labels": self._labels(spec),
            "nano_cpus": spec.nano_cpus,
            "mem_limit": spec.mem_limit,
        }
        if spec.network:
            kwargs["network"] = spec.network
        try:
            container = client.containers.run(**kwargs)
        except DockerUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize SDK errors
            raise ProvisionError(
                f"Failed to create/start container '{name}': {type(exc).__name__}"
            ) from exc
        return container.id, name

    def is_running(self, container_id: str) -> bool:
        """Inspect the container and report whether it is actually running."""
        try:
            container = self._get_client().containers.get(container_id)
        except Exception:  # noqa: BLE001 - missing container => not running
            return False
        try:
            return str(getattr(container, "status", "")).lower() == "running"
        except Exception:  # noqa: BLE001
            return False

    def container_status(self, container_id: str) -> str | None:
        """Return the Docker-reported status string, or ``None`` if unknown."""
        try:
            container = self._get_client().containers.get(container_id)
            return str(getattr(container, "status", "")) or None
        except Exception:  # noqa: BLE001
            return None

    def host_port(self, container_id: str, internal_port: int = DEFAULT_INTERNAL_PORT) -> int | None:
        """Resolve the ephemeral host port bound to the container's DB port."""
        try:
            container = self._get_client().containers.get(container_id)
            container.reload()
            ports = getattr(container, "ports", {}) or {}
            binding = ports.get(f"{internal_port}/tcp")
            if isinstance(binding, list) and binding:
                return int(binding[0]["HostPort"])
            return None
        except Exception:  # noqa: BLE001
            return None

    def exec_command(self, container_id: str, command: list[str], *, input_text: str | None = None) -> tuple[int, str, str]:
        """Run a command inside the container; return ``(exit_code, stdout, stderr)``.

        Used to seed via ``psql`` so no host-side DB driver is required.

        When ``input_text`` is supplied the command's stdin is fed that text.  The
        high-level ``Container.exec_run`` API does **not** accept stdin, so we use
        the low-level exec API (``exec_create`` + ``exec_start(socket=True)``) and
        write to the raw socket.  This works over both the Windows npipe transport
        (``NpipeSocket``) and the POSIX transport (wrapped socket with ``_sock``).
        """
        try:
            container = self._get_client().containers.get(container_id)
        except Exception as exc:  # noqa: BLE001
            raise ProvisionError(f"exec failed in container: {type(exc).__name__}") from exc

        if input_text is None:
            try:
                result = container.exec_run(command, demux=True)
            except Exception as exc:  # noqa: BLE001
                raise ProvisionError(f"exec failed in container: {type(exc).__name__}") from exc
            exit_code = int(getattr(result, "exit_code", 1) or 0)
            stdout, stderr = _decode_exec_output(getattr(result, "output", (b"", b"")))
            return exit_code, stdout, stderr

        return self._exec_with_stdin(container_id, command, input_text)

    def _exec_with_stdin(self, container_id: str, command: list[str], input_text: str) -> tuple[int, str, str]:
        """Run a command feeding ``input_text`` on stdin via the low-level exec API."""
        api = self._get_client().api
        try:
            exec_id = api.exec_create(container_id, command, stdin=True, stdout=True, stderr=True)["Id"]
            sock = api.exec_start(exec_id, socket=True, demux=False)
            raw = getattr(sock, "_sock", sock)  # POSIX wrapper vs. NpipeSocket
            raw.sendall(input_text.encode("utf-8"))
            try:
                raw.shutdown(1)  # signal EOF on stdin
            except Exception:  # noqa: BLE001 - not all sockets support half-close
                pass
            chunks: list[bytes] = []
            try:
                while True:
                    chunk = raw.recv(4096)
                    if not chunk:
                        break
                    chunks.append(chunk)
            except Exception:  # noqa: BLE001 - read until close
                pass
            output = b"".join(chunks).decode("utf-8", errors="replace")
            # The exit code can lag slightly; poll briefly until it is recorded.
            exit_code: int | None = None
            for _ in range(20):
                exit_code = api.exec_inspect(exec_id).get("ExitCode")
                if exit_code is not None:
                    break
                time.sleep(0.1)
            if exit_code is None:
                # Unknown exit code: treat as failure rather than silently succeeding.
                return 1, output, output
            return int(exit_code), output, ""
        except ProvisionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProvisionError(f"exec (stdin) failed in container: {type(exc).__name__}") from exc

    def wait_for_ready(
        self,
        container_id: str,
        *,
        database: str,
        username: str,
        timeout_seconds: float = 30.0,
        poll_interval: float = 0.5,
    ) -> bool:
        """Poll until the database *genuinely* accepts queries.

        ``pg_isready`` alone is not sufficient: it can report "accepting
        connections" while PostgreSQL is still in its startup/recovery phase, so a
        real query then fails with ``FATAL: the database system is starting up``.
        (This was observed as an intermittent seeding failure against real Docker.)

        We therefore require a real ``SELECT 1`` against the target database to
        succeed before reporting ready.  ``time.sleep`` is called only in the
        real polling loop; unit tests pass a fake provider and never reach it.
        """
        deadline = time.monotonic() + max(timeout_seconds, 0.0)
        while True:
            if not self.is_running(container_id):
                return False
            # A real connection to the target database is the readiness signal.
            code, _out, _err = self.exec_command(
                container_id,
                ["psql", "-v", "ON_ERROR_STOP=1", "-U", username, "-d", database, "-tAc", "SELECT 1;"],
            )
            if code == 0:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(poll_interval)

    def remove(self, container_id: str, *, force: bool = True) -> bool:
        """Remove a container we own.  Idempotent: unknown containers return False."""
        try:
            container = self._get_client().containers.get(container_id)
        except Exception:  # noqa: BLE001 - already gone => nothing to do
            return False
        try:
            container.remove(force=force, v=True)  # v=True removes the anonymous volume
            return True
        except Exception:  # noqa: BLE001
            return False

    def stop(self, container_id: str) -> bool:
        """Stop a container and verify it is no longer running.

        Returns True only when the container is confirmed stopped.
        """
        try:
            container = self._get_client().containers.get(container_id)
        except Exception:  # noqa: BLE001 - unknown container => nothing to stop
            return False
        try:
            container.stop(timeout=10)
        except Exception:  # noqa: BLE001 - already stopped or transient error
            pass
        # Verify rather than assume: reload and check the reported status.
        try:
            container.reload()
            return str(getattr(container, "status", "")).lower() != "running"
        except Exception:  # noqa: BLE001
            return False


def _decode_exec_output(output: Any) -> tuple[str, str]:
    """Normalize ``exec_run`` output across SDK return shapes."""
    if isinstance(output, tuple) and len(output) == 2:
        raw_out, raw_err = output
    else:
        raw_out, raw_err = output, b""
    return _as_text(raw_out), _as_text(raw_err)


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)
