"""Load a stock's raw data from DB and run ai_engine scoring."""
from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_engine.scoring import ScoredStock, rank_top_n, score_stock
from app.db.models import ChipData, DailyPrice, Score, Stock


async def _build_payload(session: AsyncSession, stock: Stock, as_of: date) -> dict:
    price_rows = (
        await session.execute(
            select(DailyPrice)
            .where(DailyPrice.stock_id == stock.id, DailyPrice.date <= as_of)
            .order_by(DailyPrice.date.asc())
            .limit(120)
        )
    ).scalars().all()
    closes = [float(p.close) for p in price_rows]
    chip_rows = (
        await session.execute(
            select(ChipData)
            .where(ChipData.stock_id == stock.id, ChipData.date <= as_of)
            .order_by(ChipData.date.asc())
            .limit(120)
        )
    ).scalars().all()
    # Date-keyed alignment — see scanner_service for the same fix.
    chip_by_date = {str(c.date): c for c in chip_rows}
    chip_records: list[dict] = []
    for p in price_rows:
        c = chip_by_date.get(str(p.date))
        chip_records.append({
            "date": str(p.date),
            "foreign_buy": float(c.foreign_buy or 0) if c else 0.0,
            "investment_buy": float(c.investment_buy or 0) if c else 0.0,
            "dealer_buy": float(c.dealer_buy or 0) if c else 0.0,
            "volume": int(p.volume or 0),
            "chip_available": c is not None,
        })
    return {
        "symbol": stock.symbol,
        "name": stock.name,
        "chip_records": chip_records,
        "fundamentals": {},  # TODO: wire MOPS fundamentals
        "closes": closes,
    }


async def score_symbol(session: AsyncSession, symbol: str, as_of: Optional[date] = None) -> Optional[ScoredStock]:
    as_of = as_of or date.today()
    res = await session.execute(select(Stock).where(Stock.symbol == symbol))
    stock = res.scalar_one_or_none()
    if stock is None:
        return None
    payload = await _build_payload(session, stock, as_of)
    return score_stock(payload)


async def score_all(session: AsyncSession, as_of: Optional[date] = None) -> List[ScoredStock]:
    as_of = as_of or date.today()
    stocks = (await session.execute(select(Stock))).scalars().all()
    payloads = [await _build_payload(session, s, as_of) for s in stocks]
    return rank_top_n(payloads, n=len(payloads))


async def persist_scores(session: AsyncSession, scored: List[ScoredStock], as_of: date) -> int:
    sym_to_id = {
        s.symbol: s.id
        for s in (await session.execute(select(Stock))).scalars().all()
    }
    n = 0
    for sc in scored:
        sid = sym_to_id.get(sc.symbol)
        if sid is None:
            continue
        existing = (
            await session.execute(
                select(Score).where(Score.stock_id == sid, Score.date == as_of)
            )
        ).scalar_one_or_none()
        if existing:
            existing.chip_score = sc.chip_score
            existing.fundamental_score = sc.fundamental_score
            existing.technical_score = sc.technical_score
            existing.total_score = sc.total_score
            existing.reason = sc.reason
        else:
            session.add(
                Score(
                    stock_id=sid,
                    date=as_of,
                    chip_score=sc.chip_score,
                    fundamental_score=sc.fundamental_score,
                    technical_score=sc.technical_score,
                    total_score=sc.total_score,
                    reason=sc.reason,
                )
            )
        n += 1
    await session.commit()
    return n


async def load_top_n(session: AsyncSession, n: int = 30, as_of: Optional[date] = None) -> List[dict]:
    """Read TOP-N from persisted `scores` for `as_of` (or most recent)."""
    if as_of is None:
        latest = (await session.execute(select(Score.date).order_by(Score.date.desc()).limit(1))).scalar()
        if latest is None:
            return []
        as_of = latest

    rows = (
        await session.execute(
            select(Score, Stock)
            .join(Stock, Stock.id == Score.stock_id)
            .where(Score.date == as_of)
            .order_by(Score.total_score.desc())
            .limit(n)
        )
    ).all()
    return [
        {
            "symbol": st.symbol,
            "name": st.name,
            "chip_score": sc.chip_score,
            "fundamental_score": sc.fundamental_score,
            "technical_score": sc.technical_score,
            "total_score": sc.total_score,
            "reason": sc.reason or "",
        }
        for sc, st in rows
    ]


async def load_top10(session: AsyncSession, as_of: Optional[date] = None) -> List[dict]:
    return await load_top_n(session, n=10, as_of=as_of)
