"""Edge tracking — turn every LONG signal into measurable historical edge.

Three responsibilities:
  1. persist_signal()       — store a fresh signal at scan time (idempotent)
  2. evaluate_open_signals() — for any signal older than N bars, walk forward
                               on real OHLC and mark TP1 / TP2 / stop / timeout
  3. setup_stats()          — return {setup: SetupStats} dict for the scanner

All evaluation is *strictly* lookahead-free. Today's signal is not evaluated
until at least EVAL_HORIZON_BARS days have elapsed. Even then, evaluation
walks bars **after** the signal date (entry fill at next bar's open + slippage,
identical to the backtest engine).
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, List, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DailyPrice, EdgeSignal, Stock

log = logging.getLogger("edge_tracking")


# ─────────────────────────── config ────────────────────────────

EVAL_HORIZON_BARS = 7      # number of trading days to give each trade
SLIPPAGE_BPS = 5.0         # 0.05% per side, matches backtest engine
COMMISSION_BPS = 5.0
WINRATE_MIN_SAMPLES = 8    # don't compute stats until this many evaluated trades


@dataclass
class SetupStats:
    setup: str
    sample_size: int
    win_rate: float           # 0..1
    avg_rr: float             # in R units (positive = profitable)
    expectancy: float         # win_rate*avg_win_R - (1-win_rate)*avg_loss_R
    max_consecutive_loss: int
    avg_bars_held: float
    last_30d_count: int
    is_healthy: bool          # auto-disable flag

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────── persist ───────────────────────────

async def persist_signal(
    session: AsyncSession,
    *,
    symbol: str,
    setup: str,
    plan: dict,
    regime: Optional[str] = None,
    on_date: Optional[date] = None,
) -> Optional[EdgeSignal]:
    """Insert a row for today's LONG signal (no-op on duplicate)."""
    on_date = on_date or date.today()
    if plan.get("bias") != "LONG":
        return None
    entry_zone = plan.get("entry_zone") or [None, None]
    sl = plan.get("stop_loss")
    tp = plan.get("take_profit") or [None, None]
    if not (entry_zone[0] and sl and tp[0] and tp[1]):
        return None

    existing = (await session.execute(
        select(EdgeSignal).where(
            EdgeSignal.date == on_date,
            EdgeSignal.symbol == symbol,
            EdgeSignal.setup == setup,
        )
    )).scalar_one_or_none()
    if existing is not None:
        return existing

    obj = EdgeSignal(
        date=on_date,
        symbol=symbol,
        setup=setup,
        bias="LONG",
        regime=regime,
        entry=float(entry_zone[0]),
        stop_loss=float(sl),
        tp1=float(tp[0]),
        tp2=float(tp[1]),
        risk_reward=float(plan.get("risk_reward") or 0),
        confidence=float(plan.get("confidence") or 0),
        edge_score=float(plan.get("edge") or 0),
    )
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj


# ─────────────────────────── evaluate ──────────────────────────

async def _bars_after(
    session: AsyncSession, symbol: str, after: date, limit: int = EVAL_HORIZON_BARS + 1,
) -> List[DailyPrice]:
    stock = (
        await session.execute(select(Stock).where(Stock.symbol == symbol))
    ).scalar_one_or_none()
    if stock is None:
        return []
    return (
        await session.execute(
            select(DailyPrice)
            .where(DailyPrice.stock_id == stock.id, DailyPrice.date > after)
            .order_by(DailyPrice.date.asc())
            .limit(limit)
        )
    ).scalars().all()


def _evaluate_walk(sig: EdgeSignal, bars: List[DailyPrice]) -> dict:
    """Walk forward through bars and find the outcome.

    Pessimistic: if both stop and TP can hit on the same bar, stop wins.
    Entry fills at next bar open + slippage (lookahead-free).
    """
    if not bars:
        return {"exit_reason": "no_data", "exit_price": None, "realized_r": None,
                "win": None, "bars_held": 0}
    fill_bar = bars[0]
    fill_price = float(fill_bar.open) * (1 + (SLIPPAGE_BPS + COMMISSION_BPS) / 10_000)
    risk = fill_price - sig.stop_loss
    if risk <= 0:
        return {"exit_reason": "invalid", "exit_price": fill_price, "realized_r": 0.0,
                "win": False, "bars_held": 0}

    held = 0
    for b in bars[1:]:
        held += 1
        # pessimistic SL first
        if b.low <= sig.stop_loss:
            exit_p = sig.stop_loss * (1 - COMMISSION_BPS / 10_000)
            r = (exit_p - fill_price) / risk
            return {"exit_reason": "stop", "exit_price": float(exit_p),
                    "realized_r": round(r, 4), "win": False, "bars_held": held}
        if b.high >= sig.tp2:
            exit_p = sig.tp2 * (1 - COMMISSION_BPS / 10_000)
            r = (exit_p - fill_price) / risk
            return {"exit_reason": "tp2", "exit_price": float(exit_p),
                    "realized_r": round(r, 4), "win": True, "bars_held": held}
        if b.high >= sig.tp1:
            exit_p = sig.tp1 * (1 - COMMISSION_BPS / 10_000)
            r = (exit_p - fill_price) / risk
            return {"exit_reason": "tp1", "exit_price": float(exit_p),
                    "realized_r": round(r, 4), "win": True, "bars_held": held}

    # ran out of horizon — close at last bar's close
    last = bars[-1]
    exit_p = float(last.close) * (1 - COMMISSION_BPS / 10_000)
    r = (exit_p - fill_price) / risk
    return {"exit_reason": "timeout", "exit_price": exit_p,
            "realized_r": round(r, 4), "win": r > 0, "bars_held": held}


async def evaluate_open_signals(session: AsyncSession,
                                horizon_bars: int = EVAL_HORIZON_BARS) -> dict:
    """For every unevaluated signal at least `horizon_bars` calendar days old,
    walk forward and mark the outcome."""
    cutoff = date.today() - timedelta(days=horizon_bars)
    open_signals = (
        await session.execute(
            select(EdgeSignal)
            .where(EdgeSignal.evaluated == False, EdgeSignal.date <= cutoff)  # noqa: E712
            .order_by(EdgeSignal.date.asc())
        )
    ).scalars().all()
    n_eval = 0
    for sig in open_signals:
        bars = await _bars_after(session, sig.symbol, sig.date, limit=horizon_bars + 1)
        if len(bars) < 2:
            # not enough data yet — leave for next run
            continue
        result = _evaluate_walk(sig, bars)
        sig.evaluated = True
        sig.evaluated_at = datetime.utcnow()
        sig.exit_reason = result["exit_reason"]
        sig.exit_price = result["exit_price"]
        sig.realized_r = result["realized_r"]
        sig.win = result["win"]
        sig.bars_held = result["bars_held"]
        n_eval += 1
    if n_eval:
        await session.commit()
    log.info("evaluate_open_signals: %d signals scored", n_eval)
    return {"evaluated": n_eval, "still_open": len(open_signals) - n_eval}


# ─────────────────────────── stats ─────────────────────────────

def _max_consecutive_loss(realized_rs: Iterable[float]) -> int:
    cur = mx = 0
    for r in realized_rs:
        if r is None:
            continue
        if r < 0:
            cur += 1
            mx = max(mx, cur)
        else:
            cur = 0
    return mx


async def setup_stats(
    session: AsyncSession, lookback_days: int = 90,
) -> dict[str, SetupStats]:
    """Compute SetupStats per setup over the last `lookback_days`."""
    cutoff = date.today() - timedelta(days=lookback_days)
    rows = (
        await session.execute(
            select(EdgeSignal)
            .where(EdgeSignal.evaluated == True, EdgeSignal.date >= cutoff)  # noqa: E712
        )
    ).scalars().all()

    by_setup: dict[str, list[EdgeSignal]] = {}
    for r in rows:
        by_setup.setdefault(r.setup, []).append(r)

    out: dict[str, SetupStats] = {}
    last30 = date.today() - timedelta(days=30)
    for setup, items in by_setup.items():
        wins = [s for s in items if s.win is True]
        losses = [s for s in items if s.win is False]
        n = len(wins) + len(losses)
        if n == 0:
            continue
        win_rate = len(wins) / n
        win_rs = [s.realized_r for s in wins if s.realized_r is not None]
        loss_rs = [s.realized_r for s in losses if s.realized_r is not None]
        avg_win_r = (sum(win_rs) / len(win_rs)) if win_rs else 0.0
        avg_loss_r = abs(sum(loss_rs) / len(loss_rs)) if loss_rs else 0.0
        expectancy = win_rate * avg_win_r - (1 - win_rate) * avg_loss_r
        all_rs = [s.realized_r for s in items if s.realized_r is not None]
        avg_rr = sum(all_rs) / len(all_rs) if all_rs else 0.0
        bars_kept = [s.bars_held for s in items if s.bars_held is not None]
        avg_bars = sum(bars_kept) / len(bars_kept) if bars_kept else 0.0
        # walk by date for max consecutive loss
        items_sorted = sorted(items, key=lambda s: s.date)
        max_streak = _max_consecutive_loss([s.realized_r for s in items_sorted])
        last30_count = sum(1 for s in items if s.date >= last30)
        is_healthy = (
            n < WINRATE_MIN_SAMPLES  # not enough data — give it benefit of the doubt
            or (win_rate >= 0.45 and expectancy > -0.2)
        )
        out[setup] = SetupStats(
            setup=setup,
            sample_size=n,
            win_rate=round(win_rate, 4),
            avg_rr=round(avg_rr, 4),
            expectancy=round(expectancy, 4),
            max_consecutive_loss=int(max_streak),
            avg_bars_held=round(avg_bars, 2),
            last_30d_count=last30_count,
            is_healthy=bool(is_healthy),
        )
    return out


async def disabled_setups(session: AsyncSession) -> set[str]:
    stats = await setup_stats(session)
    return {k for k, v in stats.items() if not v.is_healthy}
