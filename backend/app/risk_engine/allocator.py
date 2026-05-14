"""Risk allocator — convert ranker + regime + vol into actionable allocations.

Inputs:
  strategies     : list of {name, rank_score, production_status, live_expectancy_R}
  regime_label   : trending_up | sideways | bearish | ...
  base_risk_pct  : default 0.01 (1% per signal)
  max_concurrent : default 3 open positions

Outputs:
  weight[strategy]                 — sum to 1.0 across ACTIVE
  max_exposure_pct[strategy]       — fraction of equity that strategy may hold
  per_signal_risk_pct[strategy]    — base_risk_pct × regime_modifier
  notes                            — human-readable rationale strings

Rules:
  * DISABLED → weight 0, exposure 0
  * WATCH    → weight halved, exposure cap halved
  * Regime modifier:
        trending_up        : 1.00
        trending_up_weak   : 0.75
        sideways           : 0.40   # tighten everything
        bearish            : 0.30   # mostly cash
        unknown            : 0.50
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List


REGIME_MODIFIER: Dict[str, float] = {
    "trending_up": 1.0,
    "trending_up_weak": 0.75,
    "sideways": 0.40,
    "trending_down_weak": 0.30,
    "trending_down": 0.20,
    "bearish": 0.30,
    "unknown": 0.50,
}


@dataclass
class Allocation:
    strategy: str
    weight: float
    max_exposure_pct: float
    per_signal_risk_pct: float
    production_status: str

    def to_dict(self) -> dict:
        return asdict(self)


def allocate(
    strategies: List[dict],
    *,
    regime_label: str = "unknown",
    base_risk_pct: float = 0.01,
    max_concurrent: int = 3,
    max_portfolio_exposure: float = 0.30,   # 30% of equity max at any time
) -> dict:
    mod = REGIME_MODIFIER.get(regime_label, 0.5)
    # Compute raw weights from rank_score among ACTIVE/WATCH
    raw: List[Allocation] = []
    notes: List[str] = []
    for s in strategies:
        status = s.get("production_status", "UNKNOWN")
        rank = float(s.get("rank_score", 0.0))
        if status == "DISABLED":
            raw.append(Allocation(strategy=s["strategy"], weight=0.0,
                                  max_exposure_pct=0.0,
                                  per_signal_risk_pct=0.0,
                                  production_status=status))
            continue
        live_exp = float(s.get("live_expectancy_R", 0.0))
        # only credit positive-expectancy strategies
        score = max(0.0, rank) * (1.0 if live_exp >= 0 else 0.5)
        if status == "WATCH":
            score *= 0.5
            notes.append(f"{s['strategy']}: WATCH — weight halved")
        raw.append(Allocation(strategy=s["strategy"], weight=score,
                              max_exposure_pct=0.0,
                              per_signal_risk_pct=0.0,
                              production_status=status))

    total = sum(a.weight for a in raw)
    out: List[Allocation] = []
    for a in raw:
        if total > 0 and a.weight > 0:
            a.weight = round(a.weight / total, 4)
        else:
            a.weight = 0.0
        exposure_cap = max_portfolio_exposure * mod
        if a.production_status == "WATCH":
            exposure_cap *= 0.5
        a.max_exposure_pct = round(min(1.0 / max(1, max_concurrent), exposure_cap), 4)
        a.per_signal_risk_pct = round(base_risk_pct * mod, 4)
        out.append(a)

    return {
        "regime": regime_label,
        "regime_modifier": mod,
        "max_concurrent": max_concurrent,
        "max_portfolio_exposure": max_portfolio_exposure,
        "base_risk_pct": base_risk_pct,
        "allocations": [a.to_dict() for a in out],
        "notes": notes,
    }
