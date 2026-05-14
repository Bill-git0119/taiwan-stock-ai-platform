"""Daily APScheduler jobs (Asia/Taipei).

08:50  update_data           — pull TWSE quotes + institutional flows
09:00  send_open             — push 開盤觀察股 to subscribed users
13:25  send_intraday         — push 尾盤強勢股
15:10  ingest_daily          — backfill any missing OHLCV + chips
15:20  run_scoring           — recompute scores, persist top10
15:25  refresh_trade_plans   — bust cache so /trade-plan re-computes
15:30  send_close            — push 收盤 TOP10
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings
from app.db.session import async_session_maker
from app.services.cache_service import cache
from app.services.line_notify import broadcast_top10
from app.services.scoring_pipeline import load_top10, persist_scores, score_all

log = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None


# ───────── jobs ─────────

async def job_update_data() -> None:
    log.info("[scheduler] 08:50 update_data")
    try:
        from scripts.data_collector import collect  # type: ignore
        await collect(date.today())
    except Exception as e:
        log.exception("update_data failed: %s", e)


async def job_ingest_daily() -> None:
    """15:10 — full_data_pipeline (last 7 days; idempotent upsert)."""
    log.info("[scheduler] 15:10 ingest_daily")
    try:
        from scripts.full_data_pipeline import run_pipeline  # type: ignore
        report = await run_pipeline(days=7, chip_days=2, skip_chips=False)
        log.info("ingest_daily report: %s", report)
    except Exception as e:
        log.exception("ingest_daily failed: %s", e)


async def job_run_scoring() -> None:
    """15:20 — recompute scores from latest DB rows."""
    log.info("[scheduler] 15:20 run_scoring")
    async with async_session_maker() as s:
        scored = await score_all(s)
        await persist_scores(s, scored, date.today())


async def job_refresh_trade_plans() -> None:
    """15:25 — invalidate trade-plan cache so next request recomputes."""
    log.info("[scheduler] 15:25 refresh_trade_plans")
    try:
        await cache.clear()
    except Exception as e:
        log.warning("cache clear failed: %s", e)


async def job_persist_signals() -> None:
    """15:35 — run scanner with persist=True so today's LONG plans get
    written to edge_signals for later evaluation."""
    log.info("[scheduler] 15:35 persist_signals")
    try:
        from app.services.scanner_service import scan_universe
        async with async_session_maker() as s:
            res = await scan_universe(s, bias_filter="LONG", persist=True, limit=200)
        log.info("persist_signals: matched=%d", res.get("matched", 0))
    except Exception as e:
        log.exception("persist_signals failed: %s", e)


async def job_evaluate_signals() -> None:
    """09:00 — walk forward through any unevaluated signals at least
    EVAL_HORIZON_BARS days old and mark TP/SL/timeout outcomes."""
    log.info("[scheduler] 09:00 evaluate_signals")
    try:
        from app.services.edge_tracking_service import evaluate_open_signals
        async with async_session_maker() as s:
            res = await evaluate_open_signals(s)
        log.info("evaluate_signals: %s", res)
    except Exception as e:
        log.exception("evaluate_signals failed: %s", e)


async def _push(kind: str, min_plan: str = "elite") -> None:
    async with async_session_maker() as s:
        rows = await load_top10(s)
        await broadcast_top10(s, rows, kind=kind, min_plan=min_plan)


async def job_send_open() -> None:
    log.info("[scheduler] 09:00 send_open")
    await _push("open", min_plan="elite")


async def job_send_intraday() -> None:
    log.info("[scheduler] 13:25 send_intraday")
    await _push("intraday", min_plan="elite")


async def job_send_close() -> None:
    log.info("[scheduler] 15:30 send_close")
    await _push("close", min_plan="elite")


# ───────── lifecycle ─────────

def start() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    s = get_settings()
    sched = AsyncIOScheduler(timezone=s.scheduler_timezone)
    sched.add_job(job_update_data,        CronTrigger(day_of_week="mon-fri", hour=8,  minute=50, timezone=s.scheduler_timezone), id="update_data")
    sched.add_job(job_evaluate_signals,   CronTrigger(day_of_week="mon-fri", hour=9,  minute=0,  timezone=s.scheduler_timezone), id="evaluate_signals")
    sched.add_job(job_send_open,          CronTrigger(day_of_week="mon-fri", hour=9,  minute=5,  timezone=s.scheduler_timezone), id="send_open")
    sched.add_job(job_send_intraday,      CronTrigger(day_of_week="mon-fri", hour=13, minute=25, timezone=s.scheduler_timezone), id="send_intraday")
    sched.add_job(job_ingest_daily,       CronTrigger(day_of_week="mon-fri", hour=15, minute=10, timezone=s.scheduler_timezone), id="ingest_daily")
    sched.add_job(job_run_scoring,        CronTrigger(day_of_week="mon-fri", hour=15, minute=20, timezone=s.scheduler_timezone), id="run_scoring")
    sched.add_job(job_refresh_trade_plans,CronTrigger(day_of_week="mon-fri", hour=15, minute=25, timezone=s.scheduler_timezone), id="refresh_trade_plans")
    sched.add_job(job_send_close,         CronTrigger(day_of_week="mon-fri", hour=15, minute=30, timezone=s.scheduler_timezone), id="send_close")
    sched.add_job(job_persist_signals,    CronTrigger(day_of_week="mon-fri", hour=15, minute=35, timezone=s.scheduler_timezone), id="persist_signals")
    sched.start()
    _scheduler = sched
    log.info("APScheduler started in %s with %d jobs", s.scheduler_timezone, len(sched.get_jobs()))
    return sched


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def list_jobs() -> list[dict]:
    if _scheduler is None:
        return []
    out = []
    for j in _scheduler.get_jobs():
        out.append({"id": j.id, "next_run_time": str(j.next_run_time) if j.next_run_time else None})
    return out
