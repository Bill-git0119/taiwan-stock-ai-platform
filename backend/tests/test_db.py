from datetime import date

import pytest
from sqlalchemy import select

from app.db.models import ChipData, DailyPrice, Score, Stock
from app.db.session import async_session_maker
from app.services.scoring_pipeline import load_top10, persist_scores
from ai_engine.scoring import ScoredStock


@pytest.mark.asyncio
async def test_crud_stock_and_price():
    today = date(2026, 4, 23)
    async with async_session_maker() as s:
        stock = Stock(symbol="DB0001", name="測試A", market="TWSE")
        s.add(stock)
        await s.flush()
        s.add(DailyPrice(stock_id=stock.id, date=today, open=100, high=105, low=99, close=104, volume=1000))
        s.add(ChipData(stock_id=stock.id, date=today, foreign_buy=500, investment_buy=200, dealer_buy=-100))
        await s.commit()

        got = (await s.execute(select(Stock).where(Stock.symbol == "DB0001"))).scalar_one()
        assert got.name == "測試A"
        prices = (await s.execute(select(DailyPrice).where(DailyPrice.stock_id == got.id))).scalars().all()
        assert len(prices) == 1
        assert prices[0].close == 104
        chips = (await s.execute(select(ChipData).where(ChipData.stock_id == got.id))).scalars().all()
        assert len(chips) == 1
        assert chips[0].foreign_buy == 500


@pytest.mark.asyncio
async def test_persist_and_load_top10():
    today = date(2026, 4, 22)
    async with async_session_maker() as s:
        for i in range(12):
            s.add(Stock(symbol=f"T{i:04d}", name=f"名{i}"))
        await s.commit()

        scored = [
            ScoredStock(
                symbol=f"T{i:04d}", name=f"名{i}",
                chip_score=50 + i, fundamental_score=40 + i,
                technical_score=30 + i, total_score=50 + i * 2,
                reason=f"reason {i}",
            )
            for i in range(12)
        ]
        n = await persist_scores(s, scored, today)
        assert n == 12

        top = await load_top10(s, as_of=today)
        assert len(top) == 10
        scores = [r["total_score"] for r in top]
        assert scores == sorted(scores, reverse=True)
        assert top[0]["symbol"] == "T0011"  # highest total_score
