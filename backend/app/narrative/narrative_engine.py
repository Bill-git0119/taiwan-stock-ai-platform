"""Narrative engine — synthesises today's market story.

Output schema:
  {
    "market_style":  "risk_on" | "risk_off" | "neutral" | "mixed",
    "dominant_themes": [{"theme": ..., "hits": ...}, ...],
    "leading_sector": "...",
    "weakest_sector": "...",
    "institutional_focus": [{"symbol": ..., "foreign_streak": ...}, ...],
    "market_summary": "human-readable one-liner",
    "risk_factors": ["...", "..."]
  }

All inputs come from already-collected intelligence + DB rows.
Deterministic, no LLM, lookahead-free.
"""
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.aggregator import collect_intelligence
from app.narrative.capital_flow_detector import institutional_focus
from app.narrative.theme_tracker import score_themes
from strategy.market_regime import detect_regime


def _market_style(regime_label: str,
                  strongest_pct: float | None,
                  weakest_pct: float | None,
                  anomaly_count: int) -> str:
    if regime_label.startswith("trending_up"):
        if strongest_pct is not None and strongest_pct > 5:
            return "risk_on"
        return "neutral"
    if regime_label in ("bearish", "trending_down"):
        return "risk_off"
    if regime_label == "sideways":
        if anomaly_count >= 5:
            return "mixed"
        return "neutral"
    return "neutral"


def _summary(style: str, leading: str, themes: list[dict], focus_count: int) -> str:
    bits = []
    if style == "risk_on":
        bits.append("市場處於 risk-on 模式，主流順勢買進。")
    elif style == "risk_off":
        bits.append("市場處於 risk-off，須降低槓桿、優先做空或現金。")
    elif style == "mixed":
        bits.append("市場呈現混亂，個股表現分化、輪動快速。")
    else:
        bits.append("市場處於整理階段，無明顯方向。")
    if leading:
        bits.append(f"領漲族群：{leading}。")
    if themes:
        top_t = ", ".join([t["theme"] for t in themes[:3]])
        bits.append(f"主題集中於 {top_t}。")
    if focus_count > 0:
        bits.append(f"{focus_count} 檔個股出現法人連續買超 + 爆量同步訊號。")
    return " ".join(bits)


def _risk_factors(regime: dict, sectors: list[dict]) -> list[str]:
    out: list[str] = []
    if regime.get("label") == "bearish":
        out.append("大盤趨勢向下 — 多單高度警戒")
    if regime.get("adx") and regime["adx"] < 18:
        out.append(f"ADX={regime['adx']:.1f} 低於 18，趨勢動能不足")
    if regime.get("atr_contraction") and regime["atr_contraction"] < 0.7:
        out.append(f"ATR 收斂至 {regime['atr_contraction']:.2f}，可能即將變盤")
    weakest = sectors[-1] if sectors else None
    if weakest and weakest.get("return_20d", 0) < -5:
        out.append(f"{weakest['sector']} 月線跌幅 {weakest['return_20d']:.1f}% — 避開")
    return out


async def build_narrative(session: AsyncSession,
                          intel: Dict[str, Any] | None = None,
                          regime: dict | None = None) -> dict:
    intel = intel or await collect_intelligence(session)
    if regime is None:
        # use proxy 0050 / 2330
        from sqlalchemy import select as _sel
        from app.db.models import DailyPrice, Stock
        proxy = None
        for sym in ("0050", "2330", "2317"):
            proxy = (await session.execute(
                _sel(Stock).where(Stock.symbol == sym)
            )).scalar_one_or_none()
            if proxy:
                break
        if proxy is None:
            regime = {"label": "unknown", "adx": None, "atr_contraction": None,
                      "allowed_setups": []}
        else:
            rows = (await session.execute(
                _sel(DailyPrice).where(DailyPrice.stock_id == proxy.id)
                .order_by(DailyPrice.date.asc())
            )).scalars().all()
            if len(rows) >= 60:
                r = detect_regime([float(p.close) for p in rows],
                                  [float(p.high) for p in rows],
                                  [float(p.low) for p in rows])
                regime = r.to_dict()
            else:
                regime = {"label": "unknown", "adx": None,
                          "atr_contraction": None, "allowed_setups": []}

    sectors = intel.get("sectors", {}).get("sectors", [])
    leading = sectors[0]["sector"] if sectors else ""
    weakest = sectors[-1]["sector"] if sectors else ""
    strongest_pct = sectors[0]["return_20d"] if sectors else None
    weakest_pct = sectors[-1]["return_20d"] if sectors else None

    news_titles = [n["title"] for n in intel.get("news", {}).get("items", [])]
    ptt_keywords = [k["keyword"] for k in intel.get("ptt", {}).get("hot_keywords", [])]
    themes = score_themes(news_titles, ptt_keywords)

    focus = await institutional_focus(session, intel.get("volume_anomalies", []))

    style = _market_style(
        regime.get("label", "unknown"),
        strongest_pct, weakest_pct,
        len(intel.get("volume_anomalies", [])),
    )

    return {
        "market_style": style,
        "regime": regime,
        "dominant_themes": themes[:5],
        "leading_sector": leading,
        "weakest_sector": weakest,
        "institutional_focus": focus,
        "market_summary": _summary(style, leading, themes, len(focus)),
        "risk_factors": _risk_factors(regime, sectors),
    }
