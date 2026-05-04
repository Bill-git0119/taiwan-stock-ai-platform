"""Three reference strategies for backtest_engine_v2.

All strategies are LONG-only, no lookahead, ATR-based stops, R:R ≥ 1.5.
Each is a pure function (bar_index, history) -> Optional[TradeSignal] —
so they can be tested with synthetic data and parallel-run cross-symbol.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from technical_analysis.calculator import Indicators  # noqa: E402

from .backtest_engine_v2 import TradeSignal


def _ind(history: List[dict]):
    return Indicators(
        closes=[float(b["close"]) for b in history],
        highs=[float(b["high"]) for b in history],
        lows=[float(b["low"]) for b in history],
        volumes=[float(b.get("volume", 0)) for b in history],
    ).compute()


# ─────────────────────── 1. trend breakout ──────────────────────────

def trend_breakout(bar_index: int, history: List[dict]) -> Optional[TradeSignal]:
    if len(history) < 60: return None
    ind = _ind(history)
    if ind.atr14 is None or ind.atr14 <= 0: return None
    if not ind.breakout_20: return None
    if not ind.ma_alignment: return None
    if ind.volume_spike < 1.3: return None

    last = ind.last
    atr = ind.atr14
    sl = last - 1.5 * atr
    if sl <= 0 or sl >= last: return None
    risk = last - sl
    tp = last + 1.5 * risk     # RR = 1.5 (engine fills next-bar so realized RR ≈ 1.4)
    # Bump to 1.8 to keep RR > 1.5 after slippage at fill.
    tp = last + 1.8 * risk

    return TradeSignal(bias="LONG", entry_hint=last,
                       stop_loss=round(sl, 4), take_profit=round(tp, 4),
                       note="trend_breakout")


# ─────────────────────── 2. mean reversion ──────────────────────────

def mean_reversion(bar_index: int, history: List[dict]) -> Optional[TradeSignal]:
    """Bounce off oversold while still in uptrend (ema50 > ema200)."""
    if len(history) < 60: return None
    ind = _ind(history)
    if ind.atr14 is None or ind.atr14 <= 0: return None
    if ind.ema50 is None or ind.ema200 is None: return None
    if ind.ema50 <= ind.ema200: return None       # only buy dips in uptrend
    if ind.rsi14 is None or ind.rsi14 > 40: return None
    if ind.last >= ind.ema20 * 1.05 if ind.ema20 else True: return None

    last = ind.last
    atr = ind.atr14
    sl = last - 1.8 * atr
    if sl <= 0 or sl >= last: return None
    risk = last - sl
    # mean reversion targets the ema20 or last ATR top — pick further of (1.7R, ema20)
    tp_struct = ind.ema20 if ind.ema20 else (last + 2 * atr)
    tp = max(last + 1.7 * risk, tp_struct)
    if tp <= last: return None

    return TradeSignal(bias="LONG", entry_hint=last,
                       stop_loss=round(sl, 4), take_profit=round(tp, 4),
                       note="mean_reversion")


# ─────────────────────── 3. chip follow ─────────────────────────────

def chip_follow(bar_index: int, history: List[dict]) -> Optional[TradeSignal]:
    """Volume confirmation + EMA stack. Stand-in for foreign-buy follow when
    only OHLCV is available; volume_spike ≥ 1.6 + above ema20 + ema50>ema200.
    Real chip data plugs in via build_plan; here we use volume as proxy.
    """
    if len(history) < 60: return None
    ind = _ind(history)
    if ind.atr14 is None or ind.atr14 <= 0: return None
    if ind.ema20 is None or ind.ema50 is None or ind.ema200 is None: return None
    if not (ind.ema50 > ind.ema200): return None
    if ind.last <= ind.ema20: return None
    if ind.volume_spike < 1.6: return None

    last = ind.last
    atr = ind.atr14
    sl = last - 1.6 * atr
    if sl <= 0 or sl >= last: return None
    risk = last - sl
    tp = last + 1.7 * risk    # RR ≥ 1.5 after friction

    return TradeSignal(bias="LONG", entry_hint=last,
                       stop_loss=round(sl, 4), take_profit=round(tp, 4),
                       note="chip_follow")


REGISTRY = {
    "trend_breakout": trend_breakout,
    "mean_reversion": mean_reversion,
    "chip_follow": chip_follow,
}
