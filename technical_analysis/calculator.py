"""Technical analysis — score + structural indicators for trade planning.

Backwards-compatible: legacy `technical_score(closes)` and the
TechnicalCalculator boolean rules still return identical outputs.

New surface (used by trade_plan_engine):
    Indicators(closes, highs, lows, volumes).compute() -> IndicatorBundle
        ema20 / ema50 / ema200
        rsi14
        atr14
        donchian20 (high, low)
        vwap
        volume_spike_ratio  (today / 20-day average)
        breakout_20
        ma_alignment
        rsi_zone

All routines are pure, vectorised, and lookahead-free: indicators at index `i`
only use bars 0..i.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence


# ─────────────────────────── primitives ────────────────────────────

def _ma(vals: Sequence[float], n: int) -> Optional[float]:
    if len(vals) < n:
        return None
    return sum(vals[-n:]) / n


def _ema(vals: Sequence[float], n: int) -> List[float]:
    if not vals:
        return []
    k = 2 / (n + 1)
    out = [vals[0]]
    for v in vals[1:]:
        out.append(out[-1] * (1 - k) + v * k)
    return out


def _rsi(closes: Sequence[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains, losses = 0.0, 0.0
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100 - (100 / (1 + rs))


def _macd(closes: Sequence[float]) -> Optional[tuple[float, float]]:
    if len(closes) < 35:
        return None
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line = [a - b for a, b in zip(ema12[-len(ema26):], ema26)]
    signal = _ema(macd_line, 9)
    return macd_line[-1], signal[-1]


def _atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float],
         period: int = 14) -> Optional[float]:
    """Wilder's ATR. Needs ≥ period+1 bars."""
    n = len(closes)
    if n < period + 1 or len(highs) != n or len(lows) != n:
        return None
    trs = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    # Wilder smoothing seeded with simple mean of first `period` TRs
    if len(trs) < period:
        return None
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def _vwap(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float],
          volumes: Sequence[float], window: int = 20) -> Optional[float]:
    n = min(len(closes), len(volumes), len(highs), len(lows))
    if n < window:
        return None
    h = highs[-window:]; l = lows[-window:]; c = closes[-window:]; v = volumes[-window:]
    pv = 0.0; vv = 0.0
    for i in range(window):
        typ = (h[i] + l[i] + c[i]) / 3.0
        vol = max(0.0, float(v[i]))
        pv += typ * vol
        vv += vol
    if vv <= 0:
        return None
    return pv / vv


def _donchian(highs: Sequence[float], lows: Sequence[float], window: int = 20
              ) -> Optional[tuple[float, float]]:
    if len(highs) < window or len(lows) < window:
        return None
    return max(highs[-window:]), min(lows[-window:])


# ─────────────────────────── new indicator bundle ────────────────────────────

@dataclass
class IndicatorBundle:
    last: float
    ema20: Optional[float] = None
    ema50: Optional[float] = None
    ema200: Optional[float] = None
    rsi14: Optional[float] = None
    atr14: Optional[float] = None
    donchian_high: Optional[float] = None
    donchian_low: Optional[float] = None
    vwap20: Optional[float] = None
    volume_spike: float = 1.0          # today / 20-day mean
    breakout_20: bool = False           # close > prior 20-bar high
    ma_alignment: bool = False          # ema20 > ema50 > ema200
    macd_bull: bool = False             # MACD > signal && > 0
    rsi_zone: str = "neutral"           # bear / weak / neutral / healthy / overbought
    prior_swing_low_5: Optional[float] = None
    prior_swing_high_5: Optional[float] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class Indicators:
    closes: List[float]
    highs: List[float] = field(default_factory=list)
    lows: List[float] = field(default_factory=list)
    volumes: List[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Auto-fallback when only closes are provided.
        n = len(self.closes)
        if not self.highs:
            self.highs = list(self.closes)
        if not self.lows:
            self.lows = list(self.closes)
        if not self.volumes:
            self.volumes = [0.0] * n

    def compute(self) -> IndicatorBundle:
        c = self.closes
        n = len(c)
        if n == 0:
            return IndicatorBundle(last=0.0)

        last = c[-1]
        ema20s = _ema(c, 20) if n >= 20 else []
        ema50s = _ema(c, 50) if n >= 50 else []
        ema200s = _ema(c, 200) if n >= 200 else []

        ema20 = ema20s[-1] if ema20s else None
        ema50 = ema50s[-1] if ema50s else None
        ema200 = ema200s[-1] if ema200s else None

        rsi = _rsi(c)
        atr = _atr(self.highs, self.lows, c)
        don = _donchian(self.highs, self.lows, 20)
        vwap = _vwap(self.highs, self.lows, c, self.volumes, 20)

        # volume spike vs trailing 20-day mean (today / mean of prior 20, no lookahead)
        vol_spike = 1.0
        if len(self.volumes) >= 21:
            recent = float(self.volumes[-1])
            mean20 = sum(self.volumes[-21:-1]) / 20.0
            vol_spike = recent / mean20 if mean20 > 0 else 1.0

        breakout_20 = False
        if n >= 21:
            prior_high = max(c[-21:-1])
            breakout_20 = last > prior_high

        ma_align = (
            ema20 is not None and ema50 is not None and ema200 is not None
            and ema20 > ema50 > ema200
        )

        macd_bull = False
        m = _macd(c)
        if m is not None:
            macd_bull = m[0] > m[1] and m[0] > 0

        zone = "neutral"
        if rsi is not None:
            if rsi < 30: zone = "bear"
            elif rsi < 45: zone = "weak"
            elif rsi <= 70: zone = "healthy"
            elif rsi > 70: zone = "overbought"
            else: zone = "neutral"

        # Recent swing levels for stop placement / TP structure
        sw_low5 = min(self.lows[-5:]) if len(self.lows) >= 5 else None
        sw_high5 = max(self.highs[-5:]) if len(self.highs) >= 5 else None

        return IndicatorBundle(
            last=last,
            ema20=ema20, ema50=ema50, ema200=ema200,
            rsi14=rsi, atr14=atr,
            donchian_high=don[0] if don else None,
            donchian_low=don[1] if don else None,
            vwap20=vwap,
            volume_spike=vol_spike,
            breakout_20=breakout_20,
            ma_alignment=ma_align,
            macd_bull=macd_bull,
            rsi_zone=zone,
            prior_swing_low_5=sw_low5,
            prior_swing_high_5=sw_high5,
        )


# ─────────────────────── legacy 0-100 score (backcompat) ────────────────────────

@dataclass
class TechnicalCalculator:
    closes: List[float]

    def ma_bullish(self) -> bool:
        ma20 = _ma(self.closes, 20)
        ma60 = _ma(self.closes, 60)
        return ma20 is not None and ma60 is not None and ma20 > ma60

    def macd_golden(self) -> bool:
        m = _macd(self.closes)
        if m is None:
            return False
        macd_line, signal = m
        return macd_line > signal and macd_line > 0

    def rsi_healthy(self) -> bool:
        r = _rsi(self.closes)
        return r is not None and 50 <= r <= 70

    def breakout(self) -> bool:
        if len(self.closes) < 21:
            return False
        last = self.closes[-1]
        prior20_high = max(self.closes[-21:-1])
        return last > prior20_high

    def score(self) -> float:
        pts = 0.0
        if self.ma_bullish():
            pts += 25
        if self.macd_golden():
            pts += 25
        if self.rsi_healthy():
            pts += 25
        if self.breakout():
            pts += 25
        return max(0.0, min(100.0, pts))


def technical_score(closes: Sequence[float]) -> float:
    return TechnicalCalculator(list(closes)).score()
