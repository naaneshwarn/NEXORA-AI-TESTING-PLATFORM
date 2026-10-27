from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.agents import router as agents_router
from app.api.routes.environments import router as environment_router
from app.api.routes.evaluations import router as evaluation_router
from app.api.routes.health import router as health_router
from app.api.routes.test_runs import router as test_run_router
from app.api.routes.workflow import router as workflow_router
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.core.auth import configured_api_keys, resolve_auth_mode
from app.core.middleware import AuthMiddleware, ObservabilityMiddleware
from app.core.persistence import configure_from_settings, persistence
from app.integrations.synthetic_api import create_synthetic_api_router
from app.workflow.runtime import configure_logging, get_logger
from app.workflow.service import recover_startup_runs

configure_logging(settings.log_level)
_startup_log = get_logger("startup")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown lifecycle for the application.

    On startup:
      * configure and hydrate the durable core-store snapshot (agents, runs,
        environments, leads, traces, reports survive restarts),
      * recover workflow runs interrupted by a previous process crash so none
        dangle in a non-terminal state,
      * report the effective authentication mode and warn loudly when it was
        explicitly requested but cannot be enforced (no keys configured).

    On shutdown the store is flushed one last time (a no-op when persistence
    is disabled).
    """
    state_path = configure_from_settings()
    reloaded = persistence.load()

    auth_mode = resolve_auth_mode()
    keys_configured = bool(configured_api_keys())
    requested_mode = (settings.auth_mode or "auto").strip().lower()
    if requested_mode in {"write", "full"} and not keys_configured:
        _startup_log.warning(
            "NEXORA_AUTH_MODE=%s requested but NEXORA_API_KEYS is empty; "
            "authentication is disabled until at least one key is configured",
            requested_mode.upper(),
        )

    recovered = recover_startup_runs()
    _startup_log.info(
        "workflow subsystem ready",
        extra={
            "recovered_runs": recovered,
            "max_concurrent_runs": settings.workflow_max_concurrent_runs,
            "total_timeout_seconds": settings.workflow_total_timeout_seconds,
        },
    )
    _startup_log.info(
        "platform ready",
        extra={
            "store_persistence": str(state_path) if state_path else "disabled",
            "store_reloaded": reloaded,
            "auth_mode": auth_mode,
            "api_keys_configured": keys_configured,
        },
    )
    yield
    persistence.save()
    _startup_log.info("workflow subsystem shutting down")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "NEXORA AI Testing Platform — workflow orchestration, synthetic "
        "environments, target-agent execution, fault injection and "
        "evaluation reporting (Phase 3)."
    ),
    lifespan=lifespan,
)

# Middleware registration order.  Starlette applies the *last* middleware added
# as the outermost layer, so this list is written inside-out:
#
#   1. AuthMiddleware      — innermost of the three: rejects unauthenticated
#                            mutations before they reach a route.
#   2. CORSMiddleware      — answers preflight OPTIONS itself, so browsers get
#                            CORS headers without needing credentials.
#   3. ObservabilityMiddleware — outermost: security headers + access logging
#                            apply to every response, including CORS preflights
#                            and middleware-generated 401s.
app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ObservabilityMiddleware)

register_error_handlers(app)
app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(agents_router, prefix=settings.api_prefix)
app.include_router(test_run_router, prefix=settings.api_prefix)
app.include_router(environment_router, prefix=settings.api_prefix)
app.include_router(evaluation_router, prefix=settings.api_prefix)
app.include_router(workflow_router, prefix=settings.api_prefix)
app.include_router(create_synthetic_api_router(), prefix=settings.api_prefix)


@app.get("/health")
async def root_health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name.lower()}


from app.api.routes.agent_execution import router as agent_execution_router
from app.api.routes.crm import router as crm_router
from app.api.routes.streaming import router as streaming_router

app.include_router(crm_router, prefix=settings.api_prefix)
app.include_router(agent_execution_router, prefix=settings.api_prefix)
app.include_router(streaming_router, prefix=settings.api_prefix)


@app.get('/v1/models')
async def openai_compatible_models():
    return {'object': 'list', 'data': [{'id': 'nexora-mock-agent', 'object': 'model', 'created': 1729999999, 'owned_by': 'nexora'}, {'id': 'crm-read-customer-summary', 'object': 'model', 'created': 1729999999, 'owned_by': 'nexora'}]}


@app.get('/v1/health')
async def openai_compatible_health():
    return {'status': 'ok'}
