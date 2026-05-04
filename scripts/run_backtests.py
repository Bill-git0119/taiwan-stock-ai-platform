"""Run all strategies on a symbol universe; rank by Sharpe-adjusted return.

Usage:
    python scripts/run_backtests.py
    python scripts/run_backtests.py --symbols 2330,2454,2317
    python scripts/run_backtests.py --strategies trend_breakout,mean_reversion

Output:
    data/backtests_<timestamp>.json  (full reports)
    stdout: summary table sorted by score
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.backtest_engine_v2 import BacktestConfig, run_backtest  # noqa: E402
from strategy.strategies import REGISTRY  # noqa: E402

DEFAULT_SYMBOLS = [
    "2330", "2454", "2317", "2303", "3008", "2308",
    "2881", "2603", "3034", "2382", "3231", "2376",
]


def synth_bars(symbol: str, n: int = 300) -> List[dict]:
    seed = sum(ord(c) for c in symbol) or 1
    base = 100 + (seed % 50) * 4
    bars: List[dict] = []
    px = base
    for i in range(n):
        drift = 0.10
        wave = 1.5 * math.sin(i / 6 + seed)
        noise = ((i * 1103515245 + seed) % 1000) / 1000.0 - 0.5
        close = max(1.0, px + drift + wave + noise * 1.4)
        high = close + abs(noise) * 1.7 + 0.4
        low = close - abs(noise) * 1.7 - 0.4
        open_ = (high + low + close) / 3
        vol = 800_000 + int(abs(math.sin(i / 4)) * 400_000)
        bars.append({
            "date": f"2024-{((i // 22) % 12) + 1:02d}-{(i % 22) + 1:02d}",
            "open": round(open_, 2), "high": round(high, 2),
            "low": round(low, 2), "close": round(close, 2),
            "volume": vol,
        })
        px = close
    return bars


def score(report) -> float:
    """Composite ranking score: total_return * sharpe / (1 + |max_dd|)."""
    return report.total_return * (1 + max(0.0, report.sharpe)) / (1 + abs(report.max_drawdown))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    ap.add_argument("--strategies", default=",".join(REGISTRY.keys()))
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]

    cfg = BacktestConfig(starting_equity=1_000_000.0, risk_pct=0.01)
    results = []
    for sym in symbols:
        bars = synth_bars(sym)
        for sname in strategies:
            fn = REGISTRY.get(sname)
            if fn is None:
                continue
            rep = run_backtest(bars, fn, strategy_name=sname, symbol=sym, cfg=cfg)
            results.append(rep)

    results.sort(key=score, reverse=True)

    print(f"\n{'symbol':<8}{'strategy':<18}{'trades':>8}{'win%':>8}{'sharpe':>10}{'PF':>10}{'maxDD':>10}{'totRet':>10}")
    print("-" * 82)
    for r in results:
        print(f"{r.symbol:<8}{r.strategy:<18}"
              f"{r.trades_count:>8}{r.win_rate*100:>7.1f}%"
              f"{r.sharpe:>10.2f}{r.profit_factor:>10.2f}"
              f"{r.max_drawdown*100:>9.1f}%{r.total_return*100:>9.1f}%")

    out_path = Path(args.out) if args.out else Path(f"data/backtests_{int(time.time())}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"\n[run_backtests] full report -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
