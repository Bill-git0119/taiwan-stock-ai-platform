import pytest

from chip_analysis.calculator import ChipCalculator, chip_score
from fundamental_analysis.calculator import FundamentalCalculator, fundamental_score
from technical_analysis.calculator import TechnicalCalculator, technical_score
from ai_engine.scoring import (
    CHIP_WEIGHT,
    FUNDAMENTAL_WEIGHT,
    TECHNICAL_WEIGHT,
    compute_total_score,
    rank_top_n,
    score_stock,
)


def test_chip_all_zero():
    records = [{"foreign_buy": 0, "investment_buy": 0, "dealer_buy": 0, "volume": 100} for _ in range(20)]
    assert chip_score(records) == 0


def test_chip_strong_flow():
    records = []
    for i in range(20):
        records.append({
            "foreign_buy": 1000 if i >= 15 else -100,
            "investment_buy": 500 if i >= 17 else 0,
            "dealer_buy": 0,
            "volume": 2000 if i >= 15 else 1000,
        })
    s = chip_score(records)
    assert 50 < s <= 100


def test_fundamental_sweet_spot():
    s = fundamental_score(eps_yoy=25, roe=22, rev_mom=12, pe=15)
    assert 80 <= s <= 100


def test_fundamental_pe_penalty():
    cheap = fundamental_score(eps_yoy=0, roe=0, rev_mom=0, pe=5)
    fair = fundamental_score(eps_yoy=0, roe=0, rev_mom=0, pe=15)
    pricey = fundamental_score(eps_yoy=0, roe=0, rev_mom=0, pe=50)
    assert fair > cheap
    assert fair > pricey


def test_technical_bullish_stack():
    closes = [100 + i * 0.8 for i in range(80)]
    s = technical_score(closes)
    assert s >= 50


def test_technical_flat_boring():
    closes = [100.0] * 80
    assert technical_score(closes) < 50


def test_total_weight_sum_is_one():
    assert abs(CHIP_WEIGHT + FUNDAMENTAL_WEIGHT + TECHNICAL_WEIGHT - 1.0) < 1e-9


def test_compute_total_score_math():
    assert compute_total_score(100, 100, 100) == 100.0
    assert compute_total_score(0, 0, 0) == 0.0
    assert abs(compute_total_score(80, 60, 40) - (80 * 0.40 + 60 * 0.35 + 40 * 0.25)) < 0.01


def test_compute_total_score_rejects_out_of_range():
    with pytest.raises(ValueError):
        compute_total_score(-1, 0, 0)
    with pytest.raises(ValueError):
        compute_total_score(0, 101, 0)


def test_score_stock_produces_reason():
    payload = {
        "symbol": "2330", "name": "台積電",
        "chip_records": [
            {"foreign_buy": 1000, "investment_buy": 500, "dealer_buy": 0, "volume": 3000}
            for _ in range(20)
        ],
        "fundamentals": {"eps_yoy": 30, "roe": 22, "rev_mom": 12, "pe": 18},
        "closes": [100 + i for i in range(80)],
    }
    s = score_stock(payload)
    assert s.symbol == "2330"
    assert 0 <= s.total_score <= 100
    assert s.reason and len(s.reason) > 0


def test_rank_top_n_orders_desc():
    stocks = [
        {
            "symbol": f"000{i}",
            "name": f"S{i}",
            "chip_records": [],
            "fundamentals": {"eps_yoy": i * 5},
            "closes": [100 + j for j in range(80)],
        }
        for i in range(5)
    ]
    top = rank_top_n(stocks, n=3)
    assert len(top) == 3
    scores = [s.total_score for s in top]
    assert scores == sorted(scores, reverse=True)
