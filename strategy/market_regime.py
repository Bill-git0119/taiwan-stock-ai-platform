"""Market regime classifier — trending / sideways / bearish.

A *regime* tells us **which strategies are allowed to fire today**.
This is the single most important upgrade to make the scanner edge-aware.

Inputs (lookahead-free): closes, highs, lows
Outputs: Regime dataclass with classification + numerical components.

Classification rules (any may abstain → "unknown" if data thin):
  trending_up    : EMA200 slope > +0.05% / bar OVER last 30 bars
                   AND ADX(14) >= 20
                   AND last close > EMA50 > EMA200
  trending_down  : EMA200 slope < -0.05% / bar
                   AND ADX(14) >= 20
                   AND last close < EMA50 < EMA200
  sideways       : ADX(14) < 18  OR  ATR contraction (recent ATR < 0.7 * 60-bar mean ATR)
  bearish        : last close < EMA200 AND ema50 slope < 0
  trending_up_weak / trending_down_weak when ADX 18-22 (transitional)

Setup whitelist applied by scanner:
  trending_up      → trend_breakout_retest, ma20_support_bounce, chip_follow_long
  trending_up_weak → ma20_support_bounce, chip_follow_long
  sideways         → (none — refuse breakouts)
  bearish          → (none for LONG)
  trending_down    → SHORT setups (future)

These rules are intentionally simple and explainable to the trader.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import List, Optional, Sequence


# ─────────────────────────── primitives ────────────────────────────

def _ema_series(vals: Sequence[float], n: int) -> List[float]:
    if not vals:
        return []
    k = 2.0 / (n + 1)
    out = [float(vals[0])]
    for v in vals[1:]:
        out.append(out[-1] * (1 - k) + float(v) * k)
    return out


def _wilder_smooth(vals: List[float], n: int) -> List[float]:
    """Wilder's running-sum smoothing for TR / DM.

    smoothed[i] = smoothed[i-1] - smoothed[i-1]/n + raw[i]

    Used as the denominator for DI/ADX where the missing 1/n factor cancels
    in the ratio. Do NOT use this directly to smooth DX → ADX; use
    `_wilder_average` for that (which is a proper RMA dividing by n).
    """
    if len(vals) < n:
        return []
    first = sum(vals[:n])  # initial seed is sum (not avg) for Wilder RMS
    out = [first]
    for v in vals[n:]:
        out.append(out[-1] - out[-1] / n + v)
    return out


def _wilder_average(vals: List[float], n: int) -> List[float]:
    """Wilder's running average (RMA) — averaging variant for ADX smoothing.

    smoothed[i] = ((n-1) * smoothed[i-1] + raw[i]) / n

    The classic ADX line uses this — output stays in DX's 0..100 range.
    """
    if len(vals) < n:
        return []
    first = sum(vals[:n]) / n
    out = [first]
    for v in vals[n:]:
        out.append(((n - 1) * out[-1] + v) / n)
    return out


def _adx_series(highs: Sequence[float], lows: Sequence[float],
                closes: Sequence[float], n: int = 14) -> List[float]:
    """ADX(n). Returns the smoothed ADX series (length ~ len(closes) - 2n)."""
    L = len(closes)
    if L < n * 2 + 1:
        return []
    tr, plus_dm, minus_dm = [], [], []
    for i in range(1, L):
        high, low, prev_close = highs[i], lows[i], closes[i - 1]
        a = high - low
        b = abs(high - prev_close)
        c = abs(low - prev_close)
        tr.append(max(a, b, c))
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dm.append(up_move if (up_move > down_move and up_move > 0) else 0.0)
        minus_dm.append(down_move if (down_move > up_move and down_move > 0) else 0.0)

    atr = _wilder_smooth(tr, n)
    pdm = _wilder_smooth(plus_dm, n)
    mdm = _wilder_smooth(minus_dm, n)
    if not atr or not pdm or not mdm:
        return []
    plus_di = [100 * p / a if a else 0.0 for p, a in zip(pdm, atr)]
    minus_di = [100 * m / a if a else 0.0 for m, a in zip(mdm, atr)]
    dx = [
        100 * abs(p - m) / (p + m) if (p + m) > 0 else 0.0
        for p, m in zip(plus_di, minus_di)
    ]
    if len(dx) < n:
        return []
    # ADX uses the *averaging* smoother (RMA) so output stays in 0..100.
    return _wilder_average(dx, n)


def _atr_series(highs: Sequence[float], lows: Sequence[float],
                closes: Sequence[float], n: int = 14) -> List[float]:
    L = len(closes)
    if L < n + 1:
        return []
    tr = []
    for i in range(1, L):
        a = highs[i] - lows[i]
        b = abs(highs[i] - closes[i - 1])
        c = abs(lows[i] - closes[i - 1])
        tr.append(max(a, b, c))
    return _wilder_smooth(tr, n)


def _slope_pct_per_bar(series: List[float], window: int) -> Optional[float]:
    """Avg per-bar percentage change of series across the last `window` bars."""
    if len(series) < window + 1:
        return None
    head = series[-window - 1]
    tail = series[-1]
    if head == 0:
        return None
    total_pct = (tail / head - 1.0) * 100.0
    return total_pct / window


# ─────────────────────────── output ────────────────────────────────

@dataclass
class Regime:
    label: str                              # see _classify
    adx: Optional[float] = None
    ema200_slope_pct: Optional[float] = None
    ema50_slope_pct: Optional[float] = None
    atr_contraction: Optional[float] = None  # recent_atr / mean_atr (60 bars)
    last: Optional[float] = None
    ema50: Optional[float] = None
    ema200: Optional[float] = None
    allowed_setups: List[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# Setup permission table — single source of truth used by scanner & engine.
ALLOWED_SETUPS: dict[str, List[str]] = {
    "trending_up":      ["trend_breakout_retest", "ma20_support_bounce", "chip_follow_long"],
    "trending_up_weak": ["ma20_support_bounce", "chip_follow_long"],
    "sideways":         [],
    "bearish":          [],
    "trending_down":    [],
    "trending_down_weak": [],
    "unknown":          ["ma20_support_bounce"],  # safest default
}


def _classify(closes, highs, lows) -> Regime:
    n = len(closes)
    if n < 60:
        r = Regime(label="unknown", reason="insufficient_history")
        r.allowed_setups = ALLOWED_SETUPS["unknown"]
        return r

    ema50 = _ema_series(closes, 50)
    ema200 = _ema_series(closes, min(200, max(50, n // 2)))
    last = float(closes[-1])
    e50 = ema50[-1] if ema50 else None
    e200 = ema200[-1] if ema200 else None

    slope200 = _slope_pct_per_bar(ema200, 30) if len(ema200) > 30 else None
    slope50 = _slope_pct_per_bar(ema50, 20) if len(ema50) > 20 else None

    adx_series = _adx_series(highs, lows, closes, 14)
    adx = adx_series[-1] if adx_series else None

    atr_series = _atr_series(highs, lows, closes, 14)
    atr_contraction: Optional[float] = None
    if len(atr_series) >= 60:
        recent = sum(atr_series[-10:]) / 10
        mean = sum(atr_series[-60:]) / 60
        if mean > 0:
            atr_contraction = recent / mean

    r = Regime(
        label="unknown",
        adx=round(adx, 2) if adx is not None else None,
        ema200_slope_pct=round(slope200, 4) if slope200 is not None else None,
        ema50_slope_pct=round(slope50, 4) if slope50 is not None else None,
        atr_contraction=round(atr_contraction, 3) if atr_contraction is not None else None,
        last=round(last, 4),
        ema50=round(e50, 4) if e50 else None,
        ema200=round(e200, 4) if e200 else None,
    )

    # Hard bearish gate first — require true down-stack (ema50 < ema200)
    # plus negative ema50 slope. A flat market that happens to dip below ema200
    # for a single bar should NOT trigger this.
    if (e200 is not None and e50 is not None and last < e200 and e50 < e200
            and slope50 is not None and slope50 < -0.05):
        r.label = "bearish"
        r.reason = "price<EMA200, EMA50<EMA200, slope down"
        r.allowed_setups = ALLOWED_SETUPS["bearish"]
        return r

    # Sideways: low ADX or ATR contraction
    if (adx is not None and adx < 18) or (atr_contraction is not None and atr_contraction < 0.7):
        r.label = "sideways"
        r.reason = f"adx={adx:.1f}" if adx is not None else "atr contraction"
        r.allowed_setups = ALLOWED_SETUPS["sideways"]
        return r

    # Trend gates
    is_up_stack = (e50 is not None and e200 is not None
                   and last > e50 > e200
                   and slope200 is not None and slope200 > 0.05)
    is_dn_stack = (e50 is not None and e200 is not None
                   and last < e50 < e200
                   and slope200 is not None and slope200 < -0.05)

    if is_up_stack:
        if adx is not None and adx >= 22:
            r.label = "trending_up"
            r.reason = f"stacked up + adx {adx:.1f}"
        else:
            r.label = "trending_up_weak"
            r.reason = f"stacked up but adx {adx:.1f} weak"
    elif is_dn_stack:
        if adx is not None and adx >= 22:
            r.label = "trending_down"
        else:
            r.label = "trending_down_weak"
        r.reason = "stacked down"
    else:
        r.label = "sideways"
        r.reason = "no clean stack"

    r.allowed_setups = ALLOWED_SETUPS.get(r.label, [])
    return r


def detect_regime(
    closes: Sequence[float],
    highs: Optional[Sequence[float]] = None,
    lows: Optional[Sequence[float]] = None,
) -> Regime:
    """Public entry point. Falls back to closes when highs/lows unavailable."""
    closes = list(closes)
    highs = list(highs) if highs else list(closes)
    lows = list(lows) if lows else list(closes)
    return _classify(closes, highs, lows)


def setup_allowed(setup: str, regime_label: str) -> bool:
    return setup in ALLOWED_SETUPS.get(regime_label, [])
