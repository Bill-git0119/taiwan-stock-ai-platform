"""Intraday engine — 15-minute bars for finer entry timing.

Used to refine an EOD trade plan: instead of "buy at the open of day i+1",
we wait for one of these intraday triggers:

  • Opening Range Break (ORB)  — break of the first 30-minute high with volume
  • VWAP Reclaim                — price retraces to VWAP and reclaims
  • Pullback                    — first pullback to ORB midpoint then bounce

Source: yfinance interval="15m". 15m data on .TW is supported with ~60 day
history limit; we only need today's bars so that's fine.

This module is intentionally fault-tolerant: if intraday data isn't available
(weekend, pre-market, or yfinance flake), it returns
{ "ok": False, "reason": "..." } so the caller can fall back to the EOD plan.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import List, Optional

log = logging.getLogger("intraday_engine")


@dataclass
class IntradayPlan:
    symbol: str
    ok: bool
    reason: Optional[str] = None
    bars_count: int = 0
    opening_range_high: Optional[float] = None
    opening_range_low: Optional[float] = None
    vwap: Optional[float] = None
    last_15m_close: Optional[float] = None
    last_15m_volume: Optional[int] = None
    cumulative_volume: Optional[int] = None
    suggested_entry: Optional[float] = None
    trigger: Optional[str] = None              # "orb_break" / "vwap_reclaim" / "pullback" / "wait"
    confidence_boost: float = 0.0              # add to plan.confidence (0..0.15)

    def to_dict(self) -> dict:
        return asdict(self)


def _fetch_15m(symbol: str) -> List[dict]:
    """Pull today's 15-minute bars via yfinance."""
    try:
        import yfinance as yf
    except Exception as e:
        log.warning("yfinance unavailable: %s", e)
        return []

    bars: List[dict] = []
    for suffix in (".TW", ".TWO"):
        try:
            df = yf.download(
                f"{symbol}{suffix}",
                period="2d",
                interval="15m",
                progress=False,
                auto_adjust=False,
                threads=False,
            )
        except Exception as e:
            log.warning("yfinance %s: %s", symbol, e)
            df = None
        if df is None or df.empty:
            continue
        try:
            import pandas as pd
            if isinstance(df.columns, getattr(pd, "MultiIndex", tuple)):
                df.columns = df.columns.get_level_values(0)
        except Exception:
            pass
        df = df.rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        })
        df = df.reset_index().rename(columns={"Datetime": "ts", "Date": "ts"})
        # keep only today's session
        try:
            today = df["ts"].iloc[-1].date()
            df = df[df["ts"].dt.date == today]
        except Exception:
            pass
        for _, row in df.iterrows():
            bars.append({
                "ts": str(row["ts"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"] or 0),
            })
        if bars:
            return bars
    return bars


def compute_intraday_plan(symbol: str, eod_plan: Optional[dict] = None) -> IntradayPlan:
    bars = _fetch_15m(symbol)
    if len(bars) < 2:
        return IntradayPlan(symbol=symbol, ok=False, reason="no_intraday_bars")

    # Opening range = first 2 bars (= 30 minutes)
    or_bars = bars[:2]
    or_high = max(b["high"] for b in or_bars)
    or_low = min(b["low"] for b in or_bars)

    # VWAP: cumulative typical-price-weighted-by-volume
    cum_pv = 0.0
    cum_vol = 0
    for b in bars:
        tp = (b["high"] + b["low"] + b["close"]) / 3
        cum_pv += tp * b["volume"]
        cum_vol += b["volume"]
    vwap = cum_pv / cum_vol if cum_vol > 0 else None

    last = bars[-1]
    plan = IntradayPlan(
        symbol=symbol,
        ok=True,
        bars_count=len(bars),
        opening_range_high=round(or_high, 2),
        opening_range_low=round(or_low, 2),
        vwap=round(vwap, 2) if vwap else None,
        last_15m_close=round(last["close"], 2),
        last_15m_volume=last["volume"],
        cumulative_volume=cum_vol,
    )

    # Trigger logic — first match wins (priority order: ORB > VWAP > pullback > wait)
    avg_or_vol = sum(b["volume"] for b in or_bars) / len(or_bars) if or_bars else 0
    last_vol_strong = last["volume"] >= avg_or_vol * 0.8

    # Already broke ORB high with strong volume → buy at last close (or pullback)
    if last["close"] > or_high and last_vol_strong:
        plan.trigger = "orb_break"
        plan.suggested_entry = round(last["close"], 2)
        plan.confidence_boost = 0.10
    elif vwap and last["close"] >= vwap and any(b["close"] < vwap for b in bars[1:-1]):
        plan.trigger = "vwap_reclaim"
        plan.suggested_entry = round(vwap, 2)
        plan.confidence_boost = 0.05
    elif last["close"] > or_low and last["close"] < or_high:
        plan.trigger = "wait_for_break"
        plan.suggested_entry = round(or_high * 1.001, 2)
        plan.confidence_boost = 0.0
    else:
        plan.trigger = "below_or_avoid"
        plan.suggested_entry = None
        plan.confidence_boost = -0.05

    return plan
