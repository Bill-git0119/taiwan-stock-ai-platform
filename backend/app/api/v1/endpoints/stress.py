"""Regime stress-test endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DailyPrice, Stock
from app.db.session import get_db
from app.services.cache_service import cached
from strategy.stress.regime_segments import all_segments
from strategy.stress.stress_runner import run_stress
from strategy.strategies import REGISTRY

router = APIRouter()


@router.get("/run/{strategy}")
async def run(
    strategy: str,
    symbol: str = Query("0050", description="proxy symbol whose bars feed the stress test"),
    session: AsyncSession = Depends(get_db),
):
    fn = REGISTRY.get(strategy)
    if fn is None:
        raise HTTPException(404, f"unknown strategy {strategy!r}")

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
        report = run_stress(bars, fn, strategy_name=strategy, symbol=symbol)
        return report.to_dict()
    return await cached(f"stress:{strategy}:{symbol}", loader, ttl=900)


@router.get("/segments")
async def segments(session: AsyncSession = Depends(get_db)):
    return {"known_segments": [s.to_dict() for s in all_segments(include_known=True)]}
