"""Robustness validator — anti-overfitting checks beyond walk-forward + MC.

Four invariants. A strategy must pass ALL of them to be promoted from
WATCH → ACTIVE.

  1. cross_regime_consistency: PF > 1 in >= 60% of regime segments
  2. monte_carlo_stability:    p05/start_equity >= 1.0 AND profitable >= 60%
  3. low_parameter_sensitivity: placeholder (we have no tunables today)
  4. no_single_period_dominance: max single segment cannot exceed 60% of
     the strategy's lifetime cumulative return

Output is a single dict with per-check pass/fail + composite robustness_score.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import List

from app.strategy_lab.monte_carlo import MonteCarloReport
from strategy.stress.stress_runner import StressReport


GATES = {
    "min_cross_regime_consistency": 0.60,
    "max_single_period_dominance": 0.60,
    "min_mc_p05_ratio": 1.0,
    "min_mc_profitable": 0.60,
}


@dataclass
class RobustnessReport:
    strategy: str
    cross_regime_consistency: float
    single_period_dominance: float
    mc_p05_ratio: float
    mc_pct_profitable: float
    parameter_sensitivity: float
    robustness_score: float
    passed: bool
    failures: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_robustness(
    *,
    strategy: str,
    stress: StressReport,
    mc: MonteCarloReport,
    parameter_sensitivity: float = 1.0,
) -> RobustnessReport:
    failures: List[str] = []
    notes: List[str] = []

    crc = stress.cross_regime_consistency
    if crc < GATES["min_cross_regime_consistency"]:
        failures.append(f"cross_regime_consistency={crc:.2f} < {GATES['min_cross_regime_consistency']}")

    spd = stress.single_period_dominance
    if spd > GATES["max_single_period_dominance"]:
        failures.append(f"single_period_dominance={spd:.2f} > {GATES['max_single_period_dominance']}")

    mc_ratio = (mc.p05_final_equity / mc.starting_equity) if mc.starting_equity else 0.0
    if mc.n_trades > 0:
        if mc_ratio < GATES["min_mc_p05_ratio"]:
            failures.append(f"mc_p05_ratio={mc_ratio:.2f} < {GATES['min_mc_p05_ratio']}")
        if mc.pct_profitable < GATES["min_mc_profitable"]:
            failures.append(f"mc_profitable={mc.pct_profitable:.2f} < {GATES['min_mc_profitable']}")
    else:
        notes.append("mc skipped: no trades")

    # Composite — 0..1
    score = (
        0.35 * min(1.0, crc / 0.8) +
        0.20 * (1.0 - min(1.0, spd / 0.8)) +
        0.20 * min(1.0, mc_ratio / 1.3) +
        0.15 * min(1.0, mc.pct_profitable / 0.9 if mc.n_trades else 0.5) +
        0.10 * max(0.0, min(1.0, parameter_sensitivity))
    )

    return RobustnessReport(
        strategy=strategy,
        cross_regime_consistency=round(crc, 4),
        single_period_dominance=round(spd, 4),
        mc_p05_ratio=round(mc_ratio, 4),
        mc_pct_profitable=round(mc.pct_profitable, 4),
        parameter_sensitivity=round(parameter_sensitivity, 4),
        robustness_score=round(score, 4),
        passed=not failures,
        failures=failures,
        notes=notes,
    )
