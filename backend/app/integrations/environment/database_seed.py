"""Synthetic PostgreSQL seed data for provisioning test environments.

Owner: Rajath (Work Package B — Docker environment lifecycle).

This module produces a small, **deterministic** synthetic CRM-style schema and
dataset.  It is the "deterministic synthetic seed data" the Phase 3 guide asks
for, and it contains **no real customer records** — every value is fabricated
and stable across runs so evaluation scenarios can assert on exact content.

Why generate SQL text instead of connecting with a driver?
- The backend declares no PostgreSQL client dependency, and the guide forbids
  exposing database ports broadly.  We seed from *inside* the container using
  ``psql`` via ``container.exec_run``, so no host-side driver is required.
- The generated SQL is pure data, trivially unit-testable without Docker.

The seed is expressed as data (:data:`SEED_LEADS`) plus a renderer, so tests can
assert on the deterministic values independently of how they are applied.
"""

from __future__ import annotations

from dataclasses import dataclass

# Names of the synthetic objects.  Kept in constants so the application layer,
# scenarios, and tests can refer to them without duplicating string literals.
SCHEMA_NAME = "nexora"
LEADS_TABLE = "leads"

# The single table our synthetic CRM exposes.  Column order here is the
# canonical insert order used by :func:`render_inserts`.
LEADS_COLUMNS: tuple[str, ...] = (
    "id",
    "name",
    "email",
    "company",
    "status",
    "created_at",
)


@dataclass(frozen=True)
class SeedLead:
    """One deterministic synthetic CRM lead (never a real person)."""

    id: str
    name: str
    email: str
    company: str
    status: str
    created_at: str  # ISO-8601, fixed so seeding is reproducible


# Deterministic synthetic dataset.  IDs/emails use the reserved ``.test`` TLD so
# they can never collide with a real address.  ``created_at`` values are fixed
# timestamps (not ``now()``) so two seeds are byte-identical.
SEED_LEADS: tuple[SeedLead, ...] = (
    SeedLead(
        id="lead-0001",
        name="Synthetic Seed Lead",
        email="seed.lead@nexora.test",
        company="NEXORA Synthetic Labs",
        status="qualified",
        created_at="2026-01-01T00:00:00+00:00",
    ),
    SeedLead(
        id="lead-0002",
        name="Ada Synthetic",
        email="ada.synthetic@nexora.test",
        company="Synthetic Analytics Ltd",
        status="new",
        created_at="2026-01-02T00:00:00+00:00",
    ),
    SeedLead(
        id="lead-0003",
        name="Grace Mock",
        email="grace.mock@nexora.test",
        company="Mock Industries",
        status="contacted",
        created_at="2026-01-03T00:00:00+00:00",
    ),
)


def _sql_quote(value: str) -> str:
    """Quote a string as a single-quoted SQL literal.

    Only single quotes need escaping for these fixed, code-controlled values;
    the function is deliberately minimal and never used for untrusted input.
    """
    return "'" + value.replace("'", "''") + "'"


def render_schema_sql(schema: str = SCHEMA_NAME, table: str = LEADS_TABLE) -> str:
    """Return idempotent DDL that creates the synthetic schema and table.

    ``CREATE ... IF NOT EXISTS`` makes reset-safe re-application trivial.
    """
    return (
        f"CREATE SCHEMA IF NOT EXISTS {schema};\n"
        f"CREATE TABLE IF NOT EXISTS {schema}.{table} (\n"
        "    id          TEXT PRIMARY KEY,\n"
        "    name        TEXT NOT NULL,\n"
        "    email       TEXT NOT NULL,\n"
        "    company     TEXT NOT NULL,\n"
        "    status      TEXT NOT NULL,\n"
        "    created_at  TIMESTAMPTZ NOT NULL\n"
        ");\n"
    )


def render_inserts_sql(
    schema: str = SCHEMA_NAME,
    table: str = LEADS_TABLE,
) -> str:
    """Return the seed INSERTs, deterministic and idempotent.

    ``ON CONFLICT DO NOTHING`` on the primary key means re-seeding never
    duplicates rows and never overwrites an operator's changes silently.
    """
    lines: list[str] = []
    for lead in SEED_LEADS:
        values = ", ".join(
            _sql_quote(v) if column != "created_at" else f"{_sql_quote(v)}::timestamptz"
            for column, v in (
                ("id", lead.id),
                ("name", lead.name),
                ("email", lead.email),
                ("company", lead.company),
                ("status", lead.status),
                ("created_at", lead.created_at),
            )
        )
        lines.append(
            f"INSERT INTO {schema}.{table} "
            f"({', '.join(LEADS_COLUMNS)}) VALUES ({values}) "
            "ON CONFLICT (id) DO NOTHING;"
        )
    return "\n".join(lines) + "\n"


def render_truncate_sql(schema: str = SCHEMA_NAME, table: str = LEADS_TABLE) -> str:
    """Return DML that removes all rows (used by reset)."""
    return f"TRUNCATE TABLE {schema}.{table};\n"


def render_full_seed_sql(schema: str = SCHEMA_NAME, table: str = LEADS_TABLE) -> str:
    """Return the complete seed program: schema, table, and rows."""
    return render_schema_sql(schema, table) + "\n" + render_inserts_sql(schema, table)


def expected_seed_rows() -> list[dict[str, str]]:
    """Return the seed rows as plain dicts (for assertions and documentation)."""
    return [
        {
            "id": lead.id,
            "name": lead.name,
            "email": lead.email,
            "company": lead.company,
            "status": lead.status,
            "created_at": lead.created_at,
        }
        for lead in SEED_LEADS
    ]
