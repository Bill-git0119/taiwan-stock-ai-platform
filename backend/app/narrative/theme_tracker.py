"""Theme tracker — score keywords across news + PTT + cross-source.

A "theme" is a keyword that shows up in multiple sources simultaneously.
We deliberately do NOT use an LLM here — themes need to be deterministic
and reproducible for backtesting decisions.
"""
from __future__ import annotations

from collections import Counter
from typing import Dict, List

KNOWN_THEMES: List[tuple[str, list[str]]] = [
    ("AI 半導體",          ["AI", "輝達", "NVIDIA", "HBM", "ASIC", "AI 伺服器", "GenAI"]),
    ("CoWoS / 先進封裝",   ["CoWoS", "封裝", "先進封裝", "ABF"]),
    ("航運",               ["航運", "貨櫃", "BDI", "運費", "塞港"]),
    ("金融除息",           ["除息", "除權", "現金股利", "殖利率"]),
    ("ETF 成分股調整",     ["ETF", "成分股", "00878", "00919", "00713"]),
    ("外資買超",           ["外資", "買超", "土洋"]),
    ("投信買超",           ["投信", "作帳", "季底"]),
    ("法說會",             ["法說會", "Q1", "Q2", "Q3", "Q4", "毛利", "EPS", "展望"]),
    ("元宇宙 / 顯卡",      ["顯卡", "GPU", "繪圖", "電競"]),
    ("電動車",             ["電動車", "EV", "Tesla", "特斯拉"]),
    ("綠能",               ["綠能", "離岸風電", "太陽能", "氫能"]),
    ("生技",               ["生技", "新藥", "FDA", "臨床"]),
]


def score_themes(news_titles: List[str],
                  ptt_keywords: List[str],
                  ptt_titles: List[str] | None = None) -> List[dict]:
    text_blob = " ".join(news_titles + ptt_keywords + (ptt_titles or []))
    out: List[dict] = []
    for theme, terms in KNOWN_THEMES:
        hits = 0
        matched_terms = []
        for term in terms:
            if term in text_blob:
                hits += text_blob.count(term)
                matched_terms.append(term)
        if hits >= 1:
            out.append({
                "theme": theme,
                "hits": hits,
                "matched_terms": matched_terms,
            })
    out.sort(key=lambda t: t["hits"], reverse=True)
    return out
