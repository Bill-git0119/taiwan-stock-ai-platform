"""Universe management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.cache_service import cached
from app.universe import manager, universe_builder

router = APIRouter()


@router.get("/active")
async def active(session: AsyncSession = Depends(get_db)):
    async def loader():
        rows = await manager.get_active_universe(session)
        return {
            "count": len(rows),
            "items": [
                {"symbol": r.symbol, "name": r.name, "sector": r.sector_zh,
                 "market": r.market, "rank": r.rank_by_notional,
                 "notional_twd": r.notional_twd,
                 "avg_volume_20d": r.avg_volume_20d,
                 "last_close": r.last_close}
                for r in rows
            ],
        }
    return await cached("universe-active", loader, ttl=600)


@router.get("/sectors")
async def sectors(session: AsyncSession = Depends(get_db)):
    async def loader():
        return {"sectors": await manager.sector_breakdown(session)}
    return await cached("universe-sectors", loader, ttl=600)


@router.post("/rebuild")
async def rebuild(session: AsyncSession = Depends(get_db)):
    """Manual trigger to rebuild the snapshot. Idempotent."""
    return await universe_builder.build_snapshot(session)
