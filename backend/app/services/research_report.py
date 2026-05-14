"""Daily research report — markdown rendering of the brief + narrative.

Output is fully reproducible from DB rows; same inputs → same report.
"""
from __future__ import annotations

from datetime import datetime
from io import StringIO

from sqlalchemy.ext.asyncio import AsyncSession

from app.narrative.narrative_engine import build_narrative
from app.services.daily_brief import build_brief


def _fmt_pct(v):
    if v is None:
        return "—"
    return f"{v:+.2f}%"


async def render_markdown(session: AsyncSession) -> str:
    brief = await build_brief(session)
    narrative = await build_narrative(session)

    buf = StringIO()
    w = buf.write
    w("# Taiwan Stock AI — Daily Research Report\n\n")
    w(f"_Generated_: {datetime.utcnow().isoformat()}Z\n\n")
    w("## 市場敘事\n\n")
    w(f"- **市場風格**：`{narrative['market_style']}`\n")
    w(f"- **領漲族群**：{narrative['leading_sector'] or '—'}\n")
    w(f"- **最弱族群**：{narrative['weakest_sector'] or '—'}\n")
    w(f"- **市場摘要**：{narrative['market_summary']}\n\n")

    if narrative["risk_factors"]:
        w("### ⚠ 風險因子\n")
        for r in narrative["risk_factors"]:
            w(f"- {r}\n")
        w("\n")

    if narrative["dominant_themes"]:
        w("### 主題熱度 TOP 5\n")
        for t in narrative["dominant_themes"][:5]:
            w(f"- **{t['theme']}** ×{t['hits']} — {', '.join(t['matched_terms'][:5])}\n")
        w("\n")

    w("## 市場結構 (Regime)\n\n")
    reg = brief["market_regime"]
    w(f"- Label: `{reg.get('label')}`\n")
    w(f"- ADX(14): {reg.get('adx')}\n")
    w(f"- EMA200 slope: {reg.get('ema200_slope_pct')}\n")
    w(f"- Allowed setups: {', '.join(reg.get('allowed_setups') or []) or '—'}\n\n")

    w("## 強勢族群 (Sector Rotation)\n\n")
    w("| # | Sector | N | 5D | 20D | Leaders |\n")
    w("|---|---|---|---|---|---|\n")
    for s in brief["strongest_sectors"][:8]:
        leads = " ".join(l["symbol"] for l in s.get("leaders", [])[:3])
        w(f"| {s['rs_rank']} | {s['sector']} | {s['count']} | "
          f"{_fmt_pct(s['return_5d'])} | {_fmt_pct(s['return_20d'])} | {leads} |\n")
    w("\n")

    w("## ✅ Edge-Validated 訊號\n\n")
    if not brief["top_signals"]["validated"]:
        w("_今日無 edge-validated 訊號。研究候選請見下方。_\n\n")
    else:
        w("| SYM | SETUP | ENTRY | SL | TP1 | RR | CONF | WIN% | EXP_R | N | STATUS |\n")
        w("|---|---|---|---|---|---|---|---|---|---|---|\n")
        for s in brief["top_signals"]["validated"]:
            v = s.get("validation") or {}
            w(f"| {s['symbol']} | {s.get('setup','—')} | "
              f"{(s.get('entry_zone') or [None])[0]} | {s.get('stop_loss')} | "
              f"{(s.get('take_profit') or [None])[0]} | {s.get('risk_reward')} | "
              f"{int((s.get('confidence') or 0)*100)}% | "
              f"{int((v.get('win_rate') or 0)*100)}% | "
              f"{v.get('expectancy_r', '—')} | {v.get('sample_size', 0)} | "
              f"{s.get('production_status','UNKNOWN')} |\n")
        w("\n")

    w("## 異常爆量\n\n")
    if not brief["volume_anomalies"]:
        w("無異常爆量\n\n")
    else:
        w("| SYM | NAME | CLOSE | CHG | × AVG |\n|---|---|---|---|---|\n")
        for v in brief["volume_anomalies"][:10]:
            w(f"| {v['symbol']} | {v['name']} | {v['close']} | "
              f"{_fmt_pct(v['change_pct'])} | {v['ratio']:.1f}x |\n")
        w("\n")

    if narrative["institutional_focus"]:
        w("## 法人聚焦 (連續買超 + 爆量)\n\n")
        w("| SYM | SECTOR | 外資連 | 投信連 |\n|---|---|---|---|\n")
        for f in narrative["institutional_focus"][:10]:
            w(f"| {f['symbol']} | {f['sector']} | "
              f"{f['foreign_streak']} | {f['investment_streak']} |\n")
        w("\n")

    w("## 策略健康\n\n")
    if brief["disabled_setups"]:
        w(f"- DISABLED: {', '.join(brief['disabled_setups'])}\n\n")
    else:
        w("- 全部策略目前健康\n\n")

    w("## 明日觀察名單\n\n")
    if brief["top_signals"]["unvalidated"]:
        for s in brief["top_signals"]["unvalidated"][:5]:
            w(f"- **{s['symbol']}** {s.get('setup','—')} "
              f"@ {(s.get('entry_zone') or [None])[0]} "
              f"(SL {s.get('stop_loss')}, TP1 {(s.get('take_profit') or [None])[0]}, "
              f"RR {s.get('risk_reward')})\n")
        w("\n")
    else:
        w("- 暫無研究候選\n\n")

    w(f"---\n\n_Disclaimer: {brief.get('disclosure','')}_\n")
    return buf.getvalue()
