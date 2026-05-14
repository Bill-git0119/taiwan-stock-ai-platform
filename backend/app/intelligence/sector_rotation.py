"""Sector rotation — relative strength across sectors from DailyPrice rows.

Output for each sector:
  symbols      : list[str]
  count        : int
  return_5d    : avg 5-day % return
  return_20d   : avg 20-day % return
  rs_rank      : 1 = strongest, N = weakest (by 20d return)
  momentum     : 0..1 normalized
  leaders      : top 3 symbols by 20d return inside this sector

Strict no-lookahead — uses only DB-stored close prices, no estimates.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DailyPrice, Stock

log = logging.getLogger("intel.sectors")


def _pct_return(closes: List[float], n: int) -> float | None:
    if len(closes) < n + 1:
        return None
    head = closes[-n - 1]
    if head == 0:
        return None
    return (closes[-1] / head - 1.0) * 100.0


async def sector_rotation(session: AsyncSession) -> dict:
    stocks = (await session.execute(select(Stock))).scalars().all()
    by_sector: Dict[str, List[Stock]] = defaultdict(list)
    for st in stocks:
        sec = (st.sector or "其他").strip()
        by_sector[sec].append(st)

    sector_rows: List[dict] = []
    leader_pool: List[dict] = []
    for sector, items in by_sector.items():
        per_symbol: List[dict] = []
        for st in items:
            rows = (
                await session.execute(
                    select(DailyPrice)
                    .where(DailyPrice.stock_id == st.id)
                    .order_by(DailyPrice.date.asc())
                )
            ).scalars().all()
            closes = [float(r.close) for r in rows]
            r5 = _pct_return(closes, 5)
            r20 = _pct_return(closes, 20)
            if r20 is None:
                continue
            per_symbol.append({
                "symbol": st.symbol, "name": st.name,
                "return_5d": round(r5, 2) if r5 is not None else None,
                "return_20d": round(r20, 2),
                "last_close": closes[-1] if closes else None,
            })
            leader_pool.append({"symbol": st.symbol, "sector": sector,
                                "return_20d": round(r20, 2),
                                "return_5d": round(r5, 2) if r5 is not None else None})
        if not per_symbol:
            continue
        avg5 = sum(p["return_5d"] for p in per_symbol if p["return_5d"] is not None)
        n5 = sum(1 for p in per_symbol if p["return_5d"] is not None)
        avg20 = sum(p["return_20d"] for p in per_symbol) / len(per_symbol)
        per_symbol.sort(key=lambda r: r["return_20d"], reverse=True)
        sector_rows.append({
            "sector": sector,
            "count": len(per_symbol),
            "return_5d": round(avg5 / n5, 2) if n5 else None,
            "return_20d": round(avg20, 2),
            "leaders": per_symbol[:3],
        })

    sector_rows.sort(key=lambda r: r["return_20d"], reverse=True)
    # rank + momentum
    if sector_rows:
        mx = sector_rows[0]["return_20d"]
        mn = sector_rows[-1]["return_20d"]
        spread = max(0.01, mx - mn)
        for i, row in enumerate(sector_rows, start=1):
            row["rs_rank"] = i
            row["momentum"] = round((row["return_20d"] - mn) / spread, 3)

    # cross-sector leaders
    leader_pool.sort(key=lambda r: r["return_20d"], reverse=True)
    return {
        "sectors": sector_rows,
        "top_leaders": leader_pool[:10],
        "bottom_laggards": leader_pool[-10:][::-1],
    }
