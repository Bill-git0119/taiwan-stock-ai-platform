"""Intelligence engine — extractors + aggregator (network-free)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import List

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.db.models import DailyPrice, Stock
from app.db.session import async_session_maker
from app.intelligence.news import _extract_symbols  # noqa: SLF001
from app.intelligence.sector_rotation import sector_rotation
from app.intelligence.volume_anomaly import volume_anomalies


def test_extract_symbols_picks_taiwan_codes():
    out = _extract_symbols("台積電 2330 法說會看好 2024 年展望", "鴻海 2317")
    assert "2330" in out and "2317" in out
    assert "2024" not in out


def test_extract_symbols_skips_years():
    out = _extract_symbols("2023 年回顧", "")
    assert out == []


@pytest_asyncio.fixture
async def seeded_intel_db():
    """Two sectors, three symbols, 30 bars each."""
    today = date.today()
    async with async_session_maker() as s:
        # clean leftovers
        await s.execute(delete(DailyPrice))
        await s.execute(delete(Stock).where(Stock.symbol.in_(["IA", "IB", "IC"])))
        await s.commit()
        a = Stock(symbol="IA", name="強A", market="TWSE", sector="半導體")
        b = Stock(symbol="IB", name="弱B", market="TWSE", sector="金融")
        c = Stock(symbol="IC", name="量爆C", market="TWSE", sector="半導體")
        s.add_all([a, b, c])
        await s.commit()
        for st in (a, b, c):
            await s.refresh(st)
        for i in range(30):
            d = today - timedelta(days=29 - i)
            # IA: strong uptrend
            s.add(DailyPrice(stock_id=a.id, date=d, open=100 + i, high=102 + i,
                             low=99 + i, close=101 + i, volume=500_000))
            # IB: flat
            s.add(DailyPrice(stock_id=b.id, date=d, open=50, high=50.5,
                             low=49.5, close=50, volume=500_000))
            # IC: flat until last bar volume spike
            vol = 500_000 if i < 29 else 5_000_000
            s.add(DailyPrice(stock_id=c.id, date=d, open=80, high=81,
                             low=79, close=80, volume=vol))
        await s.commit()
    yield
    async with async_session_maker() as s:
        await s.execute(delete(DailyPrice))
        await s.execute(delete(Stock).where(Stock.symbol.in_(["IA", "IB", "IC"])))
        await s.commit()


@pytest.mark.asyncio
async def test_sector_rotation_orders_by_strength(seeded_intel_db):
    async with async_session_maker() as s:
        out = await sector_rotation(s)
    secs = {row["sector"]: row for row in out["sectors"]}
    assert "半導體" in secs and "金融" in secs
    # 半導體 has IA (strong uptrend) → must rank above 金融 (flat)
    assert secs["半導體"]["return_20d"] > secs["金融"]["return_20d"]
    assert secs["半導體"]["rs_rank"] < secs["金融"]["rs_rank"]


@pytest.mark.asyncio
async def test_volume_anomaly_finds_spike(seeded_intel_db):
    async with async_session_maker() as s:
        out = await volume_anomalies(s, min_ratio=2.0)
    syms = {r["symbol"] for r in out}
    assert "IC" in syms                 # last-bar 10× spike
    assert "IB" not in syms             # flat volume
    ic = next(r for r in out if r["symbol"] == "IC")
    assert ic["ratio"] >= 2.0
