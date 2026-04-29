from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    env: str
    timestamp: str


@router.get("", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service="taiwan-stock-ai-platform",
        version="0.1.0",
        env=settings.app_env,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
