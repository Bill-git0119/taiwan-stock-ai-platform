"""Promotion gate — turns walk-forward + Monte Carlo into a yes/no decision.

A strategy must pass *all* of these to be promoted. Nothing else is allowed
to fire signals on production.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from app.strategy_lab.monte_carlo import MonteCarloReport
from app.strategy_lab.walk_forward import WalkForwardReport


PROMOTION_THRESHOLDS = {
    "min_oos_sharpe": 0.8,
    "min_oos_profit_factor": 1.3,
    "min_oos_trades": 30,
    "max_oos_drawdown": -0.25,        # OOS DD floor (=-25%)
    "min_oos_win_rate": 0.40,
    "min_mc_p05_ratio": 1.0,           # 5%-worst final / starting
    "min_mc_pct_profitable": 0.60,
}


@dataclass
class PromotionDecision:
    promoted: bool
    failures: List[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


def evaluate(wf: WalkForwardReport, mc: MonteCarloReport) -> PromotionDecision:
    fail: List[str] = []
    if wf.oos_trades < PROMOTION_THRESHOLDS["min_oos_trades"]:
        fail.append(f"oos_trades={wf.oos_trades} < {PROMOTION_THRESHOLDS['min_oos_trades']}")
    if wf.oos_avg_sharpe < PROMOTION_THRESHOLDS["min_oos_sharpe"]:
        fail.append(f"oos_sharpe={wf.oos_avg_sharpe} < {PROMOTION_THRESHOLDS['min_oos_sharpe']}")
    if wf.oos_avg_profit_factor < PROMOTION_THRESHOLDS["min_oos_profit_factor"]:
        fail.append(f"oos_pf={wf.oos_avg_profit_factor} < {PROMOTION_THRESHOLDS['min_oos_profit_factor']}")
    if wf.oos_max_drawdown < PROMOTION_THRESHOLDS["max_oos_drawdown"]:
        fail.append(f"oos_dd={wf.oos_max_drawdown} < {PROMOTION_THRESHOLDS['max_oos_drawdown']}")
    if wf.oos_win_rate < PROMOTION_THRESHOLDS["min_oos_win_rate"]:
        fail.append(f"oos_winrate={wf.oos_win_rate} < {PROMOTION_THRESHOLDS['min_oos_win_rate']}")
    if mc.n_trades > 0:
        ratio = mc.p05_final_equity / mc.starting_equity
        if ratio < PROMOTION_THRESHOLDS["min_mc_p05_ratio"]:
            fail.append(f"mc_p05_ratio={round(ratio,3)} < {PROMOTION_THRESHOLDS['min_mc_p05_ratio']}")
        if mc.pct_profitable < PROMOTION_THRESHOLDS["min_mc_pct_profitable"]:
            fail.append(f"mc_pct_profitable={mc.pct_profitable} < {PROMOTION_THRESHOLDS['min_mc_pct_profitable']}")

    metrics = {
        "oos_trades": wf.oos_trades,
        "oos_sharpe": wf.oos_avg_sharpe,
        "oos_profit_factor": wf.oos_avg_profit_factor,
        "oos_max_drawdown": wf.oos_max_drawdown,
        "oos_win_rate": wf.oos_win_rate,
        "oos_total_return": wf.oos_total_return,
        "mc_p05_final_equity": mc.p05_final_equity,
        "mc_median_final_equity": mc.median_final_equity,
        "mc_pct_profitable": mc.pct_profitable,
    }
    return PromotionDecision(promoted=not fail, failures=fail, metrics=metrics)
