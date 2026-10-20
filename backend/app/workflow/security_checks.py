"""Standalone security/advisory checks for workflow runs (Rahul / Work Package D).

The Phase 3 guide asks for security checks to be *modular*: task completion
and factual correctness are the core evaluators, and security/advisory checks
should be addable separately without touching the scoring of the core
criteria.  This module owns secret-leak detection end to end:

1. collect secret values from sensitive-named run variables,
2. scan every persisted artifact (traces, summary, raw record) for them,
3. emit a critical ``secret_exposure`` finding when one leaks.

``evaluate_run`` in :mod:`app.workflow.evaluator` calls
:func:`evaluate_security` and applies the result to the trace-integrity
criterion, so a leaked secret still zeroes trace integrity and blocks a
passing result — but the detection logic lives here and can be extended or
replaced independently (e.g. a future advisory-only severity mode).

Like the rest of Work Package D this module is deterministic: no clocks,
randomness, network, or credentials.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.core.redaction import SENSITIVE_KEYS
from app.schemas.workflow_report import Finding

# Normalized key names that mark a scenario variable as secret ("API_KEY",
# "api-key", "apiKey" all normalize to "apikey").
_NORMALIZED_SENSITIVE_KEYS = frozenset(re.sub(r"[^a-z0-9]", "", key.lower()) for key in SENSITIVE_KEYS)


@dataclass(slots=True)
class SecurityCheckResult:
    """Outcome of the security scan over one run's artifacts."""

    findings: list[Finding] = field(default_factory=list)
    leaked_secret: str | None = None

    @property
    def leaked(self) -> bool:
        return self.leaked_secret is not None


def extract_secret_values(variables: dict[str, Any]) -> list[str]:
    """Collect values of sensitive scenario variables for leak detection."""
    secrets: list[str] = []
    for key, value in variables.items():
        normalized_key = re.sub(r"[^a-z0-9]", "", str(key).lower())
        if normalized_key in _NORMALIZED_SENSITIVE_KEYS and isinstance(value, str) and value:
            secrets.append(value)
    return secrets


def artifact_contains_secret(artifacts: Iterable[Any], secrets: list[str]) -> str | None:
    """Return the first secret found in the serialized artifacts, if any."""
    if not secrets:
        return None
    serialized = json.dumps(list(artifacts), default=str, sort_keys=True)
    for secret in secrets:
        if secret in serialized:
            return secret
    return None


def evaluate_security(
    traces: list[dict[str, Any]],
    summary: str,
    record: dict[str, Any] | None,
    run_variables: dict[str, Any] | None,
    evidence_ref: str | None = None,
) -> SecurityCheckResult:
    """Scan persisted run artifacts for leaked secret scenario variables.

    ``traces``, ``summary``, and ``record`` are exactly the artifacts that get
    persisted and shown in reports — if a secret value appears in any of them
    it has leaked.  Returns a critical ``secret_exposure`` finding when that
    happens; the empty (clean) result otherwise.
    """
    secrets = extract_secret_values(run_variables or {})
    leaked = artifact_contains_secret([traces, summary, record], secrets)
    if leaked is None:
        return SecurityCheckResult()
    return SecurityCheckResult(
        leaked_secret=leaked,
        findings=[
            Finding(
                severity="critical",
                code="secret_exposure",
                message="A secret value from the run variables appeared in traces or reports.",
                evidence_ref=evidence_ref,
            )
        ],
    )
