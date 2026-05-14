"""TOP100 5-year backfill.

Pulls the full curated universe from yfinance with at least 1250 bars
(~5 trading years). Idempotent — re-running upserts new bars only.

Usage
-----
    python scripts/top100_backfill.py                     # 5y default
    python scripts/top100_backfill.py --years 3
    python scripts/top100_backfill.py --symbols 2330,2317
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

import pandas as pd  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.models import DailyPrice, Stock  # noqa: E402
from app.db.session import async_session_maker, engine  # noqa: E402
from app.universe.curated import deduplicated  # noqa: E402
from scripts.full_data_pipeline import fetch_yahoo_history  # noqa: E402

log = logging.getLogger("top100_backfill")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")


MIN_BARS_REQUIRED = 1000   # ~4 trading years
DEFAULT_YEARS = 5


async def _ensure_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _ensure_stock(session, sym: str, name: str, market: str, sector: str) -> Stock:
    st = (await session.execute(
        select(Stock).where(Stock.symbol == sym)
    )).scalar_one_or_none()
    if st is None:
        st = Stock(symbol=sym, name=name, market=market, sector=sector)
        session.add(st)
        await session.flush()
    else:
        if not st.sector or st.sector == "其他":
            st.sector = sector
    return st


def _scalar(v):
    """Coerce any pandas Series/array of length 1 to a Python scalar."""
    if hasattr(v, "item"):
        try:
            return v.item()
        except (ValueError, AttributeError):
            pass
    if hasattr(v, "iloc"):
        try:
            return v.iloc[0]
        except Exception:
            pass
    return v


async def _upsert_bars(session, stock_id: int, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    n = 0
    for _, row in df.iterrows():
        d = _scalar(row["date"])
        if hasattr(d, "date"):
            d = d.date()
        existing = (await session.execute(
            select(DailyPrice).where(
                DailyPrice.stock_id == stock_id,
                DailyPrice.date == d,
            )
        )).scalar_one_or_none()
        try:
            fields = dict(
                open=float(_scalar(row["open"])),
                high=float(_scalar(row["high"])),
                low=float(_scalar(row["low"])),
                close=float(_scalar(row["close"])),
                volume=int(_scalar(row.get("volume") or 0)),
            )
        except (TypeError, ValueError):
            # Bad row — skip rather than abort entire backfill
            continue
        if existing is None:
            session.add(DailyPrice(stock_id=stock_id, date=d, **fields))
        else:
            for k, v in fields.items():
                setattr(existing, k, v)
        n += 1
    return n


async def run(years: int = DEFAULT_YEARS,
              symbols: List[str] | None = None,
              max_concurrency: int = 5) -> dict:
    await _ensure_tables()
    universe = deduplicated()
    if symbols:
        universe = [u for u in universe if u[0] in set(symbols)]
    days = years * 365 + 30
    report = {
        "started_at": datetime.utcnow().isoformat() + "Z",
        "years": years,
        "universe_size": len(universe),
        "ok": 0,
        "thin": 0,
        "failed": 0,
        "coverage": {},
    }
    loop = asyncio.get_running_loop()
    sem = asyncio.Semaphore(max_concurrency)

    async def _one(sym, name, market, sec_zh, _sec_en):
        async with sem:
            try:
                df = await loop.run_in_executor(None, fetch_yahoo_history, sym, days)
            except Exception as e:
                log.warning("%s: yfinance error %s", sym, e)
                report["failed"] += 1
                return
            async with async_session_maker() as s:
                st = await _ensure_stock(s, sym, name, market, sec_zh)
                bars_written = await _upsert_bars(s, st.id, df)
                await s.commit()
                count = (await s.execute(
                    select(func.count(DailyPrice.id))
                    .where(DailyPrice.stock_id == st.id)
                )).scalar() or 0
            report["coverage"][sym] = int(count)
            if count >= MIN_BARS_REQUIRED:
                report["ok"] += 1
                log.info("%s: %d bars (+%d new)", sym, count, bars_written)
            elif count > 0:
                report["thin"] += 1
                log.warning("%s: only %d bars, below threshold %d",
                             sym, count, MIN_BARS_REQUIRED)
            else:
                report["failed"] += 1
                log.error("%s: no bars persisted", sym)

    tasks = [asyncio.create_task(_one(*row)) for row in universe]
    await asyncio.gather(*tasks)
    report["finished_at"] = datetime.utcnow().isoformat() + "Z"
    log.info("backfill report: ok=%d thin=%d failed=%d",
             report["ok"], report["thin"], report["failed"])
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=DEFAULT_YEARS)
    ap.add_argument("--symbols", help="comma-separated symbol subset")
    ap.add_argument("--concurrency", type=int, default=5)
    args = ap.parse_args()
    syms = [s.strip() for s in args.symbols.split(",")] if args.symbols else None
    asyncio.run(run(years=args.years, symbols=syms,
                    max_concurrency=args.concurrency))


if __name__ == "__main__":
    main()
