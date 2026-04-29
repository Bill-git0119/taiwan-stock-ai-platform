"""Unified AI scoring engine.

Score = Chip × 0.40 + Fundamental × 0.35 + Technical × 0.25

Input contract per stock:
{
    "symbol":        str,
    "name":          str,
    "chip_records":  list[dict],  # last ~20 days, see chip_analysis.calculator
    "fundamentals":  dict,        # eps_yoy, roe, rev_mom, pe
    "closes":        list[float], # last ≥60 daily closes
}
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, List

from chip_analysis.calculator import ChipCalculator
from fundamental_analysis.calculator import FundamentalCalculator
from technical_analysis.calculator import TechnicalCalculator

CHIP_WEIGHT = 0.40
FUNDAMENTAL_WEIGHT = 0.35
TECHNICAL_WEIGHT = 0.25


@dataclass
class ScoredStock:
    symbol: str
    name: str
    chip_score: float
    fundamental_score: float
    technical_score: float
    total_score: float
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def compute_total_score(chip: float, fundamental: float, technical: float) -> float:
    for v, n in ((chip, "chip"), (fundamental, "fundamental"), (technical, "technical")):
        if not (0.0 <= v <= 100.0):
            raise ValueError(f"{n} score {v} out of [0, 100]")
    return round(
        chip * CHIP_WEIGHT
        + fundamental * FUNDAMENTAL_WEIGHT
        + technical * TECHNICAL_WEIGHT,
        2,
    )


def _reason_phrases(chip: ChipCalculator, fund: FundamentalCalculator, tech: TechnicalCalculator) -> List[str]:
    phrases: List[str] = []

    fstreak = chip.foreign_streak()
    if fstreak >= 3:
        phrases.append(f"外資連買{fstreak}日")
    istreak = chip.investment_streak()
    if istreak >= 2:
        phrases.append(f"投信連買{istreak}日")
    vr = chip.volume_ratio()
    if vr >= 1.5:
        phrases.append(f"量能放大{vr:.1f}x")

    if fund.eps_yoy >= 20:
        phrases.append(f"EPS+{fund.eps_yoy:.0f}%")
    if fund.roe >= 15:
        phrases.append(f"ROE {fund.roe:.0f}%")
    if fund.rev_mom >= 10:
        phrases.append(f"營收MoM+{fund.rev_mom:.0f}%")

    if tech.ma_bullish():
        phrases.append("MA多頭排列")
    if tech.macd_golden():
        phrases.append("MACD金叉")
    if tech.breakout():
        phrases.append("突破20日高")

    return phrases


def score_stock(payload: dict) -> ScoredStock:
    chip_calc = ChipCalculator(list(payload.get("chip_records") or []))
    fund_raw = payload.get("fundamentals") or {}
    fund_calc = FundamentalCalculator(
        eps_yoy=float(fund_raw.get("eps_yoy", 0) or 0),
        roe=float(fund_raw.get("roe", 0) or 0),
        rev_mom=float(fund_raw.get("rev_mom", 0) or 0),
        pe=float(fund_raw.get("pe", 0) or 0),
    )
    tech_calc = TechnicalCalculator(list(payload.get("closes") or []))

    chip = round(chip_calc.score(), 2)
    fund = round(fund_calc.score(), 2)
    tech = round(tech_calc.score(), 2)
    total = compute_total_score(chip, fund, tech)

    phrases = _reason_phrases(chip_calc, fund_calc, tech_calc)
    reason = " + ".join(phrases) if phrases else "綜合評分"

    return ScoredStock(
        symbol=str(payload["symbol"]),
        name=str(payload.get("name", payload["symbol"])),
        chip_score=chip,
        fundamental_score=fund,
        technical_score=tech,
        total_score=total,
        reason=reason,
    )


def rank_top_n(stocks: Iterable[dict], n: int = 10) -> List[ScoredStock]:
    scored = [score_stock(s) for s in stocks]
    scored.sort(key=lambda s: s.total_score, reverse=True)
    return scored[:n]
