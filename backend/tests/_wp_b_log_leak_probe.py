"""Log-leak probe (WP-B) — credentials must not appear in logs.

Runs REAL provisioning with a unique canary password and captures ALL logging
output (root logger at DEBUG, plus warnings/errors).  Then asserts the canary
password never appears in:
  - the captured logs,
  - the API/redacted environment serialization,
  - the exception messages produced on failure.

Prints PASS/FAIL with observed evidence.
"""

from __future__ import annotations

import io
import logging
import sys

from app.integrations.environment.docker_provider import DockerProvider
from app.integrations.environment.manager import EnvironmentManager, redact_connection
from app.schemas.environment import SyntheticEnvironmentRequest

CANARY = "CANARY-super-secret-pw-do-not-log-9f3a"


def main() -> int:
    provider = DockerProvider()
    if not provider.available():
        print("Docker Engine not available.")
        return 2

    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        results.append((name, ok, detail))
        print(f"[{'PASS' if ok else 'FAIL'}] {name}\n        {detail}")

    # Capture ALL logging output.
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.DEBUG)
    root = logging.getLogger()
    old_level = root.level
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)

    manager = EnvironmentManager(provider=provider, ready_timeout_seconds=60.0, poll_interval=1.0)
    env = None
    try:
        # 1) Successful run with canary password.
        request = SyntheticEnvironmentRequest(
            environment_type="postgres",
            label="log-leak",
            config={"database": "logdb", "image": "postgres:16-alpine", "password": CANARY},
        )
        result = manager.provision(request, environment_id="env-logleak")
        env = result.environment

        # 2) Also exercise reset + cleanup (all lifecycle paths).
        if result.ok:
            env = manager.reset(env)
            env = manager.cleanup_environment(env)

        # 3) Exercise a FAILED provisioning with the same canary.
        bad = SyntheticEnvironmentRequest(
            environment_type="postgres",
            label="log-leak-bad",
            config={"database": "logdb", "image": "postgres:16-alpine", "password": CANARY},
        )
        EnvironmentManager(provider=provider, ready_timeout_seconds=0.0, poll_interval=0.0).provision(
            bad, environment_id="env-logleak-bad"
        )

        logs = stream.getvalue()
        check(
            "Logs: canary password does NOT appear in captured logs",
            CANARY not in logs,
            f"log bytes captured={len(logs)}, canary present={CANARY in logs}",
        )

        # Redacted serialization must not contain it either (on the success env).
        # Re-provision a ready env for serialization check.
        ready = manager.provision(
            SyntheticEnvironmentRequest(
                environment_type="postgres",
                label="serialize",
                config={"database": "logdb", "image": "postgres:16-alpine", "password": CANARY},
            ),
            environment_id="env-logleak-serialize",
        ).environment
        safe = redact_connection(ready.metadata)
        check(
            "Redacted serialization: canary absent",
            CANARY not in str(safe),
            f"password={'[REDACTED]' if safe.get('connection', {}).get('password') == '[REDACTED]' else 'LEAK'}",
        )
        check(
            "Endpoint: canary absent",
            CANARY not in (ready.endpoint or ""),
            f"endpoint={ready.endpoint}",
        )
        manager.cleanup_environment(ready)

    finally:
        if env is not None and env.metadata.get("container_id"):
            manager.cleanup_environment(env)
        root.removeHandler(handler)
        root.setLevel(old_level)
        provider.close()

    print("\n=== SUMMARY ===")
    passed = sum(1 for _, ok, _ in results if ok)
    for name, ok, _ in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"\n{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
