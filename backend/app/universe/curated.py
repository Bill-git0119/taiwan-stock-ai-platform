"""Curated TOP100 Taiwan equities universe.

Composition (deterministic, hand-curated for liquidity + sector coverage):
  * TWSE-50 component proxies (large-cap blue chips)
  * Mid-cap leaders across sectors
  * Selected TPEX growth names
  * Major ETFs: 0050, 0056, 00878, 00919, 00713

Each tuple: (symbol, name, market, sector_zh, sector_en)
Sector codes follow TWSE classification but are kept short for UI use.

NOTE: this list is updated quarterly. The weekly UniverseSnapshot job
re-evaluates liquidity from DB and may DEACTIVATE specific symbols, but
does not add new ones automatically — additions go through this file.
"""
from __future__ import annotations

from typing import List, Tuple

UniverseRow = Tuple[str, str, str, str, str]


CURATED_TOP100: List[UniverseRow] = [
    # === ETFs (always-in) ===
    ("0050", "元大台灣50",      "TWSE", "ETF",       "ETF"),
    ("0056", "元大高股息",      "TWSE", "ETF",       "ETF"),
    ("00878", "國泰永續高股息", "TWSE", "ETF",       "ETF"),
    ("00919", "群益台灣精選高息","TWSE", "ETF",      "ETF"),
    ("00713", "元大台灣高息低波","TWSE", "ETF",      "ETF"),

    # === Semiconductors (半導體) ===
    ("2330", "台積電",          "TWSE", "半導體", "Semiconductor"),
    ("2454", "聯發科",          "TWSE", "半導體", "Semiconductor"),
    ("2303", "聯電",            "TWSE", "半導體", "Semiconductor"),
    ("2308", "台達電",          "TWSE", "電子零組件", "Components"),
    ("3711", "日月光投控",      "TWSE", "半導體", "Semiconductor"),
    ("2379", "瑞昱",            "TWSE", "半導體", "Semiconductor"),
    ("3034", "聯詠",            "TWSE", "半導體", "Semiconductor"),
    ("3105", "穩懋",            "TWSE", "半導體", "Semiconductor"),
    ("3443", "創意",            "TWSE", "半導體", "Semiconductor"),
    ("6488", "環球晶",          "TPEX", "半導體", "Semiconductor"),
    ("8046", "南電",            "TWSE", "電子零組件", "Components"),
    ("3037", "欣興",            "TWSE", "電子零組件", "Components"),
    ("6669", "緯穎",            "TWSE", "電腦週邊", "Computer"),
    ("2449", "京元電子",        "TWSE", "半導體", "Semiconductor"),
    ("5347", "世界",            "TPEX", "半導體", "Semiconductor"),
    ("6533", "晶心科",          "TPEX", "半導體", "Semiconductor"),

    # === Electronics / Hardware (電子組裝/品牌) ===
    ("2317", "鴻海",            "TWSE", "其他電子", "Electronics"),
    ("2382", "廣達",            "TWSE", "其他電子", "Electronics"),
    ("2356", "英業達",          "TWSE", "其他電子", "Electronics"),
    ("2376", "技嘉",            "TWSE", "電腦週邊", "Computer"),
    ("2377", "微星",            "TWSE", "電腦週邊", "Computer"),
    ("3231", "緯創",            "TWSE", "其他電子", "Electronics"),
    ("4938", "和碩",            "TWSE", "其他電子", "Electronics"),
    ("2353", "宏碁",            "TWSE", "電腦週邊", "Computer"),
    ("2357", "華碩",            "TWSE", "電腦週邊", "Computer"),
    ("3017", "奇鋐",            "TWSE", "電子零組件", "Components"),
    ("6505", "台塑化",          "TWSE", "石化",       "Petrochemical"),

    # === Optoelectronics / Display (光電/面板) ===
    ("3008", "大立光",          "TWSE", "光電",       "Optoelectronics"),
    ("2409", "友達",            "TWSE", "光電",       "Optoelectronics"),
    ("3481", "群創",            "TWSE", "光電",       "Optoelectronics"),
    ("2474", "可成",            "TWSE", "電腦週邊", "Computer"),

    # === Networking & Communications (網通) ===
    ("2454", "聯發科",          "TWSE", "半導體", "Semiconductor"),   # dup-safe (filtered)
    ("3702", "大聯大",          "TWSE", "半導體", "Semiconductor"),
    ("2412", "中華電",          "TWSE", "通信網路", "Telecom"),
    ("3045", "台灣大",          "TWSE", "通信網路", "Telecom"),
    ("4904", "遠傳",            "TWSE", "通信網路", "Telecom"),
    ("2345", "智邦",            "TWSE", "通信網路", "Telecom"),
    ("6285", "啟碁",            "TWSE", "通信網路", "Telecom"),
    ("3596", "智易",            "TWSE", "通信網路", "Telecom"),

    # === Financials (金融) ===
    ("2881", "富邦金",          "TWSE", "金融",     "Financial"),
    ("2882", "國泰金",          "TWSE", "金融",     "Financial"),
    ("2891", "中信金",          "TWSE", "金融",     "Financial"),
    ("2883", "開發金",          "TWSE", "金融",     "Financial"),
    ("2884", "玉山金",          "TWSE", "金融",     "Financial"),
    ("2885", "元大金",          "TWSE", "金融",     "Financial"),
    ("2886", "兆豐金",          "TWSE", "金融",     "Financial"),
    ("2887", "台新金",          "TWSE", "金融",     "Financial"),
    ("2890", "永豐金",          "TWSE", "金融",     "Financial"),
    ("2892", "第一金",          "TWSE", "金融",     "Financial"),
    ("5880", "合庫金",          "TWSE", "金融",     "Financial"),
    ("2880", "華南金",          "TWSE", "金融",     "Financial"),
    ("2888", "新光金",          "TWSE", "金融",     "Financial"),

    # === Plastics / Petrochemical (塑膠) ===
    ("1301", "台塑",            "TWSE", "塑膠",     "Plastic"),
    ("1303", "南亞",            "TWSE", "塑膠",     "Plastic"),
    ("1326", "台化",            "TWSE", "塑膠",     "Plastic"),

    # === Steel / Industrial (鋼鐵/工業) ===
    ("2002", "中鋼",            "TWSE", "鋼鐵",     "Steel"),
    ("2049", "上銀",            "TWSE", "機械",     "Machinery"),
    ("1605", "華新",            "TWSE", "電器電纜", "Electrical"),

    # === Auto / Transport (汽車/運輸) ===
    ("2207", "和泰車",          "TWSE", "汽車",     "Automotive"),
    ("2603", "長榮",            "TWSE", "航運",     "Shipping"),
    ("2609", "陽明",            "TWSE", "航運",     "Shipping"),
    ("2615", "萬海",            "TWSE", "航運",     "Shipping"),
    ("2618", "長榮航",          "TWSE", "航運",     "Airline"),
    ("2610", "華航",            "TWSE", "航運",     "Airline"),

    # === Food & Retail (食品/零售) ===
    ("1216", "統一",            "TWSE", "食品",     "Food"),
    ("2912", "統一超",          "TWSE", "貿易百貨", "Retail"),
    ("9933", "中鼎",            "TWSE", "其他",     "Other"),

    # === Biotech (生技) ===
    ("4174", "浩鼎",            "TWSE", "生技",     "Biotech"),
    ("6446", "藥華藥",          "TWSE", "生技",     "Biotech"),
    ("3105", "穩懋",            "TWSE", "半導體", "Semiconductor"),  # dup-safe

    # === Energy / Green (綠能) ===
    ("6244", "茂迪",            "TPEX", "綠能",     "Green Energy"),
    ("3691", "碩禾",            "TPEX", "綠能",     "Green Energy"),

    # === Building (建材) ===
    ("2542", "興富發",          "TWSE", "建材",     "Construction"),
    ("2545", "皇翔",            "TWSE", "建材",     "Construction"),

    # === Other ===
    ("2105", "正新",            "TWSE", "橡膠",     "Rubber"),
    ("9904", "寶成",            "TWSE", "其他",     "Other"),
    ("2731", "雄獅",            "TWSE", "觀光",     "Tourism"),
    ("2723", "美食-KY",         "TWSE", "觀光",     "Tourism"),

    # === High-momentum mid-caps (歷年強勢標的) ===
    ("8069", "元太",            "TPEX", "光電",     "Optoelectronics"),
    ("3231", "緯創",            "TWSE", "其他電子", "Electronics"),  # dup-safe
    ("6770", "力積電",          "TWSE", "半導體", "Semiconductor"),
    ("2376", "技嘉",            "TWSE", "電腦週邊", "Computer"),    # dup-safe
    ("2890", "永豐金",          "TWSE", "金融",     "Financial"),   # dup-safe
    ("6271", "同欣電",          "TWSE", "半導體", "Semiconductor"),
    ("3661", "世芯-KY",         "TWSE", "半導體", "Semiconductor"),
    ("3653", "健策",            "TWSE", "電子零組件", "Components"),
    ("6271", "同欣電",          "TWSE", "半導體", "Semiconductor"),  # dup-safe
    ("3530", "晶相光",          "TPEX", "半導體", "Semiconductor"),
    ("3406", "玉晶光",          "TWSE", "光電",     "Optoelectronics"),
    ("4763", "材料-KY",         "TWSE", "化學",     "Chemical"),
    ("5269", "祥碩",            "TWSE", "半導體", "Semiconductor"),
    ("3653", "健策",            "TWSE", "電子零組件", "Components"),  # dup-safe
    ("8210", "勤誠",            "TWSE", "電腦週邊", "Computer"),
    ("3018", "燿華",            "TWSE", "電子零組件", "Components"),
    ("1707", "葡萄王",          "TWSE", "生技",     "Biotech"),
    ("8044", "網家",            "TWSE", "貿易百貨", "Retail"),
]


def deduplicated() -> List[UniverseRow]:
    """Return curated list with duplicates removed (first occurrence wins)."""
    seen: set[str] = set()
    out: List[UniverseRow] = []
    for row in CURATED_TOP100:
        if row[0] in seen:
            continue
        seen.add(row[0])
        out.append(row)
    return out
