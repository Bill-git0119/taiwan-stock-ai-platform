"""Edge persistence endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.edge.edge_persistence import persistence_report
from app.services.cache_service import cached

router = APIRouter()


@router.get("/")
async def persistence(window: int = Query(90, ge=14, le=365),
                       session: AsyncSession = Depends(get_db)):
    async def loader():
        return await persistence_report(session, window_days=window)
    return await cached(f"persistence:{window}", loader, ttl=600)
