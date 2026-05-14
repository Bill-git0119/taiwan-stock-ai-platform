"""Capital flow detector — infers institutional focus from chip + volume.

A sector or symbol is in "institutional focus" when at least two of:
  * Volume ratio >= 2.0 (today vs 20d avg)
  * Foreign or investment trust net-buy streak >= 3 days
  * Volume spike alignment with a sector that's RS-rank top 3

We look at the universe + DB only; no external data needed.
"""
from __future__ import annotations

from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChipData, Stock


async def institutional_focus(session: AsyncSession,
                              volume_anomalies: List[dict]) -> List[dict]:
    out: List[dict] = []
    sym_set = {v["symbol"] for v in volume_anomalies}
    if not sym_set:
        return out
    for sym in sym_set:
        stock = (await session.execute(
            select(Stock).where(Stock.symbol == sym)
        )).scalar_one_or_none()
        if stock is None:
            continue
        chips = (await session.execute(
            select(ChipData).where(ChipData.stock_id == stock.id)
            .order_by(ChipData.date.desc()).limit(10)
        )).scalars().all()
        foreign_streak = 0
        invest_streak = 0
        for c in chips:
            if (c.foreign_buy or 0) > 0:
                foreign_streak += 1
            else:
                break
        for c in chips:
            if (c.investment_buy or 0) > 0:
                invest_streak += 1
            else:
                break
        if foreign_streak >= 3 or invest_streak >= 3:
            out.append({
                "symbol": sym,
                "foreign_streak": foreign_streak,
                "investment_streak": invest_streak,
                "name": stock.name,
                "sector": stock.sector or "其他",
            })
    out.sort(key=lambda r: (r["foreign_streak"] + r["investment_streak"]),
             reverse=True)
    return out[:15]
