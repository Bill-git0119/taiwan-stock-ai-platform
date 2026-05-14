"""Strategy ranking endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.cache_service import cached
from app.strategy_registry.ranker import rank_all

router = APIRouter()


@router.get("/")
async def list_ranks(session: AsyncSession = Depends(get_db)):
    async def loader():
        rankings = await rank_all(session)
        return {
            "items": [
                {
                    "strategy": r.strategy,
                    "rank_score": r.rank_score,
                    "production_status": r.production_status,
                    "components": r.components,
                    "failures": r.failures,
                }
                for r in rankings
            ],
        }
    return await cached("strategy-rank", loader, ttl=300)
