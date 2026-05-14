"""Boot-time data seed — runs once during Render deploy.

Two stages, both fault-tolerant:

  Stage A : if DB has < SEED_MIN_ROWS rows of OHLCV, run the TOP100 5-year
            backfill (scripts/top100_backfill). Covers the full curated
            universe (~90 symbols × ~1240 bars).

  Stage B : after data lands, replay the last SEED_REPLAY_YEARS years
            through the trade-plan engine to seed edge_signals so the
            scanner / brief / performance pages have real numbers from
            day 1. Off by default — set SEED_REPLAY=true to enable.

Always returns 0 so it never blocks the web service from starting.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

# Resolve repo root: this file lives at backend/scripts/seed_data.py
_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parent
_ROOT = _BACKEND.parent
for p in (str(_ROOT), str(_BACKEND)):
    if p not in sys.path:
        sys.path.insert(0, p)

from sqlalchemy import func, select  # noqa: E402

from app.db.models import DailyPrice  # noqa: E402
from app.db.session import async_session_maker  # noqa: E402

log = logging.getLogger("seed_data")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s - %(message)s")


SEED_MIN_ROWS = int(os.environ.get("SEED_MIN_ROWS", "1000"))
SEED_YEARS = int(os.environ.get("SEED_YEARS", "5"))
SEED_REPLAY = os.environ.get("SEED_REPLAY", "false").lower() == "true"
SEED_REPLAY_YEARS = int(os.environ.get("SEED_REPLAY_YEARS", "2"))


async def _row_count() -> int:
    async with async_session_maker() as s:
        return (await s.execute(select(func.count(DailyPrice.id)))).scalar() or 0


async def main() -> int:
    try:
        count = await _row_count()
        log.info("DailyPrice rows present: %d (threshold %d)", count, SEED_MIN_ROWS)
        if count < SEED_MIN_ROWS:
            log.info("DB sparse — running top100_backfill (years=%d) ...", SEED_YEARS)
            try:
                from scripts.top100_backfill import run as backfill_run
                report = await backfill_run(years=SEED_YEARS, max_concurrency=1)
                log.info("backfill: ok=%d thin=%d failed=%d",
                          report.get("ok", 0), report.get("thin", 0),
                          report.get("failed", 0))
            except Exception as e:
                log.exception("backfill failed (continuing boot): %s", e)
        else:
            log.info("DB already seeded — skipping backfill.")

        if SEED_REPLAY:
            current = await _row_count()
            if current >= SEED_MIN_ROWS:
                log.info("Replaying %d years to seed edge_signals ...", SEED_REPLAY_YEARS)
                try:
                    from scripts.replay_history import run as replay_run
                    from app.services.edge_tracking_service import evaluate_open_signals
                    rep = await replay_run(years=SEED_REPLAY_YEARS)
                    log.info("replay: persisted=%d failed=%d",
                              rep.get("signals_persisted", 0),
                              len(rep.get("failures", [])))
                    async with async_session_maker() as s:
                        ev = await evaluate_open_signals(s)
                    log.info("evaluator: evaluated=%d still_open=%d",
                              ev.get("evaluated", 0), ev.get("still_open", 0))
                except Exception as e:
                    log.exception("replay failed (continuing boot): %s", e)
            else:
                log.info("Skipping replay — DB still under threshold (%d rows)", current)
        return 0
    except Exception as e:
        log.exception("seed failed (non-fatal): %s", e)
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
