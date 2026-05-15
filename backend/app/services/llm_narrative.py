"""LLM Narrative — daily brief generator backed by OpenAI / Anthropic.

Contract:
  * If ANTHROPIC_API_KEY or OPENAI_API_KEY is set, call the real model.
  * Otherwise return a deterministic stub built from the same data — so
    the workspace always has SOMETHING to show, but never makes up facts.
  * Never invents tickers, returns, or events: the prompt only contains
    data from compute_market_state / decisions / breadth / macro.

Output is structured Markdown the workspace renders directly.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from loguru import logger

PROVIDERS_ORDER = ("anthropic", "openai")  # try Claude first

# ── prompt template ─────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a senior Taiwan quantitative trader writing the
desk's morning brief for ONE professional reader (yourself).

Rules:
- Reply in zh-Hant.
- Use ONLY the data in the user message. Never invent tickers, prices,
  returns, events, or news headlines.
- 6 sections in this exact order, with H2 headers:
    今日市場狀態 / 強勢股觀察 / 風險警告 / 族群輪動 /
    昨日 vs 今日改變 / 明日 watchlist
- Each section under 80 words. Total under 500 words.
- Reference numbers exactly as given. Don't round aggressively.
- If a section has no data, say so plainly: "資料尚未灌入". Do not pad.
"""


@dataclass
class NarrativeResult:
    markdown: str
    provider: str             # "anthropic" / "openai" / "stub"
    generated_at: str
    facts_used: dict          # echo of the data we fed to the model

    def to_dict(self) -> dict:
        return {
            "markdown": self.markdown,
            "provider": self.provider,
            "generated_at": self.generated_at,
            "facts_used": self.facts_used,
        }


def _build_user_prompt(facts: dict) -> str:
    """Plain-text dump of the facts. Caller decides what's worth sending."""
    lines = ["[市場狀態]"]
    ms = facts.get("market_state") or {}
    lines.append(f"regime={ms.get('regime')}  risk_level={ms.get('risk_level')}  "
                 f"risk_on_score={ms.get('risk_on_score')}  exposure_mult={ms.get('exposure_mult')}")
    lines.append(f"allowed_setups={ms.get('allowed_setups')}")
    lines.append(f"forbidden_setups={ms.get('forbidden_setups')}")
    for r in (ms.get("reasons") or [])[:8]:
        lines.append(f"  · {r}")

    macro = ms.get("macro") or {}
    if macro:
        lines.append("\n[macro]")
        for k, v in list(macro.items())[:8]:
            if not isinstance(v, dict):
                continue
            lines.append(f"  {k}: last={v.get('last')} d1%={v.get('d1_pct')}")

    breadth = facts.get("breadth") or {}
    if breadth:
        ad = breadth.get("advance_decline") or {}
        lines.append(
            f"\n[breadth] hint={breadth.get('regime_hint')}  "
            f"AD={ad.get('advancing')}/{ad.get('declining')}  "
            f">MA20%={breadth.get('above_ma20_pct')}  "
            f"20D NH/NL={breadth.get('new_highs_20')}/{breadth.get('new_lows_20')}"
        )
        sectors = breadth.get("sectors") or []
        if sectors:
            top = ", ".join(f"{s['sector']}{s['ret_5d']:+.1f}" for s in sectors[:5])
            bot = ", ".join(f"{s['sector']}{s['ret_5d']:+.1f}" for s in sectors[-5:])
            lines.append(f"  top sectors 5D: {top}")
            lines.append(f"  bottom sectors 5D: {bot}")

    decisions = (facts.get("decisions") or {}).get("decisions") or []
    if decisions:
        lines.append(f"\n[actionable decisions — {len(decisions)} candidates]")
        for d in decisions[:8]:
            lines.append(
                f"  {d['symbol']} {d['name']} setup={d.get('setup')} "
                f"conf={d.get('confidence'):.2f} RR={d.get('risk_reward')} "
                f"sector={d.get('sector')} rs_5d={d.get('rs_5d')} "
                f"actionable={d.get('actionable')}"
            )
    return "\n".join(lines)


# ── provider implementations ─────────────────────────────────────────

async def _anthropic_call(system: str, user: str, max_tokens: int = 1200) -> str:
    import httpx
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError("no ANTHROPIC_API_KEY")
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        r.raise_for_status()
        j = r.json()
        return "".join(b.get("text", "") for b in j.get("content", []))


async def _openai_call(system: str, user: str, max_tokens: int = 1200) -> str:
    import httpx
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("no OPENAI_API_KEY")
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            json={
                "model": "gpt-4o-mini",
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        r.raise_for_status()
        j = r.json()
        return j["choices"][0]["message"]["content"]


def _stub_render(facts: dict) -> str:
    """No-LLM fallback — deterministic markdown built directly from facts."""
    ms = facts.get("market_state") or {}
    breadth = facts.get("breadth") or {}
    decisions = (facts.get("decisions") or {}).get("decisions") or []
    actionable = [d for d in decisions if d.get("actionable")]
    research = [d for d in decisions if not d.get("actionable")]

    parts = []
    parts.append("## 今日市場狀態")
    parts.append(
        f"- regime: **{ms.get('regime', 'unknown')}** "
        f"(confidence {ms.get('confidence', 0):.2f})"
    )
    parts.append(
        f"- risk_on_score: **{ms.get('risk_on_score', 0):+.2f}** "
        f"→ risk_level={ms.get('risk_level')} · exposure×{ms.get('exposure_mult')}"
    )
    if ms.get("allowed_setups"):
        parts.append(f"- 允許 setup：`{', '.join(ms['allowed_setups'])}`")
    else:
        parts.append("- 允許 setup：**全部封鎖**")

    parts.append("\n## 強勢股觀察")
    if actionable:
        for d in actionable[:5]:
            parts.append(
                f"- **{d['symbol']} {d['name']}** · {d.get('setup')} · "
                f"RR={d.get('risk_reward')} · 信心 {d.get('confidence', 0)*100:.0f}% · "
                f"{d.get('sector', '')}"
            )
    else:
        parts.append("- 今日無可進場標的（market_state 已封鎖或無 ACTIVE setup）")

    parts.append("\n## 風險警告")
    for r in (ms.get("reasons") or [])[:5]:
        parts.append(f"- {r}")
    if breadth.get("regime_hint") in ("broad_weakness", "mixed"):
        parts.append(f"- breadth = {breadth.get('regime_hint')} → 縮減部位")

    parts.append("\n## 族群輪動")
    sectors = breadth.get("sectors") or []
    if sectors:
        top = sectors[:3]
        bot = sectors[-3:]
        parts.append("- **領漲**：" + " · ".join(
            f"{s['sector']} {s['ret_5d']:+.1f}%" for s in top))
        parts.append("- **領跌**：" + " · ".join(
            f"{s['sector']} {s['ret_5d']:+.1f}%" for s in bot))
    else:
        parts.append("- 資料尚未灌入")

    parts.append("\n## 昨日 vs 今日改變")
    parts.append("- _(需要昨日的快照才能比較 — Phase 9 排程啟動後自動填上)_")

    parts.append("\n## 明日 watchlist")
    if research:
        for d in research[:5]:
            parts.append(
                f"- {d['symbol']} {d['name']} · 阻擋原因：{d.get('invalidation_reason')}"
            )
    else:
        parts.append("- 無 research candidates")

    parts.append("\n---\n*由 stub renderer 產出（沒有 LLM API key）。所有數據皆為真實。*")
    return "\n".join(parts)


# ── public API ──────────────────────────────────────────────────────

async def generate_narrative(facts: dict) -> NarrativeResult:
    user_prompt = _build_user_prompt(facts)
    for provider in PROVIDERS_ORDER:
        try:
            if provider == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
                text = await _anthropic_call(SYSTEM_PROMPT, user_prompt)
                return NarrativeResult(
                    markdown=text, provider="anthropic",
                    generated_at=datetime.utcnow().isoformat(), facts_used=facts,
                )
            if provider == "openai" and os.environ.get("OPENAI_API_KEY"):
                text = await _openai_call(SYSTEM_PROMPT, user_prompt)
                return NarrativeResult(
                    markdown=text, provider="openai",
                    generated_at=datetime.utcnow().isoformat(), facts_used=facts,
                )
        except Exception as e:
            logger.warning("llm provider {} failed: {}", provider, e)

    return NarrativeResult(
        markdown=_stub_render(facts), provider="stub",
        generated_at=datetime.utcnow().isoformat(), facts_used=facts,
    )


def has_llm_key() -> bool:
    return any(os.environ.get(k) for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"))
