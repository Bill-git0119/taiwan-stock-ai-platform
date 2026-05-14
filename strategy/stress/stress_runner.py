"""Run a strategy across multiple historical regime segments."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Callable, List

from strategy.backtest_engine_v2 import BacktestConfig, run_backtest
from strategy.stress.regime_segments import RegimeSegment, all_segments, filter_bars


@dataclass
class SegmentReport:
    segment: dict
    bars_in_segment: int
    trades: int
    win_rate: float
    profit_factor: float
    expectancy_R: float
    sharpe: float
    max_drawdown: float
    total_return: float


@dataclass
class StressReport:
    strategy: str
    symbol: str
    segments: List[SegmentReport] = field(default_factory=list)
    cross_regime_consistency: float = 0.0   # fraction of segments with PF > 1
    cross_regime_min_pf: float = 0.0
    cross_regime_max_dd: float = 0.0
    single_period_dominance: float = 0.0    # max segment's return / total return

    def to_dict(self) -> dict:
        return asdict(self)


def _expectancy_R_from_report(rep) -> float:
    """Crude expectancy_R approximation from a BacktestReport."""
    if rep.trades_count == 0:
        return 0.0
    wins = [t for t in rep.trades if t.get("pnl_pct", 0) > 0]
    losses = [t for t in rep.trades if t.get("pnl_pct", 0) <= 0]
    n = len(wins) + len(losses)
    if n == 0:
        return 0.0
    avg_win_r = (sum(t["pnl_pct"] for t in wins) / len(wins) /
                  max(0.01, abs(sum(t["pnl_pct"] for t in losses) / len(losses)) if losses else 0.01)) if wins else 0
    win_rate = len(wins) / n
    return round(win_rate * avg_win_r - (1 - win_rate) * 1.0, 4)


def run_stress(
    bars: List[dict],
    strategy_fn: Callable,
    *,
    strategy_name: str,
    symbol: str,
    segments: List[RegimeSegment] | None = None,
    cfg: BacktestConfig | None = None,
) -> StressReport:
    cfg = cfg or BacktestConfig()
    segs = segments if segments is not None else all_segments(include_known=True,
                                                                bars_for_auto=bars)
    report = StressReport(strategy=strategy_name, symbol=symbol)
    pf_vals: List[float] = []
    dd_vals: List[float] = []
    rets: List[float] = []
    for seg in segs:
        sliced = filter_bars(bars, seg)
        if len(sliced) < 30:
            continue
        rep = run_backtest(sliced, strategy_fn, strategy_name=strategy_name,
                           symbol=symbol, cfg=cfg)
        sr = SegmentReport(
            segment=seg.to_dict(),
            bars_in_segment=len(sliced),
            trades=rep.trades_count,
            win_rate=rep.win_rate,
            profit_factor=rep.profit_factor,
            expectancy_R=_expectancy_R_from_report(rep),
            sharpe=rep.sharpe,
            max_drawdown=rep.max_drawdown,
            total_return=rep.total_return,
        )
        report.segments.append(sr)
        if rep.trades_count >= 3:
            pf_vals.append(rep.profit_factor)
            dd_vals.append(rep.max_drawdown)
            rets.append(rep.total_return)
    if pf_vals:
        passing = sum(1 for p in pf_vals if p > 1.0)
        report.cross_regime_consistency = round(passing / len(pf_vals), 4)
        report.cross_regime_min_pf = round(min(pf_vals), 4)
    if dd_vals:
        report.cross_regime_max_dd = round(min(dd_vals), 4)
    if rets:
        total = sum(rets)
        peak = max(rets, default=0)
        report.single_period_dominance = round(peak / total, 4) if total else 0.0
    return report
