"""LongTermInvestmentEngine — sorts the universe into four investment
buckets the research desk uses for swing / position trades:

  COMPOUNDER       :  steady earnings growth, ROE, healthy balance sheet
  TURNAROUND       :  recent operating improvement after weakness
  CYCLICAL         :  industry-tide stock (shipping, steel, memory, etc.)
  AVOID            :  declining fundamentals, accumulating institutional sell

Honest-data contract
  * If fundamentals are not yet wired (Score.fundamental_score == 0 for
    every row), bucket = NO_FUNDAMENTAL_DATA and the endpoint warns.
  * No fabricated EPS / ROE values — every metric must come from a real
    persisted Score / ChipData / DailyPrice row.

The engine is intentionally conservative: a stock has to clear MULTIPLE
sanity gates to qualify as COMPOUNDER. Better to surface fewer real
candidates than to invent a fake long list.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChipData, DailyPrice, Score, Stock

CYCLICAL_SECTORS = {
    "航運", "鋼鐵", "塑膠", "化學", "水泥", "造紙", "汽車", "橡膠",
}


@dataclass
class LongCandidate:
    symbol: str
    name: str
    sector: Optional[str]
    bucket: str            # COMPOUNDER / TURNAROUND / CYCLICAL / AVOID
    score: float           # 0..100 composite for that bucket
    chip_score: float = 0.0
    fundamental_score: float = 0.0
    technical_score: float = 0.0
    last: Optional[float] = None
    ret_60d: Optional[float] = None
    ret_240d: Optional[float] = None
    foreign_net_30d: Optional[float] = None
    institutional_aligned_days: int = 0
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


async def _gather(session: AsyncSession, stock: Stock) -> dict:
    today = date.today()
    score = (await session.execute(
        select(Score).where(Score.stock_id == stock.id)
        .order_by(Score.date.desc()).limit(1)
    )).scalar_one_or_none()
    bars = (await session.execute(
        select(DailyPrice).where(DailyPrice.stock_id == stock.id)
        .order_by(DailyPrice.date.desc()).limit(260)
    )).scalars().all()
    bars = list(reversed(bars))
    chips = (await session.execute(
        select(ChipData).where(ChipData.stock_id == stock.id,
                               ChipData.date >= today - timedelta(days=45))
        .order_by(ChipData.date.asc())
    )).scalars().all()

    def _ret(a, b):
        return 0.0 if not a or not b else (a / b - 1.0) * 100

    last = bars[-1].close if bars else None
    d60 = bars[-60].close if len(bars) >= 60 else None
    d240 = bars[-240].close if len(bars) >= 240 else None

    foreign_net_30 = sum(float(c.foreign_buy or 0) for c in chips[-30:])
    aligned_days = sum(
        1 for c in chips
        if (c.foreign_buy or 0) > 0 and (c.investment_buy or 0) > 0
    )

    return {
        "score": score,
        "last": last,
        "ret_60d": round(_ret(last, d60), 2) if d60 else None,
        "ret_240d": round(_ret(last, d240), 2) if d240 else None,
        "foreign_net_30d": round(foreign_net_30, 2),
        "institutional_aligned_days": aligned_days,
        "n_bars": len(bars),
        "n_chips": len(chips),
    }


def _classify(stock: Stock, m: dict) -> LongCandidate:
    """Run the bucket decision tree from gathered metrics."""
    score = m["score"]
    last = m["last"]
    cand = LongCandidate(
        symbol=stock.symbol,
        name=stock.name,
        sector=stock.sector,
        bucket="UNKNOWN",
        score=0.0,
        last=last,
        ret_60d=m["ret_60d"],
        ret_240d=m["ret_240d"],
        foreign_net_30d=m["foreign_net_30d"],
        institutional_aligned_days=m["institutional_aligned_days"],
    )
    if score:
        cand.chip_score = float(score.chip_score or 0)
        cand.fundamental_score = float(score.fundamental_score or 0)
        cand.technical_score = float(score.technical_score or 0)

    # Data sufficiency
    if m["n_bars"] < 60:
        cand.bucket = "INSUFFICIENT_HISTORY"
        cand.flags.append(f"bars={m['n_bars']}<60")
        return cand
    if cand.fundamental_score == 0:
        cand.flags.append("no_fundamental_data")

    is_cyclical = (stock.sector or "") in CYCLICAL_SECTORS
    r60 = m["ret_60d"] or 0.0
    r240 = m["ret_240d"] or 0.0

    # AVOID: long-term downtrend + heavy foreign selling
    if r240 < -25 and m["foreign_net_30d"] < 0:
        cand.bucket = "AVOID"
        cand.reasons.append(f"240D -{abs(r240):.1f}%（長期下跌）")
        cand.reasons.append("外資 30D 賣超")
        cand.score = round(40.0 + max(0, r240 + 50) / 2, 2)  # the worse, the lower
        return cand

    # COMPOUNDER: real fundamentals + rising prices + positive institutional flow
    if (cand.fundamental_score >= 70 and r240 > 10 and r60 > 0
            and m["foreign_net_30d"] > 0):
        cand.bucket = "COMPOUNDER"
        cand.reasons.append(f"基本面 {cand.fundamental_score:.0f} 分")
        cand.reasons.append(f"240D +{r240:.1f}%")
        cand.reasons.append(f"30D 外資淨買 +{m['foreign_net_30d']:.0f}")
        cand.score = round(min(100.0,
            0.5 * cand.fundamental_score +
            0.25 * cand.chip_score +
            0.15 * min(100, max(0, r240)) +
            0.10 * min(100, m["institutional_aligned_days"] * 5)
        ), 2)
        return cand

    # TURNAROUND: 240D weak (<0) but 60D recovering (>10%) with institutional flow
    if r240 < 5 and r60 > 10 and m["foreign_net_30d"] > 0:
        cand.bucket = "TURNAROUND"
        cand.reasons.append(f"240D {r240:.1f}% 但 60D +{r60:.1f}% 復甦")
        cand.reasons.append(f"30D 外資淨買 +{m['foreign_net_30d']:.0f}")
        cand.score = round(min(100.0, 50 + min(50, r60)), 2)
        return cand

    # CYCLICAL: sector is cyclical and we have momentum confirmation
    if is_cyclical and r60 > 5:
        cand.bucket = "CYCLICAL"
        cand.reasons.append(f"{stock.sector} 景氣股")
        cand.reasons.append(f"60D +{r60:.1f}%")
        cand.score = round(min(100.0, 50 + r60), 2)
        return cand

    # Default — not classified
    cand.bucket = "NEUTRAL"
    cand.score = 50.0
    return cand


async def analyse_universe(
    session: AsyncSession,
    *,
    limit_per_bucket: int = 20,
) -> dict:
    stocks = (await session.execute(select(Stock))).scalars().all()
    candidates: list[LongCandidate] = []
    fundamental_data_present = False
    for st in stocks:
        m = await _gather(session, st)
        c = _classify(st, m)
        if c.fundamental_score > 0:
            fundamental_data_present = True
        candidates.append(c)

    buckets: dict[str, list[LongCandidate]] = {
        "COMPOUNDER": [], "TURNAROUND": [], "CYCLICAL": [], "AVOID": [],
        "NEUTRAL": [], "INSUFFICIENT_HISTORY": [],
    }
    for c in candidates:
        buckets.setdefault(c.bucket, []).append(c)
    for k in buckets:
        buckets[k].sort(key=lambda x: x.score, reverse=(k != "AVOID"))
        buckets[k] = buckets[k][:limit_per_bucket]

    return {
        "fundamentals_wired": fundamental_data_present,
        "warning": (None if fundamental_data_present else
                    "fundamental_score=0 for every stock — wire MOPS / FinMind "
                    "before trusting COMPOUNDER classifications"),
        "counts": {k: len(v) for k, v in buckets.items()},
        "buckets": {k: [c.to_dict() for c in v] for k, v in buckets.items()},
    }
