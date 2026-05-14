"""Sector tagging — pulls sector_zh/sector_en from the curated table."""
from __future__ import annotations

from typing import Dict

from app.universe.curated import deduplicated

_SECTOR_BY_SYMBOL: Dict[str, tuple[str, str]] = {
    row[0]: (row[3], row[4]) for row in deduplicated()
}


def sector_for(symbol: str) -> tuple[str, str]:
    return _SECTOR_BY_SYMBOL.get(symbol, ("其他", "Other"))


def symbols_for_sector(sector_zh: str) -> list[str]:
    return [s for s, (z, _) in _SECTOR_BY_SYMBOL.items() if z == sector_zh]


def all_sectors() -> list[str]:
    return sorted(set(z for (z, _) in _SECTOR_BY_SYMBOL.values()))
