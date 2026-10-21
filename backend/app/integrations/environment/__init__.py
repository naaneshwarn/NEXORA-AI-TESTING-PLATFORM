"""Synthetic environment provisioning (Rajath — Work Package B).

Public surface:

- :class:`EnvironmentManager` — lifecycle service behind the environment routes.
- :class:`DockerProvider` — real Docker Engine provider (Python Docker SDK).
- :class:`MockDatabaseProvider` — deterministic, Docker-free provider for tests.
- :func:`redact_connection` — strips credentials before responses/logs.

See ``docs/work-package-b-summary.md`` for the full design record.
"""

from __future__ import annotations

from app.integrations.environment.docker_provider import (
    ConnectionInfo,
    ContainerSpec,
    DockerProvider,
    DockerUnavailableError,
    ProvisionError,
)
from app.integrations.environment.manager import (
    DatabaseProvider,
    EnvironmentManager,
    ProvisionResult,
    generate_password,
    redact_connection,
)

__all__ = [
    "ConnectionInfo",
    "ContainerSpec",
    "DatabaseProvider",
    "DockerProvider",
    "DockerUnavailableError",
    "EnvironmentManager",
    "ProvisionError",
    "ProvisionResult",
    "generate_password",
    "redact_connection",
]
