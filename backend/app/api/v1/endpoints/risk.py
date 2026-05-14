"""Risk allocation endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.risk_engine.allocator import allocate
from app.services.cache_service import cached
from app.strategy_registry.ranker import rank_all

router = APIRouter()


@router.get("/allocation")
async def allocation(regime: str = Query("unknown"),
                     base_risk_pct: float = Query(0.01, ge=0.001, le=0.05),
                     max_concurrent: int = Query(3, ge=1, le=10),
                     session: AsyncSession = Depends(get_db)):
    async def loader():
        rankings = await rank_all(session)
        strategies = [
            {
                "strategy": r.strategy,
                "rank_score": r.rank_score,
                "production_status": r.production_status,
                "live_expectancy_R": r.components.get("live_expectancy_R", 0.0),
            }
            for r in rankings
        ]
        return allocate(strategies, regime_label=regime,
                        base_risk_pct=base_risk_pct,
                        max_concurrent=max_concurrent)
    return await cached(f"risk:{regime}:{base_risk_pct}:{max_concurrent}", loader, ttl=600)
