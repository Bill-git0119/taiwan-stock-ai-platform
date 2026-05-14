"""Research quality gate endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.edge import edge_decay, strategy_metrics
from app.services.cache_service import cached
from app.strategy_registry import research_quality
from strategy.correlation.correlation_analyzer import correlation_matrix

router = APIRouter()


@router.get("/")
async def quality_report(session: AsyncSession = Depends(get_db)):
    async def loader():
        stats = await strategy_metrics.by_setup(session, window_days=90)
        decay = await edge_decay.decay_scores(session)
        corr = await correlation_matrix(session, window_days=90)
        flagged_setups: set[str] = set()
        for pair in corr.get("flagged_pairs", []):
            flagged_setups.update([pair["a"], pair["b"]])

        out = []
        for setup, s in stats.items():
            d = decay.get(setup, {})
            verdict = research_quality.evaluate(
                setup,
                sample_size=s.get("sample_size", 0),
                cross_regime_consistency=0.6,    # placeholder until stress runner integrated
                single_period_dominance=0.3,
                correlation_flagged=setup in flagged_setups,
                decay_label=d.get("label"),
                robustness_score=0.7,
            )
            out.append(verdict.to_dict())
        return {"items": sorted(out, key=lambda x: x["production_research_score"], reverse=True)}
    return await cached("quality", loader, ttl=600)
