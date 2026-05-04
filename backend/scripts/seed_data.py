"""Boot-time data seed — runs once during Render deploy.

If DB has < SEED_MIN_ROWS rows of OHLCV, kick off full_data_pipeline.
Otherwise no-op so subsequent deploys don't waste time.

Idempotent and fault-tolerant — never blocks the web service from starting.
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

from sqlalchemy import select, func  # noqa: E402

from app.db.models import DailyPrice  # noqa: E402
from app.db.session import async_session_maker  # noqa: E402
from scripts.full_data_pipeline import run_pipeline  # noqa: E402

log = logging.getLogger("seed_data")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")


SEED_MIN_ROWS = int(os.environ.get("SEED_MIN_ROWS", "100"))
SEED_DAYS = int(os.environ.get("SEED_DAYS", "180"))


async def main() -> int:
    try:
        async with async_session_maker() as s:
            count = (await s.execute(select(func.count(DailyPrice.id)))).scalar() or 0
        log.info("DailyPrice rows present: %d (threshold %d)", count, SEED_MIN_ROWS)
        if count >= SEED_MIN_ROWS:
            log.info("DB already seeded — skipping full backfill.")
            return 0
        log.info("DB sparse — running full_data_pipeline (days=%d) ...", SEED_DAYS)
        report = await run_pipeline(days=SEED_DAYS)
        log.info("seed report: %s", report)
        return 0
    except Exception as e:
        # NEVER fail the boot — log loudly, return 0.
        log.exception("seed failed (non-fatal): %s", e)
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
