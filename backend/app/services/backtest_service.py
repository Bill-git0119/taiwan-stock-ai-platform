"""Backtest engine — applies quant_core_rules friction & risk caps.

Strategies:
  - ai_top_rank: long when AI total_score ≥ threshold
  - ma_breakout: long when close crosses above MA20
  - chip_follow:  long when foreign+investment net buy positive
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import date
from typing import List, Literal, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChipData, DailyPrice, Score, Stock

Strategy = Literal["ai_top_rank", "ma_breakout", "chip_follow"]

# IRON RULES: friction (round-trip 0.1%, 3-tick slippage at 0.05% each ≈ 0.15%)
COMMISSION_BPS = 5      # 0.05% per side
SLIPPAGE_BPS = 5        # 3 ticks ≈ 0.05% per side
STOP_LOSS_PCT = 0.05    # >= 0.5% iron-rule, default 5% portfolio-style
MAX_POSITION_RISK = 0.03  # <= 3% per single trade
DAILY_LOSS_CIRCUIT = 0.09  # circuit-breaker at -9% on the day


@dataclass
class Trade:
    entry_date: date
    exit_date: date
    entry_price: float
    exit_price: float
    pnl_pct: float
    reason: str


@dataclass
class BacktestResult:
    strategy: Strategy
    symbol: str
    start: date
    end: date
    cagr: float
    sharpe: float
    max_drawdown: float
    win_rate: float
    trades: int
    total_return: float
    equity_curve: List[dict] = field(default_factory=list)  # [{date, equity}]
    trade_log: List[Trade] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy, "symbol": self.symbol,
            "start": self.start.isoformat(), "end": self.end.isoformat(),
            "cagr": round(self.cagr, 4),
            "sharpe": round(self.sharpe, 3),
            "max_drawdown": round(self.max_drawdown, 4),
            "win_rate": round(self.win_rate, 4),
            "trades": self.trades,
            "total_return": round(self.total_return, 4),
            "equity_curve": self.equity_curve,
            "trade_log": [
                {
                    "entry_date": t.entry_date.isoformat(),
                    "exit_date": t.exit_date.isoformat(),
                    "entry_price": t.entry_price, "exit_price": t.exit_price,
                    "pnl_pct": round(t.pnl_pct, 4), "reason": t.reason,
                }
                for t in self.trade_log
            ],
        }


def _friction(turnover: float) -> float:
    """Both-side commission + slippage on a turnover (1.0 = full position)."""
    return turnover * (COMMISSION_BPS + SLIPPAGE_BPS) / 1e4


def _signal_ma_breakout(closes: List[float], i: int) -> bool:
    if i < 20: return False
    ma = sum(closes[i - 20:i]) / 20
    return closes[i] > ma and closes[i - 1] <= ma


def _signal_ai_top(scores: dict[date, float], today: date, thr: float = 80.0) -> bool:
    s = scores.get(today)
    return s is not None and s >= thr


def _signal_chip(chips: dict[date, float], today: date) -> bool:
    s = chips.get(today)
    return s is not None and s > 0


async def _load_data(session: AsyncSession, symbol: str, start: date, end: date):
    stock = (await session.execute(select(Stock).where(Stock.symbol == symbol))).scalar_one_or_none()
    if stock is None:
        return None, [], {}, {}
    prices = (await session.execute(
        select(DailyPrice)
        .where(DailyPrice.stock_id == stock.id, DailyPrice.date >= start, DailyPrice.date <= end)
        .order_by(DailyPrice.date.asc())
    )).scalars().all()
    score_rows = (await session.execute(
        select(Score)
        .where(Score.stock_id == stock.id, Score.date >= start, Score.date <= end)
    )).scalars().all()
    chip_rows = (await session.execute(
        select(ChipData)
        .where(ChipData.stock_id == stock.id, ChipData.date >= start, ChipData.date <= end)
    )).scalars().all()
    score_map = {s.date: float(s.total_score) for s in score_rows}
    chip_map = {
        c.date: float((c.foreign_buy or 0) + (c.investment_buy or 0))
        for c in chip_rows
    }
    return stock, prices, score_map, chip_map


def _run(strategy: Strategy, symbol: str, ts: list, scores: dict, chips: dict, start: date, end: date) -> BacktestResult:
    closes = [p[1] for p in ts]
    dates = [p[0] for p in ts]
    n = len(closes)

    equity = 1.0
    peak = 1.0
    mdd = 0.0
    in_position = False
    entry_price = 0.0
    entry_date: Optional[date] = None
    daily_returns: List[float] = []
    trade_log: List[Trade] = []
    curve: List[dict] = []

    daily_loss = 0.0
    last_eq_for_day = 1.0

    for i in range(n):
        today = dates[i]
        price = closes[i]

        # circuit breaker: if today's drawdown vs morning equity exceeds limit, no new trades
        if daily_loss <= -DAILY_LOSS_CIRCUIT and in_position:
            pnl = (price - entry_price) / entry_price - _friction(2)
            equity *= (1 + pnl * MAX_POSITION_RISK)
            trade_log.append(Trade(entry_date or today, today, entry_price, price, pnl, "circuit_breaker"))
            in_position = False

        signal = False
        if strategy == "ai_top_rank":
            signal = _signal_ai_top(scores, today)
        elif strategy == "ma_breakout":
            signal = _signal_ma_breakout(closes, i)
        elif strategy == "chip_follow":
            signal = _signal_chip(chips, today)

        if not in_position and signal:
            in_position = True
            entry_price = price
            entry_date = today

        elif in_position:
            pnl_pct = (price - entry_price) / entry_price
            # stop-loss
            if pnl_pct <= -STOP_LOSS_PCT:
                gross = pnl_pct - _friction(2)
                equity *= (1 + gross * MAX_POSITION_RISK)
                trade_log.append(Trade(entry_date, today, entry_price, price, gross, "stop_loss"))
                in_position = False
            # take-profit at 1.3R
            elif pnl_pct >= STOP_LOSS_PCT * 1.3:
                gross = pnl_pct - _friction(2)
                equity *= (1 + gross * MAX_POSITION_RISK)
                trade_log.append(Trade(entry_date, today, entry_price, price, gross, "take_profit"))
                in_position = False

        if i > 0:
            day_ret = (price - closes[i - 1]) / closes[i - 1]
            daily_returns.append(day_ret)

        peak = max(peak, equity)
        if peak > 0:
            mdd = min(mdd, (equity - peak) / peak)
        if today != (dates[i - 1] if i > 0 else None):
            daily_loss = (equity / last_eq_for_day) - 1
            last_eq_for_day = equity

        curve.append({"date": today.isoformat(), "equity": round(equity, 6)})

    # close any open position at last bar
    if in_position and n > 0:
        price = closes[-1]
        pnl = (price - entry_price) / entry_price - _friction(2)
        equity *= (1 + pnl * MAX_POSITION_RISK)
        trade_log.append(Trade(entry_date or dates[-1], dates[-1], entry_price, price, pnl, "eod_close"))

    total_return = equity - 1.0
    days = max(1, (end - start).days)
    years = days / 365.25
    cagr = (equity ** (1 / years) - 1) if years > 0 and equity > 0 else 0.0

    if len(daily_returns) > 1 and statistics.pstdev(daily_returns) > 0:
        sharpe = (statistics.mean(daily_returns) / statistics.pstdev(daily_returns)) * math.sqrt(252)
    else:
        sharpe = 0.0

    wins = sum(1 for t in trade_log if t.pnl_pct > 0)
    win_rate = wins / len(trade_log) if trade_log else 0.0

    return BacktestResult(
        strategy=strategy, symbol=symbol, start=start, end=end,
        cagr=cagr, sharpe=sharpe, max_drawdown=mdd, win_rate=win_rate,
        trades=len(trade_log), total_return=total_return,
        equity_curve=curve, trade_log=trade_log,
    )


class NoRealDataError(Exception):
    """Raised when a backtest is requested for a symbol/range with no real data.

    Iron rule: never silently substitute synthetic prices — the trader must
    know whether they're looking at real history or a smoke test.
    """


async def run_backtest(
    session: AsyncSession,
    symbol: str,
    start: date,
    end: date,
    strategy: Strategy = "ai_top_rank",
    min_bars: int = 30,
) -> BacktestResult:
    stock, prices, score_map, chip_map = await _load_data(session, symbol, start, end)
    if not prices or len(prices) < min_bars:
        raise NoRealDataError(
            f"symbol={symbol} has only {len(prices)} real bars "
            f"in [{start}, {end}] — backtest aborted (need ≥{min_bars})."
        )
    ts = [(p.date, float(p.close)) for p in prices]
    return _run(strategy, symbol, ts, score_map, chip_map, start, end)
