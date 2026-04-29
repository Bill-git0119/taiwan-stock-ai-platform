from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user, current_user_optional, plan_of, top_n_for
from app.db.models import DailyPrice, Favorite, Plan, Score, Stock, User
from app.db.session import get_db
from app.services.cache_service import cached
from app.services.scoring_pipeline import load_top_n, score_symbol

router = APIRouter()


class StockScore(BaseModel):
    symbol: str = Field(..., description="股票代號")
    name: str
    chip_score: float
    fundamental_score: float
    technical_score: float
    total_score: float
    reason: str = ""


class TierMeta(BaseModel):
    plan: str
    limit: int
    showing: int
    total_available: int
    upgrade_message: Optional[str] = None


class Top10Response(BaseModel):
    items: List[StockScore]
    tier: TierMeta


class PricePoint(BaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


class StockDetail(BaseModel):
    symbol: str
    name: str
    market: str
    sector: Optional[str] = None
    latest_score: Optional[StockScore] = None
    prices: List[PricePoint] = []


# ───────── mock fallback (first run, before collector populates DB) ─────────

_MOCK_TOP30: List[StockScore] = [
    StockScore(symbol="2330", name="台積電",   chip_score=92, fundamental_score=95, technical_score=88, total_score=92.15, reason="外資連買5日 + ROE 28% + MA多頭排列"),
    StockScore(symbol="2454", name="聯發科",   chip_score=86, fundamental_score=90, technical_score=82, total_score=86.40, reason="外資連買3日 + EPS+35% + MACD金叉"),
    StockScore(symbol="2317", name="鴻海",     chip_score=84, fundamental_score=78, technical_score=85, total_score=82.15, reason="量能放大1.8x + 突破20日高"),
    StockScore(symbol="2303", name="聯電",     chip_score=80, fundamental_score=72, technical_score=83, total_score=77.95, reason="外資連買2日 + MA多頭排列"),
    StockScore(symbol="3008", name="大立光",   chip_score=75, fundamental_score=85, technical_score=78, total_score=79.25, reason="ROE 22% + EPS+28%"),
    StockScore(symbol="2308", name="台達電",   chip_score=78, fundamental_score=80, technical_score=72, total_score=77.20, reason="投信連買3日 + MACD金叉"),
    StockScore(symbol="2881", name="富邦金",   chip_score=72, fundamental_score=73, technical_score=68, total_score=71.45, reason="外資連買3日 + 量能放大"),
    StockScore(symbol="2882", name="國泰金",   chip_score=70, fundamental_score=74, technical_score=66, total_score=70.40, reason="投信連買2日"),
    StockScore(symbol="2603", name="長榮",     chip_score=78, fundamental_score=65, technical_score=82, total_score=74.65, reason="量能放大2.1x + 突破20日高"),
    StockScore(symbol="2412", name="中華電",   chip_score=70, fundamental_score=80, technical_score=65, total_score=72.25, reason="ROE 15% + 穩健"),
    StockScore(symbol="1216", name="統一",     chip_score=66, fundamental_score=78, technical_score=62, total_score=69.30, reason="ROE 18%"),
    StockScore(symbol="2891", name="中信金",   chip_score=68, fundamental_score=72, technical_score=64, total_score=68.40, reason="外資連買2日"),
    StockScore(symbol="2002", name="中鋼",     chip_score=62, fundamental_score=58, technical_score=72, total_score=63.10, reason="MACD金叉"),
    StockScore(symbol="2207", name="和泰車",   chip_score=64, fundamental_score=82, technical_score=58, total_score=68.40, reason="ROE 20%"),
    StockScore(symbol="2884", name="玉山金",   chip_score=68, fundamental_score=70, technical_score=60, total_score=66.20, reason="投信連買2日"),
    StockScore(symbol="2885", name="元大金",   chip_score=66, fundamental_score=68, technical_score=58, total_score=64.50, reason="量能放大"),
    StockScore(symbol="2886", name="兆豐金",   chip_score=64, fundamental_score=72, technical_score=56, total_score=64.40, reason="ROE 14%"),
    StockScore(symbol="2890", name="永豐金",   chip_score=62, fundamental_score=68, technical_score=54, total_score=61.50, reason="—"),
    StockScore(symbol="2615", name="萬海",     chip_score=70, fundamental_score=58, technical_score=76, total_score=68.30, reason="MA多頭排列"),
    StockScore(symbol="2609", name="陽明",     chip_score=68, fundamental_score=55, technical_score=74, total_score=65.95, reason="量能放大"),
    StockScore(symbol="3034", name="聯詠",     chip_score=72, fundamental_score=80, technical_score=66, total_score=72.30, reason="ROE 22% + EPS+24%"),
    StockScore(symbol="3711", name="日月光投控", chip_score=70, fundamental_score=72, technical_score=68, total_score=70.20, reason="外資連買2日"),
    StockScore(symbol="2379", name="瑞昱",     chip_score=68, fundamental_score=78, technical_score=62, total_score=70.10, reason="EPS+30%"),
    StockScore(symbol="2382", name="廣達",     chip_score=82, fundamental_score=72, technical_score=78, total_score=78.10, reason="外資連買4日 + AI 概念"),
    StockScore(symbol="2357", name="華碩",     chip_score=66, fundamental_score=70, technical_score=64, total_score=66.90, reason="—"),
    StockScore(symbol="2353", name="宏碁",     chip_score=60, fundamental_score=62, technical_score=58, total_score=60.20, reason="—"),
    StockScore(symbol="3231", name="緯創",     chip_score=78, fundamental_score=68, technical_score=80, total_score=75.00, reason="量能放大1.6x + AI 受惠"),
    StockScore(symbol="2376", name="技嘉",     chip_score=72, fundamental_score=70, technical_score=74, total_score=71.80, reason="MACD金叉"),
    StockScore(symbol="6505", name="台塑化",   chip_score=58, fundamental_score=64, technical_score=52, total_score=58.40, reason="—"),
    StockScore(symbol="1303", name="南亞",     chip_score=56, fundamental_score=62, technical_score=50, total_score=56.10, reason="—"),
]


def _build_tier(rows: List[StockScore], user: Optional[User]) -> Top10Response:
    plan = plan_of(user)
    cap = top_n_for(user)
    showing = min(cap, len(rows))
    items = rows[:showing]
    upgrade_msg: Optional[str] = None
    if plan == Plan.FREE:
        upgrade_msg = "升級 PRO（NT$299/月）解鎖 TOP10、即時訊號、主力籌碼"
    elif plan == Plan.PRO:
        upgrade_msg = "升級 ELITE（NT$1499/月）解鎖 TOP30、LINE 推播、回測"
    return Top10Response(
        items=items,
        tier=TierMeta(
            plan=plan, limit=cap, showing=showing, total_available=len(rows),
            upgrade_message=upgrade_msg,
        ),
    )


# ───────── endpoints ─────────

async def _resolve_top30(session: AsyncSession) -> List[StockScore]:
    async def loader():
        rows = await load_top_n(session, n=30)
        if rows:
            return rows
        # Fallback while collector hasn't run yet.
        return [s.model_dump() for s in sorted(_MOCK_TOP30, key=lambda s: s.total_score, reverse=True)]
    cached_rows = await cached("stocks:top30", loader, ttl=60)
    return [StockScore(**r) for r in cached_rows]


@router.get("/top10", response_model=Top10Response)
async def get_top10(
    user: Optional[User] = Depends(current_user_optional),
    session: AsyncSession = Depends(get_db),
):
    """Tier-aware: FREE→3, PRO→10, ELITE→30. Anonymous = FREE."""
    return _build_tier(await _resolve_top30(session), user)


@router.get("/{symbol}", response_model=StockDetail)
async def get_stock(symbol: str, session: AsyncSession = Depends(get_db)) -> StockDetail:
    result = await session.execute(select(Stock).where(Stock.symbol == symbol))
    stock = result.scalar_one_or_none()
    if stock is None:
        mock = next((m for m in _MOCK_TOP30 if m.symbol == symbol), None)
        if mock is None:
            raise HTTPException(status_code=404, detail=f"stock {symbol} not found")
        return StockDetail(symbol=mock.symbol, name=mock.name, market="TWSE", latest_score=mock, prices=[])

    prices = (
        await session.execute(
            select(DailyPrice)
            .where(DailyPrice.stock_id == stock.id)
            .order_by(DailyPrice.date.asc())
            .limit(120)
        )
    ).scalars().all()

    latest = (
        await session.execute(
            select(Score).where(Score.stock_id == stock.id).order_by(Score.date.desc()).limit(1)
        )
    ).scalar_one_or_none()

    score_payload: Optional[StockScore]
    if latest is None:
        scored = await score_symbol(session, symbol)
        score_payload = StockScore(**scored.to_dict()) if scored else None
    else:
        score_payload = StockScore(
            symbol=stock.symbol, name=stock.name,
            chip_score=latest.chip_score, fundamental_score=latest.fundamental_score,
            technical_score=latest.technical_score, total_score=latest.total_score,
            reason=latest.reason or "",
        )

    return StockDetail(
        symbol=stock.symbol, name=stock.name, market=stock.market, sector=stock.sector,
        latest_score=score_payload,
        prices=[
            PricePoint(date=p.date, open=p.open, high=p.high, low=p.low, close=p.close, volume=p.volume)
            for p in prices
        ],
    )


# ───────── favorites (login required) ─────────

class FavoriteIn(BaseModel):
    symbol: str


@router.get("/me/favorites", response_model=List[str])
async def list_favorites(user: User = Depends(current_user), session: AsyncSession = Depends(get_db)):
    rows = (
        await session.execute(select(Favorite).where(Favorite.user_id == user.id))
    ).scalars().all()
    return [r.symbol for r in rows]


@router.post("/me/favorites")
async def add_favorite(body: FavoriteIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_db)):
    existing = (
        await session.execute(
            select(Favorite).where(Favorite.user_id == user.id, Favorite.symbol == body.symbol)
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(Favorite(user_id=user.id, symbol=body.symbol))
        await session.commit()
    return {"ok": True}


@router.delete("/me/favorites/{symbol}")
async def remove_favorite(symbol: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_db)):
    existing = (
        await session.execute(
            select(Favorite).where(Favorite.user_id == user.id, Favorite.symbol == symbol)
        )
    ).scalar_one_or_none()
    if existing:
        await session.delete(existing)
        await session.commit()
    return {"ok": True}
