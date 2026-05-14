"""GET /api/v1/intraday/{symbol} — refine an EOD plan with 15m bar entry timing."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from app.services.cache_service import cached
from app.services.intraday_engine import compute_intraday_plan

router = APIRouter()


@router.get("/{symbol}")
async def get_intraday(symbol: str):
    symbol = symbol.strip().upper()
    if not symbol:
        raise HTTPException(400, "symbol required")

    async def loader():
        loop = asyncio.get_running_loop()
        plan = await loop.run_in_executor(None, compute_intraday_plan, symbol)
        return plan.to_dict()

    return await cached(f"intraday:{symbol}", loader, ttl=120)
