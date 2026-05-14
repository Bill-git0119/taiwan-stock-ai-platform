"""Daily intelligence aggregator — fans out to every signal collector and
collapses results into one structured payload for the brief endpoint."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.news import fetch_news
from app.intelligence.ptt import hot_topics
from app.intelligence.sector_rotation import sector_rotation
from app.intelligence.volume_anomaly import volume_anomalies

log = logging.getLogger("intel.aggregator")


async def collect_intelligence(session: AsyncSession) -> Dict[str, Any]:
    """Concurrent fan-out; any individual source failure degrades gracefully."""
    news_task = asyncio.create_task(fetch_news(limit=30))
    ptt_task = asyncio.create_task(hot_topics())
    sectors_task = sector_rotation(session)
    anomalies_task = volume_anomalies(session)

    news = await news_task
    ptt = await ptt_task
    sectors = await sectors_task
    anomalies = await anomalies_task

    sym_mentions: Dict[str, int] = {}
    for it in news:
        for sym in it.mentioned_symbols:
            sym_mentions[sym] = sym_mentions.get(sym, 0) + 1
    for hs in ptt.get("hot_symbols", []):
        sym = hs["symbol"]
        sym_mentions[sym] = sym_mentions.get(sym, 0) + hs["mentions"]
    cross_buzz = sorted(sym_mentions.items(), key=lambda x: x[1], reverse=True)[:15]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "news": {
            "count": len(news),
            "items": [n.to_dict() for n in news[:20]],
        },
        "ptt": ptt,
        "sectors": sectors,
        "volume_anomalies": anomalies,
        "cross_source_buzz": [
            {"symbol": s, "mentions": n} for s, n in cross_buzz
        ],
    }
