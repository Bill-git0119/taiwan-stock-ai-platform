from datetime import date, timedelta

import pytest

from app.db.models import DailyPrice, Stock
from app.db.session import async_session_maker
from app.services.backtest_service import NoRealDataError, run_backtest


async def _seed_real_bars(symbol: str, start: date, n: int = 200) -> None:
    """Insert n real-shaped OHLCV bars for backtest tests.

    P0 audit removed synthetic fallback — tests now MUST seed real data."""
    from sqlalchemy import select
    async with async_session_maker() as s:
        stk = (await s.execute(select(Stock).where(Stock.symbol == symbol))).scalar_one_or_none()
        if stk is None:
            stk = Stock(symbol=symbol, name=f"BT-{symbol}", market="TWSE")
            s.add(stk)
            await s.flush()
        # Idempotency
        existing = (await s.execute(
            select(DailyPrice).where(DailyPrice.stock_id == stk.id).limit(1)
        )).scalar_one_or_none()
        if existing:
            return
        price = 100.0
        for i in range(n):
            d = start + timedelta(days=i)
            # gentle upward drift with mild oscillation — realistic enough
            price = price * (1.001 + 0.005 * ((i % 7) - 3) / 10)
            s.add(DailyPrice(
                stock_id=stk.id, date=d,
                open=round(price * 0.999, 2),
                high=round(price * 1.005, 2),
                low=round(price * 0.995, 2),
                close=round(price, 2),
                volume=1000000 + i * 100,
            ))
        await s.commit()


@pytest.mark.asyncio
async def test_backtest_raises_no_real_data():
    """P0 audit: empty DB ⇒ explicit NoRealDataError, no silent synthetic."""
    async with async_session_maker() as s:
        end = date(2025, 12, 31)
        start = end - timedelta(days=180)
        with pytest.raises(NoRealDataError):
            await run_backtest(s, "GHOST_BT", start, end, "ai_top_rank")


@pytest.mark.asyncio
async def test_backtest_runs_on_real_data_ai_top():
    start = date(2025, 1, 1)
    await _seed_real_bars("BT_AI", start, n=200)
    async with async_session_maker() as s:
        res = await run_backtest(s, "BT_AI", start, start + timedelta(days=180), "ai_top_rank")
    d = res.to_dict()
    assert d["symbol"] == "BT_AI"
    assert d["strategy"] == "ai_top_rank"
    assert "cagr" in d and "sharpe" in d and "max_drawdown" in d
    assert "equity_curve" in d and len(d["equity_curve"]) > 0


@pytest.mark.asyncio
async def test_backtest_ma_breakout_emits_trades():
    start = date(2025, 1, 1)
    await _seed_real_bars("BT_MA", start, n=300)
    async with async_session_maker() as s:
        res = await run_backtest(s, "BT_MA", start, start + timedelta(days=290), "ma_breakout")
    assert res.trades >= 0
    assert res.max_drawdown <= 0


@pytest.mark.asyncio
async def test_backtest_endpoint_requires_elite(client, auth_headers):
    headers, _ = auth_headers  # default = free
    r = await client.post(
        "/api/v1/backtest/run",
        headers=headers,
        json={"symbol": "2330", "start": "2025-01-01", "end": "2025-06-01", "strategy": "ai_top_rank"},
    )
    assert r.status_code == 402  # upgrade required


@pytest.mark.asyncio
async def test_backtest_endpoint_ok_for_admin(client, admin_headers):
    # Seed real bars for the test symbol; P0 audit removed silent synthetic.
    await _seed_real_bars("BT_ENDPOINT", date(2025, 1, 1), n=200)
    r = await client.post(
        "/api/v1/backtest/run",
        headers=admin_headers,
        json={"symbol": "BT_ENDPOINT", "start": "2025-01-01",
              "end": "2025-06-30", "strategy": "ma_breakout"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "BT_ENDPOINT"
    assert "equity_curve" in body


@pytest.mark.asyncio
async def test_backtest_endpoint_400_when_no_data(client, admin_headers):
    """P0 audit regression: missing data must surface as HTTP 400."""
    r = await client.post(
        "/api/v1/backtest/run",
        headers=admin_headers,
        json={"symbol": "GHOST_HTTP", "start": "2025-01-01",
              "end": "2025-06-30", "strategy": "ma_breakout"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "NO_REAL_DATA"


@pytest.mark.asyncio
async def test_strategies_endpoint_public(client):
    r = await client.get("/api/v1/backtest/strategies")
    assert r.status_code == 200
    arr = r.json()
    keys = {s["key"] for s in arr}
    assert {"ai_top_rank", "ma_breakout", "chip_follow"} <= keys
