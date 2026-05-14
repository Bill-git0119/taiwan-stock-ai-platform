"""UniverseManager — single source of truth for "which symbols are tracked"."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Iterable, List, Optional

from sqlalchemy import desc, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UniverseSnapshot
from app.universe.curated import deduplicated


async def _latest_snapshot_date(session: AsyncSession) -> Optional[date]:
    return (await session.execute(
        select(func.max(UniverseSnapshot.date))
    )).scalar()


async def get_active_universe(session: AsyncSession,
                              on_date: date | None = None,
                              limit: int | None = None) -> List[UniverseSnapshot]:
    """Active symbols on the given (or most recent) snapshot date."""
    on_date = on_date or await _latest_snapshot_date(session)
    if on_date is None:
        # No snapshot yet — fall back to the curated list (active=True)
        # via a synthetic list. This keeps the scanner working on day 1.
        return []
    q = (select(UniverseSnapshot)
         .where(UniverseSnapshot.date == on_date,
                UniverseSnapshot.is_active == True)  # noqa: E712
         .order_by(UniverseSnapshot.rank_by_notional.asc()))
    if limit:
        q = q.limit(limit)
    return list((await session.execute(q)).scalars().all())


async def get_active_symbols(session: AsyncSession,
                             limit: int | None = None) -> List[str]:
    rows = await get_active_universe(session, limit=limit)
    if rows:
        return [r.symbol for r in rows]
    # fallback to curated
    return [c[0] for c in deduplicated()][: limit or len(deduplicated())]


async def get_sector_members(session: AsyncSession,
                             sector_zh: str) -> List[str]:
    on_date = await _latest_snapshot_date(session)
    if on_date is None:
        return [c[0] for c in deduplicated() if c[3] == sector_zh]
    rows = (await session.execute(
        select(UniverseSnapshot.symbol)
        .where(UniverseSnapshot.date == on_date,
               UniverseSnapshot.sector_zh == sector_zh,
               UniverseSnapshot.is_active == True)  # noqa: E712
    )).scalars().all()
    return list(rows)


async def get_liquid_symbols(session: AsyncSession,
                             top_n: int = 50) -> List[str]:
    rows = await get_active_universe(session, limit=top_n)
    return [r.symbol for r in rows]


async def sector_breakdown(session: AsyncSession) -> dict:
    rows = await get_active_universe(session)
    by: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        by[r.sector_zh].append(r.symbol)
    return {k: v for k, v in sorted(by.items(), key=lambda kv: -len(kv[1]))}
