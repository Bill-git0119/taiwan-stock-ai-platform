"""Daily research report endpoint — returns markdown."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.cache_service import cached
from app.services.research_report import render_markdown

router = APIRouter()


@router.get("/today.md", response_class=PlainTextResponse)
async def today_md(session: AsyncSession = Depends(get_db)) -> str:
    async def loader():
        return await render_markdown(session)
    return await cached("research-md", loader, ttl=600)


@router.get("/today")
async def today_json(session: AsyncSession = Depends(get_db)):
    async def loader():
        return {"markdown": await render_markdown(session)}
    return await cached("research-json", loader, ttl=600)
