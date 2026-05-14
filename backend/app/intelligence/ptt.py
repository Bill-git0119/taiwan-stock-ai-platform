"""PTT Stock board hot-topic scraper — title-only counting.

Only reads public titles + push counts from the board index page. No bodies,
no copyright violation. Used to surface which symbols are being talked about
right now, never to generate signals on its own.

Fault-tolerant: if PTT is down or blocks the request, returns [].
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from typing import List

import httpx

log = logging.getLogger("intel.ptt")

PTT_URL = "https://www.ptt.cc/bbs/Stock/index.html"
USER_AGENT = "Mozilla/5.0 (compatible; TaiwanStockAIResearch/1.0)"
COOKIES = {"over18": "1"}

_SYMBOL_RE = re.compile(r"\b(\d{4})\b")
_TITLE_RE = re.compile(r'<div class="title">.*?<a [^>]+>(.*?)</a>', re.S)
_PUSH_RE = re.compile(r'<div class="nrec">(.*?)</div>', re.S)


async def hot_topics(limit_pages: int = 2) -> dict:
    titles: List[str] = []
    push_scores: List[int] = []
    url = PTT_URL
    try:
        async with httpx.AsyncClient(timeout=15, cookies=COOKIES,
                                     headers={"User-Agent": USER_AGENT}) as cli:
            for _ in range(limit_pages):
                r = await cli.get(url)
                if r.status_code != 200:
                    break
                html = r.text
                page_titles = _TITLE_RE.findall(html)
                pushes = _PUSH_RE.findall(html)
                titles.extend(t.strip() for t in page_titles if "(本文已被刪除)" not in t)
                for p in pushes:
                    score = 0
                    p = p.strip()
                    if p.isdigit():
                        score = int(p)
                    elif p.startswith("X"):
                        score = -int(p[1:]) if p[1:].isdigit() else -10
                    elif p == "爆":
                        score = 100
                    push_scores.append(score)
                # find prev page link
                prev = re.search(r'href="(/bbs/Stock/index\d+\.html)"[^>]*>‹', html)
                if not prev:
                    break
                url = "https://www.ptt.cc" + prev.group(1)
    except Exception as e:
        log.warning("PTT fetch failed: %s", e)
        return {"titles_seen": 0, "hot_symbols": [], "hot_keywords": []}

    # count mentions
    sym_counter: Counter[str] = Counter()
    for t in titles:
        for sym in _SYMBOL_RE.findall(t):
            if not sym.startswith(("19", "20", "21")):
                sym_counter[sym] += 1
    keywords = []
    for t in titles:
        for kw in ("除息", "ETF", "AI", "重訊", "法說", "外資", "投信",
                   "土洋", "禿鷹", "波段", "短線", "盤前", "盤後", "Q1",
                   "Q2", "Q3", "Q4"):
            if kw in t:
                keywords.append(kw)
    kw_counter = Counter(keywords)
    avg_push = round(sum(push_scores) / len(push_scores), 2) if push_scores else 0.0
    return {
        "titles_seen": len(titles),
        "avg_push": avg_push,
        "hot_symbols": [{"symbol": s, "mentions": n} for s, n in sym_counter.most_common(15)],
        "hot_keywords": [{"keyword": k, "count": n} for k, n in kw_counter.most_common(10)],
    }
