"""Strong-stock scanner endpoints — built for short-term traders."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.cache_service import cached
from app.services.scanner_service import scan_movers, scan_sectors, scan_universe
from app.services.strategy_health import health_report

router = APIRouter()


@router.get("/scan")
async def scan(
    bias: Optional[str] = Query(None, pattern="^(LONG|SHORT|NO_TRADE)$"),
    setup: Optional[str] = Query(None),
    min_rr: Optional[float] = Query(None, ge=0),
    min_confidence: Optional[float] = Query(None, ge=0, le=1),
    min_winrate: Optional[float] = Query(None, ge=0, le=1),
    include_disabled: bool = Query(False),
    limit: int = Query(60, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
):
    """Run trade-plan engine across the whole universe and rank by
    expectancy × frequency × confidence.

    Disabled setups (auto-disable rule) excluded unless include_disabled=true.
    """
    cache_key = (
        f"scan:{bias}:{setup}:{min_rr}:{min_confidence}:"
        f"{min_winrate}:{include_disabled}:{limit}"
    )

    async def loader():
        return await scan_universe(
            session,
            bias_filter=bias,
            min_rr=min_rr,
            min_confidence=min_confidence,
            setup_filter=setup,
            min_winrate=min_winrate,
            include_disabled=include_disabled,
            limit=limit,
        )
    return await cached(cache_key, loader, ttl=180)


@router.get("/movers")
async def movers(session: AsyncSession = Depends(get_db)):
    async def loader():
        return await scan_movers(session)
    return await cached("movers", loader, ttl=120)


@router.get("/sectors")
async def sectors(session: AsyncSession = Depends(get_db)):
    async def loader():
        return await scan_sectors(session)
    return await cached("sectors", loader, ttl=300)


@router.get("/strategy-health")
async def strategy_health(session: AsyncSession = Depends(get_db)):
    """Per-setup historical performance + auto-disable status.

    Public — there is value in users seeing why a setup is disabled.
    """
    async def loader():
        return {"setups": await health_report(session)}
    return await cached("strategy-health", loader, ttl=600)
