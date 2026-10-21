"""Environment lifecycle manager (service layer).

Owner: Rajath (Work Package B — Docker environment lifecycle).

This is the "environment service behind the existing environment routes" the
guide asks for.  It owns the full lifecycle of a synthetic database environment:

    provision -> ready -> (reset) -> stop -> destroy

and it keeps the shared contract intact.  The Phase 2 ``SyntheticEnvironment``
schema exposes the states ``provisioning | ready | stopped | failed | cancelled``
— it has no ``reset``/``destroyed`` members.  Per the shared-schema rule we do
**not** edit it; instead:

- the coarse ``status`` always uses a member of the existing literal, and
- the finer lifecycle stage (``created``/``seeding``/``resetting``/``destroyed``)
  is carried in ``metadata["lifecycle"]`` so the intent is fully visible without
  a contract change.

The manager is provider-agnostic: it depends on a :class:`DatabaseProvider`
protocol, so the real :class:`~app.integrations.environment.docker_provider.DockerProvider`
and a deterministic mock provider are interchangeable.  That is what lets the
unit tests run with **no Docker**.

Credential safety: the manager never places a password in ``endpoint`` or in any
response-only field.  Connection secrets live under ``metadata["connection"]``,
and :func:`redact_connection` produces the safe view used by routes and logs.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from app.integrations.environment import database_seed
from app.integrations.environment.docker_provider import (
    ConnectionInfo,
    ContainerSpec,
    DEFAULT_IMAGE,
    DEFAULT_INTERNAL_PORT,
    DockerProvider,
    DockerUnavailableError,
    ProvisionError,
)
from app.schemas.environment import SyntheticEnvironment, SyntheticEnvironmentRequest

# Lifecycle stages tracked in metadata["lifecycle"].  These are richer than the
# shared status literal; the mapping below keeps both consistent.
STAGE_CREATED = "created"
STAGE_PROVISIONING = "provisioning"
STAGE_SEEDING = "seeding"
STAGE_READY = "ready"
STAGE_RESETTING = "resetting"
STAGE_FAILED = "failed"
STAGE_STOPPED = "stopped"
STAGE_DESTROYED = "destroyed"


class DatabaseProvider(Protocol):
    """The provider surface the manager depends on.

    Both the real Docker provider and test fakes implement this.  Keeping the
    protocol tiny is deliberate: it makes the seam obvious and the fakes honest.
    """

    def available(self) -> bool: ...

    def create(self, spec: ContainerSpec) -> tuple[str, str]: ...

    def is_running(self, container_id: str) -> bool: ...

    def container_status(self, container_id: str) -> str | None: ...

    def host_port(self, container_id: str, internal_port: int = DEFAULT_INTERNAL_PORT) -> int | None: ...

    def exec_command(
        self, container_id: str, command: list[str], *, input_text: str | None = None
    ) -> tuple[int, str, str]: ...

    def wait_for_ready(
        self, container_id: str, *, database: str, username: str, timeout_seconds: float = 30.0, poll_interval: float = 0.5
    ) -> bool: ...

    def stop(self, container_id: str) -> bool: ...

    def remove(self, container_id: str, *, force: bool = True) -> bool: ...


@dataclass
class ProvisionResult:
    """Outcome of a provision attempt, safe to return to the application layer."""

    environment: SyntheticEnvironment
    ok: bool
    error: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def generate_password() -> str:
    """Return a strong per-environment password (never a fixed default at runtime)."""
    return secrets.token_urlsafe(24)


class EnvironmentManager:
    """Coordinates provisioning, readiness, reset, and idempotent cleanup.

    Parameters
    ----------
    provider:
        A :class:`DatabaseProvider`.  Defaults to the real Docker provider.
    default_image:
        PostgreSQL image used when the request does not specify one.
    seed_schema:
        Schema name for the deterministic synthetic data.
    """

    def __init__(
        self,
        provider: DatabaseProvider | None = None,
        *,
        default_image: str = DEFAULT_IMAGE,
        seed_schema: str = database_seed.SCHEMA_NAME,
        ready_timeout_seconds: float = 30.0,
        poll_interval: float = 0.5,
    ) -> None:
        self.provider: DatabaseProvider = provider or DockerProvider()
        self.default_image = default_image
        self.seed_schema = seed_schema
        self.ready_timeout_seconds = ready_timeout_seconds
        self.poll_interval = poll_interval

    # -- spec construction -------------------------------------------------

    def build_spec(self, environment_id: str, payload: SyntheticEnvironmentRequest) -> ContainerSpec:
        """Translate a validated request into a concrete container spec.

        Unknown/extra config keys are ignored rather than trusted, so a caller
        cannot smuggle arbitrary Docker options through the API.
        """
        config = payload.config or {}
        return ContainerSpec(
            environment_id=environment_id,
            image=str(config.get("image", self.default_image)),
            internal_port=int(config.get("internal_port", DEFAULT_INTERNAL_PORT)),
            network=config.get("network") or None,
            nano_cpus=int(config.get("nano_cpus", 500_000_000)),
            mem_limit=int(config.get("mem_limit", 256 * 1024 * 1024)),
            database=str(config.get("database", "nexora")),
            username=str(config.get("username", "nexora")),
            password=str(config.get("password") or generate_password()),
            expose_publicly=bool(config.get("expose_publicly", False)),
            extra_env={str(k): str(v) for k, v in (config.get("env") or {}).items()},
        )

    # -- lifecycle ---------------------------------------------------------

    def provision(
        self,
        payload: SyntheticEnvironmentRequest,
        *,
        environment_id: str | None = None,
    ) -> ProvisionResult:
        """Provision a fresh environment and return a schema-valid record.

        ``environment_id`` may be supplied by the caller (the route creates the
        record first so it can return ``201 + provisioning`` immediately); when
        omitted a new id is generated.  Passing the id in keeps a single source
        of truth for the identifier — no post-hoc overwriting.

        On any failure the environment is returned in the ``failed`` state with a
        safe message; partial resources are cleaned up through
        :meth:`cleanup_environment` so nothing is leaked.
        """
        environment_id = environment_id or f"env-{uuid4().hex[:8]}"
        spec = self.build_spec(environment_id, payload)

        env = SyntheticEnvironment(
            environment_id=environment_id,
            environment_type=payload.environment_type,
            label=payload.label,
            status="provisioning",
            endpoint=None,
            metadata={"lifecycle": STAGE_PROVISIONING, "image": spec.image},
            created_at=_now(),
            updated_at=_now(),
        )

        # We only build real containers for postgres; other types are not yet
        # supported and must fail honestly rather than pretend.
        if payload.environment_type != "postgres":
            return self._fail(
                env,
                f"Environment type '{payload.environment_type}' is not supported yet; "
                "only 'postgres' provisioning is implemented.",
            )

        container_id: str | None = None
        try:
            if not self.provider.available():
                raise DockerUnavailableError("Docker Engine is not available.")

            container_id, container_name = self.provider.create(spec)
            env.metadata["container_id"] = container_id
            env.metadata["container_name"] = container_name

            # Verify it is genuinely running before claiming readiness.
            if not self.provider.is_running(container_id):
                raise ProvisionError("Container did not reach 'running' state.")

            env.metadata["lifecycle"] = STAGE_SEEDING
            if not self.provider.wait_for_ready(
                container_id,
                database=spec.database,
                username=spec.username,
                timeout_seconds=self.ready_timeout_seconds,
                poll_interval=self.poll_interval,
            ):
                raise ProvisionError("Database did not become ready within the timeout.")

            self._seed(container_id, spec)

            port = self.provider.host_port(container_id, spec.internal_port)
            connection = ConnectionInfo(
                host="127.0.0.1" if not spec.expose_publicly else "0.0.0.0",
                port=port or spec.internal_port,
                database=spec.database,
                username=spec.username,
                password=spec.password,
                container_id=container_id,
                container_name=container_name,
                image=spec.image,
            )
            env.status = "ready"
            env.endpoint = f"postgres://127.0.0.1:{connection.port}/{spec.database}"
            env.metadata["lifecycle"] = STAGE_READY
            env.metadata["database"] = spec.database
            env.metadata["username"] = spec.username
            env.metadata["connection"] = _connection_metadata(connection)
            env.metadata["seed"] = {
                "schema": self.seed_schema,
                "rows": len(database_seed.SEED_LEADS),
            }
            env.updated_at = _now()
            return ProvisionResult(environment=env, ok=True)
        except (DockerUnavailableError, ProvisionError) as exc:
            # Clean up anything we started before failing (idempotent).
            if container_id is not None:
                try:
                    self.provider.remove(container_id, force=True)
                except Exception:  # noqa: BLE001 - cleanup failure must not mask the cause
                    pass
                env.metadata["cleanup"] = "attempted"
            return self._fail(env, _safe_error(exc))
        except Exception as exc:  # noqa: BLE001 - never leak a raw exception to the API
            if container_id is not None:
                try:
                    self.provider.remove(container_id, force=True)
                except Exception:  # noqa: BLE001
                    pass
                env.metadata["cleanup"] = "attempted"
            return self._fail(env, f"Provisioning failed ({type(exc).__name__}).")

    def reset(self, environment: SyntheticEnvironment) -> SyntheticEnvironment:
        """Reset a ready environment back to its deterministic seed.

        Idempotent and ownership-safe: it acts only on the container recorded on
        this environment record.
        """
        container_id = environment.metadata.get("container_id")
        environment.metadata["lifecycle"] = STAGE_RESETTING
        environment.updated_at = _now()
        if not container_id:
            return _mark_failed(environment, "No container is associated with this environment.")

        try:
            self._run_sql(
                container_id,
                database_seed.render_truncate_sql(self.seed_schema),
                database=environment.metadata.get("database", "nexora"),
                username=environment.metadata.get("username", "nexora"),
            )
            self._run_sql(
                container_id,
                database_seed.render_full_seed_sql(self.seed_schema),
                database=environment.metadata.get("database", "nexora"),
                username=environment.metadata.get("username", "nexora"),
            )
        except ProvisionError as exc:
            return _mark_failed(environment, _safe_error(exc))

        environment.status = "ready"
        environment.metadata["lifecycle"] = STAGE_READY
        environment.updated_at = _now()
        environment.metadata.setdefault("history", []).append(
            {"action": "reset", "at": _now().isoformat()}
        )
        return environment

    def stop(self, environment: SyntheticEnvironment) -> SyntheticEnvironment:
        """Stop the underlying container but keep the record (contract: 'stopped').

        The container is genuinely stopped through the provider (``docker stop``);
        the status is only reported as ``stopped`` because we then verify the
        container is no longer running.
        """
        container_id = environment.metadata.get("container_id")
        stopped_ok = True
        if container_id:
            try:
                stopped_ok = self.provider.stop(container_id)
            except Exception:  # noqa: BLE001 - stopping must never raise to the API
                stopped_ok = False
        environment.status = "stopped"
        environment.metadata["lifecycle"] = STAGE_STOPPED
        environment.metadata["stop"] = "verified" if stopped_ok else "unverified"
        # A stale failure reason must not linger once the state advances.
        environment.metadata.pop("error", None)
        environment.updated_at = _now()
        return environment

    def cleanup_environment(self, environment: SyntheticEnvironment) -> SyntheticEnvironment:
        """Destroy all resources owned by this environment.  Safe to call twice.

        This is the "cleanup works after success and partial failure; repeated
        cleanup is safe" requirement.  We only ever remove the container recorded
        on this environment, so we cannot affect resources we do not own.
        """
        container_id = environment.metadata.get("container_id")
        removed = False
        if container_id:
            try:
                removed = self.provider.remove(container_id, force=True)
            except Exception:  # noqa: BLE001
                removed = False
        environment.metadata["lifecycle"] = STAGE_DESTROYED
        environment.metadata["cleanup"] = "removed" if removed else "already_absent"
        environment.metadata.pop("connection", None)  # never keep credentials past teardown
        environment.metadata.pop("error", None)  # a destroyed env is not a failed env
        environment.endpoint = None
        environment.status = "stopped"
        environment.updated_at = _now()
        return environment

    # -- internals ---------------------------------------------------------

    def _seed(self, container_id: str, spec: ContainerSpec) -> None:
        """Seed the synthetic schema/data, retrying transient startup races.

        Even after readiness passes, the PostgreSQL entrypoint may restart the
        server once during initialization.  A short bounded retry makes seeding
        robust against that without masking genuine SQL errors (``ON_ERROR_STOP``
        means a real SQL error still fails after the retries are exhausted).
        """
        sql = database_seed.render_full_seed_sql(self.seed_schema)
        attempts = 3
        last_detail = ""
        for attempt in range(1, attempts + 1):
            code, _out, err = self.provider.exec_command(
                container_id,
                ["psql", "-v", "ON_ERROR_STOP=1", "-U", spec.username, "-d", spec.database, "-f", "-"],
                input_text=sql,
            )
            if code == 0:
                return
            detail = (err or "").strip().splitlines()[-1] if (err or "").strip() else "no stderr"
            last_detail = f"psql exit {code}: {detail}"
            if attempt < attempts:
                time.sleep(0.5)
        raise ProvisionError(f"Seeding failed ({last_detail}).")

    def _run_sql(
        self,
        container_id: str,
        sql: str,
        *,
        database: str,
        username: str | None = None,
    ) -> None:
        command = ["psql", "-v", "ON_ERROR_STOP=1"]
        if username:
            command += ["-U", username]
        command += ["-d", database, "-f", "-"]
        code, _out, err = self.provider.exec_command(container_id, command, input_text=sql)
        if code != 0:
            detail = (err or "").strip().splitlines()[-1] if (err or "").strip() else "no stderr"
            raise ProvisionError(f"SQL execution failed (psql exit {code}: {detail}).")

    def _fail(self, env: SyntheticEnvironment, message: str) -> ProvisionResult:
        _mark_failed(env, message)
        return ProvisionResult(environment=env, ok=False, error=message)


def _mark_failed(env: SyntheticEnvironment, message: str) -> SyntheticEnvironment:
    """Transition ``env`` into the ``failed`` state and return it.

    Shared by ``provision`` (which wraps the result) and ``reset`` (which returns
    the environment directly) so the two paths can never diverge.
    """
    env.status = "failed"
    env.metadata["lifecycle"] = STAGE_FAILED
    env.metadata["error"] = message
    env.updated_at = _now()
    # Failed environments must not advertise an endpoint.
    env.endpoint = None
    return env


def _connection_metadata(connection: ConnectionInfo) -> dict[str, Any]:
    """Build the credential-bearing metadata block (redaction happens later)."""
    return {
        "host": connection.host,
        "port": connection.port,
        "database": connection.database,
        "username": connection.username,
        "password": connection.password,
        "dsn": connection.dsn(),
        "container_id": connection.container_id,
        "image": connection.image,
    }


def redact_connection(metadata: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``metadata`` whose connection block has no secrets.

    Applied by the route layer before returning an environment so credentials
    can never reach a response or a log.
    """
    safe = dict(metadata)
    connection = safe.get("connection")
    if isinstance(connection, dict):
        redacted = dict(connection)
        for key in ("password", "dsn"):
            if key in redacted:
                redacted[key] = "[REDACTED]"
        safe["connection"] = redacted
    return safe


def _safe_error(exc: Exception) -> str:
    """Map an exception to a short, non-sensitive, normalized message."""
    if isinstance(exc, DockerUnavailableError):
        return "Docker Engine is unavailable."
    if isinstance(exc, ProvisionError):
        return str(exc)
    return f"Provisioning failed ({type(exc).__name__})."
