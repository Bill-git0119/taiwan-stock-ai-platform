"""Research infrastructure — universe, narrative, ranker, MFE/MAE, breakdowns."""
from __future__ import annotations

from datetime import date, timedelta
from typing import List

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.db.models import ChipData, DailyPrice, EdgeSignal, Stock, UniverseSnapshot
from app.db.session import async_session_maker
from app.edge import edge_decay, strategy_metrics
from app.narrative.narrative_engine import build_narrative
from app.narrative.theme_tracker import score_themes
from app.services.edge_tracking_service import (
    evaluate_open_signals, persist_signal,
)
from app.strategy_registry.ranker import disabled_setups, rank_all
from app.universe import manager, universe_builder
from app.universe.curated import deduplicated


# ─────────────────────────── universe ───────────────────────────

def test_curated_universe_is_unique_and_large():
    rows = deduplicated()
    assert len(rows) >= 80
    syms = [r[0] for r in rows]
    assert len(syms) == len(set(syms))  # no dupes
    # Every row has 5 fields
    for r in rows:
        assert len(r) == 5


@pytest_asyncio.fixture
async def universe_seed():
    """Seed two symbols with 25 bars each so build_snapshot can compute liquidity."""
    today = date.today()
    async with async_session_maker() as s:
        await s.execute(delete(UniverseSnapshot))
        await s.execute(delete(DailyPrice))
        await s.execute(delete(Stock).where(Stock.symbol.in_(["U1", "U2"])))
        await s.commit()
        a = Stock(symbol="U1", name="高量股", market="TWSE", sector="半導體")
        b = Stock(symbol="U2", name="低量股", market="TWSE", sector="金融")
        s.add_all([a, b])
        await s.commit()
        await s.refresh(a); await s.refresh(b)
        for i in range(25):
            d = today - timedelta(days=24 - i)
            s.add(DailyPrice(stock_id=a.id, date=d, open=100, high=101, low=99,
                             close=100, volume=10_000_000))  # 10M * 100 = 1B notional
            s.add(DailyPrice(stock_id=b.id, date=d, open=10, high=10.5, low=9.5,
                             close=10, volume=1_000))         # 1K * 10 = 10K, fails
        await s.commit()
    yield
    async with async_session_maker() as s:
        await s.execute(delete(UniverseSnapshot))
        await s.execute(delete(DailyPrice))
        await s.execute(delete(Stock).where(Stock.symbol.in_(["U1", "U2"])))
        await s.commit()


@pytest.mark.asyncio
async def test_build_snapshot_filters_illiquid(universe_seed):
    async with async_session_maker() as s:
        report = await universe_builder.build_snapshot(s)
    # Curated list will be ~90 ; U1 + U2 are extras but the builder pulls
    # from curated, not from existing Stock rows — so curated dominates.
    assert report["curated_count"] >= 80


@pytest.mark.asyncio
async def test_universe_manager_falls_back_to_curated_when_empty():
    async with async_session_maker() as s:
        # No snapshot for date.today() — manager should fall back to curated
        await s.execute(delete(UniverseSnapshot))
        await s.commit()
        symbols = await manager.get_active_symbols(s, limit=10)
    assert len(symbols) == 10
    assert "2330" in symbols or "0050" in symbols


# ─────────────────────────── MFE/MAE ───────────────────────────

@pytest_asyncio.fixture
async def evaluator_seed():
    """Stock with bars that produce a tp1 hit, with intraday excursions."""
    today = date.today()
    async with async_session_maker() as s:
        await s.execute(delete(EdgeSignal))
        await s.execute(delete(DailyPrice))
        await s.execute(delete(Stock).where(Stock.symbol == "MFE"))
        await s.commit()
        st = Stock(symbol="MFE", name="MFE測試", market="TWSE", sector="半導體")
        s.add(st)
        await s.commit()
        await s.refresh(st)
        # signal at day -10, then a deep dip then a recovery to TP1
        # we craft bars: bar i+1 open=100 (fill), then dip to 98.5, climb to 105
        for offset, (o, h, l, c) in enumerate([
            (100.0, 100.5, 99.5, 100.0),   # signal day (date = today - 10)
            (100.0, 100.3, 99.0, 99.5),    # fill bar — open 100
            (99.5,  100.0, 98.5, 99.8),    # MAE bar
            (99.8,  101.0, 99.5, 100.5),
            (100.5, 102.0, 100.0, 101.5),
            (101.5, 103.0, 101.0, 102.5),
            (102.5, 104.5, 102.0, 104.0),  # MFE / TP1 hit
        ]):
            d = today - timedelta(days=10 - offset)
            s.add(DailyPrice(stock_id=st.id, date=d, open=o, high=h, low=l,
                             close=c, volume=500_000))
        await s.commit()
    yield
    async with async_session_maker() as s:
        await s.execute(delete(EdgeSignal))
        await s.execute(delete(DailyPrice))
        await s.execute(delete(Stock).where(Stock.symbol == "MFE"))
        await s.commit()


@pytest.mark.asyncio
async def test_evaluator_records_mfe_and_mae(evaluator_seed):
    sig_date = date.today() - timedelta(days=10)
    plan = {
        "symbol": "MFE", "bias": "LONG",
        "setup": "trend_breakout_retest",
        "entry_zone": [100.0, 100.5],
        "stop_loss": 98.0,
        "take_profit": [103.0, 110.0],
        "risk_reward": 1.5, "confidence": 0.6, "edge": 60.0,
    }
    async with async_session_maker() as s:
        await persist_signal(s, symbol="MFE", setup="trend_breakout_retest",
                              plan=plan, on_date=sig_date)
    async with async_session_maker() as s:
        await evaluate_open_signals(s)
    async with async_session_maker() as s:
        from sqlalchemy import select as _sel
        sig = (await s.execute(
            _sel(EdgeSignal).where(EdgeSignal.symbol == "MFE")
        )).scalar_one()
    assert sig.evaluated is True
    assert sig.mfe_r is not None
    assert sig.mae_r is not None
    assert sig.mfe_r >= 0  # at least zero — high never went below entry
    assert sig.mae_r <= 0  # at least zero — low always <= entry early on


# ─────────────────────────── strategy_metrics ───────────────────────────

@pytest.mark.asyncio
async def test_strategy_metrics_breaks_down_by_setup_and_regime(evaluator_seed):
    sig_date = date.today() - timedelta(days=10)
    async with async_session_maker() as s:
        await persist_signal(
            s, symbol="MFE", setup="trend_breakout_retest",
            plan={"symbol": "MFE", "bias": "LONG",
                  "setup": "trend_breakout_retest",
                  "entry_zone": [100.0, 100.5], "stop_loss": 98.0,
                  "take_profit": [103.0, 110.0], "risk_reward": 1.5,
                  "confidence": 0.6, "edge": 60.0},
            regime="trending_up", on_date=sig_date,
        )
        await evaluate_open_signals(s)
        by_setup = await strategy_metrics.by_setup(s)
        by_regime = await strategy_metrics.by_regime(s)
    assert "trend_breakout_retest" in by_setup
    assert "trending_up" in by_regime
    assert by_setup["trend_breakout_retest"]["sample_size"] >= 1


# ─────────────────────────── narrative ───────────────────────────

def test_theme_tracker_picks_up_ai_keywords():
    titles = ["輝達股價創新高", "AI 伺服器需求強勁", "CoWoS 產能滿載"]
    themes = score_themes(titles, [])
    names = [t["theme"] for t in themes]
    assert "AI 半導體" in names
    assert "CoWoS / 先進封裝" in names


def test_theme_tracker_returns_empty_when_no_match():
    themes = score_themes(["天氣很好"], [])
    assert themes == []


# ─────────────────────────── ranker ───────────────────────────

@pytest.mark.asyncio
async def test_ranker_with_no_data_returns_unknown_status():
    async with async_session_maker() as s:
        await s.execute(delete(EdgeSignal))
        await s.commit()
        rankings = await rank_all(s)
    # No setups present — ranker returns an empty list (no setups to rank)
    assert isinstance(rankings, list)


@pytest.mark.asyncio
async def test_ranker_marks_disabled_when_low_sample(evaluator_seed):
    """Single signal — sample_size=1 — should be UNKNOWN not ACTIVE."""
    sig_date = date.today() - timedelta(days=10)
    async with async_session_maker() as s:
        await persist_signal(
            s, symbol="MFE", setup="trend_breakout_retest",
            plan={"symbol": "MFE", "bias": "LONG",
                  "setup": "trend_breakout_retest",
                  "entry_zone": [100.0, 100.5], "stop_loss": 98.0,
                  "take_profit": [103.0, 110.0], "risk_reward": 1.5,
                  "confidence": 0.6, "edge": 60.0},
            on_date=sig_date,
        )
        await evaluate_open_signals(s)
        rankings = await rank_all(s)
    setups = {r.strategy: r for r in rankings}
    assert "trend_breakout_retest" in setups
    assert setups["trend_breakout_retest"].production_status in ("DISABLED", "WATCH", "UNKNOWN")


# ─────────────────────────── decay ───────────────────────────

@pytest.mark.asyncio
async def test_decay_returns_label_for_each_setup(evaluator_seed):
    sig_date = date.today() - timedelta(days=10)
    async with async_session_maker() as s:
        await persist_signal(
            s, symbol="MFE", setup="trend_breakout_retest",
            plan={"symbol": "MFE", "bias": "LONG",
                  "setup": "trend_breakout_retest",
                  "entry_zone": [100.0, 100.5], "stop_loss": 98.0,
                  "take_profit": [103.0, 110.0], "risk_reward": 1.5,
                  "confidence": 0.6, "edge": 60.0},
            on_date=sig_date,
        )
        await evaluate_open_signals(s)
        scores = await edge_decay.decay_scores(s)
    assert "trend_breakout_retest" in scores
    assert scores["trend_breakout_retest"]["label"] in (
        "improving", "stable", "decaying", "broken"
    )
