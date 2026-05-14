"""Monte Carlo robustness test.

Given a list of *realised trade R-multiples*, resample N times with replacement
to estimate the distribution of the final-equity outcome. We report:

  * median   final equity
  * 5th-percentile final equity (worst-realistic case)
  * 95th-percentile final equity
  * pct_profitable iterations  — probability the strategy ends in green

A strategy passes the MC gate when the 5th-percentile final equity is still
above the starting equity. This catches strategies that *can* be profitable
but only in lucky path orderings.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List


@dataclass
class MonteCarloReport:
    n_iterations: int
    n_trades: int
    median_final_equity: float
    p05_final_equity: float
    p95_final_equity: float
    pct_profitable: float
    starting_equity: float

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


def run_monte_carlo(
    realised_rs: List[float],
    *,
    iterations: int = 1000,
    starting_equity: float = 1_000_000.0,
    risk_pct: float = 0.01,
    seed: int = 42,
) -> MonteCarloReport:
    if not realised_rs:
        return MonteCarloReport(
            n_iterations=0, n_trades=0,
            median_final_equity=starting_equity,
            p05_final_equity=starting_equity,
            p95_final_equity=starting_equity,
            pct_profitable=0.0,
            starting_equity=starting_equity,
        )
    rng = random.Random(seed)
    rs = list(realised_rs)
    finals: List[float] = []
    for _ in range(iterations):
        eq = starting_equity
        order = rng.choices(rs, k=len(rs))
        for r in order:
            risk_dollars = eq * risk_pct
            eq += risk_dollars * r
            if eq <= 0:
                eq = 0
                break
        finals.append(eq)
    finals.sort()
    n = len(finals)
    median = finals[n // 2]
    p05 = finals[max(0, int(n * 0.05) - 1)]
    p95 = finals[min(n - 1, int(n * 0.95))]
    profitable = sum(1 for f in finals if f > starting_equity) / n
    return MonteCarloReport(
        n_iterations=iterations,
        n_trades=len(rs),
        median_final_equity=round(median, 2),
        p05_final_equity=round(p05, 2),
        p95_final_equity=round(p95, 2),
        pct_profitable=round(profitable, 4),
        starting_equity=starting_equity,
    )
