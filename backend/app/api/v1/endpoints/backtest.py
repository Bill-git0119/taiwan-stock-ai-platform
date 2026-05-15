from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_plan
from app.db.models import Plan, User
from app.db.session import get_db
from app.services.backtest_service import NoRealDataError, run_backtest
from ai_engine.predictor import predict
from sqlalchemy import select
from app.db.models import DailyPrice, Stock

router = APIRouter()

Strategy = Literal["ai_top_rank", "ma_breakout", "chip_follow"]


class BacktestRequest(BaseModel):
    symbol: str = Field(..., examples=["2330"])
    start: date
    end: date
    strategy: Strategy = "ai_top_rank"


@router.post("/run")
async def run_bt(
    body: BacktestRequest,
    user: User = Depends(require_plan(Plan.ELITE)),  # Elite-only
    session: AsyncSession = Depends(get_db),
):
    try:
        res = await run_backtest(session, body.symbol, body.start, body.end, body.strategy)
    except NoRealDataError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "NO_REAL_DATA", "message": str(e), "symbol": body.symbol},
        ) from e
    return res.to_dict()


@router.get("/strategies")
async def list_strategies():
    return [
        {"key": "ai_top_rank", "name": "AI Top Rank", "description": "AI 總分 ≥ 80 進場，停損 5%，1.3R 停利"},
        {"key": "ma_breakout", "name": "均線突破",     "description": "突破 20MA 進場，停損 5%，1.3R 停利"},
        {"key": "chip_follow", "name": "籌碼跟單",     "description": "外資+投信淨買進場，停損 5%，1.3R 停利"},
    ]


@router.get("/predict/{symbol}")
async def predict_symbol(
    symbol: str,
    user: User = Depends(require_plan(Plan.PRO)),
    session: AsyncSession = Depends(get_db),
):
    stock = (await session.execute(select(Stock).where(Stock.symbol == symbol))).scalar_one_or_none()
    closes: list[float] = []
    if stock is not None:
        rows = (await session.execute(
            select(DailyPrice).where(DailyPrice.stock_id == stock.id)
            .order_by(DailyPrice.date.desc()).limit(120)
        )).scalars().all()
        closes = [float(r.close) for r in reversed(rows)]
    if not closes or len(closes) < 30:
        # Iron rule: never substitute synthetic data. Tell the caller.
        raise HTTPException(
            status_code=400,
            detail={
                "error": "NO_REAL_DATA",
                "symbol": symbol,
                "bars_available": len(closes),
                "bars_required": 30,
            },
        )
    p = predict(symbol, closes)
    if not p:
        return {"symbol": symbol, "error": "insufficient_data"}
    return p.to_dict()
