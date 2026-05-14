"""Market regime classifier — invariants + each label."""
from __future__ import annotations

import math

import pytest

from strategy.market_regime import (
    ALLOWED_SETUPS, detect_regime, setup_allowed,
)


def _trend_up_bars(n: int = 250):
    closes = [100 + i * 0.7 + math.sin(i / 6) * 0.5 for i in range(n)]
    highs = [c + 0.6 for c in closes]
    lows = [c - 0.6 for c in closes]
    return closes, highs, lows


def _trend_down_bars(n: int = 250):
    closes = [200 - i * 0.7 + math.sin(i / 6) * 0.5 for i in range(n)]
    highs = [c + 0.6 for c in closes]
    lows = [c - 0.6 for c in closes]
    return closes, highs, lows


def _sideways_bars(n: int = 250):
    closes = [100 + math.sin(i / 5) * 0.6 for i in range(n)]
    highs = [c + 0.3 for c in closes]
    lows = [c - 0.3 for c in closes]
    return closes, highs, lows


def test_unknown_when_history_too_short():
    r = detect_regime(closes=[100, 101, 102, 103])
    assert r.label == "unknown"
    assert "ma20_support_bounce" in r.allowed_setups


def test_trending_up_detected():
    c, h, l = _trend_up_bars()
    r = detect_regime(c, h, l)
    assert r.label.startswith("trending_up")
    assert r.ema200_slope_pct is not None and r.ema200_slope_pct > 0
    assert "trend_breakout_retest" in r.allowed_setups or "ma20_support_bounce" in r.allowed_setups


def test_trending_down_detected():
    c, h, l = _trend_down_bars()
    r = detect_regime(c, h, l)
    assert r.label.startswith("trending_down") or r.label == "bearish"
    # Either way LONG breakouts must be blocked
    assert "trend_breakout_retest" not in r.allowed_setups


def test_sideways_blocks_breakout():
    c, h, l = _sideways_bars()
    r = detect_regime(c, h, l)
    assert r.label == "sideways"
    assert r.allowed_setups == []
    assert not setup_allowed("trend_breakout_retest", r.label)


def test_iron_rule_no_long_in_bearish():
    c, h, l = _trend_down_bars()
    r = detect_regime(c, h, l)
    # all LONG setups must be denied
    for setup in ("trend_breakout_retest", "ma20_support_bounce", "chip_follow_long"):
        assert not setup_allowed(setup, r.label)


def test_allowed_setups_table_consistency():
    # No regime label maps to unknown setups
    for _label, setups in ALLOWED_SETUPS.items():
        for s in setups:
            assert s in {
                "trend_breakout_retest", "ma20_support_bounce", "chip_follow_long",
            }
