"""Liquidity filter — keep only symbols above a daily volume floor.

A symbol passes when:
    avg_20d_volume * last_close >= MIN_DAILY_NOTIONAL_TWD

Default MIN_DAILY_NOTIONAL_TWD = 50,000,000 (NT$50M turnover / day).
This is conservative enough that short-term traders can size positions
without becoming a meaningful fraction of average volume.

Returns a list of (symbol, avg_volume_20d, last_close, notional_twd, passes).
"""
from __future__ import annotations

import logging
from typing import Iterable, List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DailyPrice, Stock

log = logging.getLogger("universe.liquidity")


MIN_DAILY_NOTIONAL_TWD = 50_000_000
MIN_BARS_FOR_LIQUIDITY = 20


async def evaluate(session: AsyncSession,
                   symbols: Iterable[str]) -> List[Tuple[str, int, float, float, bool]]:
    rows: List[Tuple[str, int, float, float, bool]] = []
    for sym in symbols:
        stock = (await session.execute(
            select(Stock).where(Stock.symbol == sym)
        )).scalar_one_or_none()
        if stock is None:
            rows.append((sym, 0, 0.0, 0.0, False))
            continue
        bars = (await session.execute(
            select(DailyPrice).where(DailyPrice.stock_id == stock.id)
            .order_by(DailyPrice.date.desc()).limit(MIN_BARS_FOR_LIQUIDITY)
        )).scalars().all()
        if len(bars) < MIN_BARS_FOR_LIQUIDITY:
            rows.append((sym, 0, 0.0, 0.0, False))
            continue
        avg_vol = sum(b.volume for b in bars) / len(bars)
        last = float(bars[0].close)
        notional = avg_vol * last
        rows.append((sym, int(avg_vol), last, float(notional),
                     notional >= MIN_DAILY_NOTIONAL_TWD))
    return rows
