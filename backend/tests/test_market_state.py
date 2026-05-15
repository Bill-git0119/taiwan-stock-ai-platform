"""MarketState engine smoke tests.

Verify the decision logic, not the data plumbing. We feed _decide a
known (idx_regime, breadth, macro) tuple and assert the verdict.
"""
from __future__ import annotations

import pytest

from app.services.market_state import _decide


def test_decide_trending_up_low_vix_allows_everything():
    idx = {"label": "trending_up", "adx": 28, "ema200_slope_pct": 0.12}
    breadth = {"regime_hint": "broad_strength", "universe_size": 94}
    macro = {
        "vix": {"last": 13.5, "d1_pct": -2.0},
        "sp500": {"last": 5000, "d1_pct": 0.8},
        "twii": {"last": 18000, "d1_pct": 1.2},
        "dxy": {"last": 103, "d1_pct": -0.2},
    }
    st = _decide(idx, breadth, macro)
    assert st.regime == "trending_up"
    assert st.risk_level in ("low", "normal")
    assert st.risk_on_score > 0.2
    assert "trend_breakout_retest" in st.allowed_setups
    assert st.exposure_mult >= 0.75


def test_decide_unknown_regime_locks_setups():
    idx = {"label": "unknown", "adx": None, "ema200_slope_pct": None}
    breadth = {"regime_hint": "no_data", "universe_size": 0}
    macro = {}
    st = _decide(idx, breadth, macro)
    assert st.regime == "unknown"
    assert st.allowed_setups == []
    assert st.exposure_mult <= 0.25


def test_decide_high_vix_blocks_breakouts():
    idx = {"label": "trending_up_weak", "adx": 18, "ema200_slope_pct": 0.05}
    breadth = {"regime_hint": "mixed", "universe_size": 94}
    macro = {
        "vix": {"last": 28, "d1_pct": 12},
        "sp500": {"last": 5000, "d1_pct": -1.5},
        "twii": {"last": 18000, "d1_pct": -1.2},
        "dxy": {"last": 105, "d1_pct": 0.8},
    }
    st = _decide(idx, breadth, macro)
    assert st.risk_on_score < 0
    # In risk-off, breakouts must be the first to go
    assert "trend_breakout_retest" not in st.allowed_setups


def test_decide_severe_risk_off_locks_everything():
    idx = {"label": "trending_up_weak", "adx": 18}
    breadth = {"regime_hint": "broad_weakness", "universe_size": 94}
    macro = {
        "vix": {"last": 35, "d1_pct": 25},
        "sp500": {"d1_pct": -3.0},
        "nasdaq": {"d1_pct": -4.0},
        "twii": {"d1_pct": -2.5},
        "dxy": {"d1_pct": 1.5},
    }
    st = _decide(idx, breadth, macro)
    assert st.risk_on_score <= -0.5
    assert st.allowed_setups == []
    assert st.exposure_mult <= 0.5


@pytest.mark.asyncio
async def test_state_endpoint_returns_full_shape(client):
    r = await client.get("/api/v1/market/state")
    assert r.status_code == 200
    j = r.json()
    for f in ("regime", "risk_on_score", "allowed_setups", "forbidden_setups",
              "exposure_mult", "risk_level", "reasons"):
        assert f in j, f"missing {f} in {j}"
