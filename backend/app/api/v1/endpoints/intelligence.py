"""Market intelligence endpoints — news, sectors, volume anomalies, PTT."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.intelligence.aggregator import collect_intelligence
from app.intelligence.news import fetch_news, symbol_news
from app.intelligence.ptt import hot_topics
from app.intelligence.sector_rotation import sector_rotation
from app.intelligence.volume_anomaly import volume_anomalies
from app.services.cache_service import cached

router = APIRouter()


@router.get("/news")
async def news(limit: int = Query(30, ge=1, le=100)):
    async def loader():
        items = await fetch_news(limit=limit)
        return {"count": len(items), "items": [i.to_dict() for i in items]}
    return await cached(f"intel-news:{limit}", loader, ttl=300)


@router.get("/news/{symbol}")
async def news_for_symbol(symbol: str, limit: int = Query(10, ge=1, le=30)):
    async def loader():
        items = await symbol_news(symbol, limit=limit)
        return {"symbol": symbol, "count": len(items),
                "items": [i.to_dict() for i in items]}
    return await cached(f"intel-news-sym:{symbol}:{limit}", loader, ttl=300)


@router.get("/sectors")
async def sectors(session: AsyncSession = Depends(get_db)):
    async def loader():
        return await sector_rotation(session)
    return await cached("intel-sectors", loader, ttl=300)


@router.get("/volume-anomalies")
async def volumes(session: AsyncSession = Depends(get_db),
                  min_ratio: float = Query(2.0, ge=1.0)):
    async def loader():
        return {"items": await volume_anomalies(session, min_ratio=min_ratio)}
    return await cached(f"intel-vol:{min_ratio}", loader, ttl=180)


@router.get("/ptt")
async def ptt():
    async def loader():
        return await hot_topics()
    return await cached("intel-ptt", loader, ttl=600)


@router.get("/")
async def all_intel(session: AsyncSession = Depends(get_db)):
    async def loader():
        return await collect_intelligence(session)
    return await cached("intel-all", loader, ttl=300)
