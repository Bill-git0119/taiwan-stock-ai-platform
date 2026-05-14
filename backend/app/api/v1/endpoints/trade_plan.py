"""GET /api/v1/trade-plan/{symbol} — full actionable trade plan.

Production rule: if DB has no OHLCV for the symbol, refuse to compute a plan.
We never serve a plan derived from synthetic data — instead return
NO_TRADE / NO_REAL_DATA so the UI shows a clear "資料尚未灌入" state.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChipData, DailyPrice, Stock
from app.db.session import get_db
from app.services.cache_service import cached
from app.services.trade_plan_engine import build_plan

router = APIRouter()

MIN_BARS_REQUIRED = 60  # need enough history for EMA200 / ATR / breakout windows


async def _load_real_bars(
    session: AsyncSession, symbol: str, limit: int = 240,
) -> tuple[List[dict], List[dict]]:
    """Load OHLCV + chip rows for a symbol. Returns ([], []) when no real data."""
    stock = (
        await session.execute(select(Stock).where(Stock.symbol == symbol))
    ).scalar_one_or_none()
    if stock is None:
        return [], []
    rows = (
        await session.execute(
            select(DailyPrice)
            .where(DailyPrice.stock_id == stock.id)
            .order_by(DailyPrice.date.asc())
            .limit(limit)
        )
    ).scalars().all()
    bars = [{
        "date": str(r.date), "open": r.open, "high": r.high,
        "low": r.low, "close": r.close, "volume": r.volume,
    } for r in rows]
    chip_rows = (
        await session.execute(
            select(ChipData)
            .where(ChipData.stock_id == stock.id)
            .order_by(ChipData.date.asc())
            .limit(60)
        )
    ).scalars().all()
    chip_records = [{
        "foreign_buy": float(c.foreign_buy or 0),
        "investment_buy": float(c.investment_buy or 0),
        "dealer_buy": float(c.dealer_buy or 0),
        "volume": int(rows[i].volume) if i < len(rows) else 0,
    } for i, c in enumerate(chip_rows)]
    return bars, chip_records


def _no_real_data_response(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "bias": "NO_TRADE",
        "setup": None,
        "entry_zone": None,
        "stop_loss": None,
        "take_profit": None,
        "risk_reward": None,
        "confidence": 0.0,
        "chip_score": 0.0,
        "technical_score": 0.0,
        "fundamental_score": 0.0,
        "reasons": [],
        "indicators": {},
        "chip": {},
        "no_trade_reason": "NO_REAL_DATA",
        "last_close": None,
        "atr": None,
        "position_size_hint": None,
        "data_source": "none",
    }


@router.get("/{symbol}")
async def get_trade_plan(
    symbol: str,
    account_size: Optional[float] = Query(
        None, ge=0, description="account size in TWD for position-sizing hint",
    ),
    session: AsyncSession = Depends(get_db),
):
    symbol = symbol.strip().upper()
    if not symbol:
        raise HTTPException(400, "symbol required")

    cache_key = f"trade-plan:{symbol}:{int(account_size or 0)}"

    async def loader():
        bars, chip_records = await _load_real_bars(session, symbol)
        # Iron rule: no synthetic fallback. If real data is missing or too thin,
        # return NO_REAL_DATA so callers (UI / scheduler) know to wait for ingest.
        if not bars or len(bars) < MIN_BARS_REQUIRED:
            return _no_real_data_response(symbol)
        plan = build_plan(
            symbol=symbol,
            closes=[b["close"] for b in bars],
            highs=[b["high"] for b in bars],
            lows=[b["low"] for b in bars],
            volumes=[b["volume"] for b in bars],
            chip_records=chip_records,
            # Honest signal — no synthetic fundamentals (re-weighted internally).
            fundamental_score=None,
            account_size=account_size,
        )
        out = plan.to_dict()
        out["data_source"] = "real"
        # Data freshness — last bar date used to build the plan
        out["as_of"] = bars[-1].get("date") if bars else None
        return out

    return await cached(cache_key, loader, ttl=120)
