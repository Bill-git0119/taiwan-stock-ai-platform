"""Fundamental analysis — 0~100 score.

Input dict:
{
    "eps_yoy":     float,   # EPS 年增率 (%)
    "roe":         float,   # 股東權益報酬率 (%)
    "rev_mom":     float,   # 營收月增率 (%)
    "pe":          float,   # 本益比
}

Rules
-----
+ EPS YoY: 0%→0, ≥20%→30
+ ROE: 0%→0, ≥20%→30
+ Revenue MoM: 0%→0, ≥15%→20
+ PE in [8, 20] (sweet spot): full 20, outside: decays
"""
from __future__ import annotations

from dataclasses import dataclass


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _pe_points(pe: float) -> float:
    if pe is None or pe <= 0:
        return 0.0
    if 8 <= pe <= 20:
        return 20.0
    if pe < 8:
        return _clip(20 - (8 - pe) * 3)
    return _clip(20 - (pe - 20) * 1.5)


@dataclass
class FundamentalCalculator:
    eps_yoy: float = 0.0
    roe: float = 0.0
    rev_mom: float = 0.0
    pe: float = 0.0

    def eps_points(self) -> float:
        return _clip(self.eps_yoy * 1.5, 0, 30)

    def roe_points(self) -> float:
        return _clip(self.roe * 1.5, 0, 30)

    def rev_points(self) -> float:
        return _clip(self.rev_mom * 1.33, 0, 20)

    def pe_points(self) -> float:
        return _pe_points(self.pe)

    def score(self) -> float:
        return _clip(self.eps_points() + self.roe_points() + self.rev_points() + self.pe_points())


def fundamental_score(
    eps_yoy: float = 0.0,
    roe: float = 0.0,
    rev_mom: float = 0.0,
    pe: float = 0.0,
) -> float:
    return FundamentalCalculator(eps_yoy, roe, rev_mom, pe).score()
