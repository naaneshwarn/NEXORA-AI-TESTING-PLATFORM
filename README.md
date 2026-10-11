# NEXORA AI Testing Platform

NEXORA is a modular monolith foundation for an AI-powered testing platform that supports workflow orchestration, synthetic environments, and evaluation-driven test runs.

## Repository status

The repository already contains a frontend scaffold under `apps/web` and a Node-based placeholder API under `apps/api`. Those files are preserved as the starting point for the team UI and future frontend work.

This foundation adds a Python FastAPI backend under `backend/` so the project can start with a minimal working API while the rest of the platform is implemented in stages.

## Repository layout

- `apps/web/` – existing React + TypeScript frontend scaffold
- `apps/api/` – existing Node/Express placeholder service retained for compatibility
- `backend/` – Python FastAPI application and tests
- `docs/` – architecture and API contract documentation
- `packages/shared/` – existing shared TypeScript utilities retained for frontend use

## Module boundaries

- `apps/web/` – user dashboard and orchestration views
- `backend/app/` – API, config, schemas, and core application logic
- `backend/tests/` – API smoke tests and contract validation
- `docs/` – architectural guidance for team responsibilities and module interfaces
- Future modules such as workflow orchestration, synthetic database management, and profiling adapters should be added as separate subpackages under `backend/` or dedicated service folders, not as business logic embedded in `main.py`.

## Minimal setup

### Python backend

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend (existing scaffold)

```bash
npm install
npm run dev
```

### Run tests

```bash
cd backend
python -m pytest
```

## Environment configuration

Copy the sample environment file before running services:

```bash
copy .env.example .env
```

The application is intentionally designed to work without LLM API keys, Neo4j, Redis, or external services enabled. The health endpoint and schema layer should work in local development mode using default values.

## Initial assumptions

- The application is a local-development-first foundation; production secrets remain externalised via `.env` and deployment environment variables.
- The service is intentionally minimal. It exposes configuration and response contracts without creating fake integrations.
- The team will agree on additional service boundaries before adding workflow orchestration, Docker provisioning, or target-agent adapters.

## Current status

This repository currently contains the shared building blocks required for team work:

- React frontend scaffold retained
- Python FastAPI foundation added
- Minimal health endpoint and schema layer
- Basic pytest smoke test
- Architecture and API contract documentation
- Git exclusions for Python and Node generated artifacts

## Notes for the team

- Naaneshwar: backend API and target-agent integrations
- Rajath: Docker provisioning, synthetic database lifecycle, storage infrastructure
- Prajwal: target-agent profiling, protocol adapters, simulation APIs
- Rahul: LangGraph workflows, simulated users, evaluation metrics and reporting

The interface contracts documented in `docs/api-contracts.md` are intentionally simple and can be extended once the implementation starts.
