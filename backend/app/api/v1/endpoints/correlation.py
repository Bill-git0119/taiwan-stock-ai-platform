"""Strategy correlation endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.cache_service import cached
from strategy.correlation.correlation_analyzer import correlation_matrix

router = APIRouter()


@router.get("/matrix")
async def matrix(window: int = Query(90, ge=14, le=365),
                 session: AsyncSession = Depends(get_db)):
    async def loader():
        return await correlation_matrix(session, window_days=window)
    return await cached(f"corr:{window}", loader, ttl=600)
