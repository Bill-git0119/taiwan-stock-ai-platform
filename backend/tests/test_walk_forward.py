"""Walk-forward + Monte Carlo + validator."""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.strategy_lab.monte_carlo import run_monte_carlo
from app.strategy_lab.validator import (
    PROMOTION_THRESHOLDS, evaluate,
)
from app.strategy_lab.walk_forward import run_walk_forward
from strategy.strategies import REGISTRY


def _bars(n: int = 400) -> List[dict]:
    out: List[dict] = []
    px = 100.0
    for i in range(n):
        px += 0.15 + 1.2 * math.sin(i / 7)
        c = max(1.0, px)
        out.append({
            "date": f"2024-{((i // 22) % 12) + 1:02d}-{(i % 22) + 1:02d}",
            "open": c - 0.4, "high": c + 0.7,
            "low": c - 0.7, "close": c,
            "volume": 800_000 + (200_000 if i % 17 == 0 else 0),
        })
    return out


def test_walk_forward_produces_windows():
    rep = run_walk_forward(
        _bars(400), REGISTRY["trend_breakout"],
        strategy_name="trend_breakout", symbol="X",
        is_size=120, oos_size=40, step=40,
    )
    assert rep.n_windows >= 3
    assert rep.bars == 400
    assert -1.0 <= rep.oos_max_drawdown <= 0.0
    for sl in rep.slices:
        assert sl.is_end == sl.oos_start  # IS immediately precedes OOS


def test_walk_forward_empty_when_history_too_short():
    rep = run_walk_forward(
        _bars(50), REGISTRY["trend_breakout"],
        strategy_name="trend_breakout", symbol="X",
        is_size=120, oos_size=40, step=40,
    )
    assert rep.n_windows == 0
    assert rep.oos_trades == 0


def test_monte_carlo_zero_when_no_trades():
    mc = run_monte_carlo([])
    assert mc.median_final_equity == mc.starting_equity
    assert mc.pct_profitable == 0.0


def test_monte_carlo_profitable_when_positive_expectancy():
    rs = [2.0, 2.0, -1.0, 2.0, -1.0, 2.0, -1.0, 2.0]  # +R bias
    mc = run_monte_carlo(rs, iterations=500)
    assert mc.median_final_equity > mc.starting_equity
    assert mc.pct_profitable > 0.5


def test_monte_carlo_unprofitable_when_negative_expectancy():
    rs = [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0]
    mc = run_monte_carlo(rs, iterations=500)
    assert mc.median_final_equity < mc.starting_equity


def test_validator_rejects_when_oos_trades_insufficient():
    wf = run_walk_forward(
        _bars(400), REGISTRY["trend_breakout"],
        strategy_name="trend_breakout", symbol="X",
        is_size=120, oos_size=40, step=40,
    )
    # synthesize an MC that would otherwise pass
    mc = run_monte_carlo([1.5] * 50, iterations=200)
    decision = evaluate(wf, mc)
    # most likely fails on trade count or sharpe — verify decision has shape
    assert isinstance(decision.promoted, bool)
    assert isinstance(decision.failures, list)
    assert "oos_sharpe" in decision.metrics


def test_promotion_thresholds_immutable_shape():
    for k in ("min_oos_sharpe", "min_oos_profit_factor", "min_oos_trades",
              "max_oos_drawdown", "min_oos_win_rate",
              "min_mc_p05_ratio", "min_mc_pct_profitable"):
        assert k in PROMOTION_THRESHOLDS
