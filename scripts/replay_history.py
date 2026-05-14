"""Historical signal replay — bootstrap edge_signals with N years of real history.

For each (symbol, trading-day) in the requested window, we slice bars up to
and including that day, run the production trade-plan engine, and persist
the result to edge_signals when bias=LONG.

Strictly lookahead-free:
  * The trade-plan engine only sees bars[:i+1] (i.e. up to & including day i)
  * The signal's `date` field is set to day i — the evaluator will later walk
    forward through bars[i+1:i+1+horizon] to mark the outcome
  * No future data ever enters either the plan logic or the outcome marking

This compresses *weeks of waiting for live signals* into seconds of compute,
letting the strategy ranker / research quality gate / correlation engine /
edge persistence analyser produce real statistics immediately.

Usage
-----
    python scripts/replay_history.py                    # 2 years default
    python scripts/replay_history.py --years 5
    python scripts/replay_history.py --symbols 2330,2317
    python scripts/replay_history.py --start 200        # skip first 200 bars
                                                        # (need at least 60
                                                        #  for indicators)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

from sqlalchemy import select  # noqa: E402

from app.db.models import ChipData, DailyPrice, EdgeSignal, Stock  # noqa: E402
from app.db.session import async_session_maker  # noqa: E402
from app.services.trade_plan_engine import build_plan  # noqa: E402

log = logging.getLogger("replay")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s - %(message)s")


MIN_BARS_BEFORE_FIRST_SIGNAL = 200   # need enough history for EMA200/ADX


async def _bars_for(session, stock_id: int) -> tuple[list[dict], list[dict]]:
    rows = (await session.execute(
        select(DailyPrice).where(DailyPrice.stock_id == stock_id)
        .order_by(DailyPrice.date.asc())
    )).scalars().all()
    bars = [{"date": r.date, "open": r.open, "high": r.high,
             "low": r.low, "close": r.close, "volume": r.volume} for r in rows]
    chips = (await session.execute(
        select(ChipData).where(ChipData.stock_id == stock_id)
        .order_by(ChipData.date.asc())
    )).scalars().all()
    chip_records = [{
        "foreign_buy": float(c.foreign_buy or 0),
        "investment_buy": float(c.investment_buy or 0),
        "dealer_buy": float(c.dealer_buy or 0),
        "volume": int(rows[i].volume) if i < len(rows) else 0,
    } for i, c in enumerate(chips)]
    return bars, chip_records


async def _signal_exists(session, on_date, symbol: str, setup: str) -> bool:
    row = (await session.execute(
        select(EdgeSignal).where(
            EdgeSignal.date == on_date,
            EdgeSignal.symbol == symbol,
            EdgeSignal.setup == setup,
        )
    )).scalar_one_or_none()
    return row is not None


async def replay_symbol(
    session, stock: Stock, *, window_days: int,
    min_start_idx: int = MIN_BARS_BEFORE_FIRST_SIGNAL,
    horizon_bars: int = 7,
) -> int:
    """Walk through this stock's history, persist LONG signals.

    Stops before the last `horizon_bars` bars so every persisted signal has
    enough future data for the evaluator.
    """
    bars, chips = await _bars_for(session, stock.id)
    if len(bars) < min_start_idx + horizon_bars + 5:
        return 0
    cutoff_date = date.today() - timedelta(days=window_days)
    # find the bar index where date crosses the window
    start_idx = max(min_start_idx, 0)
    for i, b in enumerate(bars):
        if b["date"] >= cutoff_date:
            start_idx = max(start_idx, i)
            break
    end_idx = len(bars) - horizon_bars - 1  # leave room for walk-forward
    if end_idx <= start_idx:
        return 0

    persisted = 0
    sector = stock.sector or "其他"
    for i in range(start_idx, end_idx):
        slice_bars = bars[: i + 1]
        slice_chips = chips[: min(i + 1, len(chips))]
        plan = build_plan(
            symbol=stock.symbol,
            closes=[b["close"] for b in slice_bars],
            highs=[b["high"] for b in slice_bars],
            lows=[b["low"] for b in slice_bars],
            volumes=[b["volume"] for b in slice_bars],
            chip_records=slice_chips,
            fundamental_score=60.0,
        )
        d = plan.to_dict()
        if d.get("bias") != "LONG":
            continue
        entry_zone = d.get("entry_zone") or [None, None]
        sl = d.get("stop_loss")
        tp = d.get("take_profit") or [None, None]
        if not (entry_zone[0] and sl and tp[0] and tp[1]):
            continue
        signal_date = bars[i]["date"]
        # idempotent — skip if we already persisted this triple
        if await _signal_exists(session, signal_date, stock.symbol, d["setup"]):
            continue
        regime_label = (d.get("regime") or {}).get("label")
        sig = EdgeSignal(
            date=signal_date,
            symbol=stock.symbol,
            setup=d["setup"],
            bias="LONG",
            regime=regime_label,
            sector=sector,
            entry=float(entry_zone[0]),
            stop_loss=float(sl),
            tp1=float(tp[0]),
            tp2=float(tp[1]),
            risk_reward=float(d.get("risk_reward") or 0),
            confidence=float(d.get("confidence") or 0),
            edge_score=float(d.get("edge") or 0),
        )
        session.add(sig)
        persisted += 1
    if persisted:
        await session.commit()
    return persisted


async def run(years: int = 2,
              symbols: Optional[List[str]] = None) -> dict:
    window_days = years * 365
    report = {"window_days": window_days, "symbols_processed": 0,
              "signals_persisted": 0, "failures": []}
    async with async_session_maker() as s:
        stocks_q = select(Stock)
        if symbols:
            stocks_q = stocks_q.where(Stock.symbol.in_(symbols))
        stocks = (await s.execute(stocks_q)).scalars().all()
        report["symbols_processed"] = len(stocks)
        for st in stocks:
            try:
                n = await replay_symbol(s, st, window_days=window_days)
                report["signals_persisted"] += n
                if n:
                    log.info("%s: %d signals", st.symbol, n)
            except Exception as e:
                log.exception("%s failed", st.symbol)
                report["failures"].append({"symbol": st.symbol, "error": str(e)})
    log.info("replay report: %s", {k: v for k, v in report.items() if k != "failures"})
    if report["failures"]:
        log.warning("%d symbols failed", len(report["failures"]))
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=2)
    ap.add_argument("--symbols", help="comma-separated subset")
    args = ap.parse_args()
    syms = [s.strip() for s in args.symbols.split(",")] if args.symbols else None
    asyncio.run(run(years=args.years, symbols=syms))


if __name__ == "__main__":
    main()
