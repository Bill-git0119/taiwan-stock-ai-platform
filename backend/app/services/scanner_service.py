"""Strong-stock scanner — runs trade-plan engine across the whole universe
and ranks the results by an "edge score" so a 短線交易員 can identify the
day's strongest actionable setups in one query.

Edge score (0..100):
    confidence * 60       — chip + fund + tech composite
  + min(rr, 4) * 5        — risk-reward
  + breakout_20 ? 8 : 0
  + volume_spike up to 8  — clamped (volume_spike-1)*8
  + foreign_streak * 1.5  — capped at 5
  + ma_alignment ? 6 : 0

This is intentionally simple and transparent — a trader can read the breakdown.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChipData, DailyPrice, Stock
from app.services.trade_plan_engine import build_plan


MIN_BARS = 60


def _edge_score(plan_dict: dict) -> float:
    if plan_dict.get("bias") != "LONG":
        return 0.0
    conf = float(plan_dict.get("confidence") or 0.0)
    rr = float(plan_dict.get("risk_reward") or 0.0)
    ind = plan_dict.get("indicators") or {}
    chip = plan_dict.get("chip") or {}
    score = conf * 60.0
    score += min(rr, 4.0) * 5.0
    if ind.get("breakout_20"):
        score += 8
    vs = float(ind.get("volume_spike") or 0)
    score += max(0.0, min(8.0, (vs - 1.0) * 8.0))
    fs = int(chip.get("foreign_streak") or 0)
    score += min(5, fs) * 1.5
    if ind.get("ma_alignment"):
        score += 6
    return round(score, 2)


async def _bars_for(session: AsyncSession, stock_id: int, limit: int = 240) -> tuple[list[dict], list[dict]]:
    rows = (
        await session.execute(
            select(DailyPrice)
            .where(DailyPrice.stock_id == stock_id)
            .order_by(DailyPrice.date.asc())
            .limit(limit)
        )
    ).scalars().all()
    bars = [
        {"date": str(r.date), "open": r.open, "high": r.high,
         "low": r.low, "close": r.close, "volume": r.volume}
        for r in rows
    ]
    chips = (
        await session.execute(
            select(ChipData)
            .where(ChipData.stock_id == stock_id)
            .order_by(ChipData.date.asc())
            .limit(60)
        )
    ).scalars().all()
    chip_records = [
        {
            "foreign_buy": float(c.foreign_buy or 0),
            "investment_buy": float(c.investment_buy or 0),
            "dealer_buy": float(c.dealer_buy or 0),
            "volume": int(rows[i].volume) if i < len(rows) else 0,
        }
        for i, c in enumerate(chips)
    ]
    return bars, chip_records


async def scan_universe(
    session: AsyncSession,
    bias_filter: Optional[str] = None,        # "LONG", "SHORT", "NO_TRADE", None=all
    min_rr: Optional[float] = None,
    min_confidence: Optional[float] = None,
    setup_filter: Optional[str] = None,
    limit: int = 60,
) -> dict:
    """Build a trade plan for every stock with sufficient data, rank by edge."""
    stocks = (await session.execute(select(Stock))).scalars().all()
    rows: List[dict] = []
    for st in stocks:
        bars, chip_records = await _bars_for(session, st.id)
        if len(bars) < MIN_BARS:
            continue
        plan = build_plan(
            symbol=st.symbol,
            closes=[b["close"] for b in bars],
            highs=[b["high"] for b in bars],
            lows=[b["low"] for b in bars],
            volumes=[b["volume"] for b in bars],
            chip_records=chip_records,
            fundamental_score=60.0,
        ).to_dict()
        plan["name"] = st.name
        plan["market"] = st.market
        plan["edge"] = _edge_score(plan)
        rows.append(plan)

    # Filters
    out = rows
    if bias_filter:
        out = [r for r in out if r.get("bias") == bias_filter]
    if setup_filter:
        out = [r for r in out if r.get("setup") == setup_filter]
    if min_rr is not None:
        out = [r for r in out if (r.get("risk_reward") or 0) >= min_rr]
    if min_confidence is not None:
        out = [r for r in out if (r.get("confidence") or 0) >= min_confidence]

    out.sort(key=lambda r: (r.get("edge", 0), r.get("confidence", 0)), reverse=True)
    return {
        "scanned": len(rows),
        "matched": len(out),
        "items": out[:limit],
    }


# ─────────────────────────── Movers ────────────────────────────

def _pct(a: float, b: float) -> float:
    return 0.0 if not b else (a / b - 1.0) * 100.0


async def scan_movers(session: AsyncSession, limit: int = 30) -> dict:
    """Compute price/volume momentum metrics across the universe.

    Returns sorted lists for several categories so the dashboard can show
    'today's strongest moves' without iterating itself.
    """
    stocks = (await session.execute(select(Stock))).scalars().all()
    rows: List[dict] = []
    for st in stocks:
        bars = (
            await session.execute(
                select(DailyPrice)
                .where(DailyPrice.stock_id == st.id)
                .order_by(DailyPrice.date.desc())
                .limit(25)
            )
        ).scalars().all()
        if len(bars) < 6:
            continue
        bars = list(reversed(bars))  # ascending
        last = bars[-1]
        prev = bars[-2]
        gap_pct = _pct(last.open, prev.close)
        d1_pct = _pct(last.close, prev.close)
        d5 = bars[-6] if len(bars) >= 6 else bars[0]
        d20 = bars[0]
        d5_pct = _pct(last.close, d5.close)
        d20_pct = _pct(last.close, d20.close)
        avg_vol = sum(b.volume for b in bars[-21:-1]) / max(1, len(bars[-21:-1]))
        vol_ratio = (last.volume / avg_vol) if avg_vol > 0 else 1.0
        # 20-bar high
        high_20 = max(b.high for b in bars[-21:])
        is_breakout = last.close >= high_20 * 0.999
        rows.append({
            "symbol": st.symbol,
            "name": st.name,
            "last": round(float(last.close), 2),
            "open": round(float(last.open), 2),
            "gap_pct": round(gap_pct, 2),
            "d1_pct": round(d1_pct, 2),
            "d5_pct": round(d5_pct, 2),
            "d20_pct": round(d20_pct, 2),
            "volume": int(last.volume),
            "volume_ratio": round(vol_ratio, 2),
            "breakout_20": bool(is_breakout),
            "date": str(last.date),
        })

    by = lambda key, desc=True: sorted(rows, key=lambda r: r.get(key, 0), reverse=desc)[:limit]
    return {
        "scanned": len(rows),
        "gainers":     by("d1_pct", desc=True),
        "losers":      by("d1_pct", desc=False),
        "gap_ups":     [r for r in by("gap_pct") if r["gap_pct"] > 0][:limit],
        "volume_spikes": by("volume_ratio"),
        "breakouts":   [r for r in rows if r["breakout_20"]][:limit],
        "momentum_5d": by("d5_pct"),
        "momentum_20d": by("d20_pct"),
    }


# ─────────────────────────── Sectors ────────────────────────────

async def scan_sectors(session: AsyncSession) -> dict:
    """Group symbols by sector and summarize 1d / 5d performance."""
    stocks = (await session.execute(select(Stock))).scalars().all()
    by_sector: dict[str, list[dict]] = {}
    for st in stocks:
        sec = st.sector or "未分類"
        bars = (
            await session.execute(
                select(DailyPrice)
                .where(DailyPrice.stock_id == st.id)
                .order_by(DailyPrice.date.desc())
                .limit(6)
            )
        ).scalars().all()
        if len(bars) < 2:
            continue
        bars = list(reversed(bars))
        last = bars[-1]
        prev = bars[-2]
        d5 = bars[0]
        by_sector.setdefault(sec, []).append({
            "symbol": st.symbol,
            "name": st.name,
            "last": round(float(last.close), 2),
            "d1_pct": round(_pct(last.close, prev.close), 2),
            "d5_pct": round(_pct(last.close, d5.close), 2),
        })

    sectors = []
    for sec, members in by_sector.items():
        if not members:
            continue
        avg_d1 = sum(m["d1_pct"] for m in members) / len(members)
        avg_d5 = sum(m["d5_pct"] for m in members) / len(members)
        leaders = sorted(members, key=lambda m: m["d1_pct"], reverse=True)[:3]
        sectors.append({
            "sector": sec,
            "count": len(members),
            "avg_d1_pct": round(avg_d1, 2),
            "avg_d5_pct": round(avg_d5, 2),
            "leaders": leaders,
        })
    sectors.sort(key=lambda s: s["avg_d5_pct"], reverse=True)
    return {"sectors": sectors}
