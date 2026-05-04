"""Chip-flow analysis. Outputs a 0–100 score + structural metrics.

Backwards compatible: legacy `chip_score(records)` and `ChipCalculator` keep
working.

New surface (used by trade_plan_engine):
    ChipMetrics(records).compute() -> ChipBundle
        foreign_streak              連續外資買超天數
        investment_streak           連續投信買超天數
        foreign_invest_alignment    法人同步度 (0/0.5/1)
        concentration_now / delta   主力前 N 大集中度 + 變化
        avg_cost_estimate           近 N 日加權成交均價（法人推估成本）
        volume_ratio                近 5 日 / 近 20 日均量
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence


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
class ChipBundle:
    foreign_streak: int = 0
    investment_streak: int = 0
    dealer_streak: int = 0
    foreign_invest_alignment: float = 0.0  # 0 / 0.5 / 1.0
    concentration_now: Optional[float] = None
    concentration_delta: float = 0.0
    avg_cost_estimate: Optional[float] = None
    volume_ratio_5_20: float = 1.0
    foreign_5d_net: float = 0.0
    investment_5d_net: float = 0.0

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


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


@dataclass
class ChipMetrics:
    """Richer feature extractor used by the trade-plan engine.

    Each record may include any of the keys consumed below; missing keys
    fall back to zero / None safely.
    """
    records: List[dict]

    def compute(self) -> ChipBundle:
        if not self.records:
            return ChipBundle()

        fb = [float(r.get("foreign_buy", 0) or 0) for r in self.records]
        ib = [float(r.get("investment_buy", 0) or 0) for r in self.records]
        db = [float(r.get("dealer_buy", 0) or 0) for r in self.records]
        vols = [float(r.get("volume", 0) or 0) for r in self.records]
        closes = [float(r.get("close", 0) or 0) for r in self.records]
        concs = [r.get("concentration") for r in self.records]

        fs = _consecutive_positive(fb)
        invs = _consecutive_positive(ib)
        ds = _consecutive_positive(db)

        # alignment: today only (so it reflects the latest signal)
        align = 0.0
        if fb and ib:
            if fb[-1] > 0 and ib[-1] > 0:
                align = 1.0
            elif (fb[-1] > 0) != (ib[-1] > 0):
                align = 0.5

        conc_now = float(concs[-1]) if concs and concs[-1] is not None else None
        conc_first = next(
            (float(c) for c in concs if c is not None), None
        )
        delta = (conc_now - conc_first) if (conc_now is not None and conc_first is not None) else 0.0

        # Cost-basis estimate: last 20-day VWAP using close*volume
        cost_est: Optional[float] = None
        if len(closes) >= 5 and len(vols) >= 5:
            window = min(20, len(closes), len(vols))
            pv = sum(closes[-window:][i] * vols[-window:][i] for i in range(window))
            vv = sum(vols[-window:])
            if vv > 0:
                cost_est = pv / vv

        ratio = 1.0
        if len(vols) >= 20:
            recent = sum(vols[-5:]) / 5.0
            ma20 = sum(vols[-20:]) / 20.0
            if ma20 > 0:
                ratio = recent / ma20

        f5 = sum(fb[-5:]) if len(fb) >= 5 else sum(fb)
        i5 = sum(ib[-5:]) if len(ib) >= 5 else sum(ib)

        return ChipBundle(
            foreign_streak=fs,
            investment_streak=invs,
            dealer_streak=ds,
            foreign_invest_alignment=align,
            concentration_now=conc_now,
            concentration_delta=delta,
            avg_cost_estimate=cost_est,
            volume_ratio_5_20=ratio,
            foreign_5d_net=f5,
            investment_5d_net=i5,
        )
