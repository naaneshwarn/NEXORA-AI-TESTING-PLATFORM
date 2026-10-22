# NEXORA AI Testing Platform

NEXORA is a modular monolith foundation for an AI-powered testing platform that supports workflow orchestration, synthetic test environments, and evaluation-driven test runs.

## Project Overview

NEXORA provides a unified platform to evaluate, stress-test, and benchmark autonomous AI agents across controlled environments and reproducible scenarios. The system coordinates agent management, test execution lifecycles, synthetic databases, and analytical reporting.

## Repository Layout

```
├── apps/
│   ├── web/               # React + TypeScript + Vite frontend dashboard
│   └── api/               # Legacy Node/Express placeholder service retained for compatibility
├── backend/
│   ├── app/
│   │   ├── api/routes/    # FastAPI route controllers (health, agents, test-runs, environments, evaluations)
│   │   ├── core/          # Configuration, thread-safe in-memory store, domain error handling
│   │   ├── schemas/       # Standardized Pydantic schemas and response envelopes
│   │   ├── services/      # Module integration interfaces and deterministic mock providers
│   │   └── main.py        # Application entry point with CORS, lifespan, and route registry
│   ├── tests/             # Pytest test suite for health, contracts, error envelopes, and concurrency
│   └── requirements.txt   # Python backend dependencies
├── docs/
│   ├── architecture.md    # Platform architecture, module boundaries, and teammate responsibilities
│   └── api-contracts.md   # Canonical API contracts, endpoints, request/response models, and error codes
├── packages/
│   └── shared/            # Shared TypeScript utilities and types for frontend apps
├── package.json           # Root workspace configuration
├── pytest.ini             # Pytest configuration
└── .env.example           # Sample environment variables
```

## Team Responsibilities

- **Naaneshwar**: FastAPI backend core, API routing, shared response contracts, error handling, store abstraction, and integration interfaces.
- **Rajath**: Docker Engine container lifecycle, synthetic databases (PostgreSQL, MySQL, MongoDB, Redis, Neo4j), and infrastructure.
- **Prajwal**: Target-agent adapters, protocol wrappers, and synthetic API simulator.
- **Rahul**: LangGraph workflow orchestration, simulated user execution, evaluation metrics, and reporting.

---

## Prerequisites

- **Python**: 3.10+ (Python 3.11 recommended)
- **Node.js**: 18.0+ & npm 9+
- **Git**

---

## Quickstart

### 1. Python Backend

From the repository root or `backend/` directory:

```bash
# Navigate to backend (or project root)
cd backend

# Create virtual environment (if not already present)
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start backend server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The backend starts at `http://localhost:8000`.

### 2. Interactive API Documentation

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **OpenAPI Schema**: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health) or [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

### 3. Frontend Dashboard

From the repository root:

```bash
# Install workspace dependencies
npm install

# Start Vite development server
npm run dev
```

The frontend will start at `http://localhost:5173`.

To configure the API endpoint targeted by the frontend, create an `.env` or `.env.local` in `apps/web/`:
```bash
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

### 4. Running Tests

Run the backend pytest test suite:

```bash
# From repository root:
python -m pytest -v

# Or from backend/ directory:
cd backend
python -m pytest -v
```

Run frontend linting and type-checks:
```bash
npm run lint
npm run build
```

---

## Environment Variables

Copy `.env.example` to `.env` to customize settings:

| Variable | Default | Description |
| --- | --- | --- |
| `APP_NAME` | `NEXORA` | Application title reported in health and documentation |
| `APP_ENV` | `development` | Deployment environment (`development`, `test`, `production`) |
| `API_PREFIX` | `/api/v1` | URL prefix for versioned API endpoints |
| `PORT` | `8000` | Local port for FastAPI server |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:5173` | Comma-separated allowed frontend origins |
| `VITE_API_BASE_URL` | `http://localhost:8000/api/v1` | Frontend target URL for backend API |

---

## Known Limitations & Planned Integrations

1. **In-Memory Store**: In the MVP, all registered agents, test runs, environments, events, and reports are held in a thread-safe in-memory store. All data is reset upon server restart. Persistent databases (PostgreSQL/Redis) are planned for future phases.
2. **Synthetic Environments**: The environment API tracks lifecycle states (`provisioning`, `stopped`). Container endpoints remain `None` in development mode until Rajath's Docker daemon lifecycle integration is connected.
3. **Target Agent Execution**: Agent registration sanitizes and redacts credentials. Real external LLM invocation interfaces are defined in `app/services/interfaces.py` and run through deterministic mock paths until Prajwal's adapter integration lands.
4. **LangGraph Workflow Orchestration**: Test runs are created in `queued` state with trace events. Rahul's LangGraph graph engine will connect via `WorkflowOrchestratorProtocol` to transition runs to execution and trigger automatic evaluations.

