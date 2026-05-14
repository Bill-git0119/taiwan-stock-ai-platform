"""Performance monitor — the API for `/terminal/performance`.

Combines breakdowns from strategy_metrics + edge_decay into one payload.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.edge import edge_decay, strategy_metrics


async def snapshot(session: AsyncSession, window: int = 30) -> dict:
    """Single payload for the dashboard."""
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": window,
        "overall": await strategy_metrics.overall(session, window),
        "by_setup": await strategy_metrics.by_setup(session, window),
        "by_regime": await strategy_metrics.by_regime(session, window),
        "by_sector": await strategy_metrics.by_sector(session, window),
        "decay": await edge_decay.decay_scores(session),
    }
    return payload
