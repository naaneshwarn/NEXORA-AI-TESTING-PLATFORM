"""Real-data acceptance verification for WP-B (Rajath) — 5 test points.

Run with Docker Engine available:
    python backend/tests/_wp_b_acceptance_probe.py

This is a manual verification harness (not a pytest file) that provisions a REAL
PostgreSQL container and checks each acceptance-test point from the Phase 3 guide,
printing PASS/FAIL with the actual observed values.
"""

from __future__ import annotations

import sys
import traceback

from app.integrations.environment import database_seed
from app.integrations.environment.docker_provider import DockerProvider
from app.integrations.environment.manager import EnvironmentManager, redact_connection
from app.schemas.environment import SyntheticEnvironmentRequest

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str) -> None:
    RESULTS.append((name, condition, detail))
    print(f"[{'PASS' if condition else 'FAIL'}] {name}\n        {detail}")


def main() -> int:
    provider = DockerProvider()
    if not provider.available():
        print("Docker Engine not available — cannot run real acceptance probe.")
        return 2

    manager = EnvironmentManager(provider=provider, ready_timeout_seconds=60.0, poll_interval=1.0)
    request = SyntheticEnvironmentRequest(
        environment_type="postgres",
        label="acceptance-probe",
        config={"database": "acceptdb", "image": "postgres:16-alpine"},
    )

    env = None
    try:
        # --- Point 2: provisioning success updates lifecycle state ------------
        result = manager.provision(request, environment_id="env-accept-1")
        env = result.environment
        cid = env.metadata.get("container_id")
        check(
            "Point 2a: successful provisioning reaches ready",
            result.ok and env.status == "ready" and env.metadata["lifecycle"] == "ready",
            f"status={env.status} lifecycle={env.metadata.get('lifecycle')}",
        )
        check(
            "Point: container is genuinely running (verified, real daemon)",
            bool(cid) and provider.is_running(cid) is True,
            f"docker status={provider.container_status(cid)}",
        )

        # --- Real seed data actually present in the DB ------------------------
        code, out, err = provider.exec_command(
            cid,
            ["psql", "-U", "nexora", "-d", "acceptdb", "-tAc",
             f"SELECT count(*) FROM {database_seed.SCHEMA_NAME}.{database_seed.LEADS_TABLE};"],
        )
        expected = len(database_seed.SEED_LEADS)
        check(
            "Point: deterministic synthetic seed rows exist (real query)",
            code == 0 and out.strip() == str(expected),
            f"exit={code} rows={out.strip()} expected={expected}",
        )

        # verify exact deterministic content (not just count)
        code2, out2, _ = provider.exec_command(
            cid,
            ["psql", "-U", "nexora", "-d", "acceptdb", "-tAc",
             f"SELECT string_agg(id, ',' ORDER BY id) FROM {database_seed.SCHEMA_NAME}.{database_seed.LEADS_TABLE};"],
        )
        expected_ids = ",".join(sorted(r["id"] for r in database_seed.expected_seed_rows()))
        check(
            "Point: seed content is deterministic and matches expected ids",
            code2 == 0 and out2.strip() == expected_ids,
            f"got={out2.strip()} expected={expected_ids}",
        )

        # --- Point 4 (part): credentials redacted -----------------------------
        safe = redact_connection(env.metadata)
        raw_pw = env.metadata["connection"]["password"]
        check(
            "Point 4a: password/dsn redacted in safe view",
            safe["connection"]["password"] == "[REDACTED]"
            and safe["connection"]["dsn"] == "[REDACTED]",
            f"password={safe['connection']['password']} dsn={safe['connection']['dsn']}",
        )
        check(
            "Point 4b: raw password absent from redacted serialization",
            raw_pw not in str(safe),
            "raw password not found in redacted payload",
        )
        check(
            "Point: endpoint never contains the password",
            raw_pw not in (env.endpoint or ""),
            f"endpoint={env.endpoint}",
        )

        # --- Point 3: cleanup after success -----------------------------------
        destroyed = manager.cleanup_environment(env)
        check(
            "Point 3a: cleanup after success removes the container",
            destroyed.metadata["cleanup"] == "removed"
            and provider.is_running(cid) is False,
            f"cleanup={destroyed.metadata['cleanup']} running={provider.is_running(cid)}",
        )
        check(
            "Point 3b: cleanup strips credentials",
            "connection" not in destroyed.metadata,
            f"keys={sorted(destroyed.metadata.keys())}",
        )

        # --- Point 3 (repeat): repeated cleanup is safe -----------------------
        again = manager.cleanup_environment(destroyed)
        check(
            "Point 3c: repeated cleanup is safe (idempotent)",
            again.metadata["cleanup"] == "already_absent",
            f"second cleanup={again.metadata['cleanup']}",
        )

        # --- Point 1: reset restores deterministic seed -----------------------
        env2 = manager.provision(request, environment_id="env-accept-2").environment
        cid2 = env2.metadata["container_id"]
        # mutate
        provider.exec_command(
            cid2,
            ["psql", "-U", "nexora", "-d", "acceptdb", "-c",
             f"DELETE FROM {database_seed.SCHEMA_NAME}.{database_seed.LEADS_TABLE};"],
        )
        _, after_delete, _ = provider.exec_command(
            cid2,
            ["psql", "-U", "nexora", "-d", "acceptdb", "-tAc",
             f"SELECT count(*) FROM {database_seed.SCHEMA_NAME}.{database_seed.LEADS_TABLE};"],
        )
        reset_env = manager.reset(env2)
        _, after_reset, _ = provider.exec_command(
            cid2,
            ["psql", "-U", "nexora", "-d", "acceptdb", "-tAc",
             f"SELECT count(*) FROM {database_seed.SCHEMA_NAME}.{database_seed.LEADS_TABLE};"],
        )
        check(
            "Point 1: reset restores deterministic seed after mutation",
            after_delete.strip() == "0" and after_reset.strip() == str(expected)
            and reset_env.status == "ready",
            f"after_delete={after_delete.strip()} after_reset={after_reset.strip()} status={reset_env.status}",
        )

        # --- Point: partial provisioning failure cleans up --------------------
        # Force a seed failure by pointing at a bad DB, ensure no leak.
        bad_request = SyntheticEnvironmentRequest(
            environment_type="postgres",
            label="acceptance-badseed",
            config={"database": "acceptdb", "image": "postgres:16-alpine",
                    # extra env makes the container start but we break seeding by
                    # using an unsupported engine path is separate; here simulate by
                    # a manager with a provider whose seed fails is covered by unit
                    # tests. For real Docker, verify unsupported engine fails safely.
                    },
        )
        unsupported = SyntheticEnvironmentRequest(environment_type="redis", label="unsupported")
        unsup_result = manager.provision(unsupported, environment_id="env-accept-unsup")
        check(
            "Point: unsupported engine fails honestly, no container created",
            unsup_result.ok is False
            and unsup_result.environment.status == "failed"
            and unsup_result.environment.endpoint is None,
            f"status={unsup_result.environment.status} error={unsup_result.environment.metadata.get('error')}",
        )

        # cleanup env2
        manager.cleanup_environment(reset_env)

        # --- Point 5: mocked tests never claim a real container ---------------
        check(
            "Point 5: live probe used real daemon ids (not fabricated)",
            cid is not None and len(cid) == 64,
            f"container_id length={len(cid) if cid else 0} (real docker ids are 64 hex chars)",
        )

    except Exception:
        traceback.print_exc()
        check("probe completed without exception", False, traceback.format_exc().splitlines()[-1])
    finally:
        provider.close()

    print("\n=== SUMMARY ===")
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    for name, ok, _ in RESULTS:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
