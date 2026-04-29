"""Run the AI scoring pipeline and persist to DB.

    python scripts/run_scoring.py
    python scripts/run_scoring.py --date 20260423
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

from app.db.base import Base  # noqa: E402
from app.db.session import async_session_maker, engine  # noqa: E402
from app.services.scoring_pipeline import persist_scores, score_all  # noqa: E402

log = logging.getLogger("scoring")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")


async def run(as_of: date) -> dict:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as session:
        scored = await score_all(session, as_of=as_of)
        n = await persist_scores(session, scored, as_of)
    top10 = scored[:10]
    log.info("Scored %d stocks; TOP10: %s", n, [(s.symbol, s.total_score) for s in top10])
    return {"scored": n, "top10": [s.to_dict() for s in top10]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYYMMDD")
    args = ap.parse_args()
    as_of = datetime.strptime(args.date, "%Y%m%d").date() if args.date else date.today()
    asyncio.run(run(as_of))


if __name__ == "__main__":
    main()
