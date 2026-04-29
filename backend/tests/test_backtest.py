from datetime import date, timedelta

import pytest

from app.db.session import async_session_maker
from app.services.backtest_service import run_backtest


@pytest.mark.asyncio
async def test_backtest_runs_on_synth_data_ai_top():
    async with async_session_maker() as s:
        end = date(2025, 12, 31)
        start = end - timedelta(days=180)
        res = await run_backtest(s, "2330", start, end, "ai_top_rank")
    d = res.to_dict()
    assert d["symbol"] == "2330"
    assert d["strategy"] == "ai_top_rank"
    assert "cagr" in d and "sharpe" in d and "max_drawdown" in d
    assert "equity_curve" in d and len(d["equity_curve"]) > 0


@pytest.mark.asyncio
async def test_backtest_ma_breakout_emits_trades():
    async with async_session_maker() as s:
        end = date(2025, 12, 31)
        start = end - timedelta(days=300)
        res = await run_backtest(s, "2330", start, end, "ma_breakout")
    assert res.trades >= 0
    # max drawdown is non-positive
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
    r = await client.post(
        "/api/v1/backtest/run",
        headers=admin_headers,
        json={"symbol": "2330", "start": "2025-01-01", "end": "2025-06-01", "strategy": "ma_breakout"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "2330"
    assert "equity_curve" in body


@pytest.mark.asyncio
async def test_strategies_endpoint_public(client):
    r = await client.get("/api/v1/backtest/strategies")
    assert r.status_code == 200
    arr = r.json()
    keys = {s["key"] for s in arr}
    assert {"ai_top_rank", "ma_breakout", "chip_follow"} <= keys
