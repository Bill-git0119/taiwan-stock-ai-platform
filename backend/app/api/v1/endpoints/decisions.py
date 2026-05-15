"""Short-term decision endpoint — workspace UI consumes this.

GET /api/v1/decisions/short-term  →  ranked decisions + market_state
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.cache_service import cached
from app.services.decision_engine import decide

router = APIRouter()


@router.get("/short-term")
async def short_term(
    limit: int = 30,
    include_research: bool = True,
    session: AsyncSession = Depends(get_db),
) -> dict:
    cache_key = f"decisions:short-term:{limit}:{int(include_research)}"
    async def loader():
        return await decide(session, limit=limit, include_research=include_research)
    return await cached(cache_key, loader, ttl=180)
