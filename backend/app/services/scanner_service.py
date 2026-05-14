"""Strong-stock scanner — runs the trade-plan engine across the whole universe
and ranks results by *real* historical edge, not a heuristic.

Ranking (in order of priority):
    rank = expectancy_R × frequency × current_confidence

Where:
    expectancy_R    = win_rate * avg_win_R - (1 - win_rate) * avg_loss_R
                       (from edge_signals table over 90 days)
    frequency       = signals in last 30d / 30  (capped at 1)
    confidence      = current plan's confidence  (0..1)

When a setup has fewer than WINRATE_MIN_SAMPLES evaluated signals, we fall
back to a small heuristic prior so the scanner still works on day 1.

Disabled setups (auto-disable from strategy_health) are excluded by default.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChipData, DailyPrice, Stock
from app.edge import edge_decay as _decay
from app.services.edge_tracking_service import (
    SetupStats, WINRATE_MIN_SAMPLES, persist_signal, setup_stats,
)
from app.services.strategy_health import disabled_setups
from app.services.trade_plan_engine import build_plan
from app.strategy_registry.ranker import rank_all


MIN_BARS = 60


def _ret_pct(curr: float, prev: float) -> float:
    return 0.0 if not prev else (curr / prev - 1.0) * 100.0


def _per_symbol_metrics(bars: list[dict]) -> dict:
    """Extract per-symbol short-term return / volume / gap metrics from bars
    (already loaded for the trade-plan engine)."""
    if not bars:
        return {}
    last = bars[-1]
    prev = bars[-2] if len(bars) >= 2 else last
    d5_anchor = bars[-6] if len(bars) >= 6 else bars[0]
    d20_anchor = bars[-21] if len(bars) >= 21 else bars[0]
    # 20-bar avg vol (excluding today)
    win = bars[-21:-1] if len(bars) >= 21 else bars[:-1]
    avg_vol = sum(b["volume"] for b in win) / max(1, len(win))
    return {
        "as_of": last["date"],
        "last": float(last["close"]),
        "ret_1d": round(_ret_pct(last["close"], prev["close"]), 2),
        "ret_5d": round(_ret_pct(last["close"], d5_anchor["close"]), 2),
        "ret_20d": round(_ret_pct(last["close"], d20_anchor["close"]), 2),
        "gap_pct": round(_ret_pct(last["open"], prev["close"]), 2),
        "rel_volume": round(last["volume"] / avg_vol, 2) if avg_vol > 0 else 1.0,
    }


def _aggregate_market_context(
    per_symbol: dict[str, dict],
    sectors: dict[str, str],
) -> dict:
    """Build market-wide context: equal-weighted index return as 'market',
    sector ranking, and the latest as_of timestamp across the universe.

    This proxy is more robust than a single TAIEX feed because it uses the
    *same* data already loaded for the scan — no extra fetch, no timezone
    skew, no stale ticker."""
    if not per_symbol:
        return {"as_of": None, "market_5d": 0.0, "market_20d": 0.0, "sectors": {}, "universe_size": 0}

    rets_5 = [m["ret_5d"] for m in per_symbol.values()]
    rets_20 = [m["ret_20d"] for m in per_symbol.values()]
    market_5 = sum(rets_5) / len(rets_5)
    market_20 = sum(rets_20) / len(rets_20)
    as_of = max(m["as_of"] for m in per_symbol.values())

    # Sector aggregation
    sec_buckets: dict[str, list[float]] = {}
    for sym, m in per_symbol.items():
        sec = sectors.get(sym) or "其他"
        sec_buckets.setdefault(sec, []).append(m["ret_5d"])
    sec_rows = []
    for sec, rs in sec_buckets.items():
        sec_rows.append({
            "sector": sec,
            "ret_5d": round(sum(rs) / len(rs), 2),
            "count": len(rs),
        })
    sec_rows.sort(key=lambda x: x["ret_5d"], reverse=True)
    sectors_out = {row["sector"]: {**row, "rank": i + 1, "total": len(sec_rows)}
                   for i, row in enumerate(sec_rows)}
    return {
        "as_of": as_of,
        "market_5d": round(market_5, 2),
        "market_20d": round(market_20, 2),
        "sectors": sectors_out,
        "universe_size": len(per_symbol),
    }


def _edge_score(plan_dict: dict) -> float:
    """Heuristic prior used as the ranking signal until each setup has
    >= WINRATE_MIN_SAMPLES evaluated trades. Kept for transparency."""
    if plan_dict.get("bias") != "LONG":
        return 0.0
    conf = float(plan_dict.get("confidence") or 0.0)
    rr = float(plan_dict.get("risk_reward") or 0.0)
    ind = plan_dict.get("indicators") or {}
    chip = plan_dict.get("chip") or {}
    score = conf * 60.0
    score += min(rr, 4.0) * 5.0
    if ind.get("breakout_20"):
        score += 8
    vs = float(ind.get("volume_spike") or 0)
    score += max(0.0, min(8.0, (vs - 1.0) * 8.0))
    fs = int(chip.get("foreign_streak") or 0)
    score += min(5, fs) * 1.5
    if ind.get("ma_alignment"):
        score += 6
    return round(score, 2)


def _rank(plan_dict: dict, stats: SetupStats | None) -> tuple[float, dict]:
    """Compute new ranking score: expectancy × frequency × confidence.

    Returns (rank, breakdown_dict). When stats is None or sample size is too
    small, fall back to (edge_score / 100) so the scanner still ranks usefully
    on day 1.
    """
    setup = plan_dict.get("setup")
    conf = float(plan_dict.get("confidence") or 0.0)
    if plan_dict.get("bias") != "LONG" or not setup:
        return 0.0, {"reason": "not_long"}
    edge_prior = _edge_score(plan_dict) / 100.0
    if stats is None or stats.sample_size < WINRATE_MIN_SAMPLES:
        # day-1 fallback — heuristic prior weighted by current confidence
        rank = edge_prior * conf * 100.0
        return round(rank, 4), {
            "mode": "prior",
            "expectancy": None,
            "frequency": None,
            "confidence": round(conf, 4),
            "sample_size": stats.sample_size if stats else 0,
        }
    expectancy = stats.expectancy
    frequency = min(1.0, stats.last_30d_count / 30.0)
    rank = expectancy * max(0.05, frequency) * conf * 100.0
    return round(rank, 4), {
        "mode": "validated",
        "expectancy": round(expectancy, 4),
        "frequency": round(frequency, 4),
        "confidence": round(conf, 4),
        "sample_size": stats.sample_size,
    }


async def _bars_for(session: AsyncSession, stock_id: int, limit: int = 240) -> tuple[list[dict], list[dict]]:
    rows = (
        await session.execute(
            select(DailyPrice)
            .where(DailyPrice.stock_id == stock_id)
            .order_by(DailyPrice.date.asc())
            .limit(limit)
        )
    ).scalars().all()
    bars = [
        {"date": str(r.date), "open": r.open, "high": r.high,
         "low": r.low, "close": r.close, "volume": r.volume}
        for r in rows
    ]
    chips = (
        await session.execute(
            select(ChipData)
            .where(ChipData.stock_id == stock_id)
            .order_by(ChipData.date.asc())
            .limit(60)
        )
    ).scalars().all()
    chip_records = [
        {
            "foreign_buy": float(c.foreign_buy or 0),
            "investment_buy": float(c.investment_buy or 0),
            "dealer_buy": float(c.dealer_buy or 0),
            "volume": int(rows[i].volume) if i < len(rows) else 0,
        }
        for i, c in enumerate(chips)
    ]
    return bars, chip_records


async def scan_universe(
    session: AsyncSession,
    bias_filter: Optional[str] = None,        # "LONG", "SHORT", "NO_TRADE", None=all
    min_rr: Optional[float] = None,
    min_confidence: Optional[float] = None,
    setup_filter: Optional[str] = None,
    min_winrate: Optional[float] = None,      # require this setup's hist winrate
    include_disabled: bool = False,
    persist: bool = False,                    # write LONG signals to edge_signals
    limit: int = 60,
) -> dict:
    """Build a trade plan for every stock with sufficient data, rank by edge."""
    stats_map = await setup_stats(session)
    disabled = set() if include_disabled else await disabled_setups(session)

    # Strategy ranking — gives us live edge + production status per setup.
    rankings = await rank_all(session)
    rank_by_setup = {r.strategy: r for r in rankings}
    decay_map = await _decay.decay_scores(session)
    # Disabled-by-ranker takes precedence over health-disabled
    if not include_disabled:
        from app.strategy_registry.ranker import disabled_setups as _ds
        disabled = disabled | _ds(rankings)

    stocks = (await session.execute(select(Stock))).scalars().all()
    sector_map = {st.symbol: (st.sector or "其他") for st in stocks}

    # First pass: load bars + compute per-symbol metrics so we can build
    # market context (RS vs market, sector rank) before the plan loop.
    loaded: dict[str, tuple[list[dict], list[dict]]] = {}
    per_metrics: dict[str, dict] = {}
    for st in stocks:
        bars, chip_records = await _bars_for(session, st.id)
        if len(bars) < MIN_BARS:
            continue
        loaded[st.symbol] = (bars, chip_records)
        per_metrics[st.symbol] = _per_symbol_metrics(bars)

    market_ctx = _aggregate_market_context(per_metrics, sector_map)

    rows: List[dict] = []
    for st in stocks:
        if st.symbol not in loaded:
            continue
        bars, chip_records = loaded[st.symbol]
        plan_obj = build_plan(
            symbol=st.symbol,
            closes=[b["close"] for b in bars],
            highs=[b["high"] for b in bars],
            lows=[b["low"] for b in bars],
            volumes=[b["volume"] for b in bars],
            chip_records=chip_records,
            # Don't fake fundamentals — keep confidence honest until MOPS is wired.
            fundamental_score=None,
        )
        plan = plan_obj.to_dict()
        plan["name"] = st.name
        plan["market"] = st.market
        plan["edge"] = _edge_score(plan)

        # ── trader context: RS vs equal-weighted market + sector rank ──
        m = per_metrics.get(st.symbol) or {}
        plan["as_of"] = m.get("as_of")
        plan["ret_1d"] = m.get("ret_1d")
        plan["ret_5d"] = m.get("ret_5d")
        plan["ret_20d"] = m.get("ret_20d")
        plan["gap_pct"] = m.get("gap_pct")
        plan["rel_volume"] = m.get("rel_volume")
        if m:
            plan["rs_5d"] = round((m.get("ret_5d") or 0) - market_ctx["market_5d"], 2)
            plan["rs_20d"] = round((m.get("ret_20d") or 0) - market_ctx["market_20d"], 2)
        sec_name = sector_map.get(st.symbol, "其他")
        sec_info = market_ctx["sectors"].get(sec_name) or {}
        plan["sector"] = sec_name
        plan["sector_rank"] = sec_info.get("rank")
        plan["sector_count"] = sec_info.get("total")
        plan["sector_ret_5d"] = sec_info.get("ret_5d")

        # Attach setup stats so the UI can show win-rate / max-loss-streak.
        setup = plan.get("setup")
        sstats = stats_map.get(setup) if setup else None
        plan["stats"] = sstats.to_dict() if sstats else None

        rank, breakdown = _rank(plan, sstats)
        plan["rank"] = rank
        plan["rank_breakdown"] = breakdown

        # Adaptive Score — live_edge_weighted_score:
        #   setup_live_expectancy * regime_confidence * strategy_rank * chip_strength
        setup_now = plan.get("setup") or ""
        live_exp = (sstats.expectancy if sstats else 0.0)
        rank_obj = rank_by_setup.get(setup_now)
        strat_rank = rank_obj.rank_score if rank_obj else 0.0
        production_status = rank_obj.production_status if rank_obj else "UNKNOWN"
        regime_block = plan.get("regime") or {}
        adx = regime_block.get("adx") or 0
        regime_conf = min(1.0, max(0.0, adx / 40.0)) if adx else 0.3
        chip = plan.get("chip") or {}
        chip_strength = min(1.0, max(0.0,
            0.5 + 0.25 * (chip.get("foreign_invest_alignment") or 0.0) +
            0.10 * min(5, int(chip.get("foreign_streak") or 0)) / 5.0,
        ))
        adaptive = round(
            max(0.0, live_exp) * regime_conf * max(0.05, strat_rank) * chip_strength * 100,
            4,
        )
        plan["adaptive_score"] = adaptive
        plan["adaptive_breakdown"] = {
            "live_expectancy_R": round(live_exp, 4),
            "regime_confidence": round(regime_conf, 4),
            "strategy_rank": round(strat_rank, 4),
            "chip_strength": round(chip_strength, 4),
            "production_status": production_status,
            "decay_label": (decay_map.get(setup_now, {}) or {}).get("label"),
        }
        plan["production_status"] = production_status

        # Signal Validation Layer — every signal must self-report its
        # validation status. UI / brief use this to decide whether to surface
        # the signal as actionable vs research-only.
        from app.services.edge_tracking_service import WINRATE_MIN_SAMPLES
        if plan.get("bias") == "LONG":
            if sstats and sstats.sample_size >= WINRATE_MIN_SAMPLES:
                plan["validation"] = {
                    "status": "validated",
                    "win_rate": sstats.win_rate,
                    "profit_factor": round(
                        max(0.01, abs(sstats.expectancy + 1)) /
                        max(0.01, abs(min(0, sstats.expectancy)) + 1), 3,
                    ),
                    "max_drawdown_r": sstats.max_consecutive_loss * -1.0,
                    "expectancy_r": sstats.expectancy,
                    "sample_size": sstats.sample_size,
                }
            else:
                plan["validation"] = {
                    "status": "unvalidated",
                    "reason": f"sample_size<{WINRATE_MIN_SAMPLES}",
                    "sample_size": sstats.sample_size if sstats else 0,
                }
        else:
            plan["validation"] = {"status": "n/a"}

        rows.append(plan)

    # Filters
    out = rows
    if bias_filter:
        out = [r for r in out if r.get("bias") == bias_filter]
    if setup_filter:
        out = [r for r in out if r.get("setup") == setup_filter]
    if min_rr is not None:
        out = [r for r in out if (r.get("risk_reward") or 0) >= min_rr]
    if min_confidence is not None:
        out = [r for r in out if (r.get("confidence") or 0) >= min_confidence]
    if min_winrate is not None:
        out = [
            r for r in out
            if r.get("stats") and r["stats"].get("win_rate", 0) >= min_winrate
        ]
    if not include_disabled:
        out = [r for r in out if r.get("setup") not in disabled]

    # Adaptive ranking — adaptive_score is the highest authority; rank +
    # heuristic edge are tie-breakers.
    out.sort(
        key=lambda r: (r.get("adaptive_score", 0), r.get("rank", 0), r.get("edge", 0)),
        reverse=True,
    )

    # Optional: persist today's LONG signals so we can score them in 7 days
    if persist:
        from app.services.edge_tracking_service import persist_signal as _persist
        # Build symbol->sector map from Stock rows so the persisted signal
        # carries the sector tag (used in by_sector breakdowns later).
        stock_sectors = {st.symbol: (st.sector or "其他") for st in stocks}
        regime_label = None
        for r in out:
            if r.get("bias") != "LONG":
                continue
            reg = r.get("regime") or {}
            regime_label = reg.get("label")
            await _persist(
                session,
                symbol=r["symbol"],
                setup=r["setup"],
                plan=r,
                regime=regime_label,
                sector=stock_sectors.get(r["symbol"]),
            )

    return {
        "scanned": len(rows),
        "matched": len(out),
        "disabled_setups": sorted(disabled),
        "as_of": market_ctx.get("as_of"),
        "market_context": market_ctx,
        "items": out[:limit],
    }


# ─────────────────────────── Movers ────────────────────────────

def _pct(a: float, b: float) -> float:
    return 0.0 if not b else (a / b - 1.0) * 100.0


async def scan_movers(session: AsyncSession, limit: int = 30) -> dict:
    """Compute price/volume momentum metrics across the universe.

    Returns sorted lists for several categories so the dashboard can show
    'today's strongest moves' without iterating itself.
    """
    stocks = (await session.execute(select(Stock))).scalars().all()
    rows: List[dict] = []
    for st in stocks:
        bars = (
            await session.execute(
                select(DailyPrice)
                .where(DailyPrice.stock_id == st.id)
                .order_by(DailyPrice.date.desc())
                .limit(25)
            )
        ).scalars().all()
        if len(bars) < 6:
            continue
        bars = list(reversed(bars))  # ascending
        last = bars[-1]
        prev = bars[-2]
        gap_pct = _pct(last.open, prev.close)
        d1_pct = _pct(last.close, prev.close)
        d5 = bars[-6] if len(bars) >= 6 else bars[0]
        d20 = bars[0]
        d5_pct = _pct(last.close, d5.close)
        d20_pct = _pct(last.close, d20.close)
        avg_vol = sum(b.volume for b in bars[-21:-1]) / max(1, len(bars[-21:-1]))
        vol_ratio = (last.volume / avg_vol) if avg_vol > 0 else 1.0
        # 20-bar high
        high_20 = max(b.high for b in bars[-21:])
        is_breakout = last.close >= high_20 * 0.999
        rows.append({
            "symbol": st.symbol,
            "name": st.name,
            "last": round(float(last.close), 2),
            "open": round(float(last.open), 2),
            "gap_pct": round(gap_pct, 2),
            "d1_pct": round(d1_pct, 2),
            "d5_pct": round(d5_pct, 2),
            "d20_pct": round(d20_pct, 2),
            "volume": int(last.volume),
            "volume_ratio": round(vol_ratio, 2),
            "breakout_20": bool(is_breakout),
            "date": str(last.date),
        })

    by = lambda key, desc=True: sorted(rows, key=lambda r: r.get(key, 0), reverse=desc)[:limit]
    return {
        "scanned": len(rows),
        "gainers":     by("d1_pct", desc=True),
        "losers":      by("d1_pct", desc=False),
        "gap_ups":     [r for r in by("gap_pct") if r["gap_pct"] > 0][:limit],
        "volume_spikes": by("volume_ratio"),
        "breakouts":   [r for r in rows if r["breakout_20"]][:limit],
        "momentum_5d": by("d5_pct"),
        "momentum_20d": by("d20_pct"),
    }


# ─────────────────────────── Sectors ────────────────────────────

async def scan_sectors(session: AsyncSession) -> dict:
    """Group symbols by sector and summarize 1d / 5d performance."""
    stocks = (await session.execute(select(Stock))).scalars().all()
    by_sector: dict[str, list[dict]] = {}
    for st in stocks:
        sec = st.sector or "未分類"
        bars = (
            await session.execute(
                select(DailyPrice)
                .where(DailyPrice.stock_id == st.id)
                .order_by(DailyPrice.date.desc())
                .limit(6)
            )
        ).scalars().all()
        if len(bars) < 2:
            continue
        bars = list(reversed(bars))
        last = bars[-1]
        prev = bars[-2]
        d5 = bars[0]
        by_sector.setdefault(sec, []).append({
            "symbol": st.symbol,
            "name": st.name,
            "last": round(float(last.close), 2),
            "d1_pct": round(_pct(last.close, prev.close), 2),
            "d5_pct": round(_pct(last.close, d5.close), 2),
        })

    sectors = []
    for sec, members in by_sector.items():
        if not members:
            continue
        avg_d1 = sum(m["d1_pct"] for m in members) / len(members)
        avg_d5 = sum(m["d5_pct"] for m in members) / len(members)
        leaders = sorted(members, key=lambda m: m["d1_pct"], reverse=True)[:3]
        sectors.append({
            "sector": sec,
            "count": len(members),
            "avg_d1_pct": round(avg_d1, 2),
            "avg_d5_pct": round(avg_d5, 2),
            "leaders": leaders,
        })
    sectors.sort(key=lambda s: s["avg_d5_pct"], reverse=True)
    return {"sectors": sectors}
