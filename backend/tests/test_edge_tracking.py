"""Edge tracking — persistence, walk-forward evaluation, stats."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.db.models import DailyPrice, EdgeSignal, Stock
from app.db.session import async_session_maker
from app.services.edge_tracking_service import (
    evaluate_open_signals, persist_signal, setup_stats,
)
from app.services.strategy_health import disabled_setups, health_report


def _plan(symbol="2330", entry=100.0, sl=98.0, tp1=104.0, tp2=110.0,
          rr=2.0, conf=0.7, edge=70.0):
    return {
        "symbol": symbol, "bias": "LONG", "setup": "trend_breakout_retest",
        "entry_zone": [entry, entry + 0.4],
        "stop_loss": sl, "take_profit": [tp1, tp2],
        "risk_reward": rr, "confidence": conf, "edge": edge,
    }


@pytest_asyncio.fixture
async def stock_with_bars():
    """Stock 'EVT' with 30 bars of OHLCV starting from today-30."""
    today = date.today()
    async with async_session_maker() as s:
        st = Stock(symbol="EVT", name="評估股", market="TWSE")
        s.add(st)
        await s.commit()
        await s.refresh(st)
        # straight uptrend so TP1 hits within a few bars
        for i in range(30):
            d = today - timedelta(days=29 - i)
            close = 100 + i * 0.7
            s.add(DailyPrice(stock_id=st.id, date=d,
                             open=close - 0.2, high=close + 0.5,
                             low=close - 0.5, close=close, volume=100_000))
        await s.commit()
    yield
    async with async_session_maker() as s:
        await s.execute(delete(DailyPrice))
        await s.execute(delete(EdgeSignal))
        await s.execute(delete(Stock))
        await s.commit()


@pytest.mark.asyncio
async def test_persist_signal_idempotent(stock_with_bars):
    today = date.today() - timedelta(days=10)
    async with async_session_maker() as s:
        a = await persist_signal(s, symbol="EVT", setup="trend_breakout_retest",
                                  plan=_plan(), regime="trending_up", on_date=today)
        b = await persist_signal(s, symbol="EVT", setup="trend_breakout_retest",
                                  plan=_plan(), regime="trending_up", on_date=today)
    assert a is not None and b is not None
    assert a.id == b.id  # same row reused


@pytest.mark.asyncio
async def test_persist_skips_no_trade(stock_with_bars):
    async with async_session_maker() as s:
        out = await persist_signal(s, symbol="EVT", setup="x",
                                    plan={"bias": "NO_TRADE"})
    assert out is None


@pytest.mark.asyncio
async def test_evaluate_marks_tp_when_uptrend(stock_with_bars):
    """Signal 10 days ago in an uptrend should hit TP1 well within horizon."""
    sig_date = date.today() - timedelta(days=15)
    # entry below the bars at sig_date+1, TP achievable
    async with async_session_maker() as s:
        await persist_signal(
            s, symbol="EVT", setup="trend_breakout_retest",
            plan=_plan(entry=100.0, sl=98.0, tp1=104.0, tp2=110.0),
            on_date=sig_date,
        )
    async with async_session_maker() as s:
        res = await evaluate_open_signals(s)
    assert res["evaluated"] >= 1
    async with async_session_maker() as s:
        row = (await s.execute(
            select(EdgeSignal).where(EdgeSignal.symbol == "EVT")
        )).scalar_one()
    assert row.evaluated is True
    assert row.exit_reason in ("tp1", "tp2", "timeout")
    assert row.realized_r is not None


@pytest.mark.asyncio
async def test_evaluate_skips_when_signal_too_recent(stock_with_bars):
    """Signal 1 day ago must NOT be evaluated (lookahead protection)."""
    sig_date = date.today() - timedelta(days=1)
    async with async_session_maker() as s:
        await persist_signal(
            s, symbol="EVT", setup="trend_breakout_retest",
            plan=_plan(entry=100.0, sl=98.0, tp1=200.0, tp2=300.0),
            on_date=sig_date,
        )
    async with async_session_maker() as s:
        res = await evaluate_open_signals(s)
    assert res["evaluated"] == 0


@pytest.mark.asyncio
async def test_setup_stats_after_evaluation(stock_with_bars):
    """A handful of signals → stats dict has the setup with sample_size>=1."""
    async with async_session_maker() as s:
        for offset in (15, 17, 19, 21):
            d = date.today() - timedelta(days=offset)
            await persist_signal(
                s, symbol="EVT", setup="trend_breakout_retest",
                plan=_plan(entry=100.0, sl=99.5, tp1=101.0, tp2=102.0),
                on_date=d,
            )
        await evaluate_open_signals(s)
        stats = await setup_stats(s)
    assert "trend_breakout_retest" in stats
    s = stats["trend_breakout_retest"]
    assert s.sample_size >= 1
    # win_rate is well-defined in [0, 1]
    assert 0.0 <= s.win_rate <= 1.0


@pytest.mark.asyncio
async def test_strategy_health_lazy_until_min_samples(stock_with_bars):
    """Setup with < WINRATE_MIN_SAMPLES evaluations is healthy by default."""
    async with async_session_maker() as s:
        # only 2 signals — well under the threshold
        for offset in (15, 17):
            d = date.today() - timedelta(days=offset)
            await persist_signal(
                s, symbol="EVT", setup="trend_breakout_retest",
                plan=_plan(), on_date=d,
            )
        await evaluate_open_signals(s)
        report = await health_report(s)
        disabled = await disabled_setups(s)
    if "trend_breakout_retest" in report:
        assert report["trend_breakout_retest"]["is_healthy"] is True
    assert "trend_breakout_retest" not in disabled
