"""StrategyRanker — composite ranking of every registered strategy.

Inputs (all real, all already in-process or in DB):
  * lab metrics (cached from latest run_lab call)
  * edge_signals real performance (last 90d)
  * edge decay (recent vs older)

Composite score:
    rank = 0.30 * normalize(oos_sharpe)
         + 0.25 * normalize(profit_factor - 1)
         + 0.20 * sigmoid(live_expectancy_R)
         + 0.15 * (1 - max(0, -decay))      # decay penalises
         + 0.10 * normalize(mc_p05_ratio)

Production gate (any failure → DISABLED):
    sample_size       < 30
    OOS profit_factor < 1.2
    MC profitable     < 55%
    live expectancy   < 0
    max consec loss   > 8

Below DISABLED but above ACTIVE → WATCH.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.edge import edge_decay, strategy_metrics


GATE = {
    "min_sample_size": 30,
    "min_oos_pf": 1.2,
    "min_mc_profitable": 0.55,
    "max_consec_loss": 8,
}


def _norm(value: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def _sigmoid(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-3.0 * x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


@dataclass
class StrategyRank:
    strategy: str
    rank_score: float
    production_status: str   # ACTIVE / WATCH / DISABLED / UNKNOWN
    components: dict = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)


async def rank_all(session: AsyncSession,
                   lab_metrics: Dict[str, dict] | None = None) -> List[StrategyRank]:
    """Return ranked list, best first.

    `lab_metrics`: optional dict {strategy: {oos_sharpe, oos_pf, mc_p05_ratio,
    mc_pct_profitable}}. When absent, lab signals contribute zero (gate
    falls back to live data only).
    """
    lab_metrics = lab_metrics or {}
    by_setup = await strategy_metrics.by_setup(session, window_days=90)
    decay = await edge_decay.decay_scores(session)

    out: List[StrategyRank] = []
    setups = set(by_setup.keys()) | set(lab_metrics.keys()) | set(decay.keys())

    for setup in setups:
        s_live = by_setup.get(setup, {})
        s_lab = lab_metrics.get(setup, {})
        s_dec = decay.get(setup, {})

        sample = s_live.get("sample_size", 0)
        live_exp = s_live.get("expectancy_R", 0.0)
        live_pf = s_live.get("profit_factor", 0.0)
        consec = s_live.get("max_consec_loss", 0)
        oos_sharpe = s_lab.get("oos_sharpe", 0.0)
        oos_pf = s_lab.get("oos_profit_factor", live_pf)
        mc_p05_ratio = s_lab.get("mc_p05_ratio", 1.0)
        mc_profitable = s_lab.get("mc_pct_profitable", 1.0)
        decay_val = s_dec.get("decay", 0.0)

        rank = (
            0.30 * _norm(oos_sharpe, 0.0, 1.5) +
            0.25 * _norm(oos_pf - 1.0, 0.0, 1.0) +
            0.20 * _sigmoid(live_exp) +
            0.15 * (1.0 - max(0.0, -decay_val)) +
            0.10 * _norm(mc_p05_ratio, 0.9, 1.5)
        )

        # Production gate
        failures: List[str] = []
        # If we don't have enough samples, status is UNKNOWN unless lab metrics
        # are present. Without samples AND no lab → cannot promote.
        if sample == 0 and not s_lab:
            failures.append("no live data, no lab run")
        else:
            if sample > 0 and sample < GATE["min_sample_size"]:
                failures.append(f"sample_size={sample}<{GATE['min_sample_size']}")
            if live_pf > 0 and live_pf < GATE["min_oos_pf"]:
                failures.append(f"live_pf={live_pf:.2f}<{GATE['min_oos_pf']}")
            if s_lab and oos_pf < GATE["min_oos_pf"]:
                failures.append(f"oos_pf={oos_pf:.2f}<{GATE['min_oos_pf']}")
            if s_lab and mc_profitable < GATE["min_mc_profitable"]:
                failures.append(f"mc_profitable={mc_profitable:.2f}<{GATE['min_mc_profitable']}")
            if sample > 0 and live_exp < 0:
                failures.append(f"live_expectancy={live_exp:.2f}<0")
            if consec > GATE["max_consec_loss"]:
                failures.append(f"max_consec_loss={consec}>{GATE['max_consec_loss']}")

        if not failures:
            status = "ACTIVE"
        elif sample == 0 and not s_lab:
            status = "UNKNOWN"
        elif len(failures) <= 1 and sample >= GATE["min_sample_size"] / 2:
            status = "WATCH"
        else:
            status = "DISABLED"

        out.append(StrategyRank(
            strategy=setup,
            rank_score=round(rank, 4),
            production_status=status,
            components={
                "oos_sharpe": oos_sharpe,
                "oos_pf": oos_pf,
                "live_expectancy_R": live_exp,
                "live_pf": live_pf,
                "mc_p05_ratio": mc_p05_ratio,
                "mc_profitable": mc_profitable,
                "decay": decay_val,
                "sample_size": sample,
                "max_consec_loss": consec,
            },
            failures=failures,
        ))

    out.sort(key=lambda r: r.rank_score, reverse=True)
    return out


def active_setups(rankings: List[StrategyRank]) -> set[str]:
    return {r.strategy for r in rankings if r.production_status == "ACTIVE"}


def disabled_setups(rankings: List[StrategyRank]) -> set[str]:
    return {r.strategy for r in rankings if r.production_status == "DISABLED"}
