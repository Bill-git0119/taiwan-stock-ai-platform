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
    """16:00 — walk forward through any unevaluated signals at least
    EVAL_HORIZON_BARS days old and mark TP/SL/timeout outcomes (+ MFE/MAE)."""
    log.info("[scheduler] evaluate_signals")
    try:
        from app.services.edge_tracking_service import evaluate_open_signals
        async with async_session_maker() as s:
            res = await evaluate_open_signals(s)
        log.info("evaluate_signals: %s", res)
    except Exception as e:
        log.exception("evaluate_signals failed: %s", e)


async def job_strategy_ranking_refresh() -> None:
    """17:00 — recompute strategy ranks + persist daily snapshot."""
    log.info("[scheduler] 17:00 strategy_ranking_refresh")
    try:
        from datetime import date as _date
        from app.db.models import StrategyPerformanceDaily
        from app.strategy_registry.ranker import rank_all
        from app.edge import strategy_metrics
        from sqlalchemy import select as _sel

        async with async_session_maker() as s:
            rankings = await rank_all(s)
            stats = await strategy_metrics.by_setup(s, window_days=30)
            today_ = _date.today()
            for r in rankings:
                st = stats.get(r.strategy, {})
                existing = (await s.execute(
                    _sel(StrategyPerformanceDaily).where(
                        StrategyPerformanceDaily.date == today_,
                        StrategyPerformanceDaily.strategy == r.strategy,
                    )
                )).scalar_one_or_none()
                fields = dict(
                    signals_emitted=0,
                    evaluated_count=st.get("sample_size", 0),
                    wins=int(st.get("sample_size", 0) * st.get("win_rate", 0)),
                    losses=int(st.get("sample_size", 0) * (1 - st.get("win_rate", 0))),
                    expectancy_r=st.get("expectancy_R", 0.0),
                    profit_factor=st.get("profit_factor", 0.0),
                    avg_mfe_r=st.get("avg_mfe_R", 0.0),
                    avg_mae_r=st.get("avg_mae_R", 0.0),
                    decay_score=r.components.get("decay", 0.0),
                    is_active=r.production_status == "ACTIVE",
                    production_status=r.production_status,
                )
                if existing:
                    for k, v in fields.items():
                        setattr(existing, k, v)
                else:
                    s.add(StrategyPerformanceDaily(
                        date=today_, strategy=r.strategy, **fields,
                    ))
            await s.commit()
        log.info("ranking refresh: %d rows", len(rankings))
    except Exception as e:
        log.exception("strategy_ranking_refresh failed: %s", e)


async def job_universe_rebuild() -> None:
    """Sun 23:00 — rebuild universe snapshot from latest DailyPrice."""
    log.info("[scheduler] universe_rebuild")
    try:
        from app.universe.universe_builder import build_snapshot
        async with async_session_maker() as s:
            report = await build_snapshot(s)
        log.info("universe_rebuild: %s", report)
    except Exception as e:
        log.exception("universe_rebuild failed: %s", e)


async def job_rolling_update() -> None:
    """08:00 — incremental OHLCV pull for every stock in DB."""
    log.info("[scheduler] rolling_update")
    try:
        from scripts.rolling_update import run as _run
        rep = await _run()
        log.info("rolling_update: %s", rep)
    except Exception as e:
        log.exception("rolling_update failed: %s", e)


async def job_correlation_refresh() -> None:
    """Sun 22:00 — recompute correlation matrix; cache will warm on first call."""
    log.info("[scheduler] correlation_refresh")
    try:
        from strategy.correlation.correlation_analyzer import correlation_matrix
        async with async_session_maker() as s:
            res = await correlation_matrix(s)
        log.info("correlation_refresh: %d flagged pairs",
                  len(res.get("flagged_pairs", [])))
    except Exception as e:
        log.exception("correlation_refresh failed: %s", e)


async def job_integrity_check() -> None:
    """Sat 02:00 — run data integrity checker."""
    log.info("[scheduler] integrity_check")
    try:
        from scripts.data_integrity_checker import check
        rep = await check()
        log.info("integrity_check: passes=%s thin=%d missing=%d",
                  rep["passes"], len(rep["thin_coverage"]),
                  len(rep["missing_bars"]))
    except Exception as e:
        log.exception("integrity_check failed: %s", e)


async def job_daily_report() -> None:
    """18:00 — pre-render the research report so cache is warm."""
    log.info("[scheduler] 18:00 daily_report")
    try:
        from app.services.research_report import render_markdown
        async with async_session_maker() as s:
            _ = await render_markdown(s)
        log.info("daily_report rendered")
    except Exception as e:
        log.exception("daily_report failed: %s", e)


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
    sched.add_job(job_update_data,             CronTrigger(day_of_week="mon-fri", hour=8,  minute=50, timezone=s.scheduler_timezone), id="update_data")
    sched.add_job(job_send_open,               CronTrigger(day_of_week="mon-fri", hour=9,  minute=5,  timezone=s.scheduler_timezone), id="send_open")
    sched.add_job(job_send_intraday,           CronTrigger(day_of_week="mon-fri", hour=13, minute=25, timezone=s.scheduler_timezone), id="send_intraday")
    sched.add_job(job_ingest_daily,            CronTrigger(day_of_week="mon-fri", hour=15, minute=10, timezone=s.scheduler_timezone), id="ingest_daily")
    sched.add_job(job_run_scoring,             CronTrigger(day_of_week="mon-fri", hour=15, minute=20, timezone=s.scheduler_timezone), id="run_scoring")
    sched.add_job(job_refresh_trade_plans,     CronTrigger(day_of_week="mon-fri", hour=15, minute=25, timezone=s.scheduler_timezone), id="refresh_trade_plans")
    sched.add_job(job_send_close,              CronTrigger(day_of_week="mon-fri", hour=15, minute=30, timezone=s.scheduler_timezone), id="send_close")
    sched.add_job(job_persist_signals,         CronTrigger(day_of_week="mon-fri", hour=15, minute=35, timezone=s.scheduler_timezone), id="persist_signals")
    sched.add_job(job_evaluate_signals,        CronTrigger(day_of_week="mon-fri", hour=16, minute=0,  timezone=s.scheduler_timezone), id="evaluate_signals")
    sched.add_job(job_strategy_ranking_refresh,CronTrigger(day_of_week="mon-fri", hour=17, minute=0,  timezone=s.scheduler_timezone), id="strategy_ranking_refresh")
    sched.add_job(job_daily_report,            CronTrigger(day_of_week="mon-fri", hour=18, minute=0,  timezone=s.scheduler_timezone), id="daily_report")
    sched.add_job(job_rolling_update,          CronTrigger(day_of_week="mon-fri", hour=8,  minute=0,  timezone=s.scheduler_timezone), id="rolling_update")
    sched.add_job(job_universe_rebuild,        CronTrigger(day_of_week="sun",     hour=23, minute=0,  timezone=s.scheduler_timezone), id="universe_rebuild")
    sched.add_job(job_correlation_refresh,     CronTrigger(day_of_week="sun",     hour=22, minute=0,  timezone=s.scheduler_timezone), id="correlation_refresh")
    sched.add_job(job_integrity_check,         CronTrigger(day_of_week="sat",     hour=2,  minute=0,  timezone=s.scheduler_timezone), id="integrity_check")
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
