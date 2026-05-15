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

Production gate (Phase 4 — hardened to local-mode iron rules):
    sample_size            < 100          → DISABLED
    OOS profit_factor      < 1.3          → DISABLED
    OOS Sharpe             < 1.0          → DISABLED
    Max DD (R units)       < -25          → DISABLED
    MC profitable          < 65%          → DISABLED
    Regime consistency     < 60%          → DISABLED
    live expectancy        < 0            → DISABLED
    max consec loss        > 8            → DISABLED

Plus a composite research_quality.evaluate() check that fuses
correlation health, edge decay, robustness validator score and
single-period-dominance into one production_research_score (0..1).
A setup must clear BOTH the heuristic gate AND the research_quality
gate; the final production_status is the MORE conservative verdict.

WATCH = one heuristic failure but sample >= min/2.
UNKNOWN = no live data AND no lab run.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.edge import edge_decay, strategy_metrics
from app.strategy_registry import research_quality


# Hardened gate — Phase 4 brings these in line with the local-mode iron rules.
# Anything that doesn't clear ALL of these is non-tradeable.
GATE = {
    "min_sample_size":      100,    # was 30
    "min_oos_pf":           1.3,    # was 1.2
    "min_oos_sharpe":       1.0,    # new
    "max_drawdown_r":      -25.0,   # new — minimum allowed maxDD in R units
    "min_mc_profitable":    0.65,   # was 0.55
    "min_regime_consist":   0.60,   # new — cross-regime consistency
    "max_consec_loss":      8,
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

        # ── Production gate (Phase 4 hardened) ─────────────────────
        failures: List[str] = []
        if sample == 0 and not s_lab:
            failures.append("no live data, no lab run")
        else:
            if sample > 0 and sample < GATE["min_sample_size"]:
                failures.append(f"sample_size={sample}<{GATE['min_sample_size']}")
            if live_pf > 0 and live_pf < GATE["min_oos_pf"]:
                failures.append(f"live_pf={live_pf:.2f}<{GATE['min_oos_pf']}")
            if s_lab and oos_pf < GATE["min_oos_pf"]:
                failures.append(f"oos_pf={oos_pf:.2f}<{GATE['min_oos_pf']}")
            if s_lab and oos_sharpe < GATE["min_oos_sharpe"]:
                failures.append(f"oos_sharpe={oos_sharpe:.2f}<{GATE['min_oos_sharpe']}")
            if s_lab and mc_profitable < GATE["min_mc_profitable"]:
                failures.append(f"mc_profitable={mc_profitable:.2f}<{GATE['min_mc_profitable']}")
            if sample > 0 and live_exp < 0:
                failures.append(f"live_expectancy={live_exp:.2f}<0")
            if consec > GATE["max_consec_loss"]:
                failures.append(f"max_consec_loss={consec}>{GATE['max_consec_loss']}")
            # MaxDD in R-units — only available from lab data, optional
            mdd_r = s_lab.get("max_drawdown_r")
            if mdd_r is not None and mdd_r < GATE["max_drawdown_r"]:
                failures.append(f"max_drawdown_r={mdd_r:.1f}<{GATE['max_drawdown_r']}")

        # ── Research quality (composite robustness) gate ───────────
        regime_consistency = s_lab.get("cross_regime_consistency",
                                       s_dec.get("cross_regime_consistency", 0.0))
        spd = s_lab.get("single_period_dominance", 0.0)
        corr_flagged = bool(s_lab.get("correlation_flagged", False))
        decay_label = s_dec.get("label")
        robustness_score = s_lab.get("robustness_score", 0.0)

        verdict = research_quality.evaluate(
            setup,
            sample_size=sample,
            cross_regime_consistency=regime_consistency,
            single_period_dominance=spd,
            correlation_flagged=corr_flagged,
            decay_label=decay_label,
            robustness_score=robustness_score,
        )

        # Cross-regime consistency hard gate (independent from research_quality)
        if s_lab and regime_consistency > 0 and regime_consistency < GATE["min_regime_consist"]:
            failures.append(
                f"regime_consistency={regime_consistency:.2f}<{GATE['min_regime_consist']}"
            )

        # ── Combine the two gates: be the MORE conservative ───────
        if not failures:
            heur_status = "ACTIVE"
        elif sample == 0 and not s_lab:
            heur_status = "UNKNOWN"
        elif len(failures) <= 1 and sample >= GATE["min_sample_size"] / 2:
            heur_status = "WATCH"
        else:
            heur_status = "DISABLED"

        research_status = verdict.research_status  # ACTIVE / RESEARCH_ONLY / DISABLED
        # Severity ranking — lowest wins (most conservative)
        rank_order = {"ACTIVE": 3, "WATCH": 2, "RESEARCH_ONLY": 1,
                      "DISABLED": 0, "UNKNOWN": 1}
        if rank_order.get(research_status, 1) < rank_order.get(heur_status, 0):
            status = research_status if research_status != "RESEARCH_ONLY" else "WATCH"
        else:
            status = heur_status

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
                "decay_label": decay_label,
                "sample_size": sample,
                "max_consec_loss": consec,
                "regime_consistency": regime_consistency,
                "research_quality_score": verdict.production_research_score,
                "research_status": verdict.research_status,
                "heur_status": heur_status,
            },
            failures=failures,
        ))

    out.sort(key=lambda r: r.rank_score, reverse=True)
    return out


def active_setups(rankings: List[StrategyRank]) -> set[str]:
    return {r.strategy for r in rankings if r.production_status == "ACTIVE"}


def disabled_setups(rankings: List[StrategyRank]) -> set[str]:
    return {r.strategy for r in rankings if r.production_status == "DISABLED"}
