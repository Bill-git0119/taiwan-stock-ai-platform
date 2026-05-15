"""Datahub status + manual trigger endpoint.

Local mode — no auth gate. Used by the workspace page (Phase 8) to
show "data sources" panel and let the trader trigger refresh on demand.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datahub.collectors.macro_signals import latest_macro
from app.datahub.collectors.twse_chips import TwseChipsCollector
from app.datahub.collectors.yfinance_daily import YFinanceDailyCollector
from app.datahub.validators.integrity import run_all_checks
from app.db.models import DataFreshness, DataIntegrityReport
from app.db.session import get_db

router = APIRouter()


@router.get("/freshness")
async def freshness(session: AsyncSession = Depends(get_db)) -> dict:
    rows = (await session.execute(
        select(DataFreshness).order_by(DataFreshness.source.asc())
    )).scalars().all()
    now = datetime.utcnow()
    out = []
    for r in rows:
        age_h: Optional[float] = None
        if r.latest_data_at:
            age_h = round((now - r.latest_data_at).total_seconds() / 3600, 1)
        severity = "ok"
        if r.consecutive_failures and r.consecutive_failures >= 3:
            severity = "fail"
        elif age_h is not None and age_h > 48:
            severity = "warn"
        out.append({
            "source": r.source,
            "latest_data_at": r.latest_data_at.isoformat() if r.latest_data_at else None,
            "last_attempted_at": r.last_attempted_at.isoformat() if r.last_attempted_at else None,
            "last_succeeded_at": r.last_succeeded_at.isoformat() if r.last_succeeded_at else None,
            "consecutive_failures": r.consecutive_failures or 0,
            "rows_last_run": r.rows_last_run or 0,
            "last_error": r.last_error,
            "age_hours": age_h,
            "severity": severity,
        })
    return {"as_of": now.isoformat(), "sources": out}


@router.get("/integrity")
async def integrity(session: AsyncSession = Depends(get_db)) -> dict:
    cutoff = datetime.utcnow() - timedelta(hours=48)
    rows = (await session.execute(
        select(DataIntegrityReport)
        .where(DataIntegrityReport.created_at >= cutoff)
        .order_by(desc(DataIntegrityReport.created_at))
        .limit(50)
    )).scalars().all()
    return {
        "reports": [
            {
                "source": r.source,
                "check_name": r.check_name,
                "severity": r.severity,
                "affected_symbols": r.affected_symbols,
                "detail": r.detail,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
    }


@router.get("/macro")
async def macro() -> dict:
    snap = await latest_macro()
    if not snap:
        return {"has_data": False, "snapshot": None}
    return {"has_data": True, "snapshot": snap}


@router.post("/run/{source}")
async def run_collector(source: str) -> dict:
    """Manual trigger — runs a single source synchronously and returns
    rows ingested. For interactive use from the workspace UI."""
    runners = {
        "yfinance.daily": lambda: YFinanceDailyCollector(days=10),
        "twse.chips": lambda: TwseChipsCollector(days=5),
    }
    if source not in runners:
        raise HTTPException(404, f"unknown source: {source}")
    coll = runners[source]()
    res = await coll.run()
    return {"source": source, "rows": res.rows,
            "latest_data_at": res.latest_data_at.isoformat() if res.latest_data_at else None,
            "note": res.note}


@router.post("/integrity/run")
async def run_integrity() -> dict:
    out = await run_all_checks()
    return {"checks": out}
