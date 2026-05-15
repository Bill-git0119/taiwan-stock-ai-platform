"""Pick-tracking + leaderboard — REAL data only.

Iron rule: never fabricate performance numbers. The leaderboard reflects
exactly what `stock_picks` measured. Empty table → empty leaderboard +
"tracking_started_at" hint so the caller knows when real data will arrive.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import List

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import StockPick


async def weekly_leaderboard(session: AsyncSession, limit: int = 10) -> List[dict]:
    today = date.today()
    week_ago = today - timedelta(days=7)
    rows = (
        await session.execute(
            select(StockPick)
            .where(StockPick.date >= week_ago)
            .order_by(desc(StockPick.return_pct))
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "rank": i + 1,
            "symbol": r.symbol, "name": r.name,
            "entry_price": r.entry_price,
            "return_pct": round(r.return_pct, 4),
            "picked_on": r.date.isoformat(),
        }
        for i, r in enumerate(rows)
    ]


async def leaderboard_status(session: AsyncSession) -> dict:
    """How far along is real pick tracking? Lets the UI explain empty state
    honestly instead of pretending there are results."""
    total = (await session.execute(select(func.count(StockPick.id)))).scalar() or 0
    earliest = (await session.execute(select(func.min(StockPick.date)))).scalar()
    latest = (await session.execute(select(func.max(StockPick.date)))).scalar()
    return {
        "total_picks_tracked": int(total),
        "tracking_started_at": earliest.isoformat() if earliest else None,
        "latest_pick_at": latest.isoformat() if latest else None,
        "has_data": total > 0,
    }


async def record_picks(session: AsyncSession, day: date, picks: list[dict]) -> int:
    """Snapshot today's TOP picks for later return-tracking."""
    n = 0
    for rank, p in enumerate(picks, start=1):
        existing = (
            await session.execute(
                select(StockPick).where(StockPick.date == day, StockPick.symbol == p["symbol"])
            )
        ).scalar_one_or_none()
        if existing:
            continue
        session.add(StockPick(
            date=day, symbol=p["symbol"], name=p.get("name", ""),
            rank=rank, entry_price=float(p.get("entry_price", 0.0)),
        ))
        n += 1
    await session.commit()
    return n
