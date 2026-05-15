"""ShortTermDecisionEngine integration tests."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_short_term_endpoint_returns_canonical_shape(client):
    r = await client.get("/api/v1/decisions/short-term?limit=5")
    assert r.status_code == 200
    body = r.json()
    for f in ("market_state", "actionable_count", "research_count", "decisions"):
        assert f in body, f"missing {f}"
    assert "regime" in body["market_state"]
    assert "allowed_setups" in body["market_state"]


def test_gate_one_blocks_when_setup_forbidden():
    from app.services.decision_engine import _gate_one
    actionable, reason = _gate_one(
        {"bias": "LONG", "setup": "trend_breakout_retest"},
        allowed_setups=["ma20_support_bounce"],
        forbidden_setups=["trend_breakout_retest"],
        active_setups={"trend_breakout_retest", "ma20_support_bounce"},
        disabled_setups=set(),
    )
    assert actionable is False
    assert "forbid" in (reason or "")


def test_gate_one_blocks_when_strategy_not_active():
    from app.services.decision_engine import _gate_one
    actionable, reason = _gate_one(
        {"bias": "LONG", "setup": "ma20_support_bounce"},
        allowed_setups=["ma20_support_bounce"],
        forbidden_setups=[],
        active_setups=set(),               # no ACTIVE setups
        disabled_setups={"ma20_support_bounce"},
    )
    assert actionable is False
    assert "DISABLED" in (reason or "")


def test_gate_one_passes_when_everything_aligned():
    from app.services.decision_engine import _gate_one
    actionable, reason = _gate_one(
        {"bias": "LONG", "setup": "ma20_support_bounce"},
        allowed_setups=["ma20_support_bounce"],
        forbidden_setups=[],
        active_setups={"ma20_support_bounce"},
        disabled_setups=set(),
    )
    assert actionable is True
    assert reason is None


def test_risk_score_inversely_tracks_confidence():
    from app.services.decision_engine import _risk_score
    hi = _risk_score({"confidence": 0.9, "rel_volume": 1.0}, exposure_mult=1.0)
    lo = _risk_score({"confidence": 0.2, "rel_volume": 1.0}, exposure_mult=0.25)
    assert hi < lo
