"""End-to-end strategy lab runner.

Pulls bars from DB → walk-forward → Monte Carlo → promotion decision.
Maintains a tiny in-memory `PROMOTED_STRATEGIES` set that the scanner can
consult to decide whether a setup is allowed to fire today.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DailyPrice, Stock
from app.strategy_lab.monte_carlo import MonteCarloReport, run_monte_carlo
from app.strategy_lab.validator import PromotionDecision, evaluate
from app.strategy_lab.walk_forward import WalkForwardReport, run_walk_forward
from strategy.strategies import REGISTRY

log = logging.getLogger("strategy_lab")

# Live promotion registry — only entries here are allowed to push signals.
# Populated by `run_lab_all_symbols` and persisted in process memory.
PROMOTED_STRATEGIES: Dict[str, dict] = {}


async def _load_bars(session: AsyncSession, symbol: str) -> List[dict]:
    stock = (
        await session.execute(select(Stock).where(Stock.symbol == symbol))
    ).scalar_one_or_none()
    if stock is None:
        return []
    rows = (
        await session.execute(
            select(DailyPrice).where(DailyPrice.stock_id == stock.id)
            .order_by(DailyPrice.date.asc())
        )
    ).scalars().all()
    return [{"date": str(r.date), "open": r.open, "high": r.high,
             "low": r.low, "close": r.close, "volume": r.volume} for r in rows]


async def run_lab(
    session: AsyncSession,
    symbol: str,
    *,
    strategy_name: Optional[str] = None,
    is_size: int = 120,
    oos_size: int = 30,
    step: int = 30,
) -> dict:
    bars = await _load_bars(session, symbol)
    if len(bars) < is_size + oos_size:
        return {"ok": False, "reason": "insufficient_history",
                "bars": len(bars), "need": is_size + oos_size}
    names = [strategy_name] if strategy_name else list(REGISTRY.keys())
    out: Dict[str, dict] = {}
    for name in names:
        fn = REGISTRY.get(name)
        if fn is None:
            continue
        wf: WalkForwardReport = run_walk_forward(
            bars, fn, strategy_name=name, symbol=symbol,
            is_size=is_size, oos_size=oos_size, step=step,
        )
        realised: List[float] = []
        # rebuild realised Rs from each window's run
        for sl in wf.slices:
            avg_r = sl.oos_total_return * 50 if sl.oos_trades else 0
            for _ in range(sl.oos_trades):
                realised.append(avg_r / max(1, sl.oos_trades))
        mc: MonteCarloReport = run_monte_carlo(realised)
        decision: PromotionDecision = evaluate(wf, mc)
        if decision.promoted:
            PROMOTED_STRATEGIES[name] = {
                "symbol": symbol,
                "metrics": decision.metrics,
            }
        out[name] = {
            "walk_forward": wf.to_dict(),
            "monte_carlo": mc.to_dict(),
            "decision": decision.to_dict(),
        }
    return {"ok": True, "symbol": symbol, "bars": len(bars), "results": out}


def is_promoted(strategy_name: str) -> bool:
    return strategy_name in PROMOTED_STRATEGIES
