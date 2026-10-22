from __future__ import annotations

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.agents import router as agents_router
from app.api.routes.environments import router as environment_router
from app.api.routes.evaluations import router as evaluation_router
from app.api.routes.health import router as health_router
from app.api.routes.test_runs import router as test_run_router
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.schemas.common import HealthResponse

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("nexora.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown lifecycle management."""
    logger.info(
        "Starting %s backend service [environment=%s, prefix=%s]",
        settings.app_name,
        settings.app_env,
        settings.api_prefix,
    )
    yield
    logger.info("Shutting down %s backend service.", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="NEXORA AI Testing Platform foundation API for test orchestration, synthetic environments, and evaluation.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
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


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def root_health() -> HealthResponse:
    """Root health endpoint reporting core service vitality."""
    return HealthResponse(
        status="ok",
        service=settings.app_name.lower(),
        environment=settings.app_env,
        version="0.1.0",
    )

