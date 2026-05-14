"""Pairwise correlation between strategies, from real edge_signal outcomes.

Three metrics per pair:
  return_corr     : Pearson correlation of daily realized R series
  drawdown_overlap: fraction of losing-days that overlap
  signal_overlap  : Jaccard similarity of (symbol, date) tuples
                    — high values mean the strategies fire on the same bars

Flagged pairs (any one of):
  return_corr > 0.75
  drawdown_overlap > 0.6
  signal_overlap > 0.5

When two strategies are flagged, the ranker keeps the one with higher
adaptive score and demotes the other to WATCH.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EdgeSignal


HIGH_CORR_THRESHOLD = 0.75
HIGH_DD_OVERLAP = 0.60
HIGH_SIGNAL_OVERLAP = 0.50


@dataclass
class PairCorrelation:
    a: str
    b: str
    return_corr: float
    drawdown_overlap: float
    signal_overlap: float
    flagged: bool
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "a": self.a, "b": self.b,
            "return_corr": round(self.return_corr, 4),
            "drawdown_overlap": round(self.drawdown_overlap, 4),
            "signal_overlap": round(self.signal_overlap, 4),
            "flagged": self.flagged, "reasons": self.reasons,
        }


def _pearson(xs: List[float], ys: List[float]) -> float:
    if len(xs) < 3 or len(xs) != len(ys):
        return 0.0
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    den = math.sqrt(vx * vy)
    return cov / den if den else 0.0


def _daily_r_series(rows: List[EdgeSignal]) -> Dict[date, float]:
    """Average realized R per signal date."""
    by_date: dict[date, List[float]] = defaultdict(list)
    for r in rows:
        if r.realized_r is None:
            continue
        by_date[r.date].append(float(r.realized_r))
    return {d: sum(v) / len(v) for d, v in by_date.items()}


def _align(a: Dict[date, float], b: Dict[date, float]) -> tuple[list[float], list[float]]:
    keys = sorted(set(a.keys()) | set(b.keys()))
    xs, ys = [], []
    for k in keys:
        xs.append(a.get(k, 0.0))
        ys.append(b.get(k, 0.0))
    return xs, ys


def _drawdown_overlap(a: Dict[date, float], b: Dict[date, float]) -> float:
    a_loss = {d for d, v in a.items() if v < 0}
    b_loss = {d for d, v in b.items() if v < 0}
    union = a_loss | b_loss
    if not union:
        return 0.0
    return len(a_loss & b_loss) / len(union)


def _signal_overlap(rows_a: List[EdgeSignal], rows_b: List[EdgeSignal]) -> float:
    a = {(r.symbol, r.date) for r in rows_a}
    b = {(r.symbol, r.date) for r in rows_b}
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


async def correlation_matrix(session: AsyncSession,
                              window_days: int = 90) -> dict:
    cutoff = date.today() - timedelta(days=window_days)
    rows = list((await session.execute(
        select(EdgeSignal)
        .where(EdgeSignal.evaluated == True, EdgeSignal.date >= cutoff)  # noqa: E712
    )).scalars().all())

    by_setup: dict[str, list[EdgeSignal]] = defaultdict(list)
    for r in rows:
        by_setup[r.setup].append(r)
    setups = sorted(by_setup.keys())
    series = {s: _daily_r_series(by_setup[s]) for s in setups}

    pairs: List[PairCorrelation] = []
    for i, a in enumerate(setups):
        for b in setups[i + 1:]:
            xs, ys = _align(series[a], series[b])
            r = _pearson(xs, ys)
            dd = _drawdown_overlap(series[a], series[b])
            sig = _signal_overlap(by_setup[a], by_setup[b])
            reasons: List[str] = []
            if r > HIGH_CORR_THRESHOLD:
                reasons.append(f"return_corr={r:.2f}>{HIGH_CORR_THRESHOLD}")
            if dd > HIGH_DD_OVERLAP:
                reasons.append(f"dd_overlap={dd:.2f}>{HIGH_DD_OVERLAP}")
            if sig > HIGH_SIGNAL_OVERLAP:
                reasons.append(f"signal_overlap={sig:.2f}>{HIGH_SIGNAL_OVERLAP}")
            pairs.append(PairCorrelation(
                a=a, b=b, return_corr=r, drawdown_overlap=dd,
                signal_overlap=sig, flagged=bool(reasons), reasons=reasons,
            ))
    return {
        "window_days": window_days,
        "setups": setups,
        "pairs": [p.to_dict() for p in pairs],
        "flagged_pairs": [p.to_dict() for p in pairs if p.flagged],
    }
