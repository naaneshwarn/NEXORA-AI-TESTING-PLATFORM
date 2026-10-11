from fastapi import APIRouter

from app.core.config import settings
from app.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name.lower(),
        environment=settings.app_env,
        version="0.1.0",
    )
