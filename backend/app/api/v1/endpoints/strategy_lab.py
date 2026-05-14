"""Strategy Lab endpoints — run walk-forward + Monte Carlo + show registry."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.cache_service import cached
from app.strategy_lab.runner import (
    PROMOTED_STRATEGIES, is_promoted, run_lab,
)
from app.strategy_lab.validator import PROMOTION_THRESHOLDS

router = APIRouter()


@router.get("/run/{symbol}")
async def run_for_symbol(
    symbol: str,
    strategy: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db),
):
    async def loader():
        return await run_lab(session, symbol.upper(), strategy_name=strategy)
    return await cached(f"lab:{symbol}:{strategy}", loader, ttl=600)


@router.get("/promoted")
async def promoted():
    return {"promoted": PROMOTED_STRATEGIES,
            "thresholds": PROMOTION_THRESHOLDS}


@router.get("/check/{strategy}")
async def check(strategy: str):
    return {"strategy": strategy, "promoted": is_promoted(strategy)}
