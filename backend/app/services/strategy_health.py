"""Strategy health — wraps edge_tracking stats with the auto-disable rule.

Auto-disable triggers (any one of these):
  * win_rate     < 0.45    over a 90-day window
  * expectancy   < -0.20 R
  * max consecutive loss >= 6 in last 30 days

Disabled setups are excluded from /scanner/scan results unless the caller
passes ?include_disabled=true (admin tool).

These thresholds are intentionally permissive — a healthy LONG breakout
strategy in any decent market should easily clear them.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.edge_tracking_service import setup_stats, WINRATE_MIN_SAMPLES


WIN_RATE_FLOOR = 0.45
EXPECTANCY_FLOOR = -0.20
MAX_CONSEC_LOSS_CAP = 6


async def health_report(session: AsyncSession) -> dict:
    """Return {setup: {is_healthy, reason, win_rate, expectancy, ...}}."""
    stats = await setup_stats(session)
    out: dict[str, dict] = {}
    for setup, s in stats.items():
        reason = ""
        is_healthy = True
        if s.sample_size >= WINRATE_MIN_SAMPLES:
            if s.win_rate < WIN_RATE_FLOOR:
                is_healthy = False
                reason = f"win_rate {s.win_rate:.0%} < {WIN_RATE_FLOOR:.0%}"
            elif s.expectancy < EXPECTANCY_FLOOR:
                is_healthy = False
                reason = f"expectancy {s.expectancy:.2f}R < {EXPECTANCY_FLOOR}R"
            elif s.max_consecutive_loss >= MAX_CONSEC_LOSS_CAP:
                is_healthy = False
                reason = f"max consec loss {s.max_consecutive_loss} >= {MAX_CONSEC_LOSS_CAP}"
        else:
            reason = "insufficient_history"
        d = s.to_dict()
        d["is_healthy"] = is_healthy
        d["reason"] = reason
        out[setup] = d
    return out


async def disabled_setups(session: AsyncSession) -> set[str]:
    rep = await health_report(session)
    return {k for k, v in rep.items() if not v["is_healthy"]}
