"""Strong-stock scanner endpoints — built for short-term traders."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.cache_service import cached
from app.services.scanner_service import scan_movers, scan_sectors, scan_universe

router = APIRouter()


@router.get("/scan")
async def scan(
    bias: Optional[str] = Query(None, pattern="^(LONG|SHORT|NO_TRADE)$"),
    setup: Optional[str] = Query(None),
    min_rr: Optional[float] = Query(None, ge=0),
    min_confidence: Optional[float] = Query(None, ge=0, le=1),
    limit: int = Query(60, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
):
    """Run trade-plan engine across the whole universe and rank by edge.

    Default with no filters returns every symbol's plan (LONG + NO_TRADE)
    so the UI can show all setups; pass ?bias=LONG&min_rr=1.5 for actionable.
    """
    cache_key = f"scan:{bias}:{setup}:{min_rr}:{min_confidence}:{limit}"

    async def loader():
        return await scan_universe(
            session,
            bias_filter=bias,
            min_rr=min_rr,
            min_confidence=min_confidence,
            setup_filter=setup,
            limit=limit,
        )
    return await cached(cache_key, loader, ttl=180)


@router.get("/movers")
async def movers(session: AsyncSession = Depends(get_db)):
    """Today's gainers, losers, gap-ups, volume spikes, breakouts."""
    async def loader():
        return await scan_movers(session)
    return await cached("movers", loader, ttl=120)


@router.get("/sectors")
async def sectors(session: AsyncSession = Depends(get_db)):
    """Sector strength heatmap (1d / 5d returns, top leaders)."""
    async def loader():
        return await scan_sectors(session)
    return await cached("sectors", loader, ttl=300)
