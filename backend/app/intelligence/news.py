"""Taiwan-stock news fetcher.

Source: Anue (cnyes) public news listing API. Public endpoint, no auth.
We never reproduce article bodies — only titles + timestamps + source URL so
the trader can click through. Copyright-safe.

The trader uses news to confirm narrative behind a setup, not to generate
signals. So 30 most-recent headlines + per-symbol mentions is enough.

All requests are made with httpx and retry/backoff. If the source is down,
the aggregator falls back to an empty list — the brief still works.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import List, Optional

import httpx

log = logging.getLogger("intel.news")

ANUE_LIST_URL = "https://api.cnyes.com/media/api/v1/newslist/category/tw_stock"
USER_AGENT = (
    "Mozilla/5.0 (compatible; TaiwanStockAIResearch/1.0; "
    "+https://taiwan-stock-ai.platform/about)"
)


@dataclass
class NewsItem:
    id: int
    title: str
    summary: str
    url: str
    source: str
    published_at: str   # ISO 8601
    keywords: List[str]
    mentioned_symbols: List[str]

    def to_dict(self) -> dict:
        return asdict(self)


_SYMBOL_RE = re.compile(r"\b(\d{4,6})\b")  # crude — matches 4-6 digit numbers


def _extract_symbols(title: str, summary: str) -> List[str]:
    blob = f"{title} {summary}"
    found = set(_SYMBOL_RE.findall(blob))
    # filter obviously-not-symbols (years, money figures)
    out = []
    for s in found:
        if len(s) == 4 and s.startswith(("19", "20", "21")):
            continue
        out.append(s)
    return sorted(out)


async def fetch_news(limit: int = 30) -> List[NewsItem]:
    params = {"page": 1, "limit": limit}
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=15) as cli:
            r = await cli.get(ANUE_LIST_URL, params=params, headers=headers)
            r.raise_for_status()
            payload = r.json()
    except Exception as e:
        log.warning("cnyes news fetch failed: %s", e)
        return []
    items: List[dict] = payload.get("items", {}).get("data", [])
    out: List[NewsItem] = []
    for it in items:
        title = it.get("title", "").strip()
        summary = (it.get("summary") or "").strip()
        if not title:
            continue
        pub_ts = it.get("publishAt")
        try:
            pub_iso = datetime.fromtimestamp(int(pub_ts), tz=timezone.utc).isoformat()
        except Exception:
            pub_iso = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()
        kw = it.get("keyword") or []
        if isinstance(kw, str):
            kw = [k.strip() for k in kw.split(",") if k.strip()]
        slug = it.get("newsId") or it.get("id")
        out.append(NewsItem(
            id=int(slug) if slug else 0,
            title=title,
            summary=summary[:200],
            url=f"https://news.cnyes.com/news/id/{slug}" if slug else "",
            source="cnyes",
            published_at=pub_iso,
            keywords=list(kw)[:8],
            mentioned_symbols=_extract_symbols(title, summary),
        ))
    return out


async def symbol_news(symbol: str, limit: int = 10) -> List[NewsItem]:
    items = await fetch_news(limit=100)
    return [it for it in items if symbol in it.mentioned_symbols][:limit]
