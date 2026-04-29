from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChipData, DailyPrice, Stock
from app.db.session import get_db

router = APIRouter()


class MarketSummary(BaseModel):
    as_of: Optional[date] = None
    stock_count: int
    total_volume: int
    foreign_net: float
    investment_net: float
    dealer_net: float
    gainers: int
    losers: int


@router.get("/summary", response_model=MarketSummary)
async def market_summary(session: AsyncSession = Depends(get_db)) -> MarketSummary:
    stock_count = (await session.execute(select(func.count(Stock.id)))).scalar() or 0

    latest_date = (
        await session.execute(select(func.max(DailyPrice.date)))
    ).scalar()

    if latest_date is None:
        return MarketSummary(
            as_of=None,
            stock_count=int(stock_count),
            total_volume=0,
            foreign_net=0.0,
            investment_net=0.0,
            dealer_net=0.0,
            gainers=0,
            losers=0,
        )

    total_volume = (
        await session.execute(
            select(func.coalesce(func.sum(DailyPrice.volume), 0)).where(DailyPrice.date == latest_date)
        )
    ).scalar() or 0

    foreign_net = (
        await session.execute(
            select(func.coalesce(func.sum(ChipData.foreign_buy), 0)).where(ChipData.date == latest_date)
        )
    ).scalar() or 0
    investment_net = (
        await session.execute(
            select(func.coalesce(func.sum(ChipData.investment_buy), 0)).where(ChipData.date == latest_date)
        )
    ).scalar() or 0
    dealer_net = (
        await session.execute(
            select(func.coalesce(func.sum(ChipData.dealer_buy), 0)).where(ChipData.date == latest_date)
        )
    ).scalar() or 0

    gainers = (
        await session.execute(
            select(func.count(DailyPrice.id)).where(
                DailyPrice.date == latest_date, DailyPrice.close > DailyPrice.open
            )
        )
    ).scalar() or 0
    losers = (
        await session.execute(
            select(func.count(DailyPrice.id)).where(
                DailyPrice.date == latest_date, DailyPrice.close < DailyPrice.open
            )
        )
    ).scalar() or 0

    return MarketSummary(
        as_of=latest_date,
        stock_count=int(stock_count),
        total_volume=int(total_volume),
        foreign_net=float(foreign_net),
        investment_net=float(investment_net),
        dealer_net=float(dealer_net),
        gainers=int(gainers),
        losers=int(losers),
    )
