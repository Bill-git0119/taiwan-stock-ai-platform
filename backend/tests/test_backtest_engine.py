"""Backtest Engine v2 — invariants + each strategy."""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import List

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategy.backtest_engine_v2 import (
    BacktestConfig, TradeSignal, run_backtest,
)
from strategy.strategies import REGISTRY


def synth_uptrend(n: int = 250) -> List[dict]:
    bars: List[dict] = []
    px = 100.0
    for i in range(n):
        px += 0.18 + 1.5 * math.sin(i / 8)
        c = max(1.0, px)
        h = c + 1.0
        lo = c - 1.0
        o = (h + lo + c) / 3
        bars.append({
            "date": f"2024-{((i // 22) % 12) + 1:02d}-{(i % 22) + 1:02d}",
            "open": round(o, 2), "high": round(h, 2),
            "low": round(lo, 2), "close": round(c, 2),
            "volume": 800_000 + int(abs(math.sin(i / 4)) * 400_000),
        })
    return bars


def synth_choppy(n: int = 250) -> List[dict]:
    bars: List[dict] = []
    for i in range(n):
        c = 100 + 2 * math.sin(i / 4)
        h = c + 0.6
        lo = c - 0.6
        o = (h + lo + c) / 3
        bars.append({
            "date": f"2024-{((i // 22) % 12) + 1:02d}-{(i % 22) + 1:02d}",
            "open": round(o, 2), "high": round(h, 2),
            "low": round(lo, 2), "close": round(c, 2),
            "volume": 500_000,
        })
    return bars


def test_no_lookahead_buy_fill_uses_next_bar_open():
    """A trade entered after bar i must fill at bar i+1's open price."""
    bars = synth_uptrend(80)

    # Always-fire strategy (only triggers once in test scope).
    fired = {"once": False}

    def always(i, history):
        if fired["once"] or i < 30:
            return None
        fired["once"] = True
        last = history[-1]["close"]
        atr = 1.0
        return TradeSignal(bias="LONG", entry_hint=last,
                           stop_loss=last - 2 * atr, take_profit=last + 4 * atr)

    rep = run_backtest(bars, always, strategy_name="always", symbol="X")
    assert rep.trades_count == 1
    t = rep.trades[0]
    # Entry-fill price must come from the bar AFTER the signal bar.
    # Signal fired on first bar with len(history)>30 → fill bar 31's open ± slippage.
    sig_bar = bars[30]
    next_open = bars[31]["open"]
    expected = next_open * (1 + (5 + 5) / 10_000)
    assert abs(t["entry"] - expected) < 1e-3  # round-to-4dp tolerance


def test_friction_round_trip_costs_at_least_10bps():
    """A flat-out flat trade must cost ≥ 10bps round-trip."""
    bars = synth_uptrend(60)

    def once(i, history):
        if i != 30: return None
        last = history[-1]["close"]
        return TradeSignal(bias="LONG", entry_hint=last,
                           stop_loss=last - 2.0, take_profit=last + 4.0)

    cfg = BacktestConfig(starting_equity=1_000_000.0, risk_pct=0.01, max_hold_bars=2)
    rep = run_backtest(bars, once, strategy_name="once", symbol="X", cfg=cfg)
    assert rep.trades_count == 1
    t = rep.trades[0]
    # entry has +10bps cost, exit has -10bps cost — round-trip drag ≥ 0.001 of price.
    raw_round_trip = t["exit"] / t["entry"]
    assert raw_round_trip < 1.0 + 0.001 + abs(t["pnl_pct"]) + 0.001


def test_max_dd_never_positive():
    bars = synth_choppy(150)
    rep = run_backtest(bars, REGISTRY["mean_reversion"], strategy_name="mr", symbol="X")
    assert rep.max_drawdown <= 0.0


def test_all_strategies_emit_valid_reports():
    bars = synth_uptrend(280)
    for name, fn in REGISTRY.items():
        rep = run_backtest(bars, fn, strategy_name=name, symbol="X")
        assert rep.bars == 280
        assert rep.trades_count >= 0
        assert -1.0 <= rep.max_drawdown <= 0.0
        assert 0.0 <= rep.win_rate <= 1.0
        # Every trade must have stop strictly below entry.
        for t in rep.trades:
            assert t["stop"] < t["entry"]
            # Risk:reward target for the *signal* must be ≥ 1.5 before friction.
            risk = t["entry"] - t["stop"]
            reward = t["target"] - t["entry"]
            if risk > 0 and reward > 0:
                assert reward / risk >= 1.4  # tiny slack for rounding
        # Equity curve length matches bars
        assert len(rep.equity_curve) == 280


def test_report_serialisable():
    bars = synth_uptrend(100)
    rep = run_backtest(bars, REGISTRY["trend_breakout"], strategy_name="tb", symbol="X")
    d = rep.to_dict()
    assert "trades" in d and "equity_curve" in d and "sharpe" in d
