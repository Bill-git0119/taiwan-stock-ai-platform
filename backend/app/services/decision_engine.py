"""ShortTermDecisionEngine — the single trader-facing decision API.

What it does:
  1. Pull MarketState (regime + breadth + macro + risk-on score)
  2. Run scanner.scan_universe (with persist=False — read-only here)
  3. For each LONG candidate:
       * filter by market_state.allowed_setups
       * gate by strategy production_status (only ACTIVE/WATCH pass)
       * scale position by market_state.exposure_mult
       * attach catalyst (from intelligence/news if available)
       * attach invalidation reason if blocked
  4. Return a ranked list of ShortTermDecisions

A ShortTermDecision is the canonical output the workspace UI reads.
It contains everything a trader needs to act:
    symbol, bias, setup, confidence,
    entry_zone, stop_loss, tp1, tp2,
    holding_days_max, risk_score, exposure_mult,
    catalyst (optional), why_now, invalidation_reason
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.market_state import compute_market_state
from app.services.scanner_service import scan_universe
from app.strategy_registry.ranker import rank_all


@dataclass
class ShortTermDecision:
    symbol: str
    name: str
    bias: str
    setup: Optional[str]
    confidence: float
    rank: float
    adaptive_score: float

    # actionable levels
    entry_zone: Optional[list[float]] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[list[float]] = None
    risk_reward: Optional[float] = None
    atr: Optional[float] = None

    # context
    sector: Optional[str] = None
    sector_rank: Optional[int] = None
    rs_5d: Optional[float] = None
    ret_5d: Optional[float] = None
    rel_volume: Optional[float] = None
    regime: Optional[str] = None
    production_status: Optional[str] = None
    as_of: Optional[str] = None

    # gating
    actionable: bool = False
    invalidation_reason: Optional[str] = None
    exposure_mult: float = 1.0

    # narrative (Phase 7 fills these in)
    catalyst: Optional[str] = None
    why_now: list[str] = field(default_factory=list)

    # holding rules
    holding_days_max: int = 12

    # risk score 0..1 (higher = riskier)
    risk_score: float = 0.5

    def to_dict(self) -> dict:
        return asdict(self)


def _gate_one(item: dict, *, allowed_setups: list[str],
              forbidden_setups: list[str],
              active_setups: set[str],
              disabled_setups: set[str]) -> tuple[bool, Optional[str]]:
    setup = item.get("setup")
    if item.get("bias") != "LONG":
        return False, item.get("no_trade_reason") or "not_long"
    if not setup:
        return False, "no_setup"
    if setup in forbidden_setups:
        return False, f"market_state forbids {setup}"
    if allowed_setups and setup not in allowed_setups:
        return False, "setup not in market_state.allowed_setups"
    if setup in disabled_setups:
        return False, "strategy DISABLED by gate"
    if setup not in active_setups:
        # WATCH / UNKNOWN — show as research candidate, not actionable
        return False, "strategy not ACTIVE (research-only)"
    return True, None


def _risk_score(item: dict, exposure_mult: float) -> float:
    """0..1, higher = riskier. Composite of:
      - 1 - confidence
      - 1 - exposure_mult
      - clamp(rel_volume too high)"""
    conf = float(item.get("confidence", 0.0))
    rv = float(item.get("rel_volume") or 1.0)
    rv_penalty = max(0.0, min(0.3, (rv - 3.0) / 10.0))  # very high vol = manic
    base = 0.5 * (1.0 - conf) + 0.3 * (1.0 - exposure_mult) + 0.2 * rv_penalty
    return round(max(0.0, min(1.0, base)), 3)


def _why_now(item: dict, market_state: dict) -> list[str]:
    """Pull the most decision-relevant lines out of the existing fields."""
    bits: list[str] = []
    for r in (item.get("reasons") or [])[:4]:
        bits.append(r)
    rs = item.get("rs_5d")
    if rs is not None and rs >= 2:
        bits.append(f"相對大盤強 +{rs:.1f}% (5D)")
    sr = item.get("sector_rank")
    sc = item.get("sector_count")
    if sr and sc and sr <= max(1, sc // 3):
        bits.append(f"族群龍頭 #{sr}/{sc}")
    breadth = (market_state.get("breadth_hint") or "")
    if breadth == "broad_strength":
        bits.append("市場廣度強勢")
    return bits


async def decide(
    session: AsyncSession,
    *,
    limit: int = 30,
    include_research: bool = True,
) -> dict:
    """Build the canonical short-term decision list.

    include_research=True surfaces non-actionable research candidates
    (gated but interesting) so the desk has visibility into the bench.
    """
    state = (await compute_market_state(session)).to_dict()
    scan = await scan_universe(session, limit=200)
    rankings = await rank_all(session)

    active_setups = {r.strategy for r in rankings if r.production_status == "ACTIVE"}
    disabled_setups = {r.strategy for r in rankings if r.production_status == "DISABLED"}
    status_by_setup = {r.strategy: r.production_status for r in rankings}

    decisions: list[ShortTermDecision] = []
    for item in scan.get("items", []):
        actionable, blocked_reason = _gate_one(
            item,
            allowed_setups=state.get("allowed_setups", []),
            forbidden_setups=state.get("forbidden_setups", []),
            active_setups=active_setups,
            disabled_setups=disabled_setups,
        )
        if not actionable and not include_research:
            continue
        em = state.get("exposure_mult", 1.0) if actionable else 0.0
        d = ShortTermDecision(
            symbol=item["symbol"],
            name=item.get("name", item["symbol"]),
            bias=item.get("bias", "NO_TRADE"),
            setup=item.get("setup"),
            confidence=float(item.get("confidence", 0.0)),
            rank=float(item.get("rank", 0.0)),
            adaptive_score=float(item.get("adaptive_score", 0.0)),
            entry_zone=item.get("entry_zone"),
            stop_loss=item.get("stop_loss"),
            take_profit=item.get("take_profit"),
            risk_reward=item.get("risk_reward"),
            atr=item.get("atr"),
            sector=item.get("sector"),
            sector_rank=item.get("sector_rank"),
            rs_5d=item.get("rs_5d"),
            ret_5d=item.get("ret_5d"),
            rel_volume=item.get("rel_volume"),
            regime=(item.get("regime") or {}).get("label") if isinstance(item.get("regime"), dict) else state.get("regime"),
            production_status=status_by_setup.get(item.get("setup")),
            as_of=item.get("as_of"),
            actionable=actionable,
            invalidation_reason=blocked_reason,
            exposure_mult=em,
            holding_days_max=(item.get("management") or {}).get("max_hold_bars", 12),
            risk_score=_risk_score(item, em or 0.5),
            why_now=_why_now(item, state),
        )
        decisions.append(d)

    # actionable first, then by adaptive_score then rank
    decisions.sort(key=lambda d: (
        0 if d.actionable else 1,
        -d.adaptive_score,
        -d.rank,
    ))

    return {
        "as_of": scan.get("as_of"),
        "market_state": state,
        "actionable_count": sum(1 for d in decisions if d.actionable),
        "research_count": sum(1 for d in decisions if not d.actionable),
        "decisions": [d.to_dict() for d in decisions[:limit]],
    }
