"""Edge persistence — how long does the edge survive?

Three metrics per setup:
  rolling_expectancy : ordered (date, expectancy_R) over the last `window_days`
                       computed using a sliding 14-day window of evaluated signals
  half_life_days     : if the rolling series fits an exponential decay
                       expectancy(t) = E0 * exp(-t / tau), then half-life = tau*ln(2).
                       returned as None when curve is improving or flat.
  decay_velocity     : (expectancy_last7 - expectancy_first7) / weeks_span
                       negative = decaying, positive = improving
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EdgeSignal


def _expectancy_for_window(rows: List[EdgeSignal]) -> float:
    wins = [r for r in rows if r.win is True]
    losses = [r for r in rows if r.win is False]
    n = len(wins) + len(losses)
    if n == 0:
        return 0.0
    win_rs = [r.realized_r for r in wins if r.realized_r is not None]
    loss_rs = [r.realized_r for r in losses if r.realized_r is not None]
    win_rate = len(wins) / n
    avg_win = sum(win_rs) / len(win_rs) if win_rs else 0
    avg_loss = abs(sum(loss_rs) / len(loss_rs)) if loss_rs else 0
    return win_rate * avg_win - (1 - win_rate) * avg_loss


def _rolling_expectancy(rows: List[EdgeSignal], window: int = 14) -> List[dict]:
    if not rows:
        return []
    rows_sorted = sorted(rows, key=lambda r: r.date)
    by_day: dict[date, list[EdgeSignal]] = defaultdict(list)
    for r in rows_sorted:
        by_day[r.date].append(r)
    days = sorted(by_day.keys())
    out: List[dict] = []
    for i, d in enumerate(days):
        lo = max(0, i - window + 1)
        bucket: List[EdgeSignal] = []
        for j in range(lo, i + 1):
            bucket.extend(by_day[days[j]])
        out.append({"date": str(d), "expectancy_R": round(_expectancy_for_window(bucket), 4),
                    "sample": len(bucket)})
    return out


def _half_life_days(series: List[dict]) -> float | None:
    """Fit y = a * exp(-t / tau) to (t, expectancy) where expectancy > 0.
    Returns ln(2) * tau when fit produces a positive tau, else None.
    """
    if len(series) < 6:
        return None
    pts = [(i, s["expectancy_R"]) for i, s in enumerate(series) if s["expectancy_R"] > 0]
    if len(pts) < 5:
        return None
    xs = [p[0] for p in pts]
    ys = [math.log(p[1]) for p in pts]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    den = sum((xs[i] - mx) ** 2 for i in range(n))
    if den == 0:
        return None
    slope = num / den
    if slope >= -1e-6:
        return None  # not decaying
    tau = -1.0 / slope
    return round(math.log(2) * tau, 2)


async def persistence_report(session: AsyncSession,
                              window_days: int = 90) -> Dict[str, dict]:
    cutoff = date.today() - timedelta(days=window_days)
    rows = list((await session.execute(
        select(EdgeSignal)
        .where(EdgeSignal.evaluated == True, EdgeSignal.date >= cutoff)  # noqa: E712
    )).scalars().all())
    by: dict[str, list[EdgeSignal]] = defaultdict(list)
    for r in rows:
        by[r.setup].append(r)

    out: Dict[str, dict] = {}
    for setup, items in by.items():
        series = _rolling_expectancy(items, window=14)
        hl = _half_life_days(series)
        if series:
            head = series[: max(1, len(series) // 7)]
            tail = series[-max(1, len(series) // 7):]
            head_avg = sum(p["expectancy_R"] for p in head) / len(head)
            tail_avg = sum(p["expectancy_R"] for p in tail) / len(tail)
            weeks_span = max(1, len(series) // 7)
            velocity = round((tail_avg - head_avg) / weeks_span, 4)
        else:
            velocity = 0.0
        out[setup] = {
            "half_life_days": hl,
            "decay_velocity": velocity,
            "rolling_expectancy": series,
            "sample_size": len(items),
        }
    return out
