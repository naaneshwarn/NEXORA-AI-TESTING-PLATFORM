# NEXORA architecture foundation

## Overview

NEXORA starts as a modular monolith with clear boundaries for a future multi-service platform. The initial MVP keeps the application small enough to run locally with default configuration while reserving the interfaces required for workflow orchestration, simulation infrastructure, and evaluation logic.

## Current structure

- `apps/web/` – existing React frontend scaffold; dashboard and workflow control surfaces
- `apps/api/` – retained placeholder Node service; not the canonical backend for MVP
- `backend/` – Python FastAPI application for API ingress, config, schemas, and orchestrator-facing routes
- `docs/` – platform architecture and contract definitions
- `packages/shared/` – existing frontend type utilities retained for shared UI use

## Responsibilities by team member

### Naaneshwar — backend and target-agent integrations

- API route design
- service-layer separation
- target-agent adapters and execution hooks
- external API integration boundaries

### Rajath — environment provisioning and storage

- Docker Engine and container lifecycle management
- synthetic database lifecycle orchestration for PostgreSQL, MySQL, and MongoDB
- Redis usage for execution state and cache
- infrastructure automation scripts and local environment support

### Prajwal — profiling and simulation

- target-agent profiling and protocol adapters
- synthetic API simulator behaviour and contract testing
- environment-level service emulation

### Rahul — workflows and evaluation

- LangGraph orchestration and simulated user flows
- security and advisory testing
- score calculation and evaluation reports
- test-run summarisation and result distillation

## Interface principles

1. The `backend/` service owns the canonical API contract for the MVP.
2. Frontend code should communicate only through typed API schemas defined in `backend/app/schemas/`.
3. Workflow logic should not live in a single `main.py` file; it should be layered into modules as the project grows.
4. External dependencies such as Neo4j, Redis, and LLM providers are optional in the local development environment and must not be required for the health route or smoke tests.
5. New modules must be added in a way that preserves the current repository and existing frontend scaffold.

## Current MVP boundary

The initial foundation includes only:

- application bootstrap
- configuration loading from environment variables
- consistent error formatting
- minimal health endpoint
- minimal schemas for agent configuration, test-run requests, execution status, and evaluation results
- smoke tests that run without external services

This deliberately excludes live LLM and database integrations until the team approves the deployment and runtime model.

## Phase 2 API contracts

The following contract areas are now defined as shared interfaces for the team:

- agent registration and configuration
- test-run creation, cancellation, and state retrieval
- synthetic environment provisioning and lifecycle tracking
- execution event and trace capture
- evaluation submission and final report retrieval

Each contract is implemented in dedicated route modules under `backend/app/api/routes/` and its corresponding models under `backend/app/schemas/` so that the service remains modular without moving all logic into the main application entry point.
