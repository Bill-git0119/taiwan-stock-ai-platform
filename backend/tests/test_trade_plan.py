"""Trade plan engine — iron-rule + structure tests."""
from __future__ import annotations

import math

import pytest

from app.services.trade_plan_engine import build_plan, MIN_RR


def _trend_up(n: int = 120):
    closes, highs, lows, vols = [], [], [], []
    px = 100.0
    for i in range(n):
        px += 0.4 + 0.6 * math.sin(i / 7)
        c = px
        h = c + 0.6
        lo = c - 0.6
        closes.append(c); highs.append(h); lows.append(lo)
        vols.append(800_000 + (200_000 if i == n - 1 else 0))
    # Force breakout on last bar
    closes[-1] = max(closes[:-1]) * 1.03
    highs[-1] = closes[-1] + 0.6
    return closes, highs, lows, vols


def _flat(n: int = 120):
    closes = [100 + math.sin(i / 7) * 0.5 for i in range(n)]
    highs = [c + 0.3 for c in closes]
    lows = [c - 0.3 for c in closes]
    vols = [500_000] * n
    return closes, highs, lows, vols


def test_no_trade_on_short_history():
    plan = build_plan("X", closes=[100, 101, 102])
    assert plan.bias == "NO_TRADE"
    assert plan.no_trade_reason == "insufficient_history"


def test_long_setup_on_breakout_trend():
    c, h, l, v = _trend_up()
    plan = build_plan("UP", closes=c, highs=h, lows=l, volumes=v, account_size=1_000_000)
    # Could be NO_TRADE if RR < 1.5; otherwise must satisfy iron rules.
    if plan.bias == "LONG":
        assert plan.entry_zone is not None and plan.stop_loss is not None
        assert plan.take_profit is not None and len(plan.take_profit) == 2
        assert plan.risk_reward is not None and plan.risk_reward >= MIN_RR
        assert plan.stop_loss < plan.entry_zone[0]
        assert plan.take_profit[0] > plan.entry_zone[0]
        assert 0.0 <= plan.confidence <= 1.0
        assert plan.position_size_hint is not None
        assert plan.position_size_hint["risk_pct"] == 0.01
    else:
        assert plan.no_trade_reason


def test_no_trade_on_flat_market():
    c, h, l, v = _flat()
    plan = build_plan("FLAT", closes=c, highs=h, lows=l, volumes=v)
    assert plan.bias == "NO_TRADE"
    assert plan.no_trade_reason in (
        "no_qualifying_setup", "no_structure (ATR missing)",
    )


def test_iron_rules_rr_threshold():
    """Any LONG plan must clear RR >= 1.5."""
    for seed in range(8):
        c, h, l, v = _trend_up(120 + seed)
        plan = build_plan(f"S{seed}", closes=c, highs=h, lows=l, volumes=v)
        if plan.bias == "LONG":
            assert plan.risk_reward >= MIN_RR


def test_to_dict_serializable():
    c, h, l, v = _trend_up()
    d = build_plan("UP", closes=c, highs=h, lows=l, volumes=v).to_dict()
    assert d["symbol"] == "UP"
    assert "bias" in d and "confidence" in d
    assert isinstance(d["reasons"], list)
