"""Daily APScheduler jobs (Asia/Taipei).

08:50  update_data        — pull TWSE quotes + institutional flows
09:00  send_open          — push 開盤觀察股 to subscribed users
13:25  send_intraday      — push 尾盤強勢股
15:10  run_scoring        — recompute scores, persist top10
15:30  send_close         — push 收盤 TOP10
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings
from app.db.session import async_session_maker
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


async def job_run_scoring() -> None:
    log.info("[scheduler] 15:10 run_scoring")
    async with async_session_maker() as s:
        scored = await score_all(s)
        await persist_scores(s, scored, date.today())


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
    sched.add_job(job_update_data,  CronTrigger(day_of_week="mon-fri", hour=8,  minute=50, timezone=s.scheduler_timezone), id="update_data")
    sched.add_job(job_send_open,    CronTrigger(day_of_week="mon-fri", hour=9,  minute=0,  timezone=s.scheduler_timezone), id="send_open")
    sched.add_job(job_send_intraday,CronTrigger(day_of_week="mon-fri", hour=13, minute=25, timezone=s.scheduler_timezone), id="send_intraday")
    sched.add_job(job_run_scoring,  CronTrigger(day_of_week="mon-fri", hour=15, minute=10, timezone=s.scheduler_timezone), id="run_scoring")
    sched.add_job(job_send_close,   CronTrigger(day_of_week="mon-fri", hour=15, minute=30, timezone=s.scheduler_timezone), id="send_close")
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
