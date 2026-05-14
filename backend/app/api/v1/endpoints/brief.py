"""Daily Trading Brief endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.cache_service import cached
from app.services.daily_brief import build_brief

router = APIRouter()


@router.get("/today")
async def today(session: AsyncSession = Depends(get_db)):
    async def loader():
        return await build_brief(session)
    return await cached("brief-today", loader, ttl=300)
