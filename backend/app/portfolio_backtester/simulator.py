"""Portfolio simulator — run multiple strategies concurrently on shared bars.

Each strategy is risk-budgeted (default 1% per trade) and constrained by
`max_concurrent_positions`. The simulator never opens more concurrent
positions than that cap, regardless of how many signals fire.

Output:
  equity_curve         : List[float]
  total_return         : pct
  sharpe               : annualised
  max_drawdown         : worst peak→trough
  portfolio_trades     : count
  by_strategy          : per-strategy breakdown
  exposure_heat        : timeseries of concurrent-position count

Lookahead-free: each strategy fires at bar i, fills at bar i+1 open with
slippage, identical to backtest_engine_v2.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


SLIPPAGE_BPS = 5.0
COMMISSION_BPS = 5.0


@dataclass
class _OpenPos:
    strategy: str
    entry_idx: int
    entry: float
    stop_loss: float
    take_profit: float
    risk_per_share: float
    shares: int


@dataclass
class PortfolioReport:
    strategies: List[str]
    bars: int
    portfolio_trades: int
    total_return: float
    sharpe: float
    max_drawdown: float
    equity_curve: List[float]
    by_strategy: Dict[str, dict]
    exposure_heat: List[int]

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


def run_portfolio(
    bars: List[dict],
    strategies: Dict[str, Callable],
    *,
    starting_equity: float = 1_000_000.0,
    risk_pct_per_trade: float = 0.01,
    max_concurrent_positions: int = 3,
    max_hold_bars: int = 12,
) -> PortfolioReport:
    n = len(bars)
    if n < 20:
        return PortfolioReport(
            strategies=list(strategies.keys()), bars=n, portfolio_trades=0,
            total_return=0.0, sharpe=0.0, max_drawdown=0.0,
            equity_curve=[starting_equity] * n,
            by_strategy={k: {"trades": 0} for k in strategies},
            exposure_heat=[0] * n,
        )

    equity = starting_equity
    eq_curve: List[float] = []
    heat: List[int] = []
    peak = starting_equity
    max_dd = 0.0
    open_positions: List[_OpenPos] = []
    by_strat: Dict[str, dict] = {k: {"trades": 0, "wins": 0, "losses": 0,
                                       "pnl_sum": 0.0} for k in strategies}
    portfolio_trade_count = 0

    for i in range(n):
        bar = bars[i]
        # 1. Close positions whose SL/TP hit on this bar
        still_open: List[_OpenPos] = []
        for pos in open_positions:
            hi, lo, cl = float(bar["high"]), float(bar["low"]), float(bar["close"])
            # SL first (pessimistic)
            if lo <= pos.stop_loss:
                exit_p = pos.stop_loss * (1 - COMMISSION_BPS / 10_000)
                pnl = (exit_p - pos.entry) * pos.shares
                equity += pnl
                by_strat[pos.strategy]["trades"] += 1
                by_strat[pos.strategy]["losses"] += 1
                by_strat[pos.strategy]["pnl_sum"] += pnl
                portfolio_trade_count += 1
            elif hi >= pos.take_profit:
                exit_p = pos.take_profit * (1 - COMMISSION_BPS / 10_000)
                pnl = (exit_p - pos.entry) * pos.shares
                equity += pnl
                by_strat[pos.strategy]["trades"] += 1
                by_strat[pos.strategy]["wins"] += 1
                by_strat[pos.strategy]["pnl_sum"] += pnl
                portfolio_trade_count += 1
            elif i - pos.entry_idx >= max_hold_bars:
                exit_p = cl * (1 - COMMISSION_BPS / 10_000)
                pnl = (exit_p - pos.entry) * pos.shares
                equity += pnl
                by_strat[pos.strategy]["trades"] += 1
                if pnl > 0:
                    by_strat[pos.strategy]["wins"] += 1
                else:
                    by_strat[pos.strategy]["losses"] += 1
                by_strat[pos.strategy]["pnl_sum"] += pnl
                portfolio_trade_count += 1
            else:
                still_open.append(pos)
        open_positions = still_open

        # 2. Generate signals (only if we have a next bar to fill on)
        if i + 1 < n and len(open_positions) < max_concurrent_positions:
            history = bars[: i + 1]
            for sname, fn in strategies.items():
                if len(open_positions) >= max_concurrent_positions:
                    break
                try:
                    sig = fn(i, history)
                except Exception:
                    sig = None
                if sig is None or sig.bias != "LONG":
                    continue
                fill_bar = bars[i + 1]
                fill_price = float(fill_bar["open"]) * (1 + (SLIPPAGE_BPS + COMMISSION_BPS) / 10_000)
                risk = fill_price - sig.stop_loss
                if risk <= 0:
                    continue
                shares = int((equity * risk_pct_per_trade) // risk)
                if shares <= 0:
                    continue
                open_positions.append(_OpenPos(
                    strategy=sname, entry_idx=i + 1, entry=fill_price,
                    stop_loss=sig.stop_loss, take_profit=sig.take_profit,
                    risk_per_share=risk, shares=shares,
                ))

        eq_curve.append(equity)
        heat.append(len(open_positions))
        peak = max(peak, equity)
        dd = (equity - peak) / peak if peak else 0
        max_dd = min(max_dd, dd)

    total_ret = (equity / starting_equity) - 1.0
    # Sharpe — simple daily-return approx
    rets: List[float] = []
    for k in range(1, len(eq_curve)):
        r = eq_curve[k] / eq_curve[k - 1] - 1 if eq_curve[k - 1] else 0
        rets.append(r)
    if rets and any(rets):
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / max(1, len(rets) - 1)
        sd = math.sqrt(var) if var > 0 else 0
        sharpe = (mean / sd) * math.sqrt(252) if sd else 0.0
    else:
        sharpe = 0.0

    return PortfolioReport(
        strategies=list(strategies.keys()),
        bars=n, portfolio_trades=portfolio_trade_count,
        total_return=round(total_ret, 6),
        sharpe=round(sharpe, 4),
        max_drawdown=round(max_dd, 4),
        equity_curve=[round(e, 2) for e in eq_curve],
        by_strategy=by_strat,
        exposure_heat=heat,
    )
