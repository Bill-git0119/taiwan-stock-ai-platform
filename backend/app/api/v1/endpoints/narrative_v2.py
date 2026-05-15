"""Narrative v2 — daily-brief endpoint backed by LLM (or honest stub)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.breadth_service import compute_breadth
from app.services.cache_service import cached
from app.services.decision_engine import decide
from app.services.llm_narrative import generate_narrative, has_llm_key
from app.services.market_state import compute_market_state

router = APIRouter()


async def _facts(session: AsyncSession) -> dict:
    ms = (await compute_market_state(session)).to_dict()
    breadth = await compute_breadth(session)
    decisions = await decide(session, limit=10, include_research=True)
    return {"market_state": ms, "breadth": breadth, "decisions": decisions}


@router.get("/daily-brief")
async def daily_brief(session: AsyncSession = Depends(get_db)) -> dict:
    async def loader():
        facts = await _facts(session)
        res = await generate_narrative(facts)
        return res.to_dict()
    return await cached("narrative:daily_brief", loader, ttl=900)


@router.get("/provider-status")
async def provider_status() -> dict:
    return {
        "has_llm_key": has_llm_key(),
        "provider_used_on_next_call": (
            "anthropic" if has_llm_key() else "stub"
        ),
    }
