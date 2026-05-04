"""Backtest Engine v2 — bar-by-bar simulation, no lookahead.

Iron rules (hard-coded):
  * Commission: 0.05% / side  (round-trip = 0.10%)
  * Slippage:   0.05% / side
  * SL & TP cleared on each bar's high/low (intrabar)
  * Risk per trade: ≤ 1% of equity (set via cfg.risk_pct)
  * Stop must sit below entry (LONG) — non-positive risk → trade rejected

Inputs
------
bars: list of OHLCV dicts ordered oldest→newest:
    {"date": "YYYY-MM-DD", "open": .., "high": .., "low": .., "close": .., "volume": ..}

strategy: callable(bar_index, history) -> Optional[Signal]
    Where Signal is a TradeSignal dataclass (see strategies module).

Returns BacktestReport with: trades, win_rate, profit_factor, sharpe,
max_drawdown, total_return, equity_curve, cagr.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Callable, Iterable, List, Optional


COMMISSION_BPS = 5.0
SLIPPAGE_BPS = 5.0


@dataclass
class TradeSignal:
    """Trade intent emitted by a strategy on bar `i`. The engine fills on
    the NEXT bar's open (no lookahead)."""
    bias: str = "LONG"           # only LONG supported in v2
    entry_hint: float = 0.0      # guidance, engine uses next-bar open
    stop_loss: float = 0.0
    take_profit: float = 0.0
    note: str = ""


@dataclass
class FilledTrade:
    entry_date: str
    exit_date: str
    entry: float
    exit: float
    stop: float
    target: float
    qty: int
    pnl_twd: float
    pnl_pct: float
    bars_held: int
    exit_reason: str             # "tp" / "sl" / "eod"
    note: str = ""


@dataclass
class BacktestConfig:
    starting_equity: float = 1_000_000.0
    risk_pct: float = 0.01       # ≤ 1% per trade
    commission_bps: float = COMMISSION_BPS
    slippage_bps: float = SLIPPAGE_BPS
    max_hold_bars: int = 30


@dataclass
class BacktestReport:
    strategy: str
    symbol: str
    bars: int
    trades_count: int
    wins: int
    losses: int
    win_rate: float
    profit_factor: float
    sharpe: float
    max_drawdown: float
    total_return: float
    cagr: float
    final_equity: float
    equity_curve: List[dict] = field(default_factory=list)
    trades: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────

def _apply_friction_buy(price: float, cfg: BacktestConfig) -> float:
    return price * (1 + (cfg.commission_bps + cfg.slippage_bps) / 10_000)


def _apply_friction_sell(price: float, cfg: BacktestConfig) -> float:
    return price * (1 - (cfg.commission_bps + cfg.slippage_bps) / 10_000)


def _max_drawdown(equity: List[float]) -> float:
    peak = equity[0] if equity else 0.0
    max_dd = 0.0
    for v in equity:
        if v > peak: peak = v
        dd = (v - peak) / peak if peak > 0 else 0.0
        if dd < max_dd: max_dd = dd
    return max_dd


def _sharpe(returns: List[float]) -> float:
    if len(returns) < 2: return 0.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    sd = var ** 0.5
    if sd == 0: return 0.0
    return (mean / sd) * (252 ** 0.5)


def _cagr(start: float, end: float, days: int) -> float:
    if start <= 0 or days <= 0: return 0.0
    years = days / 365.0
    if years <= 0: return 0.0
    return (end / start) ** (1 / years) - 1


def run_backtest(
    bars: List[dict],
    strategy_fn: Callable[[int, List[dict]], Optional[TradeSignal]],
    *,
    strategy_name: str = "strategy",
    symbol: str = "TEST",
    cfg: Optional[BacktestConfig] = None,
) -> BacktestReport:
    cfg = cfg or BacktestConfig()
    n = len(bars)
    equity = cfg.starting_equity
    equity_curve: List[dict] = []
    trades: List[FilledTrade] = []

    open_pos: Optional[dict] = None

    for i in range(n):
        bar = bars[i]
        # 1) Manage existing position first (intrabar SL/TP)
        if open_pos is not None:
            stop = open_pos["stop"]
            target = open_pos["target"]
            high = float(bar["high"]); low = float(bar["low"])
            exit_price = None; reason = None
            # Pessimistic ordering: SL checked before TP if both touched
            if low <= stop:
                exit_price = stop; reason = "sl"
            elif high >= target:
                exit_price = target; reason = "tp"
            elif (i - open_pos["entry_idx"]) >= cfg.max_hold_bars:
                exit_price = float(bar["close"]); reason = "eod"

            if exit_price is not None:
                exit_fill = _apply_friction_sell(exit_price, cfg)
                pnl = (exit_fill - open_pos["entry_fill"]) * open_pos["qty"]
                equity += pnl
                trades.append(FilledTrade(
                    entry_date=open_pos["entry_date"],
                    exit_date=str(bar["date"]),
                    entry=round(open_pos["entry_fill"], 4),
                    exit=round(exit_fill, 4),
                    stop=round(open_pos["stop"], 4),
                    target=round(open_pos["target"], 4),
                    qty=open_pos["qty"],
                    pnl_twd=round(pnl, 2),
                    pnl_pct=round((exit_fill / open_pos["entry_fill"] - 1.0), 6),
                    bars_held=i - open_pos["entry_idx"],
                    exit_reason=reason,
                    note=open_pos.get("note", ""),
                ))
                open_pos = None

        # 2) Generate signals on this bar; fill on NEXT bar's open
        if open_pos is None and i < n - 1:
            sig = strategy_fn(i, bars[: i + 1])
            if sig is not None and sig.bias == "LONG":
                next_bar = bars[i + 1]
                fill = _apply_friction_buy(float(next_bar["open"]), cfg)
                risk_per_share = fill - sig.stop_loss
                if risk_per_share > 0 and sig.take_profit > fill:
                    risk_amount = equity * cfg.risk_pct
                    qty = int(risk_amount // risk_per_share)
                    if qty >= 1:
                        open_pos = {
                            "entry_idx": i + 1,
                            "entry_date": str(next_bar["date"]),
                            "entry_fill": fill,
                            "stop": sig.stop_loss,
                            "target": sig.take_profit,
                            "qty": qty,
                            "note": sig.note,
                        }

        equity_curve.append({"date": str(bar["date"]), "equity": round(equity, 2)})

    # Force-close anything still open at end of data
    if open_pos is not None and bars:
        last = bars[-1]
        exit_fill = _apply_friction_sell(float(last["close"]), cfg)
        pnl = (exit_fill - open_pos["entry_fill"]) * open_pos["qty"]
        equity += pnl
        trades.append(FilledTrade(
            entry_date=open_pos["entry_date"],
            exit_date=str(last["date"]),
            entry=round(open_pos["entry_fill"], 4),
            exit=round(exit_fill, 4),
            stop=round(open_pos["stop"], 4),
            target=round(open_pos["target"], 4),
            qty=open_pos["qty"],
            pnl_twd=round(pnl, 2),
            pnl_pct=round((exit_fill / open_pos["entry_fill"] - 1.0), 6),
            bars_held=len(bars) - 1 - open_pos["entry_idx"],
            exit_reason="eod",
        ))
        if equity_curve:
            equity_curve[-1]["equity"] = round(equity, 2)

    # ───────── stats ─────────
    wins = sum(1 for t in trades if t.pnl_twd > 0)
    losses = sum(1 for t in trades if t.pnl_twd <= 0)
    gross_profit = sum(t.pnl_twd for t in trades if t.pnl_twd > 0)
    gross_loss = -sum(t.pnl_twd for t in trades if t.pnl_twd < 0)
    pf = (gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
    win_rate = (wins / len(trades)) if trades else 0.0

    eq_vals = [p["equity"] for p in equity_curve] or [cfg.starting_equity]
    daily_rets = []
    for i in range(1, len(eq_vals)):
        prev = eq_vals[i - 1] or 1
        daily_rets.append((eq_vals[i] - prev) / prev)
    sharpe = _sharpe(daily_rets)
    max_dd = _max_drawdown(eq_vals)
    total_ret = (eq_vals[-1] / eq_vals[0]) - 1 if eq_vals[0] > 0 else 0.0
    cagr = _cagr(eq_vals[0], eq_vals[-1], len(eq_vals))

    return BacktestReport(
        strategy=strategy_name,
        symbol=symbol,
        bars=n,
        trades_count=len(trades),
        wins=wins,
        losses=losses,
        win_rate=round(win_rate, 4),
        profit_factor=round(pf, 4) if pf != float("inf") else 9999.0,
        sharpe=round(sharpe, 4),
        max_drawdown=round(max_dd, 4),
        total_return=round(total_ret, 4),
        cagr=round(cagr, 4),
        final_equity=round(eq_vals[-1], 2),
        equity_curve=equity_curve,
        trades=[asdict(t) for t in trades],
    )
