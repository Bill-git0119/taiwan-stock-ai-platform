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


# Note: mock fallback removed. Iron rule: empty DB ⇒ empty response, not
# fabricated stocks. The collector must populate `scores` for top10 to work.


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
    """Real top-30 from persisted scores. No mock fallback — empty DB returns
    an empty list so the UI can show an honest "資料尚未灌入" state."""
    async def loader():
        return await load_top_n(session, n=30)
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
        raise HTTPException(status_code=404, detail=f"stock {symbol} not found")

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
