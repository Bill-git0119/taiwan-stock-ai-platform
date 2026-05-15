"""yfinance daily OHLCV collector.

Pulls bars for every Stock in the universe and upserts into DailyPrice.
Idempotent on (stock_id, date). Handles yfinance's MultiIndex result
shape (single-symbol and multi-symbol) and never silently substitutes
fake data — raises on empty result.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.datahub.collectors.base import BaseCollector, CollectorResult
from app.db.models import DailyPrice, Stock
from app.db.session import async_session_maker


def _scalar(v):
    if hasattr(v, "item"):
        return v.item()
    if hasattr(v, "iloc"):
        return v.iloc[0]
    return v


def _flatten_columns(df: "pd.DataFrame") -> "pd.DataFrame":
    """yfinance ≥ 0.2 returns MultiIndex columns. Pick whichever level
    contains the OHLCV field names and flatten."""
    if isinstance(df.columns, pd.MultiIndex):
        FIELD_TAGS = {"Open", "High", "Low", "Close", "Adj Close", "Volume"}
        lv0 = set(df.columns.get_level_values(0))
        lv1 = set(df.columns.get_level_values(1))
        level = 0 if (FIELD_TAGS & lv0) else (1 if (FIELD_TAGS & lv1) else 0)
        df.columns = df.columns.get_level_values(level)
    return df.loc[:, ~df.columns.duplicated()]


class YFinanceDailyCollector(BaseCollector):
    source = "yfinance.daily"

    def __init__(self, *, days: int = 30, symbols: Optional[list[str]] = None):
        self.days = days
        self.symbols = symbols  # if None, pull every Stock in DB

    async def _collect(self) -> CollectorResult:
        # Lazy import — yfinance is heavy.
        import asyncio

        import yfinance as yf  # noqa: F401

        async with async_session_maker() as s:
            stocks = (await s.execute(select(Stock))).scalars().all()
        if not stocks:
            raise RuntimeError("no Stock rows — seed universe first")

        target_syms = self.symbols or [st.symbol for st in stocks]
        sym_to_id = {st.symbol: st.id for st in stocks}
        market_suffix = {st.symbol: ".TW" if st.market != "TPEX" else ".TWO"
                         for st in stocks}

        end = datetime.utcnow().date()
        start = end - timedelta(days=self.days + 5)

        rows_total = 0
        latest_any: Optional[datetime] = None
        failed: list[str] = []

        for sym in target_syms:
            sid = sym_to_id.get(sym)
            if sid is None:
                continue
            ticker = sym + market_suffix.get(sym, ".TW")
            try:
                df = await asyncio.to_thread(
                    yf.download, ticker,
                    start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
                    progress=False, auto_adjust=False, threads=False,
                )
                if df is None or df.empty:
                    failed.append(sym)
                    continue
                df = _flatten_columns(df)
                rows = []
                for idx, row in df.iterrows():
                    d = idx.date() if hasattr(idx, "date") else idx
                    try:
                        rows.append({
                            "stock_id": sid,
                            "date": d,
                            "open": float(_scalar(row["Open"])),
                            "high": float(_scalar(row["High"])),
                            "low": float(_scalar(row["Low"])),
                            "close": float(_scalar(row["Close"])),
                            "volume": int(_scalar(row["Volume"]) or 0),
                        })
                    except Exception as e:
                        logger.debug("skip {} {}: {}", sym, d, e)
                if rows:
                    async with async_session_maker() as s:
                        stmt = sqlite_insert(DailyPrice).values(rows)
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["stock_id", "date"],
                            set_={
                                "open": stmt.excluded.open,
                                "high": stmt.excluded.high,
                                "low": stmt.excluded.low,
                                "close": stmt.excluded.close,
                                "volume": stmt.excluded.volume,
                            },
                        )
                        await s.execute(stmt)
                        await s.commit()
                    rows_total += len(rows)
                    last_d = rows[-1]["date"]
                    if isinstance(last_d, datetime):
                        last_dt = last_d
                    else:
                        last_dt = datetime.combine(last_d, datetime.min.time())
                    if latest_any is None or last_dt > latest_any:
                        latest_any = last_dt
            except Exception as e:
                failed.append(sym)
                logger.warning("yfinance {} failed: {}", sym, e)

        note = None
        if failed:
            note = f"{len(failed)}/{len(target_syms)} symbols failed: {failed[:5]}"
        if rows_total == 0:
            raise RuntimeError(f"yfinance returned 0 rows for {len(target_syms)} symbols")
        return CollectorResult(rows=rows_total, latest_data_at=latest_any, note=note)
