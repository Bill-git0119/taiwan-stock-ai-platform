"""Edge decay — recent vs older expectancy comparison.

If recent expectancy is materially worse than long-window expectancy, the
edge is decaying — the strategy ranker downweights it. A strongly negative
decay score is itself grounds for production_status = WATCH or DISABLED.

Score formula:
    decay = recent_expectancy - older_expectancy
    decay_pct = (recent - older) / max(|older|, 0.01)

  decay >  0.1   →  improving
  decay >= -0.1  →  stable
  decay <  -0.1  →  decaying  (downweight)
  decay <  -0.3  →  broken    (auto-disable candidate)
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EdgeSignal


def _expectancy(rows: List[EdgeSignal]) -> float:
    wins = [s for s in rows if s.win is True]
    losses = [s for s in rows if s.win is False]
    n = len(wins) + len(losses)
    if n == 0:
        return 0.0
    win_rs = [s.realized_r for s in wins if s.realized_r is not None]
    loss_rs = [s.realized_r for s in losses if s.realized_r is not None]
    win_rate = len(wins) / n
    avg_win = sum(win_rs) / len(win_rs) if win_rs else 0.0
    avg_loss = abs(sum(loss_rs) / len(loss_rs)) if loss_rs else 0.0
    return win_rate * avg_win - (1 - win_rate) * avg_loss


async def decay_scores(session: AsyncSession,
                       recent_days: int = 30,
                       older_days: int = 90) -> Dict[str, dict]:
    cutoff_old = date.today() - timedelta(days=older_days)
    cutoff_recent = date.today() - timedelta(days=recent_days)
    rows = list((await session.execute(
        select(EdgeSignal)
        .where(EdgeSignal.evaluated == True, EdgeSignal.date >= cutoff_old)  # noqa: E712
    )).scalars().all())

    by_setup: dict[str, list[EdgeSignal]] = defaultdict(list)
    for s in rows:
        by_setup[s.setup].append(s)

    out: Dict[str, dict] = {}
    for setup, items in by_setup.items():
        recent = [s for s in items if s.date >= cutoff_recent]
        older = [s for s in items if s.date < cutoff_recent]
        rec_exp = _expectancy(recent)
        old_exp = _expectancy(older) if older else rec_exp
        denom = max(abs(old_exp), 0.01)
        decay = rec_exp - old_exp
        decay_pct = decay / denom
        if decay >= 0.1:
            label = "improving"
        elif decay >= -0.1:
            label = "stable"
        elif decay >= -0.3:
            label = "decaying"
        else:
            label = "broken"
        out[setup] = {
            "recent_expectancy_R": round(rec_exp, 4),
            "older_expectancy_R": round(old_exp, 4),
            "decay": round(decay, 4),
            "decay_pct": round(decay_pct, 4),
            "label": label,
            "recent_n": len(recent),
            "older_n": len(older),
        }
    return out
