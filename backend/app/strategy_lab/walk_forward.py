"""Walk-forward analysis runner.

Splits a time series into rolling (IS, OOS) windows. For each window:
  * Train: report on the in-sample slice (just metrics, no fitting since our
    strategies have fixed parameters today — but the surface is ready for
    parameter search later)
  * Test:  run the same strategy on the OOS slice and collect metrics

Aggregates OOS reports into one consolidated `WalkForwardReport`. This is the
*only* thing the validator looks at when deciding whether to promote.

Strict no-lookahead: backtest_engine_v2 already enforces this; we just slice
the data and feed it through.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from strategy.backtest_engine_v2 import BacktestConfig, run_backtest


@dataclass
class WalkSlice:
    is_start: int
    is_end: int
    oos_start: int
    oos_end: int
    oos_trades: int
    oos_win_rate: float
    oos_profit_factor: float
    oos_sharpe: float
    oos_max_drawdown: float
    oos_total_return: float


@dataclass
class WalkForwardReport:
    strategy: str
    symbol: str
    bars: int
    n_windows: int
    oos_total_return: float
    oos_avg_sharpe: float
    oos_avg_profit_factor: float
    oos_max_drawdown: float
    oos_trades: int
    oos_win_rate: float
    slices: List[WalkSlice] = field(default_factory=list)

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


def run_walk_forward(
    bars: List[dict],
    strategy_fn: Callable,
    *,
    strategy_name: str,
    symbol: str,
    is_size: int = 180,
    oos_size: int = 60,
    step: int = 60,
    cfg: Optional[BacktestConfig] = None,
) -> WalkForwardReport:
    cfg = cfg or BacktestConfig()
    n = len(bars)
    slices: List[WalkSlice] = []
    i = 0
    while i + is_size + oos_size <= n:
        is_lo, is_hi = i, i + is_size
        oos_lo, oos_hi = is_hi, is_hi + oos_size
        oos_bars = bars[oos_lo:oos_hi]
        rep = run_backtest(oos_bars, strategy_fn, strategy_name=strategy_name,
                           symbol=symbol, cfg=cfg)
        slices.append(WalkSlice(
            is_start=is_lo, is_end=is_hi,
            oos_start=oos_lo, oos_end=oos_hi,
            oos_trades=rep.trades_count,
            oos_win_rate=rep.win_rate,
            oos_profit_factor=rep.profit_factor,
            oos_sharpe=rep.sharpe,
            oos_max_drawdown=rep.max_drawdown,
            oos_total_return=rep.total_return,
        ))
        i += step

    if not slices:
        return WalkForwardReport(
            strategy=strategy_name, symbol=symbol, bars=n, n_windows=0,
            oos_total_return=0.0, oos_avg_sharpe=0.0,
            oos_avg_profit_factor=0.0, oos_max_drawdown=0.0,
            oos_trades=0, oos_win_rate=0.0, slices=[],
        )

    total_ret = 1.0
    for sl in slices:
        total_ret *= (1.0 + sl.oos_total_return)
    total_ret -= 1.0
    avg_sharpe = sum(s.oos_sharpe for s in slices) / len(slices)
    pf_vals = [s.oos_profit_factor for s in slices if s.oos_profit_factor > 0]
    avg_pf = sum(pf_vals) / len(pf_vals) if pf_vals else 0.0
    worst_dd = min(s.oos_max_drawdown for s in slices)
    total_trades = sum(s.oos_trades for s in slices)
    wins = sum(s.oos_win_rate * s.oos_trades for s in slices)
    win_rate = wins / total_trades if total_trades else 0.0

    return WalkForwardReport(
        strategy=strategy_name, symbol=symbol, bars=n, n_windows=len(slices),
        oos_total_return=round(total_ret, 4),
        oos_avg_sharpe=round(avg_sharpe, 4),
        oos_avg_profit_factor=round(avg_pf, 4),
        oos_max_drawdown=round(worst_dd, 4),
        oos_trades=total_trades,
        oos_win_rate=round(win_rate, 4),
        slices=slices,
    )
