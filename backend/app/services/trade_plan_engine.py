"""Trade Plan Engine — turns raw price + chip + fundamental features into
a complete actionable plan (entry / SL / TP / RR / confidence / reasons).

Iron rules (hard-coded, non-negotiable):
  * 每筆風險 ≤ 1% of account     (risk_pct_cap = 0.01)
  * RR < 1.5 不進場                (NO_TRADE if rr < MIN_RR)
  * 無明確結構（無 ATR / 無 swing low）→ 不出計畫
  * 禁用未來資料（caller must pass bars up to but not including future）

Returned dataclass is JSON-serialisable via .to_dict().
"""
from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

# Make repo-root packages importable when this module is imported through
# the FastAPI app whose CWD is backend/.
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from technical_analysis.calculator import Indicators, IndicatorBundle  # noqa: E402
from chip_analysis.calculator import ChipMetrics, ChipBundle  # noqa: E402


# ─────────────────────────── iron rules ─────────────────────────────
MIN_RR: float = 1.5
RISK_PCT_CAP: float = 0.01
ATR_STOP_MULT: float = 1.5
TP1_MULT_R: float = 1.5
TP2_MULT_R: float = 3.0
COMMISSION_BPS: float = 5.0       # 0.05% / side
SLIPPAGE_BPS: float = 5.0         # 0.05% / side, ≈ 3 ticks at typical TW prices


# ─────────────────────────── output schema ──────────────────────────
@dataclass
class TradePlan:
    symbol: str
    bias: str                              # LONG / SHORT / NO_TRADE
    setup: Optional[str] = None            # "trend_breakout_retest" / "mean_reversion_ma20" / etc.
    entry_zone: Optional[List[float]] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[List[float]] = None
    risk_reward: Optional[float] = None    # using TP1 vs SL
    confidence: float = 0.0                # 0..1
    chip_score: float = 0.0
    technical_score: float = 0.0
    fundamental_score: float = 0.0
    reasons: List[str] = field(default_factory=list)
    indicators: dict = field(default_factory=dict)
    chip: dict = field(default_factory=dict)
    no_trade_reason: Optional[str] = None
    last_close: Optional[float] = None
    atr: Optional[float] = None
    position_size_hint: Optional[dict] = None  # account-based suggestion

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────── helpers ────────────────────────────────

def _round(v: Optional[float], dp: int = 2) -> Optional[float]:
    return None if v is None else round(float(v), dp)


def _technical_score(ind: IndicatorBundle) -> float:
    """0..100 from the new indicator bundle (parallel to the legacy formula)."""
    pts = 0.0
    if ind.ma_alignment: pts += 25
    if ind.macd_bull: pts += 25
    if ind.rsi_zone == "healthy": pts += 25
    elif ind.rsi_zone == "neutral": pts += 12
    if ind.breakout_20: pts += 15
    if ind.volume_spike >= 1.5: pts += 10
    return max(0.0, min(100.0, pts))


def _chip_score(cb: ChipBundle) -> float:
    fs = min(cb.foreign_streak, 5) * 6
    inv = min(cb.investment_streak, 5) * 4
    vol_pts = max(0.0, min(30.0, (cb.volume_ratio_5_20 - 1.0) * 50))
    conc_pts = max(0.0, min(20.0, cb.concentration_delta * 200))
    align_pts = cb.foreign_invest_alignment * 10
    return max(0.0, min(100.0, fs + inv + vol_pts + conc_pts + align_pts))


def _confidence(chip: float, tech: float, fund: float) -> float:
    raw = chip * 0.40 + fund * 0.35 + tech * 0.25
    return max(0.0, min(1.0, raw / 100.0))


def _structure_ok(ind: IndicatorBundle) -> bool:
    """Iron rule: no structure → no trade."""
    return ind.atr14 is not None and ind.atr14 > 0 and ind.last > 0


# ─────────────────────────── setup detectors ────────────────────────

def _detect_long_setup(ind: IndicatorBundle, cb: ChipBundle) -> Optional[str]:
    """Pick the strongest LONG setup, or None."""
    # 1) Breakout & retest: just broke prior 20-bar high AND volume spike
    if ind.breakout_20 and ind.volume_spike >= 1.3 and ind.ma_alignment:
        return "trend_breakout_retest"

    # 2) MA20 support bounce: above ema20 by < 2*ATR, ema20 > ema50, RSI healthy
    if (ind.ema20 is not None and ind.ema50 is not None and ind.atr14 is not None
            and ind.ema20 > ind.ema50
            and ind.last >= ind.ema20
            and (ind.last - ind.ema20) < 2 * ind.atr14
            and ind.rsi_zone in ("neutral", "healthy")):
        return "ma20_support_bounce"

    # 3) Chip-led entry: foreign+investment buying with ema alignment
    if (cb.foreign_streak >= 3 and cb.foreign_invest_alignment >= 0.5
            and ind.ema20 is not None and ind.ema50 is not None
            and ind.ema20 > ind.ema50):
        return "chip_follow_long"

    return None


# ─────────────────────────── main entrypoint ────────────────────────

def build_plan(
    symbol: str,
    closes: Sequence[float],
    highs: Optional[Sequence[float]] = None,
    lows: Optional[Sequence[float]] = None,
    volumes: Optional[Sequence[float]] = None,
    chip_records: Optional[Sequence[dict]] = None,
    fundamental_score: float = 50.0,
    account_size: Optional[float] = None,
) -> TradePlan:
    """Compute a full trade plan or NO_TRADE with reason."""
    closes = list(closes)
    n = len(closes)
    plan = TradePlan(symbol=symbol, bias="NO_TRADE")

    if n < 30:
        plan.no_trade_reason = "insufficient_history"
        return plan

    ind = Indicators(
        closes=closes,
        highs=list(highs) if highs else list(closes),
        lows=list(lows) if lows else list(closes),
        volumes=list(volumes) if volumes else [0.0] * n,
    ).compute()
    cb = ChipMetrics(list(chip_records or [])).compute()

    plan.last_close = _round(ind.last)
    plan.atr = _round(ind.atr14, 4)
    plan.indicators = {k: _round(v, 4) if isinstance(v, float) else v
                       for k, v in ind.to_dict().items()}
    plan.chip = cb.to_dict()
    plan.technical_score = _round(_technical_score(ind), 2) or 0.0
    plan.chip_score = _round(_chip_score(cb), 2) or 0.0
    plan.fundamental_score = float(fundamental_score)
    plan.confidence = _round(
        _confidence(plan.chip_score, plan.technical_score, plan.fundamental_score), 4,
    ) or 0.0

    # Iron rule: structure required
    if not _structure_ok(ind):
        plan.no_trade_reason = "no_structure (ATR missing)"
        return plan

    setup = _detect_long_setup(ind, cb)
    if setup is None:
        plan.no_trade_reason = "no_qualifying_setup"
        return plan

    last = ind.last
    atr = float(ind.atr14)  # type: ignore[arg-type]

    # ─── compute SL / entry zone / TPs ───
    if setup == "trend_breakout_retest":
        entry_lo = last - 0.5 * atr
        entry_hi = last + 0.2 * atr
        sl = min(
            last - ATR_STOP_MULT * atr,
            (ind.donchian_high or last) - 1.2 * atr,
            (ind.prior_swing_low_5 or last) - 0.05 * last,
        )
    elif setup == "ma20_support_bounce":
        ema20 = float(ind.ema20)  # type: ignore[arg-type]
        entry_lo = max(ema20 - 0.3 * atr, last - 0.5 * atr)
        entry_hi = ema20 + 0.5 * atr
        sl = min(
            ema20 - ATR_STOP_MULT * atr,
            (ind.prior_swing_low_5 or ema20) - 0.05 * ema20,
        )
    else:  # chip_follow_long
        ema50 = float(ind.ema50) if ind.ema50 is not None else last
        entry_lo = last - 0.6 * atr
        entry_hi = last + 0.2 * atr
        sl = min(last - ATR_STOP_MULT * atr, ema50 - 0.5 * atr)

    if not (sl < entry_lo):
        plan.no_trade_reason = "stop_above_entry (invalid structure)"
        return plan

    risk_per_share = entry_lo - sl
    if risk_per_share <= 0:
        plan.no_trade_reason = "non_positive_risk"
        return plan

    tp1 = entry_lo + TP1_MULT_R * risk_per_share
    tp2 = entry_lo + TP2_MULT_R * risk_per_share

    # Snap TP2 toward structural objective if available
    if ind.donchian_high and ind.donchian_high > tp1:
        tp2 = max(tp2, ind.donchian_high * 1.02)

    rr = (tp1 - entry_lo) / risk_per_share

    if rr < MIN_RR:
        plan.no_trade_reason = f"rr_below_min ({rr:.2f} < {MIN_RR})"
        return plan

    # ─── reasons (stack the case from observed evidence) ───
    reasons: List[str] = []
    if cb.foreign_streak >= 3:
        reasons.append(f"外資連買 {cb.foreign_streak} 日")
    if cb.foreign_invest_alignment == 1.0:
        reasons.append("外資 + 投信同步買進")
    if ind.breakout_20:
        reasons.append("突破 20 日高點")
    if ind.ma_alignment:
        reasons.append("EMA 20/50/200 多頭排列")
    if ind.macd_bull:
        reasons.append("MACD 翻多")
    if ind.rsi_zone in ("neutral", "healthy"):
        reasons.append(f"RSI {ind.rsi14:.0f} {ind.rsi_zone}")  # type: ignore[union-attr]
    if ind.volume_spike >= 1.5:
        reasons.append(f"量能放大 {ind.volume_spike:.1f}x")
    if cb.concentration_delta > 0.01:
        reasons.append("籌碼集中度上升")
    if not reasons:
        reasons.append(setup)

    # ─── position size hint (1% account risk) ───
    pos_hint = None
    if account_size and account_size > 0:
        max_risk = account_size * RISK_PCT_CAP
        shares = int(max_risk // risk_per_share)
        pos_hint = {
            "account_size": account_size,
            "risk_pct": RISK_PCT_CAP,
            "max_risk_twd": round(max_risk, 2),
            "suggested_shares": shares,
            "suggested_notional": round(shares * entry_lo, 2),
        }

    plan.bias = "LONG"
    plan.setup = setup
    plan.entry_zone = [_round(entry_lo, 2) or 0.0, _round(entry_hi, 2) or 0.0]
    plan.stop_loss = _round(sl, 2)
    plan.take_profit = [_round(tp1, 2) or 0.0, _round(tp2, 2) or 0.0]
    plan.risk_reward = _round(rr, 2)
    plan.reasons = reasons
    plan.position_size_hint = pos_hint
    return plan
