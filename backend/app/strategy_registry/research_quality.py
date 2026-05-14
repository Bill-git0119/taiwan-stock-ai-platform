"""Research quality gates — final guard before a strategy becomes ACTIVE.

production_research_score is a 0..1 composite of:
  * sample_quality        : sample_size / 30 (capped)
  * overfit_resistance    : 1 - single_period_dominance
  * regime_stability      : cross_regime_consistency
  * correlation_health    : 1 if not flagged in correlation matrix else 0.3
  * decay_quality         : 1 if decay label in {improving, stable} else lower
  * robustness_score      : from robustness validator

A setup needs production_research_score >= 0.65 to be ACTIVE.
Below that → RESEARCH_ONLY (visible in research panels but never traded).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List


PRODUCTION_THRESHOLD = 0.65
RESEARCH_THRESHOLD = 0.40   # below this = totally disabled


DECAY_TO_SCORE = {
    "improving": 1.00,
    "stable":    0.85,
    "decaying":  0.50,
    "broken":    0.20,
}


@dataclass
class QualityVerdict:
    strategy: str
    production_research_score: float
    components: Dict[str, float] = field(default_factory=dict)
    research_status: str = "UNKNOWN"   # ACTIVE / RESEARCH_ONLY / DISABLED
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate(
    strategy: str,
    *,
    sample_size: int = 0,
    cross_regime_consistency: float = 0.0,
    single_period_dominance: float = 0.0,
    correlation_flagged: bool = False,
    decay_label: str | None = None,
    robustness_score: float = 0.0,
) -> QualityVerdict:
    notes: List[str] = []
    sample_quality = min(1.0, sample_size / 30.0)
    overfit_resist = max(0.0, 1.0 - single_period_dominance)
    regime_stab = max(0.0, min(1.0, cross_regime_consistency))
    corr_health = 0.3 if correlation_flagged else 1.0
    if correlation_flagged:
        notes.append("flagged in correlation matrix — score halved")
    decay_score = DECAY_TO_SCORE.get(decay_label or "stable", 0.85)
    if decay_label == "broken":
        notes.append("edge decay = broken")
    robust = max(0.0, min(1.0, robustness_score))

    score = (
        0.20 * sample_quality +
        0.20 * overfit_resist +
        0.15 * regime_stab +
        0.15 * corr_health +
        0.15 * decay_score +
        0.15 * robust
    )
    score = round(score, 4)

    if score >= PRODUCTION_THRESHOLD:
        status = "ACTIVE"
    elif score >= RESEARCH_THRESHOLD:
        status = "RESEARCH_ONLY"
    else:
        status = "DISABLED"

    return QualityVerdict(
        strategy=strategy,
        production_research_score=score,
        components={
            "sample_quality": round(sample_quality, 4),
            "overfit_resistance": round(overfit_resist, 4),
            "regime_stability": round(regime_stab, 4),
            "correlation_health": round(corr_health, 4),
            "decay_score": round(decay_score, 4),
            "robustness_score": round(robust, 4),
        },
        research_status=status,
        notes=notes,
    )
