"""LLM narrative — stub renderer must produce valid markdown from real facts."""
from __future__ import annotations

import pytest

from app.services.llm_narrative import _build_user_prompt, _stub_render, generate_narrative


FAKE_FACTS = {
    "market_state": {
        "regime": "trending_up",
        "confidence": 0.72,
        "risk_on_score": 0.34,
        "risk_level": "normal",
        "exposure_mult": 0.75,
        "allowed_setups": ["trend_breakout_retest", "ma20_support_bounce"],
        "forbidden_setups": [],
        "reasons": ["VIX低 13.5", "S&P +0.8%"],
        "macro": {"vix": {"last": 13.5, "d1_pct": -2.0}},
    },
    "breadth": {
        "regime_hint": "broad_strength",
        "advance_decline": {"advancing": 62, "declining": 30, "ratio": 2.07},
        "above_ma20_pct": 67.4,
        "new_highs_20": 12, "new_lows_20": 2,
        "sectors": [
            {"sector": "半導體", "ret_5d": 4.2, "rank": 1, "members": 18},
            {"sector": "金融", "ret_5d": 0.8, "rank": 5, "members": 13},
            {"sector": "塑膠", "ret_5d": -3.1, "rank": 24, "members": 3},
        ],
    },
    "decisions": {
        "decisions": [
            {"symbol": "2330", "name": "台積電",
             "setup": "trend_breakout_retest",
             "confidence": 0.78, "risk_reward": 2.1,
             "sector": "半導體", "rs_5d": 3.5, "actionable": True,
             "invalidation_reason": None},
            {"symbol": "2603", "name": "長榮",
             "setup": "ma20_support_bounce",
             "confidence": 0.55, "risk_reward": 1.6,
             "sector": "航運", "rs_5d": -0.3,
             "actionable": False,
             "invalidation_reason": "strategy not ACTIVE (research-only)"},
        ]
    },
}


def test_user_prompt_includes_all_data_sources():
    p = _build_user_prompt(FAKE_FACTS)
    assert "regime=trending_up" in p
    assert "VIX低" in p
    assert "2330" in p
    assert "半導體" in p


def test_stub_render_produces_six_sections():
    md = _stub_render(FAKE_FACTS)
    for h in ("今日市場狀態", "強勢股觀察", "風險警告", "族群輪動",
              "昨日 vs 今日改變", "明日 watchlist"):
        assert h in md
    assert "2330" in md
    assert "stub renderer" in md


def test_stub_render_handles_no_data():
    md = _stub_render({"market_state": {}, "breadth": {}, "decisions": {}})
    assert "資料尚未灌入" in md or "無" in md


@pytest.mark.asyncio
async def test_generate_falls_back_to_stub_without_keys(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    res = await generate_narrative(FAKE_FACTS)
    assert res.provider == "stub"
    assert "今日市場狀態" in res.markdown
    assert "2330" in res.markdown


@pytest.mark.asyncio
async def test_daily_brief_endpoint(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = await client.get("/api/v1/narrative-v2/daily-brief")
    assert r.status_code == 200
    body = r.json()
    assert "markdown" in body
    assert body["provider"] in ("stub", "anthropic", "openai")
