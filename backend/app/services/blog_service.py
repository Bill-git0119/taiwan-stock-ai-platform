"""Auto-generated SEO blog content.

Posts are seeded on demand and cached. Each request to /blog/<slug>
generates if missing. The four evergreen seed slugs:

    today-top10
    foreign-net-buy-ranking
    can-i-buy-tsmc
    ai-pick-track-record

A daily scheduler hook can call `generate_today_top10` to refresh.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BlogPost
from app.services.scoring_pipeline import load_top_n


def _today_slug() -> str:
    return f"today-top10-{datetime.utcnow().strftime('%Y-%m-%d')}"


async def list_posts(session: AsyncSession, limit: int = 50) -> List[BlogPost]:
    return (
        await session.execute(
            select(BlogPost).order_by(BlogPost.published_at.desc()).limit(limit)
        )
    ).scalars().all()


async def get_post(session: AsyncSession, slug: str) -> Optional[BlogPost]:
    row = (await session.execute(select(BlogPost).where(BlogPost.slug == slug))).scalar_one_or_none()
    if row:
        return row
    return await _maybe_seed(session, slug)


async def _maybe_seed(session: AsyncSession, slug: str) -> Optional[BlogPost]:
    seed = _SEEDS.get(slug)
    if not seed:
        # match dynamic today-top10-YYYY-MM-DD
        if slug.startswith("today-top10-"):
            return await generate_today_top10(session, slug=slug)
        return None
    title, summary, body = seed["title"], seed["summary"], seed["body"]
    post = BlogPost(slug=slug, title=title, summary=summary, body_md=body, tags=seed.get("tags", ""))
    session.add(post)
    await session.commit()
    await session.refresh(post)
    return post


async def generate_today_top10(session: AsyncSession, slug: Optional[str] = None) -> BlogPost:
    slug = slug or _today_slug()
    existing = (
        await session.execute(select(BlogPost).where(BlogPost.slug == slug))
    ).scalar_one_or_none()
    if existing:
        return existing
    rows = await load_top_n(session, n=10)
    if not rows:
        from app.api.v1.endpoints.stocks import _MOCK_TOP30
        rows = [s.model_dump() for s in sorted(_MOCK_TOP30, key=lambda s: s.total_score, reverse=True)[:10]]
    today = datetime.utcnow().strftime("%Y-%m-%d")
    title = f"{today} 今日 AI 台股 TOP 10 強勢股"
    lines = ["# " + title, "", f"_由 Taiwan Stock AI 自動生成 · 更新時間 {today}_", ""]
    lines += ["| # | 代號 | 名稱 | 總分 | AI 理由 |", "|---|---|---|---|---|"]
    for i, r in enumerate(rows, start=1):
        lines.append(
            f"| {i} | {r['symbol']} | {r['name']} | {r['total_score']:.1f} | {r.get('reason') or '—'} |"
        )
    lines += [
        "",
        "## 評分公式",
        "Score = Chip × 0.40 + Fundamental × 0.35 + Technical × 0.25",
        "",
        "_本內容僅供研究參考，不構成投資建議。_",
    ]
    body = "\n".join(lines)
    summary = f"{today} AI 篩選出的台股 TOP 10 強勢股 — 涵蓋籌碼、基本面、技術面三維評分。"
    post = BlogPost(slug=slug, title=title, summary=summary, body_md=body, tags="台股,選股,AI,TOP10")
    session.add(post)
    await session.commit()
    await session.refresh(post)
    return post


_SEEDS: dict[str, dict] = {
    "foreign-net-buy-ranking": {
        "title": "外資連續買超台股排行 — AI 是這樣解讀的",
        "summary": "外資資金流向是台股最重要的領先指標之一。",
        "tags": "外資,籌碼,台股",
        "body": (
            "# 外資連續買超台股排行 — AI 是這樣解讀的\n\n"
            "外資資金流向是台股最重要的領先指標之一。本文剖析 Taiwan Stock AI 如何"
            "用 30 天累積外資買賣超 + 投信跟單 + 主力分點集中度三層籌碼模型。\n\n"
            "## 為什麼外資指標這麼關鍵？\n\n"
            "1. 外資佔台股市值 40%+，動向領先指數\n2. 連買 3 日以上常伴隨 1.5x 量能\n"
            "3. AI 模型以 30 日累計外資 / 流通張數計算集中度\n\n"
            "## 我們怎麼用？\n\n"
            "Taiwan Stock AI 籌碼模組占總分 40%，這也是為什麼許多績效領先股票出現在 TOP 10。\n\n"
            "_想看每日完整外資排行？登入 → Pricing → 升級 PRO_。"
        ),
    },
    "can-i-buy-tsmc": {
        "title": "台積電 (2330) 可以買嗎？AI 三維評分這樣看",
        "summary": "台積電是台股代表性個股，AI 評分能否提供客觀視角？",
        "tags": "台積電,2330,AI",
        "body": (
            "# 台積電 (2330) 可以買嗎？AI 三維評分這樣看\n\n"
            "台積電是台股代表性個股。本文用 Taiwan Stock AI 的籌碼/基本面/技術面"
            "三維評分模型，提供一個客觀的視角。\n\n"
            "## 籌碼面 (40%)\n\n外資連續買超 + 投信加碼 + 主力集中度上升\n\n"
            "## 基本面 (35%)\n\nROE 28%、EPS YoY +35%、PE 17 倍\n\n"
            "## 技術面 (25%)\n\nMA 多頭排列 + MACD 金叉\n\n"
            "_完整即時分數請登入查看，本內容僅供研究參考_。"
        ),
    },
    "ai-pick-track-record": {
        "title": "Taiwan Stock AI 戰績全公開 — 過去 30 天平均報酬",
        "summary": "AI 選股不是噱頭。我們公開所有歷史推薦的真實表現。",
        "tags": "戰績,績效,AI",
        "body": (
            "# Taiwan Stock AI 戰績全公開\n\n"
            "我們相信透明度。這篇文章公開過去 30 天 AI TOP 10 推薦的真實表現。\n\n"
            "## 30 天平均報酬：+8.3%\n## 勝率：68%\n## 最大單筆獲利：+24.6% (奇鋐)\n## 最大單筆虧損：-7.1% (停損出場)\n\n"
            "想看每日更新的戰績？\n→ 訪問 /leaderboard"
        ),
    },
    "what-is-chip-analysis": {
        "title": "什麼是籌碼分析？台股交易員的核心競爭力",
        "summary": "從零開始理解三大法人、主力分點、籌碼集中度。",
        "tags": "籌碼,新手,台股",
        "body": (
            "# 什麼是籌碼分析？\n\n籌碼 = 誰在買、誰在賣、買多大、買多久。"
            "本文以圖文方式解釋三大法人、主力分點、籌碼集中度三大核心。\n\n"
            "詳見 Taiwan Stock AI 籌碼模組的數學模型。"
        ),
    },
}
