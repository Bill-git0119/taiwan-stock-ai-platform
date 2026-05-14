"""Rolling daily update — incremental bars only.

For each stock, find the most recent persisted bar, fetch yfinance from that
date forward, upsert. This is what the daily 15:10 cron job calls.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

import pandas as pd  # noqa: E402
import yfinance as yf  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.db.models import DailyPrice, Stock  # noqa: E402
from app.db.session import async_session_maker  # noqa: E402

log = logging.getLogger("rolling_update")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")


def _fetch(sym: str, since: date) -> pd.DataFrame:
    end = date.today() + timedelta(days=1)
    if since >= end:
        return pd.DataFrame()
    for suffix in (".TW", ".TWO"):
        try:
            df = yf.download(
                f"{sym}{suffix}",
                start=since.isoformat(),
                end=end.isoformat(),
                progress=False, auto_adjust=False, threads=False,
            )
        except Exception:
            df = pd.DataFrame()
        if df is None or df.empty:
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        }).reset_index().rename(columns={"Date": "date"})
        df["symbol"] = sym
        return df
    return pd.DataFrame()


async def run() -> dict:
    report = {
        "started_at": datetime.utcnow().isoformat() + "Z",
        "stocks_seen": 0,
        "bars_added": 0,
        "up_to_date": 0,
    }
    today = date.today()
    async with async_session_maker() as s:
        stocks = (await s.execute(select(Stock))).scalars().all()
        report["stocks_seen"] = len(stocks)
        for st in stocks:
            latest = (await s.execute(
                select(func.max(DailyPrice.date))
                .where(DailyPrice.stock_id == st.id)
            )).scalar()
            since = (latest + timedelta(days=1)) if latest else today - timedelta(days=30)
            if since > today:
                report["up_to_date"] += 1
                continue
            df = await asyncio.get_running_loop().run_in_executor(None, _fetch, st.symbol, since)
            if df.empty:
                continue
            for _, row in df.iterrows():
                d = row["date"]
                if hasattr(d, "date"):
                    d = d.date()
                exists = (await s.execute(
                    select(DailyPrice).where(
                        DailyPrice.stock_id == st.id, DailyPrice.date == d,
                    )
                )).scalar_one_or_none()
                if exists is not None:
                    continue
                s.add(DailyPrice(
                    stock_id=st.id, date=d,
                    open=float(row["open"]), high=float(row["high"]),
                    low=float(row["low"]), close=float(row["close"]),
                    volume=int(row.get("volume") or 0),
                ))
                report["bars_added"] += 1
        await s.commit()
    report["finished_at"] = datetime.utcnow().isoformat() + "Z"
    log.info("rolling_update: %s", report)
    return report


def main() -> None:
    argparse.ArgumentParser().parse_args()
    asyncio.run(run())


if __name__ == "__main__":
    main()
