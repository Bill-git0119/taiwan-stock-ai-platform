"""Scanner / Movers / Sectors endpoints + service-level tests."""
from __future__ import annotations

import math
from datetime import date, timedelta

import pytest
import pytest_asyncio

from app.db.models import ChipData, DailyPrice, Stock
from app.db.session import async_session_maker
from app.services.scanner_service import (
    _edge_score, scan_movers, scan_sectors, scan_universe,
)


def _bars_uptrend(n: int = 250, base: float = 100.0) -> list[dict]:
    """Synthetic clean uptrend with breakout on the final bar.

    Long enough (250 bars) for EMA200, ADX(14), and the regime classifier
    to reliably tag this as `trending_up`.
    """
    out = []
    px = base
    for i in range(n):
        px += 0.7 + 0.4 * math.sin(i / 5)
        c = round(px, 2)
        out.append({"open": c - 0.4, "high": c + 0.7, "low": c - 0.7, "close": c, "volume": 800_000})
    # Force last-bar breakout + volume spike
    last_high = max(b["high"] for b in out[:-1])
    out[-1]["close"] = round(last_high * 1.04, 2)
    out[-1]["high"]  = round(out[-1]["close"] + 0.5, 2)
    out[-1]["volume"] = 2_500_000
    return out


def _bars_flat(n: int = 250, base: float = 50.0) -> list[dict]:
    return [
        {"open": base, "high": base + 0.2, "low": base - 0.2, "close": base + (i % 2) * 0.05, "volume": 500_000}
        for i in range(n)
    ]


@pytest_asyncio.fixture
async def seeded_db():
    """Seed two stocks: 'UP' (clean uptrend) + 'FLAT' (no setup)."""
    from sqlalchemy import delete, select
    async with async_session_maker() as s:
        # Hard reset any leftover state from prior tests in the session
        await s.execute(delete(ChipData))
        await s.execute(delete(DailyPrice))
        await s.execute(delete(Stock).where(Stock.symbol.in_(["UPX", "FLATX"])))
        await s.commit()
        up = Stock(symbol="UPX", name="升勢股", market="TWSE", sector="半導體")
        fl = Stock(symbol="FLATX", name="盤整股", market="TWSE", sector="金融")
        s.add_all([up, fl])
        await s.commit()
        await s.refresh(up)
        await s.refresh(fl)

        today = date.today()
        up_bars = _bars_uptrend()
        fl_bars = _bars_flat()
        for i, b in enumerate(up_bars):
            d = today - timedelta(days=len(up_bars) - i)
            s.add(DailyPrice(stock_id=up.id, date=d, open=b["open"], high=b["high"],
                             low=b["low"], close=b["close"], volume=b["volume"]))
        for i, b in enumerate(fl_bars):
            d = today - timedelta(days=len(fl_bars) - i)
            s.add(DailyPrice(stock_id=fl.id, date=d, open=b["open"], high=b["high"],
                             low=b["low"], close=b["close"], volume=b["volume"]))
        # add chip rows for UPX so foreign_streak triggers
        for i in range(20):
            d = today - timedelta(days=20 - i)
            s.add(ChipData(stock_id=up.id, date=d,
                           foreign_buy=5_000_000, investment_buy=1_000_000, dealer_buy=0))
        await s.commit()
    yield
    async with async_session_maker() as s:
        from sqlalchemy import delete
        await s.execute(delete(ChipData))
        await s.execute(delete(DailyPrice))
        await s.execute(delete(Stock))
        await s.commit()


def test_edge_score_zero_when_no_trade():
    assert _edge_score({"bias": "NO_TRADE"}) == 0.0


def test_edge_score_rises_with_breakout_and_rr():
    plan = {
        "bias": "LONG", "confidence": 0.7, "risk_reward": 2.5,
        "indicators": {"breakout_20": True, "volume_spike": 1.8, "ma_alignment": True},
        "chip": {"foreign_streak": 4},
    }
    assert _edge_score(plan) > 60


@pytest.mark.asyncio
async def test_scan_universe_returns_long_for_uptrend(seeded_db):
    async with async_session_maker() as s:
        out = await scan_universe(s, bias_filter="LONG", min_rr=1.5)
    items = {r["symbol"]: r for r in out["items"]}
    # UPX should be picked up — it has chip flow + breakout, the strongest setup
    assert "UPX" in items
    upx = items["UPX"]
    assert upx["bias"] == "LONG"
    assert upx["risk_reward"] >= 1.5
    assert upx["edge"] > 0
    # If FLATX also matched, UPX must outrank it — sorted by edge
    if "FLATX" in items:
        assert upx["edge"] > items["FLATX"]["edge"]


@pytest.mark.asyncio
async def test_scan_universe_no_filter_returns_all(seeded_db):
    async with async_session_maker() as s:
        out = await scan_universe(s)
    assert out["scanned"] >= 2


@pytest.mark.asyncio
async def test_scan_movers_categories(seeded_db):
    async with async_session_maker() as s:
        out = await scan_movers(s)
    for key in ("gainers", "losers", "gap_ups", "volume_spikes", "breakouts",
                "momentum_5d", "momentum_20d"):
        assert key in out
    assert out["scanned"] >= 2


@pytest.mark.asyncio
async def test_scan_sectors_groups_by_sector(seeded_db):
    async with async_session_maker() as s:
        out = await scan_sectors(s)
    secs = {x["sector"] for x in out["sectors"]}
    assert "半導體" in secs or "金融" in secs


# ─────────────────────────── HTTP endpoint smoke ───────────────────────────

@pytest.mark.asyncio
async def test_scan_endpoint(client, seeded_db):
    r = await client.get("/api/v1/scanner/scan?bias=LONG&min_rr=1.5")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "scanned" in body and "matched" in body


@pytest.mark.asyncio
async def test_movers_endpoint(client, seeded_db):
    r = await client.get("/api/v1/scanner/movers")
    assert r.status_code == 200
    body = r.json()
    assert "gainers" in body and "breakouts" in body


@pytest.mark.asyncio
async def test_sectors_endpoint(client, seeded_db):
    r = await client.get("/api/v1/scanner/sectors")
    assert r.status_code == 200
    assert "sectors" in r.json()
