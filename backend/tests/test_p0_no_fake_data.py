"""Regression tests for P0 audit fixes.

Iron rule under test: the system NEVER fabricates trading data. When a code
path used to silently substitute synthetic/mock data, it must now either
raise an explicit error, return an empty list, or expose a clear
data-source flag.

These tests are intentionally narrow — they exist to fail loudly the moment
someone reintroduces fake-data fallback paths.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.db.models import Stock
from app.services.backtest_service import NoRealDataError, run_backtest
from app.services.leaderboard_service import (
    leaderboard_status,
    weekly_leaderboard,
)


# ───────────────────────── P0#2 backtest ─────────────────────────

@pytest.mark.asyncio
async def test_backtest_raises_on_missing_data(session):
    """Backtest must NOT silently produce results when the DB has no bars."""
    session.add(Stock(symbol="GHOST", name="幽靈股", market="TWSE"))
    await session.commit()
    with pytest.raises(NoRealDataError):
        await run_backtest(
            session, "GHOST",
            date(2025, 1, 1), date(2025, 6, 30),
            "ai_top_rank",
        )


@pytest.mark.asyncio
async def test_backtest_raises_on_unknown_symbol(session):
    with pytest.raises(NoRealDataError):
        await run_backtest(
            session, "DOES_NOT_EXIST",
            date(2025, 1, 1), date(2025, 6, 30),
            "ai_top_rank",
        )


def test_no_synthetic_helper_remains():
    """The infamous _make_synthetic_prices helper must stay deleted."""
    from app.services import backtest_service
    assert not hasattr(backtest_service, "_make_synthetic_prices"), (
        "synthetic price generator must not exist — see P0 audit"
    )


# ───────────────────────── P0#3 leaderboard ─────────────────────────

@pytest.mark.asyncio
async def test_leaderboard_returns_empty_when_no_picks(session):
    """Empty stock_picks table ⇒ empty leaderboard. No fake +5..+15% rows."""
    rows = await weekly_leaderboard(session, limit=10)
    assert rows == [], (
        "Leaderboard must NEVER fabricate returns. Got: " + repr(rows)
    )


@pytest.mark.asyncio
async def test_leaderboard_status_reports_emptiness(session):
    status = await leaderboard_status(session)
    assert status["has_data"] is False
    assert status["total_picks_tracked"] == 0


def test_no_mock_top30_constant():
    """Mock fallback removed from /stocks endpoint."""
    from app.api.v1.endpoints import stocks as stocks_ep
    assert not hasattr(stocks_ep, "_MOCK_TOP30"), (
        "_MOCK_TOP30 mock data must stay removed — see P0 audit"
    )


# ───────────────────────── P0#4 chip alignment ─────────────────────────

@pytest.mark.asyncio
async def test_chip_records_aligned_by_date(session):
    """Sparse chip data must be aligned to bar dates, not list index.

    Builds a tiny scenario: 3 price bars, only ONE chip row (the middle
    date). Index-based alignment would map chip[0] to bars[0] (wrong).
    Date-based alignment must produce chip_available=True only on the
    matching date.
    """
    from datetime import date as D

    from app.db.models import ChipData, DailyPrice
    from app.services.scanner_service import _bars_for

    s = Stock(symbol="ALIGN1", name="對齊測試", market="TWSE")
    session.add(s)
    await session.commit()
    await session.refresh(s)

    # 3 bars, 1 chip row (middle date only)
    session.add_all([
        DailyPrice(stock_id=s.id, date=D(2025, 1, 6),
                   open=100.0, high=101.0, low=99.0, close=100.5, volume=1000),
        DailyPrice(stock_id=s.id, date=D(2025, 1, 7),
                   open=100.5, high=102.0, low=100.0, close=101.5, volume=1100),
        DailyPrice(stock_id=s.id, date=D(2025, 1, 8),
                   open=101.5, high=103.0, low=101.0, close=102.5, volume=1200),
    ])
    session.add(ChipData(
        stock_id=s.id, date=D(2025, 1, 7),
        foreign_buy=500.0, investment_buy=200.0, dealer_buy=10.0,
    ))
    await session.commit()

    _bars, chip_records = await _bars_for(session, s.id)
    assert len(chip_records) == 3
    by_date = {r["date"]: r for r in chip_records}
    assert by_date["2025-01-06"]["chip_available"] is False
    assert by_date["2025-01-07"]["chip_available"] is True
    assert by_date["2025-01-07"]["foreign_buy"] == 500.0
    assert by_date["2025-01-08"]["chip_available"] is False
    # Index-based mapping would have put the chip on bars[0] — guard against
    # that specific regression.
    assert by_date["2025-01-06"]["foreign_buy"] == 0.0
