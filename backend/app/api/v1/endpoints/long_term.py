"""Long-term investment endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.cache_service import cached
from app.services.long_term_engine import analyse_universe

router = APIRouter()


@router.get("/buckets")
async def buckets(
    limit_per_bucket: int = 20,
    session: AsyncSession = Depends(get_db),
) -> dict:
    cache_key = f"long_term:buckets:{limit_per_bucket}"
    async def loader():
        return await analyse_universe(session, limit_per_bucket=limit_per_bucket)
    return await cached(cache_key, loader, ttl=600)
