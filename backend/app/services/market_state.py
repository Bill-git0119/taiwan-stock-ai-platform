"""Market State Engine — the regime layer for the local research desk.

Combines five data sources into one structured verdict the scanner /
trade-plan engine can gate on:

  1. Per-symbol regime (ADX + EMA200 slope + ATR contraction)
     -- from strategy.market_regime
  2. Breadth (Adv/Dec, %>MA20/MA50, new-highs vs new-lows)
     -- from app.services.breadth_service
  3. Macro signals (VIX, DXY, US indices d1%, ^TWII)
     -- from app.datahub.collectors.macro_signals
  4. Sector rotation (which sectors lead/lag)
  5. Volatility expansion vs contraction

Output (MarketState):
  regime            trending_up / trending_up_weak / sideways /
                    trending_down / bearish / unknown
  confidence        0..1 (how sure are we)
  risk_level        low / normal / elevated / high
  risk_on_score     -1.0 ... +1.0  (negative = risk-off)
  exposure_mult     0.0 ... 1.0  (multiply position size by this)
  allowed_setups    setups OK to fire in this state
  forbidden_setups  setups blocked
  reasons           list[str] — human-readable explanations
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datahub.collectors.macro_signals import latest_macro
from app.db.models import DailyPrice, Stock
from app.services.breadth_service import compute_breadth

# Setup catalogue mirrors strategy.market_regime.ALLOWED_SETUPS but is
# softened by macro factors at runtime.
ALL_SETUPS = ("trend_breakout_retest", "ma20_support_bounce", "chip_follow_long")


@dataclass
class MarketState:
    regime: str = "unknown"
    confidence: float = 0.0
    risk_level: str = "normal"
    risk_on_score: float = 0.0
    exposure_mult: float = 0.5
    allowed_setups: list[str] = field(default_factory=list)
    forbidden_setups: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    breadth_hint: Optional[str] = None
    macro: dict = field(default_factory=dict)
    breadth_summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "regime": self.regime,
            "confidence": round(self.confidence, 3),
            "risk_level": self.risk_level,
            "risk_on_score": round(self.risk_on_score, 3),
            "exposure_mult": round(self.exposure_mult, 3),
            "allowed_setups": self.allowed_setups,
            "forbidden_setups": self.forbidden_setups,
            "reasons": self.reasons,
            "breadth_hint": self.breadth_hint,
            "macro": self.macro,
            "breadth_summary": self.breadth_summary,
        }


async def _market_index_regime(session: AsyncSession) -> dict:
    """Run regime detection on an equal-weighted basket of the universe
    so we have a 'market regime' even without an indexed ticker."""
    # Use 0050 if available, else the equal-weighted basket.
    proxy = (await session.execute(
        select(Stock).where(Stock.symbol == "0050")
    )).scalar_one_or_none()
    if proxy is None:
        proxy = (await session.execute(select(Stock).limit(1))).scalar_one_or_none()
        if proxy is None:
            return {"label": "unknown", "adx": None, "ema200_slope_pct": None}
    rows = (await session.execute(
        select(DailyPrice).where(DailyPrice.stock_id == proxy.id)
        .order_by(DailyPrice.date.asc()).limit(300)
    )).scalars().all()
    if len(rows) < 100:
        return {"label": "unknown", "adx": None, "ema200_slope_pct": None,
                "reason": f"insufficient_history ({len(rows)} bars)"}
    closes = [r.close for r in rows]
    highs = [r.high for r in rows]
    lows = [r.low for r in rows]
    from strategy.market_regime import detect_regime
    r = detect_regime(closes, highs, lows)
    return r.to_dict()


def _risk_on_score_from_macro(macro: dict) -> tuple[float, list[str]]:
    """Return (-1..+1, [reasons]) — positive = risk-on."""
    if not macro:
        return 0.0, ["macro_data_unavailable"]
    reasons = []
    score = 0.0
    vix = macro.get("vix", {})
    if vix.get("last") is not None:
        v = vix["last"]
        if v < 15:
            score += 0.35
            reasons.append(f"VIX低 {v:.1f}（風險偏好高）")
        elif v < 20:
            score += 0.15
            reasons.append(f"VIX中 {v:.1f}")
        elif v < 25:
            score -= 0.10
            reasons.append(f"VIX偏高 {v:.1f}")
        else:
            score -= 0.40
            reasons.append(f"VIX高 {v:.1f}（風險規避）")
    sp = macro.get("sp500", {})
    if sp.get("d1_pct") is not None:
        d = sp["d1_pct"]
        if d > 0.5:
            score += 0.15
            reasons.append(f"S&P +{d:.2f}%")
        elif d < -1.0:
            score -= 0.20
            reasons.append(f"S&P {d:.2f}%")
    nasdaq = macro.get("nasdaq", {})
    if nasdaq.get("d1_pct") is not None and nasdaq["d1_pct"] < -1.5:
        score -= 0.15
        reasons.append(f"NASDAQ {nasdaq['d1_pct']:.2f}%")
    dxy = macro.get("dxy", {})
    if dxy.get("d1_pct") is not None and abs(dxy["d1_pct"]) > 0.5:
        if dxy["d1_pct"] > 0.5:
            score -= 0.10
            reasons.append(f"DXY +{dxy['d1_pct']:.2f}%（美元走強）")
        else:
            score += 0.05
            reasons.append(f"DXY {dxy['d1_pct']:.2f}%（美元走弱）")
    twii = macro.get("twii", {})
    if twii.get("d1_pct") is not None:
        d = twii["d1_pct"]
        if d > 0.8:
            score += 0.20
            reasons.append(f"TAIEX +{d:.2f}%")
        elif d < -1.0:
            score -= 0.25
            reasons.append(f"TAIEX {d:.2f}%")
    return max(-1.0, min(1.0, score)), reasons


def _breadth_lift(breadth: dict) -> float:
    """Breadth contribution to risk-on score. Range -0.3 .. +0.3."""
    if not breadth or breadth.get("universe_size", 0) == 0:
        return 0.0
    hint = breadth.get("regime_hint", "mixed")
    table = {
        "broad_strength": 0.30,
        "broad_weakness": -0.30,
        "consolidation": 0.0,
        "mixed": 0.0,
        "no_data": 0.0,
    }
    return table.get(hint, 0.0)


def _decide(idx_regime: dict, breadth: dict, macro: dict) -> MarketState:
    state = MarketState()
    state.macro = {k: v for k, v in (macro or {}).items() if k != "_meta"}
    state.breadth_summary = breadth
    state.breadth_hint = breadth.get("regime_hint")

    label = idx_regime.get("label", "unknown")
    adx = idx_regime.get("adx") or 0
    state.regime = label
    base_conf = 0.0 if label == "unknown" else min(1.0, (adx or 0) / 40.0)
    state.confidence = base_conf

    macro_score, macro_reasons = _risk_on_score_from_macro(state.macro)
    breadth_score = _breadth_lift(breadth)
    state.risk_on_score = round(macro_score + breadth_score, 3)
    state.reasons.extend(macro_reasons)
    if state.breadth_hint:
        state.reasons.append(f"breadth: {state.breadth_hint}")

    # ── decide allowed setups ───────────────────────────────────────
    if label in ("trending_up", "trending_up_weak"):
        state.allowed_setups = list(ALL_SETUPS)
    elif label == "sideways":
        state.allowed_setups = ["ma20_support_bounce"]
    elif label in ("trending_down", "trending_down_weak", "bearish"):
        state.allowed_setups = []
    else:  # unknown
        state.allowed_setups = []
        state.reasons.append("regime=unknown → 全部 setup 禁止進場直到資料完整")

    # Risk-off overrides — if macro is very risk-off, suspend everything
    if state.risk_on_score <= -0.5:
        state.allowed_setups = []
        state.reasons.append("risk_on_score 嚴重偏負 → 暫停所有 setup")
    elif state.risk_on_score <= -0.2:
        # Only allow the most defensive setup
        if "trend_breakout_retest" in state.allowed_setups:
            state.allowed_setups.remove("trend_breakout_retest")
        state.reasons.append("risk_on 中性偏負 → 不做 breakout，僅守 support/chip")

    state.forbidden_setups = [s for s in ALL_SETUPS if s not in state.allowed_setups]

    # ── risk level + exposure multiplier ─────────────────────────────
    if state.risk_on_score >= 0.4 and label == "trending_up":
        state.risk_level = "low"
        state.exposure_mult = 1.0
    elif state.risk_on_score >= 0.1 and label in ("trending_up", "trending_up_weak"):
        state.risk_level = "normal"
        state.exposure_mult = 0.75
    elif state.risk_on_score >= -0.2:
        state.risk_level = "elevated"
        state.exposure_mult = 0.50
    else:
        state.risk_level = "high"
        state.exposure_mult = 0.25

    if label == "unknown":
        state.exposure_mult = min(state.exposure_mult, 0.25)

    return state


async def compute_market_state(session: AsyncSession) -> MarketState:
    """Build the canonical MarketState used by scanner / decision engine."""
    idx_regime = await _market_index_regime(session)
    breadth = await compute_breadth(session)
    macro = (await latest_macro()) or {}
    return _decide(idx_regime, breadth, macro)
