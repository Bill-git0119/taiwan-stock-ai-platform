"""GET /api/v1/trade-plan/{symbol} — full actionable trade plan."""
from __future__ import annotations

import math
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DailyPrice, Stock
from app.db.session import get_db
from app.services.cache_service import cached
from app.services.trade_plan_engine import build_plan

router = APIRouter()


def _synth_bars(symbol: str, n: int = 180) -> List[dict]:
    """Deterministic synthetic OHLCV when DB has no prices for this symbol.
    Lookahead-free by construction (each bar depends only on i and seed).
    """
    seed = sum(ord(ch) for ch in symbol) or 1
    base = 100 + (seed % 50) * 4
    bars = []
    px = base
    for i in range(n):
        # gentle uptrend + sin oscillation + bounded noise
        drift = 0.10
        wave = 1.5 * math.sin(i / 6 + seed)
        noise = ((i * 1103515245 + seed) % 1000) / 1000.0 - 0.5
        close = max(1.0, px + drift + wave + noise * 1.2)
        high = close + abs(noise) * 1.5 + 0.3
        low = close - abs(noise) * 1.5 - 0.3
        open_ = (high + low + close) / 3
        vol = 800_000 + int(abs(math.sin(i / 4)) * 400_000)
        bars.append({
            "date": f"2025-{((i // 22) % 12) + 1:02d}-{(i % 22) + 1:02d}",
            "open": round(open_, 2), "high": round(high, 2),
            "low": round(low, 2), "close": round(close, 2),
            "volume": vol,
        })
        px = close
    return bars


async def _load_bars(session: AsyncSession, symbol: str, limit: int = 240) -> List[dict]:
    stock = (
        await session.execute(select(Stock).where(Stock.symbol == symbol))
    ).scalar_one_or_none()
    if stock is None:
        return _synth_bars(symbol)
    rows = (
        await session.execute(
            select(DailyPrice)
            .where(DailyPrice.stock_id == stock.id)
            .order_by(DailyPrice.date.asc())
            .limit(limit)
        )
    ).scalars().all()
    if not rows:
        return _synth_bars(symbol)
    return [{
        "date": str(r.date), "open": r.open, "high": r.high,
        "low": r.low, "close": r.close, "volume": r.volume,
    } for r in rows]


@router.get("/{symbol}")
async def get_trade_plan(
    symbol: str,
    account_size: Optional[float] = Query(None, ge=0, description="account size in TWD for position-sizing hint"),
    session: AsyncSession = Depends(get_db),
):
    symbol = symbol.strip().upper()
    if not symbol:
        raise HTTPException(400, "symbol required")

    cache_key = f"trade-plan:{symbol}:{int(account_size or 0)}"

    async def loader():
        bars = await _load_bars(session, symbol)
        plan = build_plan(
            symbol=symbol,
            closes=[b["close"] for b in bars],
            highs=[b["high"] for b in bars],
            lows=[b["low"] for b in bars],
            volumes=[b["volume"] for b in bars],
            chip_records=[],          # production: hook chip table here
            fundamental_score=60.0,    # production: hook fundamentals here
            account_size=account_size,
        )
        return plan.to_dict()

    return await cached(cache_key, loader, ttl=120)
