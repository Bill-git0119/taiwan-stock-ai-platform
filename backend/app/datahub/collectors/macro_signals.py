"""Macro signals collector — VIX, DXY, US indices, US 10Y yield.

Used by the regime engine to gate Taiwan setups against the broader
risk environment. Pulled from yfinance (same as daily prices), but
stored in a separate MacroSignal table-like dict in cache. Lightweight
— pulled once daily.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from loguru import logger

from app.datahub.collectors.base import BaseCollector, CollectorResult
from app.services.cache_service import cache

# yfinance symbols → friendly key
MACRO_TICKERS: dict[str, str] = {
    "^VIX": "vix",            # CBOE volatility index
    "DX-Y.NYB": "dxy",        # US dollar index
    "^GSPC": "sp500",         # S&P 500
    "^IXIC": "nasdaq",        # Nasdaq Composite
    "^DJI": "dow",            # Dow Jones
    "^TNX": "us10y_yield",    # 10-year Treasury yield (×10)
    "^TWII": "twii",          # Taiwan weighted index (real TAIEX)
}

CACHE_KEY = "macro:snapshot"
CACHE_TTL_SECONDS = 60 * 60 * 12  # 12h — refreshed by scheduler daily


class MacroSignalsCollector(BaseCollector):
    source = "macro.daily"

    def __init__(self, lookback_days: int = 90):
        self.lookback_days = lookback_days

    async def _collect(self) -> CollectorResult:
        import yfinance as yf

        end = datetime.utcnow().date()
        start = end - timedelta(days=self.lookback_days + 5)

        snap: dict[str, dict] = {}
        failed: list[str] = []
        latest_dt: Optional[datetime] = None

        for ticker, key in MACRO_TICKERS.items():
            try:
                df = await asyncio.to_thread(
                    yf.download, ticker,
                    start=start.isoformat(),
                    end=(end + timedelta(days=1)).isoformat(),
                    progress=False, auto_adjust=False, threads=False,
                )
                if df is None or df.empty:
                    failed.append(ticker)
                    continue
                closes = df["Close"].squeeze().dropna().tolist()
                dates = [d.date().isoformat() for d in df.index]
                last = float(closes[-1])
                prev = float(closes[-2]) if len(closes) >= 2 else last
                d1_pct = (last / prev - 1.0) * 100 if prev else 0.0
                # 20d realized vol = stdev of log returns
                import math
                log_rets = [math.log(closes[i] / closes[i - 1])
                            for i in range(1, len(closes))]
                window = log_rets[-20:]
                if window:
                    mean = sum(window) / len(window)
                    var = sum((r - mean) ** 2 for r in window) / len(window)
                    realized_vol = (var ** 0.5) * (252 ** 0.5) * 100
                else:
                    realized_vol = 0.0
                snap[key] = {
                    "ticker": ticker,
                    "last": round(last, 4),
                    "d1_pct": round(d1_pct, 3),
                    "realized_vol_20d": round(realized_vol, 2),
                    "as_of": dates[-1] if dates else None,
                    "n_bars": len(closes),
                }
                if dates:
                    dt = datetime.strptime(dates[-1], "%Y-%m-%d")
                    if latest_dt is None or dt > latest_dt:
                        latest_dt = dt
            except Exception as e:
                failed.append(ticker)
                logger.warning("macro {} failed: {}", ticker, e)

        if not snap:
            raise RuntimeError(f"macro: all {len(MACRO_TICKERS)} tickers failed")

        snap["_meta"] = {
            "collected_at": datetime.utcnow().isoformat(),
            "failed": failed,
            "ok": len(snap) - 0,  # snap already excludes _meta when computed
        }

        await cache.set(CACHE_KEY, snap, ttl=CACHE_TTL_SECONDS)
        return CollectorResult(
            rows=len(snap) - 1,  # excluding _meta
            latest_data_at=latest_dt,
            note=(f"{len(failed)} failed: {failed}" if failed else None),
        )


async def latest_macro() -> Optional[dict]:
    """Read latest macro snapshot from cache. Returns None if collector
    has never run."""
    return await cache.get(CACHE_KEY)
