"""Real edge performance APIs — no backtest data ever leaks in here."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.edge import edge_decay, performance_monitor, strategy_metrics
from app.services.cache_service import cached

router = APIRouter()


@router.get("/snapshot")
async def snapshot(window: int = Query(30, ge=7, le=365),
                   session: AsyncSession = Depends(get_db)):
    async def loader():
        return await performance_monitor.snapshot(session, window=window)
    return await cached(f"perf-snap:{window}", loader, ttl=180)


@router.get("/by-setup")
async def by_setup(window: int = Query(30, ge=7, le=365),
                   session: AsyncSession = Depends(get_db)):
    async def loader():
        return {"window_days": window,
                "stats": await strategy_metrics.by_setup(session, window)}
    return await cached(f"perf-setup:{window}", loader, ttl=180)


@router.get("/by-regime")
async def by_regime(window: int = Query(30, ge=7, le=365),
                    session: AsyncSession = Depends(get_db)):
    async def loader():
        return {"window_days": window,
                "stats": await strategy_metrics.by_regime(session, window)}
    return await cached(f"perf-regime:{window}", loader, ttl=180)


@router.get("/by-sector")
async def by_sector(window: int = Query(30, ge=7, le=365),
                    session: AsyncSession = Depends(get_db)):
    async def loader():
        return {"window_days": window,
                "stats": await strategy_metrics.by_sector(session, window)}
    return await cached(f"perf-sector:{window}", loader, ttl=180)


@router.get("/setup-x-regime")
async def setup_x_regime(window: int = Query(90, ge=14, le=365),
                         session: AsyncSession = Depends(get_db)):
    async def loader():
        return {"window_days": window,
                "matrix": await strategy_metrics.setup_x_regime(session, window)}
    return await cached(f"perf-sxr:{window}", loader, ttl=300)


@router.get("/decay")
async def decay(session: AsyncSession = Depends(get_db)):
    async def loader():
        return await edge_decay.decay_scores(session)
    return await cached("perf-decay", loader, ttl=300)
