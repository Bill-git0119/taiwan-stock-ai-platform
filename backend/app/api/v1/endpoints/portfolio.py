"""Portfolio simulation endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DailyPrice, Stock
from app.db.session import get_db
from app.portfolio_backtester.simulator import run_portfolio
from app.services.cache_service import cached
from strategy.strategies import REGISTRY

router = APIRouter()


@router.get("/simulate")
async def simulate(
    symbol: str = Query("0050"),
    strategies: str = Query("trend_breakout,chip_follow",
                             description="comma-separated strategy names"),
    starting_equity: float = Query(1_000_000.0, ge=100_000),
    risk_pct: float = Query(0.01, ge=0.001, le=0.05),
    max_concurrent: int = Query(3, ge=1, le=10),
    session: AsyncSession = Depends(get_db),
):
    names = [s.strip() for s in strategies.split(",") if s.strip()]
    fns = {n: REGISTRY[n] for n in names if n in REGISTRY}
    if not fns:
        raise HTTPException(400, "no valid strategies selected")

    async def loader():
        stock = (await session.execute(
            select(Stock).where(Stock.symbol == symbol)
        )).scalar_one_or_none()
        if stock is None:
            raise HTTPException(404, f"unknown symbol {symbol!r}")
        rows = (await session.execute(
            select(DailyPrice).where(DailyPrice.stock_id == stock.id)
            .order_by(DailyPrice.date.asc())
        )).scalars().all()
        bars = [{"date": str(r.date), "open": r.open, "high": r.high,
                 "low": r.low, "close": r.close, "volume": r.volume}
                for r in rows]
        rep = run_portfolio(
            bars, fns,
            starting_equity=starting_equity,
            risk_pct_per_trade=risk_pct,
            max_concurrent_positions=max_concurrent,
        )
        return rep.to_dict()
    key = f"portfolio:{symbol}:{strategies}:{int(starting_equity)}:{risk_pct}:{max_concurrent}"
    return await cached(key, loader, ttl=600)
