from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.agents import router as agents_router
from app.api.routes.environments import router as environment_router
from app.api.routes.evaluations import router as evaluation_router
from app.api.routes.health import router as health_router
from app.api.routes.test_runs import router as test_run_router
from app.core.config import settings
from app.core.errors import register_error_handlers

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="NEXORA AI Testing Platform foundation API",
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


@app.get("/health")
async def root_health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name.lower()}

from app.api.routes.agent_execution import router as agent_execution_router
from app.api.routes.crm import router as crm_router

app.include_router(crm_router, prefix=settings.api_prefix)
app.include_router(agent_execution_router, prefix=settings.api_prefix)
