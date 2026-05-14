"""Date-range definitions for famous historical regimes + auto-detector.

Known regimes (Taiwan market):
  2020 COVID crash      : 2020-02-21 → 2020-04-30
  2020 recovery rally   : 2020-05-01 → 2020-12-31
  2021 euphoria         : 2021-01-01 → 2021-07-15
  2022 bear             : 2022-01-15 → 2022-10-31
  2023 AI breakout      : 2023-02-01 → 2023-08-31
  2024 megacap rally    : 2024-01-01 → 2024-07-31

`auto_segments(bars)` synthesizes additional regimes from any series:
  low_volatility   — ATR contracted < 0.7× 60-bar avg, EMA200 flat
  euphoric_trend   — rolling 20-bar return > +12% AND ADX > 25
  sideways_chop    — rolling 60-bar |return| < 5% AND ADX < 18

All ranges are inclusive of both endpoints.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, List, Tuple


@dataclass
class RegimeSegment:
    name: str          # e.g. "2020_crash"
    start: date
    end: date
    label: str         # crash / bear / sideways / trend / euphoria / recovery

    def to_dict(self) -> dict:
        return {"name": self.name, "start": str(self.start),
                "end": str(self.end), "label": self.label}


KNOWN_SEGMENTS: List[RegimeSegment] = [
    RegimeSegment("2020_crash",     date(2020, 2, 21),  date(2020, 4, 30),  "crash"),
    RegimeSegment("2020_recovery",  date(2020, 5, 1),   date(2020, 12, 31), "recovery"),
    RegimeSegment("2021_euphoria",  date(2021, 1, 1),   date(2021, 7, 15),  "euphoria"),
    RegimeSegment("2022_bear",      date(2022, 1, 15),  date(2022, 10, 31), "bear"),
    RegimeSegment("2023_ai_break",  date(2023, 2, 1),   date(2023, 8, 31),  "trend"),
    RegimeSegment("2024_megacap",   date(2024, 1, 1),   date(2024, 7, 31),  "trend"),
]


def _parse_date(s) -> date:
    if isinstance(s, date):
        return s
    if hasattr(s, "date"):
        return s.date()
    return date.fromisoformat(str(s)[:10])


def filter_bars(bars: List[dict], seg: RegimeSegment) -> List[dict]:
    out: List[dict] = []
    for b in bars:
        d = _parse_date(b["date"])
        if seg.start <= d <= seg.end:
            out.append(b)
    return out


def auto_segments(bars: List[dict]) -> List[RegimeSegment]:
    """Detect synthetic regimes inside the data — low-vol, euphoria, sideways."""
    out: List[RegimeSegment] = []
    if len(bars) < 80:
        return out
    closes = [b["close"] for b in bars]
    # Walk rolling 60-bar windows
    i = 60
    while i < len(bars) - 20:
        window = closes[i - 60:i]
        ret_pct = (window[-1] / window[0] - 1) * 100 if window[0] else 0
        # crude vol = stdev / mean
        mean = sum(window) / len(window)
        var = sum((x - mean) ** 2 for x in window) / len(window)
        sd_pct = (var ** 0.5) / mean * 100 if mean else 0
        seg_start = _parse_date(bars[i - 60]["date"])
        seg_end = _parse_date(bars[i]["date"])
        if abs(ret_pct) < 5 and sd_pct < 2:
            out.append(RegimeSegment(f"auto_sideways_{seg_start.isoformat()}",
                                      seg_start, seg_end, "sideways"))
        elif ret_pct > 12:
            out.append(RegimeSegment(f"auto_euphoria_{seg_start.isoformat()}",
                                      seg_start, seg_end, "euphoria"))
        elif sd_pct < 1.0:
            out.append(RegimeSegment(f"auto_lowvol_{seg_start.isoformat()}",
                                      seg_start, seg_end, "low_volatility"))
        i += 30
    return out


def all_segments(include_known: bool = True,
                  bars_for_auto: List[dict] | None = None) -> List[RegimeSegment]:
    out: List[RegimeSegment] = []
    if include_known:
        out.extend(KNOWN_SEGMENTS)
    if bars_for_auto:
        out.extend(auto_segments(bars_for_auto))
    return out
