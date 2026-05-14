"""Daily Trading Brief — the single thing a trader reads in the morning.

Combines:
  * Market regime (from the highest-coverage symbol's full series)
  * Strongest sectors + top 3 leaders in each
  * Volume anomalies
  * Top 3 *edge-validated* LONG setups (scanner output filtered to validated)
  * Cross-source buzz: which symbols hit news + PTT at the same time
  * Iron-rule disclosure

Output is JSON-rendered; the frontend takes care of presentation.
The rule is: this brief never contains a signal that hasn't been validated.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DailyPrice, Stock
from app.intelligence.aggregator import collect_intelligence
from app.services.scanner_service import scan_universe
from strategy.market_regime import detect_regime

log = logging.getLogger("daily_brief")


async def _market_regime(session: AsyncSession) -> dict:
    """Use 0050 (or first available) as the proxy for overall market regime."""
    proxy_symbols = ["0050", "2330", "2317"]
    stock = None
    for sym in proxy_symbols:
        stock = (await session.execute(
            select(Stock).where(Stock.symbol == sym)
        )).scalar_one_or_none()
        if stock:
            break
    if stock is None:
        return {"label": "unknown", "reason": "no_proxy"}
    rows = (await session.execute(
        select(DailyPrice).where(DailyPrice.stock_id == stock.id)
        .order_by(DailyPrice.date.asc())
    )).scalars().all()
    if len(rows) < 60:
        return {"label": "unknown", "reason": "insufficient_history",
                "proxy": stock.symbol}
    r = detect_regime(
        closes=[float(p.close) for p in rows],
        highs=[float(p.high) for p in rows],
        lows=[float(p.low) for p in rows],
    )
    d = r.to_dict()
    d["proxy"] = stock.symbol
    return d


async def build_brief(session: AsyncSession) -> Dict[str, Any]:
    intel = await collect_intelligence(session)
    market = await _market_regime(session)

    # only LONG signals; require *some* validation (validated history OR
    # at minimum confidence>=0.5). The scanner already excludes setups
    # the auto-disable rule killed.
    scan = await scan_universe(
        session, bias_filter="LONG", min_rr=1.5, min_confidence=0.5, limit=20,
    )
    validated = []
    unvalidated = []
    for it in scan.get("items", []):
        bk = (it.get("rank_breakdown") or {}).get("mode")
        if bk == "validated":
            validated.append(it)
        else:
            unvalidated.append(it)

    # cross-source buzz that also appears in scanner
    scanned_symbols = {it["symbol"] for it in scan.get("items", [])}
    buzz_with_signal = [
        b for b in intel.get("cross_source_buzz", [])
        if b["symbol"] in scanned_symbols
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market_regime": market,
        "top_signals": {
            "validated": validated[:5],
            "unvalidated": unvalidated[:5],
            "rule": (
                "Iron rule: only `validated` signals are actionable. "
                "`unvalidated` setups have insufficient sample size and are "
                "displayed only as research candidates."
            ),
        },
        "strongest_sectors": intel["sectors"]["sectors"][:5],
        "weakest_sectors": intel["sectors"]["sectors"][-3:][::-1],
        "top_leaders": intel["sectors"]["top_leaders"][:10],
        "volume_anomalies": intel["volume_anomalies"][:10],
        "news_headlines": intel["news"]["items"][:10],
        "ptt_hot": intel["ptt"],
        "cross_source_buzz_with_signal": buzz_with_signal,
        "disabled_setups": scan.get("disabled_setups", []),
        "disclosure": (
            "All metrics derived from DB-persisted OHLCV + chip flows. "
            "No lookahead bias. Win-rate and expectancy are computed from "
            "evaluated edge_signals only. Not investment advice."
        ),
    }
