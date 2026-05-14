"""Weekly UniverseSnapshot builder.

For each curated symbol:
  1. Ensure a Stock row exists (creates with sector tags from curated table)
  2. Compute 20-day liquidity from DailyPrice
  3. Pass/fail against MIN_DAILY_NOTIONAL_TWD
  4. Persist a UniverseSnapshot row for today

The previous week's rows are kept — UniverseManager reads "most recent
snapshot" so the system can survive a missed weekly run.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Stock, UniverseSnapshot
from app.universe.curated import deduplicated
from app.universe.liquidity_filter import evaluate

log = logging.getLogger("universe.builder")


async def _ensure_stocks(session: AsyncSession) -> dict[str, Stock]:
    """Insert any missing curated symbol into stocks (with sector tag)."""
    out: dict[str, Stock] = {}
    for sym, name, market, sec_zh, _sec_en in deduplicated():
        st = (await session.execute(
            select(Stock).where(Stock.symbol == sym)
        )).scalar_one_or_none()
        if st is None:
            st = Stock(symbol=sym, name=name, market=market, sector=sec_zh)
            session.add(st)
            await session.flush()
        else:
            # keep sector fresh
            if not st.sector or st.sector == "其他":
                st.sector = sec_zh
        out[sym] = st
    await session.commit()
    return out


async def build_snapshot(session: AsyncSession,
                         on_date: date | None = None) -> dict:
    on_date = on_date or date.today()
    await _ensure_stocks(session)

    curated = deduplicated()
    symbols = [c[0] for c in curated]
    sector_map = {c[0]: (c[3], c[4]) for c in curated}
    name_map = {c[0]: c[1] for c in curated}
    market_map = {c[0]: c[2] for c in curated}

    liq_rows = await evaluate(session, symbols)
    # rank by notional desc
    liq_rows_sorted = sorted(liq_rows, key=lambda r: r[3], reverse=True)
    rank_by_symbol = {row[0]: i + 1 for i, row in enumerate(liq_rows_sorted)}

    n_active = 0
    for sym, avg_vol, last, notional, passes in liq_rows:
        sec_zh, sec_en = sector_map.get(sym, ("其他", "Other"))
        existing = (await session.execute(
            select(UniverseSnapshot)
            .where(UniverseSnapshot.date == on_date,
                   UniverseSnapshot.symbol == sym)
        )).scalar_one_or_none()
        if existing:
            existing.avg_volume_20d = avg_vol
            existing.last_close = last
            existing.notional_twd = notional
            existing.is_active = passes
            existing.rank_by_notional = rank_by_symbol[sym]
            existing.sector_zh = sec_zh
            existing.sector_en = sec_en
            existing.name = name_map.get(sym, existing.name)
            existing.market = market_map.get(sym, existing.market)
        else:
            session.add(UniverseSnapshot(
                date=on_date,
                symbol=sym,
                name=name_map.get(sym, sym),
                market=market_map.get(sym, "TWSE"),
                sector_zh=sec_zh,
                sector_en=sec_en,
                avg_volume_20d=avg_vol,
                last_close=last,
                notional_twd=notional,
                is_active=passes,
                rank_by_notional=rank_by_symbol[sym],
            ))
        if passes:
            n_active += 1
    await session.commit()
    report = {
        "date": str(on_date),
        "curated_count": len(curated),
        "active_count": n_active,
        "inactive_count": len(curated) - n_active,
    }
    log.info("universe snapshot: %s", report)
    return report
