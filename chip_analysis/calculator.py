"""Chip-flow analysis. Outputs a 0–100 score for a single stock.

Inputs
------
A list of daily records, newest last, each containing:
    {
        "foreign_buy":     float,   # 外資買賣超（張/千股）
        "investment_buy":  float,   # 投信買賣超
        "dealer_buy":      float,   # 自營商買賣超
        "volume":          int,     # 當日成交量
        "concentration":   float?,  # 券商集中度（可選，0~1）
    }

Scoring heuristic (0–100, clipped)
----------------------------------
+ 外資連續買超天數 (最多 +30)
+ 投信連續買超天數 (最多 +20)
+ 近 5 日成交量 / 近 20 日均量 放大倍數 (最多 +30)
+ 集中度上升 (最多 +20)

Every rule is independent — the sum is clipped to [0, 100].
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _consecutive_positive(values: Sequence[float]) -> int:
    count = 0
    for v in reversed(values):
        if v > 0:
            count += 1
        else:
            break
    return count


@dataclass
class ChipCalculator:
    records: List[dict]

    def foreign_streak(self) -> int:
        return _consecutive_positive([r.get("foreign_buy", 0) for r in self.records])

    def investment_streak(self) -> int:
        return _consecutive_positive([r.get("investment_buy", 0) for r in self.records])

    def volume_ratio(self) -> float:
        vols = [float(r.get("volume", 0) or 0) for r in self.records]
        if len(vols) < 20:
            return 1.0
        recent5 = sum(vols[-5:]) / 5
        ma20 = sum(vols[-20:]) / 20
        if ma20 <= 0:
            return 1.0
        return recent5 / ma20

    def concentration_delta(self) -> float:
        vals = [r.get("concentration") for r in self.records if r.get("concentration") is not None]
        if len(vals) < 2:
            return 0.0
        return float(vals[-1]) - float(vals[0])

    def score(self) -> float:
        fs = min(self.foreign_streak(), 5) * 6        # 0..30
        inv = min(self.investment_streak(), 5) * 4    # 0..20
        vr = self.volume_ratio()
        vol_pts = _clip((vr - 1.0) * 50, 0, 30)       # 1x→0, 1.6x→30
        conc = self.concentration_delta()
        conc_pts = _clip(conc * 200, 0, 20)           # +10% → +20
        return _clip(fs + inv + vol_pts + conc_pts)


def chip_score(records: Iterable[dict]) -> float:
    return ChipCalculator(list(records)).score()
