"""Robust Quant Phase — stress, correlation, robustness, risk, portfolio,
persistence, research quality."""
from __future__ import annotations

import math
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.db.models import DailyPrice, EdgeSignal, Stock
from app.db.session import async_session_maker
from app.edge.edge_persistence import persistence_report
from app.portfolio_backtester.simulator import run_portfolio
from app.risk_engine.allocator import allocate
from app.services.edge_tracking_service import (
    evaluate_open_signals, persist_signal,
)
from app.strategy_lab.monte_carlo import run_monte_carlo
from app.strategy_lab.robustness import evaluate_robustness
from app.strategy_registry.research_quality import evaluate as quality_evaluate
from strategy.correlation.correlation_analyzer import correlation_matrix
from strategy.stress.regime_segments import (
    KNOWN_SEGMENTS, all_segments, auto_segments, filter_bars,
)
from strategy.stress.stress_runner import run_stress
from strategy.strategies import REGISTRY


# ─────────────── stress engine ───────────────

def _trend_bars(n: int = 1000):
    bars = []
    px = 100.0
    for i in range(n):
        px += 0.05 + 0.5 * math.sin(i / 7)
        c = max(1.0, px)
        bars.append({
            "date": f"202{(i // 250) % 6}-{((i // 22) % 12) + 1:02d}-{(i % 22) + 1:02d}",
            "open": c - 0.2, "high": c + 0.4, "low": c - 0.4, "close": c,
            "volume": 800_000,
        })
    return bars


def test_known_segments_static():
    assert len(KNOWN_SEGMENTS) >= 6
    for s in KNOWN_SEGMENTS:
        assert s.start < s.end
        assert s.label in {"crash", "bear", "recovery", "euphoria",
                            "trend", "sideways", "low_volatility"}


def test_filter_bars_extracts_segment():
    bars = _trend_bars()
    seg = KNOWN_SEGMENTS[0]   # 2020 crash
    out = filter_bars(bars, seg)
    # bars dates are synthetic so most should fall outside; just verify it doesn't crash
    assert isinstance(out, list)


def test_auto_segments_runs_without_errors():
    bars = _trend_bars()
    segs = auto_segments(bars)
    # Synthetic data is mildly trending — may or may not find segments
    assert isinstance(segs, list)


def test_run_stress_emits_report_shape():
    bars = _trend_bars()
    # bypass known segments — they don't match synthetic dates
    autos = auto_segments(bars)
    rep = run_stress(bars, REGISTRY["trend_breakout"],
                     strategy_name="trend_breakout", symbol="X",
                     segments=autos if autos else None)
    assert rep.strategy == "trend_breakout"
    assert isinstance(rep.cross_regime_consistency, float)
    assert isinstance(rep.cross_regime_max_dd, float)


# ─────────────── correlation ───────────────

@pytest_asyncio.fixture
async def two_setup_signals():
    """Two setups with similar return profile → should produce non-zero correlation."""
    async with async_session_maker() as s:
        await s.execute(delete(EdgeSignal))
        await s.commit()
        sig_dates = [date.today() - timedelta(days=30 - i * 3) for i in range(10)]
        for i, d in enumerate(sig_dates):
            sig = EdgeSignal(
                date=d, symbol=f"S{i}", setup="A", bias="LONG",
                entry=100.0, stop_loss=98.0, tp1=104.0, tp2=110.0,
                risk_reward=2.0, confidence=0.6, edge_score=60.0,
                evaluated=True, win=(i % 2 == 0),
                realized_r=2.0 if i % 2 == 0 else -1.0,
                bars_held=3, mfe_r=2.5, mae_r=-0.5,
            )
            s.add(sig)
            sig2 = EdgeSignal(
                date=d, symbol=f"S{i}", setup="B", bias="LONG",
                entry=100.0, stop_loss=98.0, tp1=104.0, tp2=110.0,
                risk_reward=2.0, confidence=0.6, edge_score=60.0,
                evaluated=True, win=(i % 2 == 0),
                realized_r=2.0 if i % 2 == 0 else -1.0,
                bars_held=3, mfe_r=2.5, mae_r=-0.5,
            )
            s.add(sig2)
        await s.commit()
    yield
    async with async_session_maker() as s:
        await s.execute(delete(EdgeSignal))
        await s.commit()


@pytest.mark.asyncio
async def test_correlation_flags_identical_setups(two_setup_signals):
    async with async_session_maker() as s:
        out = await correlation_matrix(s)
    pairs = out["pairs"]
    assert len(pairs) >= 1
    # Identical R series → return_corr should be 1.0
    pair = pairs[0]
    assert pair["return_corr"] > 0.95
    assert pair["flagged"] is True


# ─────────────── robustness ───────────────

def test_robustness_passes_when_metrics_clean():
    from strategy.stress.stress_runner import StressReport
    stress = StressReport(
        strategy="X", symbol="Y",
        segments=[],
        cross_regime_consistency=0.75,
        cross_regime_min_pf=1.4,
        cross_regime_max_dd=-0.15,
        single_period_dominance=0.35,
    )
    mc = run_monte_carlo([2.0, -1.0, 2.0, -1.0, 2.0, -1.0, 2.0, -1.0,
                          2.0, -1.0, 2.0, -1.0])
    rep = evaluate_robustness(strategy="X", stress=stress, mc=mc)
    assert rep.cross_regime_consistency == 0.75
    assert 0.0 <= rep.robustness_score <= 1.0


def test_robustness_fails_on_single_period_dominance():
    from strategy.stress.stress_runner import StressReport
    stress = StressReport(
        strategy="Y", symbol="Y",
        segments=[],
        cross_regime_consistency=0.7,
        cross_regime_min_pf=1.3,
        cross_regime_max_dd=-0.10,
        single_period_dominance=0.85,    # one segment dominates
    )
    mc = run_monte_carlo([2.0, -1.0] * 10)
    rep = evaluate_robustness(strategy="Y", stress=stress, mc=mc)
    assert any("single_period_dominance" in f for f in rep.failures)
    assert rep.passed is False


# ─────────────── risk allocator ───────────────

def test_allocator_normalises_weights():
    strategies = [
        {"strategy": "A", "rank_score": 0.8, "production_status": "ACTIVE", "live_expectancy_R": 0.5},
        {"strategy": "B", "rank_score": 0.4, "production_status": "ACTIVE", "live_expectancy_R": 0.2},
        {"strategy": "C", "rank_score": 0.6, "production_status": "DISABLED", "live_expectancy_R": -0.1},
    ]
    out = allocate(strategies, regime_label="trending_up")
    weights = {a["strategy"]: a["weight"] for a in out["allocations"]}
    assert weights["C"] == 0.0
    assert abs(weights["A"] + weights["B"] - 1.0) < 1e-3


def test_allocator_tightens_in_bearish():
    strategies = [{"strategy": "A", "rank_score": 0.8, "production_status": "ACTIVE", "live_expectancy_R": 0.5}]
    bull = allocate(strategies, regime_label="trending_up")
    bear = allocate(strategies, regime_label="bearish")
    a_bull = bull["allocations"][0]
    a_bear = bear["allocations"][0]
    # per-signal risk shrinks in bearish regime
    assert a_bear["per_signal_risk_pct"] < a_bull["per_signal_risk_pct"]


# ─────────────── portfolio ───────────────

def test_portfolio_runs_with_zero_strategies():
    bars = _trend_bars(100)
    rep = run_portfolio(bars, {})
    assert rep.portfolio_trades == 0
    assert len(rep.equity_curve) == 100
    assert rep.equity_curve[0] == 1_000_000.0


def test_portfolio_respects_max_concurrent():
    bars = _trend_bars(300)
    rep = run_portfolio(bars, {"trend_breakout": REGISTRY["trend_breakout"]},
                        max_concurrent_positions=2)
    assert max(rep.exposure_heat) <= 2


# ─────────────── persistence ───────────────

@pytest_asyncio.fixture
async def persistence_signals():
    async with async_session_maker() as s:
        await s.execute(delete(EdgeSignal))
        await s.commit()
        # 30 evaluated signals across 30 days
        for i in range(30):
            d = date.today() - timedelta(days=30 - i)
            r = 1.5 - 0.05 * i   # gradually decaying expectancy
            s.add(EdgeSignal(
                date=d, symbol="X", setup="A", bias="LONG",
                entry=100.0, stop_loss=98.0, tp1=104.0, tp2=110.0,
                risk_reward=2.0, confidence=0.5, edge_score=50.0,
                evaluated=True, win=(r > 0),
                realized_r=r, bars_held=3, mfe_r=2.0, mae_r=-0.5,
            ))
        await s.commit()
    yield
    async with async_session_maker() as s:
        await s.execute(delete(EdgeSignal))
        await s.commit()


@pytest.mark.asyncio
async def test_persistence_returns_rolling_expectancy(persistence_signals):
    async with async_session_maker() as s:
        rep = await persistence_report(s)
    assert "A" in rep
    assert isinstance(rep["A"]["rolling_expectancy"], list)
    assert rep["A"]["sample_size"] >= 30


# ─────────────── research quality ───────────────

def test_quality_active_when_clean():
    v = quality_evaluate(
        "trend_breakout",
        sample_size=50,
        cross_regime_consistency=0.8,
        single_period_dominance=0.3,
        correlation_flagged=False,
        decay_label="stable",
        robustness_score=0.85,
    )
    assert v.production_research_score >= 0.65
    assert v.research_status == "ACTIVE"


def test_quality_research_only_with_low_sample():
    v = quality_evaluate(
        "low_sample",
        sample_size=4,
        cross_regime_consistency=0.4,
        single_period_dominance=0.5,
        correlation_flagged=False,
        decay_label="stable",
        robustness_score=0.5,
    )
    assert v.research_status in ("RESEARCH_ONLY", "DISABLED")


def test_quality_disables_when_everything_breaks():
    v = quality_evaluate(
        "broken_setup",
        sample_size=2,           # nearly no samples
        cross_regime_consistency=0.0,
        single_period_dominance=0.95,
        correlation_flagged=True,
        decay_label="broken",
        robustness_score=0.05,
    )
    assert v.research_status == "DISABLED"
    assert v.production_research_score < 0.40
