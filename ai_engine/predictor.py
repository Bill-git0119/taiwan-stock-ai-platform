"""Forward-return predictor — ensemble-style heuristic.

Real production version would train XGBoost / LightGBM / RandomForest on
labeled (close→close+5d return, vol, prob_up). Here we implement a
deterministic, math-based ensemble that consumes the same daily price
series so the API works out of the box with the limited data available
in dev. Replace `_train_ensemble` once you have a labeled training set.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Prediction:
    symbol: str
    prob_up_5d: float            # 0..1
    expected_return_10d: float   # decimal, e.g. 0.032 = +3.2%
    return_low_10d: float
    return_high_10d: float
    volatility_pred: float       # annualized stdev of daily returns
    win_rate: float              # 0..1, historical hit-ratio analogue
    confidence: float            # 0..1, ensemble agreement
    model: str = "ensemble-v1"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "prob_up_5d": round(self.prob_up_5d, 4),
            "expected_return_10d": round(self.expected_return_10d, 4),
            "return_low_10d": round(self.return_low_10d, 4),
            "return_high_10d": round(self.return_high_10d, 4),
            "volatility_pred": round(self.volatility_pred, 4),
            "win_rate": round(self.win_rate, 4),
            "confidence": round(self.confidence, 4),
            "model": self.model,
        }


# ───────── primitives ─────────

def _returns(closes: List[float]) -> List[float]:
    out = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        if prev <= 0:
            continue
        out.append((closes[i] - prev) / prev)
    return out


def _ema(series: List[float], span: int) -> float:
    if not series:
        return 0.0
    alpha = 2 / (span + 1)
    e = series[0]
    for v in series[1:]:
        e = alpha * v + (1 - alpha) * e
    return e


def _sigmoid(x: float) -> float:
    if x > 50: return 1.0
    if x < -50: return 0.0
    return 1.0 / (1.0 + math.exp(-x))


# ───────── three "models" — each returns prob_up_5d, exp_ret_10d, vol ─────────

def _model_momentum(closes: List[float]) -> tuple[float, float, float]:
    """Momentum / trend model — analogue of XGBoost on MA-derived features."""
    if len(closes) < 20:
        return 0.5, 0.0, 0.0
    ma5 = sum(closes[-5:]) / 5
    ma20 = sum(closes[-20:]) / 20
    last = closes[-1]
    rets = _returns(closes[-30:])
    drift = statistics.mean(rets) if rets else 0.0
    vol = statistics.pstdev(rets) if len(rets) > 1 else 0.01
    z = (last - ma20) / (vol * last + 1e-9)
    prob_up = _sigmoid(0.6 * z + 0.8 * (1 if ma5 > ma20 else -1))
    exp_ret = drift * 10  # 10-day forward
    return prob_up, exp_ret, vol * math.sqrt(252)


def _model_meanrev(closes: List[float]) -> tuple[float, float, float]:
    """Mean-reversion model — analogue of LightGBM on RSI/Bollinger features."""
    if len(closes) < 14:
        return 0.5, 0.0, 0.0
    rets = _returns(closes[-14:])
    gains = [r for r in rets if r > 0]
    losses = [-r for r in rets if r < 0]
    avg_g = sum(gains) / 14 if gains else 0.0
    avg_l = sum(losses) / 14 if losses else 1e-6
    rs = avg_g / avg_l if avg_l > 0 else 100
    rsi = 100 - 100 / (1 + rs)
    # oversold → bullish forward; overbought → bearish.
    prob_up = _sigmoid((50 - rsi) / 12)
    vol = statistics.pstdev(rets) if len(rets) > 1 else 0.01
    exp_ret = (50 - rsi) / 50 * 0.03  # ±3% range
    return prob_up, exp_ret, vol * math.sqrt(252)


def _model_volatility(closes: List[float]) -> tuple[float, float, float]:
    """Vol-regime model — analogue of RandomForest on realized vol features."""
    if len(closes) < 30:
        return 0.5, 0.0, 0.0
    rets = _returns(closes[-30:])
    vol_recent = statistics.pstdev(rets[-10:]) if len(rets) >= 10 else 0.01
    vol_long = statistics.pstdev(rets) if len(rets) > 1 else 0.01
    regime = vol_recent / (vol_long + 1e-9)
    # rising vol with positive drift = bullish breakout, negative drift = bearish breakdown
    drift = _ema(rets, 10)
    prob_up = _sigmoid(8 * drift * regime)
    exp_ret = drift * 10
    return prob_up, exp_ret, vol_long * math.sqrt(252)


# ───────── ensemble ─────────

_WEIGHTS = (0.45, 0.30, 0.25)  # momentum, meanrev, vol


def predict(symbol: str, closes: List[float]) -> Optional[Prediction]:
    if not closes or len(closes) < 30:
        return None

    p1, r1, v1 = _model_momentum(closes)
    p2, r2, v2 = _model_meanrev(closes)
    p3, r3, v3 = _model_volatility(closes)

    w_m, w_r, w_v = _WEIGHTS
    prob_up = p1 * w_m + p2 * w_r + p3 * w_v
    exp_ret = r1 * w_m + r2 * w_r + r3 * w_v
    vol = v1 * w_m + v2 * w_r + v3 * w_v

    # confidence = 1 - dispersion across models (clipped)
    probs = [p1, p2, p3]
    dispersion = max(probs) - min(probs)
    confidence = max(0.0, min(1.0, 1.0 - dispersion))

    # 90% interval = exp_ret ± 1.65 * vol_10d
    vol_10d = vol / math.sqrt(252) * math.sqrt(10)
    lo, hi = exp_ret - 1.65 * vol_10d, exp_ret + 1.65 * vol_10d

    # win-rate = historical share of positive 5d windows
    rets = _returns(closes)
    if len(rets) >= 5:
        wins = sum(1 for i in range(len(rets) - 5) if sum(rets[i:i + 5]) > 0)
        win_rate = wins / max(1, len(rets) - 5)
    else:
        win_rate = prob_up

    return Prediction(
        symbol=symbol,
        prob_up_5d=max(0.0, min(1.0, prob_up)),
        expected_return_10d=exp_ret,
        return_low_10d=lo,
        return_high_10d=hi,
        volatility_pred=vol,
        win_rate=win_rate,
        confidence=confidence,
    )
