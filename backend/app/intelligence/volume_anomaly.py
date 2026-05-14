"""Volume anomaly detector — finds today's outlier-volume stocks.

For each symbol with >= 25 bars:
  ratio = today_volume / avg(last 20 bars excluding today)

Returned as a sorted list. Threshold default >= 2.0×.

Lookahead-free — every row uses only data up to bar `i`.
"""
from __future__ import annotations

import logging
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DailyPrice, Stock

log = logging.getLogger("intel.volume")


async def volume_anomalies(session: AsyncSession, min_ratio: float = 2.0,
                            min_volume: int = 100_000) -> List[dict]:
    stocks = (await session.execute(select(Stock))).scalars().all()
    rows: List[dict] = []
    for st in stocks:
        prices = (
            await session.execute(
                select(DailyPrice)
                .where(DailyPrice.stock_id == st.id)
                .order_by(DailyPrice.date.asc())
            )
        ).scalars().all()
        if len(prices) < 25:
            continue
        today = prices[-1]
        prior = prices[-21:-1]
        avg_v = sum(p.volume for p in prior) / len(prior) if prior else 0
        if avg_v <= 0 or today.volume < min_volume:
            continue
        ratio = today.volume / avg_v
        if ratio < min_ratio:
            continue
        pct = (today.close / prices[-2].close - 1.0) * 100.0 if prices[-2].close else 0
        rows.append({
            "symbol": st.symbol,
            "name": st.name,
            "date": str(today.date),
            "close": float(today.close),
            "change_pct": round(pct, 2),
            "volume": int(today.volume),
            "avg_volume_20d": int(avg_v),
            "ratio": round(ratio, 2),
        })
    rows.sort(key=lambda r: r["ratio"], reverse=True)
    return rows[:30]
