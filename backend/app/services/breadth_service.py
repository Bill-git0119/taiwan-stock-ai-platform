"""Market breadth — the trader's regime instrument.

Tells the operator at a glance:
  * how many stocks are participating (adv/dec, % above MA)
  * whether expansion is happening (new highs vs lows)
  * which sectors lead / lag

No lookahead: uses only bars dated `<= as_of`.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DailyPrice, Stock


async def compute_breadth(session: AsyncSession) -> dict:
    """Snapshot of market breadth across the loaded universe."""
    stocks = (await session.execute(select(Stock))).scalars().all()
    sym_to_sector = {s.symbol: (s.sector or "其他") for s in stocks}
    sym_to_name = {s.symbol: s.name for s in stocks}

    advancing = 0
    declining = 0
    above_ma20 = 0
    above_ma50 = 0
    new_high_20 = 0
    new_low_20 = 0
    new_high_60 = 0
    new_low_60 = 0
    universe_size = 0
    as_of: Optional[str] = None

    sector_ret_buckets: dict[str, list[float]] = defaultdict(list)
    leaders: list[dict] = []
    laggards: list[dict] = []

    for st in stocks:
        rows = (
            await session.execute(
                select(DailyPrice)
                .where(DailyPrice.stock_id == st.id)
                .order_by(DailyPrice.date.desc())
                .limit(65)
            )
        ).scalars().all()
        if len(rows) < 21:
            continue
        bars = list(reversed(rows))  # ascending
        last = bars[-1]
        prev = bars[-2]
        universe_size += 1
        if as_of is None or str(last.date) > as_of:
            as_of = str(last.date)

        # Adv/Dec — close vs prior close (more meaningful than open vs close).
        d1 = last.close - prev.close
        if d1 > 0:
            advancing += 1
        elif d1 < 0:
            declining += 1

        # MA metrics
        closes_20 = [b.close for b in bars[-20:]]
        ma20 = sum(closes_20) / len(closes_20)
        if last.close >= ma20:
            above_ma20 += 1
        if len(bars) >= 50:
            closes_50 = [b.close for b in bars[-50:]]
            ma50 = sum(closes_50) / len(closes_50)
            if last.close >= ma50:
                above_ma50 += 1

        # New highs / lows
        hi20 = max(b.high for b in bars[-20:])
        lo20 = min(b.low for b in bars[-20:])
        if last.close >= hi20 * 0.999:
            new_high_20 += 1
        if last.close <= lo20 * 1.001:
            new_low_20 += 1
        if len(bars) >= 60:
            hi60 = max(b.high for b in bars[-60:])
            lo60 = min(b.low for b in bars[-60:])
            if last.close >= hi60 * 0.999:
                new_high_60 += 1
            if last.close <= lo60 * 1.001:
                new_low_60 += 1

        # Sector aggregation by 5-day return
        d5_anchor = bars[-6] if len(bars) >= 6 else bars[0]
        ret_5d = (last.close / d5_anchor.close - 1) * 100 if d5_anchor.close else 0.0
        sector_ret_buckets[sym_to_sector[st.symbol]].append(ret_5d)

        leaders.append({
            "symbol": st.symbol,
            "name": sym_to_name.get(st.symbol),
            "sector": sym_to_sector.get(st.symbol),
            "ret_5d": round(ret_5d, 2),
            "ret_1d": round((d1 / prev.close * 100) if prev.close else 0, 2),
            "last": round(float(last.close), 2),
        })

    leaders.sort(key=lambda r: r["ret_5d"], reverse=True)
    laggards = list(reversed(leaders[-10:]))
    leaders = leaders[:10]

    sectors = [
        {
            "sector": sec,
            "ret_5d": round(sum(rs) / len(rs), 2),
            "members": len(rs),
        }
        for sec, rs in sector_ret_buckets.items()
    ]
    sectors.sort(key=lambda r: r["ret_5d"], reverse=True)
    for i, s in enumerate(sectors):
        s["rank"] = i + 1

    if universe_size == 0:
        return {
            "as_of": None,
            "universe_size": 0,
            "advance_decline": {"advancing": 0, "declining": 0, "ratio": 0.0},
            "above_ma20_pct": 0.0,
            "above_ma50_pct": 0.0,
            "new_highs_20": 0,
            "new_lows_20": 0,
            "new_highs_60": 0,
            "new_lows_60": 0,
            "regime_hint": "no_data",
            "sectors": [],
            "leaders": [],
            "laggards": [],
        }

    ad_ratio = advancing / max(1, declining) if declining else float(advancing)
    pct_ma20 = above_ma20 / universe_size * 100
    pct_ma50 = above_ma50 / universe_size * 100

    # Simple regime hint from breadth alone (independent of price regime)
    if pct_ma20 >= 65 and ad_ratio >= 2.0 and new_high_20 > new_low_20:
        regime_hint = "broad_strength"
    elif pct_ma20 <= 35 and ad_ratio <= 0.5 and new_low_20 > new_high_20:
        regime_hint = "broad_weakness"
    elif new_high_20 < 3 and new_low_20 < 3:
        regime_hint = "consolidation"
    else:
        regime_hint = "mixed"

    return {
        "as_of": as_of,
        "universe_size": universe_size,
        "advance_decline": {
            "advancing": advancing,
            "declining": declining,
            "ratio": round(ad_ratio, 2),
        },
        "above_ma20_pct": round(pct_ma20, 1),
        "above_ma50_pct": round(pct_ma50, 1),
        "new_highs_20": new_high_20,
        "new_lows_20": new_low_20,
        "new_highs_60": new_high_60,
        "new_lows_60": new_low_60,
        "regime_hint": regime_hint,
        "sectors": sectors,
        "leaders": leaders,
        "laggards": laggards,
    }
