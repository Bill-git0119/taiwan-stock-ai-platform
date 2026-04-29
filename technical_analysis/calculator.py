"""Technical analysis — 0~100 score.

Input: daily closing prices (list of floats, newest last), length ≥ 60 ideal.

Rules
-----
+ MA20 > MA60 多頭排列:                +25
+ MACD 黃金交叉 (MACD 線 > Signal 且上揚): +25
+ RSI in [50, 70]:                      +25
+ 收盤突破 20 日高點 (平台突破):         +25
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence


def _ma(vals: Sequence[float], n: int) -> float | None:
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


def _rsi(closes: Sequence[float], period: int = 14) -> float | None:
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


def _macd(closes: Sequence[float]) -> tuple[float, float] | None:
    if len(closes) < 35:
        return None
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line = [a - b for a, b in zip(ema12[-len(ema26):], ema26)]
    signal = _ema(macd_line, 9)
    return macd_line[-1], signal[-1]


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
