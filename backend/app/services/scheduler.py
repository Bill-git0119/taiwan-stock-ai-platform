"""Daily APScheduler SOP — local research workstation.

Asia/Taipei timezone. All jobs are idempotent and never write fake data.

  08:30  premarket_prep         macro snapshot + integrity check
  09:00  opening_regime         compute & warm market_state cache
  12:00  midday_refresh         rolling OHLCV update
  13:30  close_prep             pre-cache scanner / decisions
  15:10  ingest_daily           full OHLCV + chip pull (TWSE + yfinance)
  15:30  run_scoring            recompute scores, persist top10
  16:00  evaluate_signals       walk forward unevaluated edge_signals
  17:00  research_refresh       strategy ranking + persistence snapshot
  18:00  narrative              warm /narrative-v2/daily-brief cache
  23:00  strategy_validation    correlation matrix + universe rebuild

Saturdays
  02:00  integrity_check        run all data_integrity checks
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
from app.services.scoring_pipeline import persist_scores, score_all

log = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None


# ───────── jobs ─────────

async def job_premarket_prep() -> None:
    """08:30 — pull overnight macro (VIX/DXY/US/TWII) and run integrity."""
    log.info("[scheduler] 08:30 premarket_prep")
    from app.datahub.collectors.macro_signals import MacroSignalsCollector
    from app.datahub.validators.integrity import run_all_checks
    try:
        await MacroSignalsCollector().run()
    except Exception as e:
        log.warning("macro pull failed: %s", e)
    try:
        await run_all_checks()
    except Exception as e:
        log.warning("integrity_check failed: %s", e)


async def job_opening_regime() -> None:
    """09:00 — compute market_state and warm cache so the workspace
    page hits a hot cache the moment the trader opens it."""
    log.info("[scheduler] 09:00 opening_regime")
    try:
        from app.services.market_state import compute_market_state
        async with async_session_maker() as s:
            st = await compute_market_state(s)
        await cache.set("market:state", st.to_dict(), ttl=300)
        log.info("opening_regime: regime=%s risk=%s", st.regime, st.risk_level)
    except Exception as e:
        log.exception("opening_regime failed: %s", e)


async def job_midday_refresh() -> None:
    """12:00 — rolling intraday OHLCV refresh (last 5 trading days)."""
    log.info("[scheduler] 12:00 midday_refresh")
    try:
        from app.datahub.collectors.yfinance_daily import YFinanceDailyCollector
        res = await YFinanceDailyCollector(days=5).run()
        log.info("midday rows=%s", res.rows)
    except Exception as e:
        log.warning("midday_refresh failed: %s", e)


async def job_close_prep() -> None:
    """13:30 — pre-cache scanner so end-of-day workflow is instant."""
    log.info("[scheduler] 13:30 close_prep")
    try:
        from app.services.scanner_service import scan_universe
        async with async_session_maker() as s:
            await scan_universe(s, limit=200)
    except Exception as e:
        log.warning("close_prep failed: %s", e)


async def job_ingest_daily() -> None:
    """15:10 — full daily pull. yfinance bars + TWSE chips, idempotent
    upsert. Both collectors are in app.datahub."""
    log.info("[scheduler] 15:10 ingest_daily")
    try:
        from app.datahub.collectors.twse_chips import TwseChipsCollector
        from app.datahub.collectors.yfinance_daily import YFinanceDailyCollector
        for coll in (YFinanceDailyCollector(days=10), TwseChipsCollector(days=5)):
            try:
                r = await coll.run()
                log.info("ingest %s rows=%d", coll.source, r.rows)
            except Exception as e:
                log.warning("ingest %s failed: %s", coll.source, e)
    except Exception as e:
        log.exception("ingest_daily failed: %s", e)


async def job_run_scoring() -> None:
    """15:30 — recompute Scores from latest DB rows."""
    log.info("[scheduler] 15:30 run_scoring")
    try:
        async with async_session_maker() as s:
            scored = await score_all(s)
            await persist_scores(s, scored, date.today())
        await cache.delete("stocks:top30")
    except Exception as e:
        log.exception("run_scoring failed: %s", e)


async def job_persist_signals() -> None:
    """15:35 — scanner with persist=True writes today's LONG plans into
    edge_signals so the 7-day walk-forward can evaluate them."""
    log.info("[scheduler] 15:35 persist_signals")
    try:
        from app.services.scanner_service import scan_universe
        async with async_session_maker() as s:
            res = await scan_universe(s, bias_filter="LONG", persist=True, limit=200)
        log.info("persist_signals matched=%d", res.get("matched", 0))
    except Exception as e:
        log.exception("persist_signals failed: %s", e)


async def job_evaluate_signals() -> None:
    """16:00 — walk forward through unevaluated signals; mark TP/SL/timeout."""
    log.info("[scheduler] 16:00 evaluate_signals")
    try:
        from app.services.edge_tracking_service import evaluate_open_signals
        async with async_session_maker() as s:
            res = await evaluate_open_signals(s)
        log.info("evaluate_signals %s", res)
    except Exception as e:
        log.exception("evaluate_signals failed: %s", e)


async def job_research_refresh() -> None:
    """17:00 — recompute strategy rankings + persist daily snapshot."""
    log.info("[scheduler] 17:00 research_refresh")
    try:
        from sqlalchemy import select as _sel

        from app.db.models import StrategyPerformanceDaily
        from app.edge import strategy_metrics
        from app.strategy_registry.ranker import rank_all
        today_ = date.today()
        async with async_session_maker() as s:
            rankings = await rank_all(s)
            stats = await strategy_metrics.by_setup(s, window_days=30)
            for r in rankings:
                st = stats.get(r.strategy, {})
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
                existing = (await s.execute(
                    _sel(StrategyPerformanceDaily).where(
                        StrategyPerformanceDaily.date == today_,
                        StrategyPerformanceDaily.strategy == r.strategy,
                    )
                )).scalar_one_or_none()
                if existing:
                    for k, v in fields.items():
                        setattr(existing, k, v)
                else:
                    s.add(StrategyPerformanceDaily(
                        date=today_, strategy=r.strategy, **fields,
                    ))
            await s.commit()
        log.info("research_refresh rows=%d", len(rankings))
    except Exception as e:
        log.exception("research_refresh failed: %s", e)


async def job_narrative_warm() -> None:
    """18:00 — warm the daily-brief cache so the trader opens to a ready
    narrative the next morning."""
    log.info("[scheduler] 18:00 narrative_warm")
    try:
        from app.services.breadth_service import compute_breadth
        from app.services.decision_engine import decide
        from app.services.llm_narrative import generate_narrative
        from app.services.market_state import compute_market_state
        async with async_session_maker() as s:
            ms = (await compute_market_state(s)).to_dict()
            br = await compute_breadth(s)
            dec = await decide(s, limit=10, include_research=True)
        facts = {"market_state": ms, "breadth": br, "decisions": dec}
        res = await generate_narrative(facts)
        await cache.set("narrative:daily_brief", res.to_dict(), ttl=14 * 3600)
        log.info("narrative_warm provider=%s", res.provider)
    except Exception as e:
        log.exception("narrative_warm failed: %s", e)


async def job_strategy_validation() -> None:
    """23:00 — recompute correlation matrix + rebuild universe snapshot."""
    log.info("[scheduler] 23:00 strategy_validation")
    try:
        from strategy.correlation.correlation_analyzer import correlation_matrix
        async with async_session_maker() as s:
            res = await correlation_matrix(s)
        log.info("correlation: %d flagged", len(res.get("flagged_pairs", [])))
    except Exception as e:
        log.warning("correlation failed: %s", e)
    try:
        from app.universe.universe_builder import build_snapshot
        async with async_session_maker() as s:
            rep = await build_snapshot(s)
        log.info("universe_rebuild %s", rep)
    except Exception as e:
        log.warning("universe_rebuild failed: %s", e)


async def job_integrity_check() -> None:
    """Sat 02:00 — full integrity sweep."""
    log.info("[scheduler] Sat 02:00 integrity_check")
    try:
        from app.datahub.validators.integrity import run_all_checks
        out = await run_all_checks()
        log.info("integrity %s", [(r["check_name"], r["severity"]) for r in out])
    except Exception as e:
        log.exception("integrity_check failed: %s", e)


# ───────── lifecycle ─────────

def start() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    s = get_settings()
    sched = AsyncIOScheduler(timezone=s.scheduler_timezone)
    tz = s.scheduler_timezone

    weekdays = {"day_of_week": "mon-fri", "timezone": tz}

    sched.add_job(job_premarket_prep,      CronTrigger(hour=8,  minute=30, **weekdays), id="premarket_prep")
    sched.add_job(job_opening_regime,      CronTrigger(hour=9,  minute=0,  **weekdays), id="opening_regime")
    sched.add_job(job_midday_refresh,      CronTrigger(hour=12, minute=0,  **weekdays), id="midday_refresh")
    sched.add_job(job_close_prep,          CronTrigger(hour=13, minute=30, **weekdays), id="close_prep")
    sched.add_job(job_ingest_daily,        CronTrigger(hour=15, minute=10, **weekdays), id="ingest_daily")
    sched.add_job(job_run_scoring,         CronTrigger(hour=15, minute=30, **weekdays), id="run_scoring")
    sched.add_job(job_persist_signals,     CronTrigger(hour=15, minute=35, **weekdays), id="persist_signals")
    sched.add_job(job_evaluate_signals,    CronTrigger(hour=16, minute=0,  **weekdays), id="evaluate_signals")
    sched.add_job(job_research_refresh,    CronTrigger(hour=17, minute=0,  **weekdays), id="research_refresh")
    sched.add_job(job_narrative_warm,      CronTrigger(hour=18, minute=0,  **weekdays), id="narrative_warm")
    sched.add_job(job_strategy_validation, CronTrigger(hour=23, minute=0,  **weekdays), id="strategy_validation")
    sched.add_job(job_integrity_check,     CronTrigger(day_of_week="sat", hour=2, minute=0, timezone=tz), id="integrity_check")
    sched.start()
    _scheduler = sched
    log.info("APScheduler started in %s with %d jobs", tz, len(sched.get_jobs()))
    return sched


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def run_job_now(job_id: str) -> bool:
    """Manual trigger (used by /api/v1/scheduler/run)."""
    if _scheduler is None:
        return False
    job = _scheduler.get_job(job_id)
    if job is None:
        return False
    asyncio.create_task(job.func())
    return True


def list_jobs() -> list[dict]:
    if _scheduler is None:
        return []
    out = []
    for j in _scheduler.get_jobs():
        out.append({
            "id": j.id,
            "next_run": j.next_run_time.isoformat() if j.next_run_time else None,
            "trigger": str(j.trigger),
        })
    return out
