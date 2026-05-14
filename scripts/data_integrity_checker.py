"""Data integrity checker — surfaces problems before they corrupt research.

Checks:
  1. Missing bars (calendar gaps inside a symbol's series)
  2. Duplicate (stock_id, date) pairs        — should be 0
  3. Anomalous prices: |daily return| > 50%
  4. Zero-volume bars
  5. Per-symbol coverage vs MIN_BARS_REQUIRED
  6. OHLC sanity: low<=open,close<=high

Exit code: 0 if all clean, 1 if any failure. Used by CI/cron.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

from sqlalchemy import func, select  # noqa: E402

from app.db.models import DailyPrice, Stock  # noqa: E402
from app.db.session import async_session_maker  # noqa: E402

log = logging.getLogger("integrity")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")


MIN_BARS_REQUIRED = 1000
MAX_DAILY_RETURN_PCT = 50.0
MAX_GAP_TRADING_DAYS = 5


def _is_weekday(d: date) -> bool:
    return d.weekday() < 5


async def check() -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "as_of": date.today().isoformat(),
        "symbols_checked": 0,
        "missing_bars": [],
        "thin_coverage": [],
        "anomalous_prices": [],
        "zero_volume_today": [],
        "ohlc_invalid": [],
        "duplicate_dates": [],
        "passes": True,
    }
    async with async_session_maker() as s:
        # duplicates
        dup_rows = (await s.execute(
            select(DailyPrice.stock_id, DailyPrice.date, func.count(DailyPrice.id).label("c"))
            .group_by(DailyPrice.stock_id, DailyPrice.date)
            .having(func.count(DailyPrice.id) > 1)
        )).all()
        if dup_rows:
            report["duplicate_dates"] = [
                {"stock_id": r[0], "date": str(r[1]), "count": r[2]}
                for r in dup_rows
            ]
            report["passes"] = False

        stocks = (await s.execute(select(Stock))).scalars().all()
        report["symbols_checked"] = len(stocks)
        for st in stocks:
            rows = (await s.execute(
                select(DailyPrice).where(DailyPrice.stock_id == st.id)
                .order_by(DailyPrice.date.asc())
            )).scalars().all()
            if len(rows) < MIN_BARS_REQUIRED:
                report["thin_coverage"].append({"symbol": st.symbol, "bars": len(rows)})

            prev_date = None
            prev_close = None
            for r in rows:
                # gap detection (>5 trading-day gap)
                if prev_date is not None:
                    gap_days = (r.date - prev_date).days
                    weekdays_between = sum(
                        1 for i in range(1, gap_days)
                        if _is_weekday(prev_date + timedelta(days=i))
                    )
                    if weekdays_between > MAX_GAP_TRADING_DAYS:
                        report["missing_bars"].append({
                            "symbol": st.symbol, "between": str(prev_date),
                            "next": str(r.date), "weekday_gap": weekdays_between,
                        })
                # OHLC sanity
                if not (r.low <= r.open <= r.high and r.low <= r.close <= r.high):
                    report["ohlc_invalid"].append({
                        "symbol": st.symbol, "date": str(r.date),
                        "o": r.open, "h": r.high, "l": r.low, "c": r.close,
                    })
                # anomalous return
                if prev_close and prev_close > 0:
                    chg = (r.close / prev_close - 1) * 100
                    if abs(chg) >= MAX_DAILY_RETURN_PCT:
                        report["anomalous_prices"].append({
                            "symbol": st.symbol, "date": str(r.date),
                            "change_pct": round(chg, 2),
                        })
                # zero volume on the most recent bar only
                if r is rows[-1] and r.volume == 0:
                    report["zero_volume_today"].append({
                        "symbol": st.symbol, "date": str(r.date),
                    })
                prev_date = r.date
                prev_close = r.close

    # decide overall pass — thin coverage is warning, not failure
    bad = (
        bool(report["missing_bars"])
        or bool(report["anomalous_prices"])
        or bool(report["ohlc_invalid"])
        or bool(report["duplicate_dates"])
    )
    if bad:
        report["passes"] = False
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="json output")
    args = ap.parse_args()
    rep = asyncio.run(check())
    if args.json:
        print(json.dumps(rep, indent=2, default=str))
    else:
        print(f"as_of: {rep['as_of']}")
        print(f"symbols_checked: {rep['symbols_checked']}")
        print(f"thin_coverage: {len(rep['thin_coverage'])}")
        print(f"missing_bars: {len(rep['missing_bars'])}")
        print(f"anomalous_prices: {len(rep['anomalous_prices'])}")
        print(f"ohlc_invalid: {len(rep['ohlc_invalid'])}")
        print(f"duplicate_dates: {len(rep['duplicate_dates'])}")
        print(f"PASSES: {rep['passes']}")
    sys.exit(0 if rep["passes"] else 1)


if __name__ == "__main__":
    main()
