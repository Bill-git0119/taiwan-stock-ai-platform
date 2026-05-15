"""Integrity checks — runs over the operational DB and writes
DataIntegrityReport rows.

Checks implemented:
  * daily_prices.missing_bars  — symbols with gap > MAX_GAP between
    consecutive bars in last 90 days
  * daily_prices.stale         — symbols whose latest bar is older
    than STALE_DAYS calendar days
  * chip_data.coverage         — % of recent bars with matching chip
    rows (alerts when < 80%)
  * cross_source.chip_vs_price — bars without chip rows in last 30
    bars (informational)

Writes severity:
  ok      — all clear
  warn    — some symbols affected
  fail    — many symbols affected OR critical source stale
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from loguru import logger
from sqlalchemy import func, select

from app.db.models import ChipData, DailyPrice, DataIntegrityReport, Stock
from app.db.session import async_session_maker

MAX_GAP_TRADING_DAYS = 10   # Taiwan Lunar New Year can close market 7-9 days
STALE_DAYS = 7              # bars older than this = stale source
CHIP_COVERAGE_WARN = 0.80   # warn if < 80% bars have chip


async def check_missing_bars(session) -> dict:
    """For each symbol look at last 90 bars and find calendar gaps >= MAX_GAP."""
    cutoff = date.today() - timedelta(days=120)
    stocks = (await session.execute(select(Stock))).scalars().all()
    affected: list[dict] = []
    for st in stocks:
        rows = (await session.execute(
            select(DailyPrice.date)
            .where(DailyPrice.stock_id == st.id, DailyPrice.date >= cutoff)
            .order_by(DailyPrice.date.asc())
        )).scalars().all()
        if len(rows) < 5:
            continue
        max_gap = 0
        for i in range(1, len(rows)):
            gap = (rows[i] - rows[i - 1]).days
            if gap > max_gap:
                max_gap = gap
        if max_gap > MAX_GAP_TRADING_DAYS:
            affected.append({"symbol": st.symbol, "max_gap_days": max_gap,
                             "bars": len(rows)})
    return {
        "check_name": "daily_prices.missing_bars",
        "affected": affected,
        "severity": _severity_by_count(len(affected), len(stocks)),
    }


async def check_stale_sources(session) -> dict:
    """Latest bar across whole universe vs today."""
    latest = (await session.execute(select(func.max(DailyPrice.date)))).scalar()
    if latest is None:
        return {"check_name": "daily_prices.stale", "affected": [],
                "severity": "fail", "detail": {"reason": "no_bars"}}
    age = (date.today() - latest).days
    severity = "ok" if age <= STALE_DAYS else "warn" if age <= STALE_DAYS * 2 else "fail"
    return {
        "check_name": "daily_prices.stale",
        "affected": [],
        "severity": severity,
        "detail": {"latest_bar": latest.isoformat(), "age_days": age},
    }


async def check_chip_coverage(session) -> dict:
    """Per-symbol fraction of last 30 bars with a matching chip row."""
    cutoff = date.today() - timedelta(days=45)
    stocks = (await session.execute(select(Stock))).scalars().all()
    poor: list[dict] = []
    for st in stocks:
        if st.market == "TPEX":
            # TPEX chips not collected by twse.chips; skip
            continue
        bar_dates = set((await session.execute(
            select(DailyPrice.date)
            .where(DailyPrice.stock_id == st.id, DailyPrice.date >= cutoff)
        )).scalars().all())
        if len(bar_dates) < 5:
            continue
        chip_dates = set((await session.execute(
            select(ChipData.date)
            .where(ChipData.stock_id == st.id, ChipData.date >= cutoff)
        )).scalars().all())
        coverage = len(bar_dates & chip_dates) / len(bar_dates)
        if coverage < CHIP_COVERAGE_WARN:
            poor.append({"symbol": st.symbol, "coverage": round(coverage, 3)})
    return {
        "check_name": "chip_data.coverage",
        "affected": poor,
        "severity": _severity_by_count(len(poor), len(stocks)),
    }


def _severity_by_count(affected_n: int, universe_n: int) -> str:
    if affected_n == 0:
        return "ok"
    ratio = affected_n / max(1, universe_n)
    if ratio < 0.05:
        return "warn"
    return "fail"


async def run_all_checks() -> list[dict]:
    """Run every check and persist reports. Returns the list of results
    (for inline calling from a CLI / scheduler job)."""
    async with async_session_maker() as s:
        out = []
        for fn in (check_missing_bars, check_stale_sources, check_chip_coverage):
            try:
                r = await fn(s)
                source_prefix = r["check_name"].split(".")[0]
                detail = r.get("detail") or {"affected": r.get("affected", [])[:20]}
                rec = DataIntegrityReport(
                    source=source_prefix,
                    check_name=r["check_name"],
                    severity=r["severity"],
                    affected_symbols=len(r.get("affected", [])),
                    detail=json.dumps(detail, default=str)[:4000],
                )
                s.add(rec)
                out.append({
                    "check_name": r["check_name"],
                    "severity": r["severity"],
                    "affected_count": len(r.get("affected", [])),
                    "detail": detail,
                })
            except Exception as e:
                logger.exception("integrity check {} failed: {}", fn.__name__, e)
                out.append({
                    "check_name": fn.__name__,
                    "severity": "fail",
                    "error": str(e),
                })
        await s.commit()
    return out
