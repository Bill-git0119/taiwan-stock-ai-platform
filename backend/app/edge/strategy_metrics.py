"""Strategy metrics — real-performance aggregations over evaluated edge_signals.

Every function reads ONLY from `edge_signals` rows where `evaluated=True`.
No backtest data is ever mixed in. Period.

All breakdowns share the same R-unit math:
    win_rate          = wins / (wins + losses)
    avg_R             = mean realized_r
    avg_win_R         = mean realized_r where realized_r > 0
    avg_loss_R        = mean realized_r where realized_r < 0
    profit_factor     = sum(win_R) / |sum(loss_R)|
    expectancy_R      = win_rate * avg_win_R - (1 - win_rate) * |avg_loss_R|
    max_consec_loss   = longest losing run by signal date
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EdgeSignal


def _agg(items: List[EdgeSignal]) -> dict:
    wins = [s for s in items if s.win is True]
    losses = [s for s in items if s.win is False]
    n_eval = len(wins) + len(losses)
    if n_eval == 0:
        return {
            "sample_size": 0, "win_rate": 0.0, "avg_R": 0.0,
            "profit_factor": 0.0, "expectancy_R": 0.0,
            "max_consec_loss": 0, "avg_mfe_R": 0.0, "avg_mae_R": 0.0,
            "avg_bars_held": 0.0,
        }
    win_rs = [s.realized_r for s in wins if s.realized_r is not None]
    loss_rs = [s.realized_r for s in losses if s.realized_r is not None]
    all_rs = [s.realized_r for s in items if s.realized_r is not None]
    win_rate = len(wins) / n_eval
    avg_R = sum(all_rs) / len(all_rs) if all_rs else 0.0
    avg_win_R = sum(win_rs) / len(win_rs) if win_rs else 0.0
    avg_loss_R = sum(loss_rs) / len(loss_rs) if loss_rs else 0.0
    sum_win = sum(win_rs)
    sum_loss = abs(sum(loss_rs)) or 0.001
    pf = sum_win / sum_loss if sum_loss else 0.0
    expectancy = win_rate * avg_win_R - (1 - win_rate) * abs(avg_loss_R)

    # max consecutive loss by date
    items_sorted = sorted(items, key=lambda s: s.date)
    cur = mx = 0
    for s in items_sorted:
        if s.win is False:
            cur += 1
            mx = max(mx, cur)
        else:
            cur = 0

    mfe = [s.mfe_r for s in items if s.mfe_r is not None]
    mae = [s.mae_r for s in items if s.mae_r is not None]
    bars_kept = [s.bars_held for s in items if s.bars_held is not None]
    return {
        "sample_size": n_eval,
        "win_rate": round(win_rate, 4),
        "avg_R": round(avg_R, 4),
        "profit_factor": round(pf, 4),
        "expectancy_R": round(expectancy, 4),
        "max_consec_loss": int(mx),
        "avg_mfe_R": round(sum(mfe) / len(mfe), 4) if mfe else 0.0,
        "avg_mae_R": round(sum(mae) / len(mae), 4) if mae else 0.0,
        "avg_bars_held": round(sum(bars_kept) / len(bars_kept), 2) if bars_kept else 0.0,
    }


async def _evaluated_window(session: AsyncSession,
                            window_days: int) -> List[EdgeSignal]:
    cutoff = date.today() - timedelta(days=window_days)
    return list((await session.execute(
        select(EdgeSignal)
        .where(EdgeSignal.evaluated == True, EdgeSignal.date >= cutoff)  # noqa: E712
    )).scalars().all())


async def overall(session: AsyncSession, window_days: int = 30) -> dict:
    items = await _evaluated_window(session, window_days)
    return _agg(items)


async def by_setup(session: AsyncSession, window_days: int = 30) -> Dict[str, dict]:
    items = await _evaluated_window(session, window_days)
    by: dict[str, list[EdgeSignal]] = defaultdict(list)
    for s in items:
        by[s.setup].append(s)
    return {k: _agg(v) for k, v in by.items()}


async def by_regime(session: AsyncSession, window_days: int = 30) -> Dict[str, dict]:
    items = await _evaluated_window(session, window_days)
    by: dict[str, list[EdgeSignal]] = defaultdict(list)
    for s in items:
        by[s.regime or "unknown"].append(s)
    return {k: _agg(v) for k, v in by.items()}


async def by_sector(session: AsyncSession, window_days: int = 30) -> Dict[str, dict]:
    items = await _evaluated_window(session, window_days)
    by: dict[str, list[EdgeSignal]] = defaultdict(list)
    for s in items:
        by[s.sector or "其他"].append(s)
    return {k: _agg(v) for k, v in by.items()}


async def setup_x_regime(session: AsyncSession, window_days: int = 90) -> Dict[str, Dict[str, dict]]:
    """2D grid: stats[setup][regime] = {win_rate, expectancy_R, ...}.

    Used to enforce "this setup only works in this regime" gating.
    """
    items = await _evaluated_window(session, window_days)
    by: dict[str, dict[str, list[EdgeSignal]]] = defaultdict(lambda: defaultdict(list))
    for s in items:
        by[s.setup][s.regime or "unknown"].append(s)
    return {setup: {reg: _agg(rows) for reg, rows in regs.items()}
            for setup, regs in by.items()}
