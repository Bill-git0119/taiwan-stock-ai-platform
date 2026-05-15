"""LongTermInvestmentEngine smoke + decision-tree tests."""
from __future__ import annotations

import pytest

from app.db.models import Stock
from app.services.long_term_engine import _classify


def _stub_metrics(**kw):
    base = {
        "score": None, "last": 100.0, "ret_60d": 0.0, "ret_240d": 0.0,
        "foreign_net_30d": 0.0, "institutional_aligned_days": 0,
        "n_bars": 200, "n_chips": 30,
    }
    base.update(kw)
    return base


def test_classify_avoid_on_deep_decline_with_selling():
    s = Stock(symbol="X", name="x", market="TWSE")
    c = _classify(s, _stub_metrics(ret_240d=-40, foreign_net_30d=-500))
    assert c.bucket == "AVOID"


def test_classify_compounder_requires_real_fundamentals():
    class _Score:
        chip_score = 60
        fundamental_score = 80
        technical_score = 65
    s = Stock(symbol="X", name="x", market="TWSE")
    c = _classify(s, _stub_metrics(
        score=_Score(), ret_60d=5, ret_240d=20, foreign_net_30d=300,
    ))
    assert c.bucket == "COMPOUNDER"
    assert c.fundamental_score == 80


def test_classify_no_fundamental_flag_when_zero():
    class _Score:
        chip_score = 60
        fundamental_score = 0   # not wired
        technical_score = 65
    s = Stock(symbol="X", name="x", market="TWSE")
    c = _classify(s, _stub_metrics(
        score=_Score(), ret_60d=5, ret_240d=20, foreign_net_30d=300,
    ))
    assert "no_fundamental_data" in c.flags


def test_classify_turnaround_on_recent_recovery():
    class _Score:
        chip_score = 50
        fundamental_score = 40
        technical_score = 55
    s = Stock(symbol="X", name="x", market="TWSE")
    c = _classify(s, _stub_metrics(
        score=_Score(), ret_60d=15, ret_240d=-5, foreign_net_30d=200,
    ))
    assert c.bucket == "TURNAROUND"


def test_classify_cyclical_sector():
    class _Score:
        chip_score = 50
        fundamental_score = 50
        technical_score = 55
    s = Stock(symbol="2603", name="長榮", market="TWSE", sector="航運")
    c = _classify(s, _stub_metrics(
        score=_Score(), ret_60d=12, ret_240d=0, foreign_net_30d=0,
    ))
    assert c.bucket == "CYCLICAL"


@pytest.mark.asyncio
async def test_buckets_endpoint_shape(client):
    r = await client.get("/api/v1/long-term/buckets?limit_per_bucket=5")
    assert r.status_code == 200
    body = r.json()
    for f in ("fundamentals_wired", "buckets", "counts"):
        assert f in body
    for bucket in ("COMPOUNDER", "TURNAROUND", "CYCLICAL", "AVOID"):
        assert bucket in body["buckets"]
