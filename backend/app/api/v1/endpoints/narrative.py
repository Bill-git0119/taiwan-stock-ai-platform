"""Narrative engine endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.narrative.narrative_engine import build_narrative
from app.services.cache_service import cached

router = APIRouter()


@router.get("/today")
async def today(session: AsyncSession = Depends(get_db)):
    async def loader():
        return await build_narrative(session)
    return await cached("narrative-today", loader, ttl=600)
