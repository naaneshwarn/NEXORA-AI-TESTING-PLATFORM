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
from app.workflow.runtime import configure_logging, get_logger
from app.workflow.service import recover_startup_runs

configure_logging(settings.log_level)
_startup_log = get_logger("startup")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown lifecycle for the application.

    On startup: recover workflow runs interrupted by a previous process crash
    so none dangle in a non-terminal state, then log the workflow subsystem's
    effective configuration.
    """
    recovered = recover_startup_runs()
    _startup_log.info(
        "workflow subsystem ready",
        extra={
            "recovered_runs": recovered,
            "max_concurrent_runs": settings.workflow_max_concurrent_runs,
            "total_timeout_seconds": settings.workflow_total_timeout_seconds,
        },
    )
    yield
    _startup_log.info("workflow subsystem shutting down")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="NEXORA AI Testing Platform foundation API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)
app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(agents_router, prefix=settings.api_prefix)
app.include_router(test_run_router, prefix=settings.api_prefix)
app.include_router(environment_router, prefix=settings.api_prefix)
app.include_router(evaluation_router, prefix=settings.api_prefix)
app.include_router(workflow_router, prefix=settings.api_prefix)


@app.get("/health")
async def root_health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name.lower()}

from app.api.routes.agent_execution import router as agent_execution_router
from app.api.routes.crm import router as crm_router
from app.api.routes.streaming import router as streaming_router

app.include_router(crm_router, prefix=settings.api_prefix)
app.include_router(agent_execution_router, prefix=settings.api_prefix)
app.include_router(streaming_router, prefix=settings.api_prefix)
