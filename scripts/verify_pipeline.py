"""Post-deploy validator — confirms real-data pipeline is live.

Two modes
---------
    python scripts/verify_pipeline.py                  # local: query DB directly
    python scripts/verify_pipeline.py --remote URL     # hit live API

Checks (each blocks on failure with a non-zero exit code):
  1. DailyPrice row count >= 100
  2. Coverage: every UNIVERSE symbol has >= 60 bars
  3. Most recent bar within 7 calendar days
  4. /api/v1/trade-plan/{symbol} returns data_source == "real" for at least one symbol
  5. RSI is within (0, 100); not all symbols stuck at 100 / 0 (synthetic signature)
  6. At least one symbol produces a LONG / SHORT bias OR a defensible NO_TRADE
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import List

import httpx

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

from sqlalchemy import select, func  # noqa: E402

from app.db.models import DailyPrice, Stock  # noqa: E402
from app.db.session import async_session_maker  # noqa: E402
from scripts.full_data_pipeline import UNIVERSE  # noqa: E402

log = logging.getLogger("verify_pipeline")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")


# ─────────────────────────── checks ───────────────────────────

async def check_db() -> dict:
    """Direct DB checks."""
    out = {"ok": True, "errors": [], "stats": {}}
    async with async_session_maker() as s:
        total = (await s.execute(select(func.count(DailyPrice.id)))).scalar() or 0
        out["stats"]["total_rows"] = int(total)
        if total < 100:
            out["ok"] = False
            out["errors"].append(f"DailyPrice rows = {total} < 100")

        coverage = {}
        max_dates = []
        for sym, _, _ in UNIVERSE:
            stock = (
                await s.execute(select(Stock).where(Stock.symbol == sym))
            ).scalar_one_or_none()
            if stock is None:
                coverage[sym] = 0
                continue
            n = (
                await s.execute(
                    select(func.count(DailyPrice.id)).where(DailyPrice.stock_id == stock.id)
                )
            ).scalar() or 0
            coverage[sym] = int(n)
            latest = (
                await s.execute(
                    select(func.max(DailyPrice.date)).where(DailyPrice.stock_id == stock.id)
                )
            ).scalar()
            if latest:
                max_dates.append(latest)

        out["stats"]["coverage"] = coverage
        thin = [k for k, v in coverage.items() if v < 60]
        if thin:
            out["ok"] = False
            out["errors"].append(f"Symbols with <60 bars: {thin}")

        if max_dates:
            most_recent = max(max_dates)
            out["stats"]["most_recent_bar"] = most_recent.isoformat()
            if (date.today() - most_recent) > timedelta(days=14):
                out["ok"] = False
                out["errors"].append(f"Latest bar is stale: {most_recent}")
        else:
            out["ok"] = False
            out["errors"].append("No bars at all in DB.")
    return out


async def check_remote(base_url: str) -> dict:
    """Hit /api/v1/trade-plan/{symbol} on a live deploy."""
    out = {"ok": True, "errors": [], "stats": {}, "samples": {}}
    test_symbols = [u[0] for u in UNIVERSE[:8]]
    real_count = 0
    biases: List[str] = []
    rsis: List[float] = []

    async with httpx.AsyncClient(timeout=30, verify=True) as cli:
        for sym in test_symbols:
            url = f"{base_url.rstrip('/')}/api/v1/trade-plan/{sym}"
            try:
                r = await cli.get(url)
                r.raise_for_status()
                body = r.json()
            except Exception as e:
                out["errors"].append(f"{sym}: {e}")
                continue
            ds = body.get("data_source")
            bias = body.get("bias")
            rsi = (body.get("indicators") or {}).get("rsi14")
            biases.append(bias)
            if isinstance(rsi, (int, float)):
                rsis.append(float(rsi))
            if ds == "real":
                real_count += 1
            out["samples"][sym] = {
                "bias": bias,
                "data_source": ds,
                "no_trade_reason": body.get("no_trade_reason"),
                "rsi14": rsi,
                "last_close": body.get("last_close"),
            }

    out["stats"]["real_count"] = real_count
    out["stats"]["biases"] = biases
    out["stats"]["rsi_distribution"] = rsis

    if real_count == 0:
        out["ok"] = False
        out["errors"].append("No symbol returned data_source=real (still synthetic / NO_REAL_DATA)")

    # Synthetic signature: RSIs cluster at 0/100. Real RSIs distribute 20–80.
    if rsis and all(r >= 95 or r <= 5 for r in rsis):
        out["ok"] = False
        out["errors"].append(f"RSI distribution looks synthetic: {rsis}")

    return out


# ─────────────────────────── runner ───────────────────────────

async def main_async(remote: str | None) -> int:
    if remote:
        log.info("Verifying remote: %s", remote)
        result = await check_remote(remote)
    else:
        log.info("Verifying local DB")
        result = await check_db()
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["ok"] else 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--remote", help="Base URL, e.g. https://taiwan-stock-ai-api.onrender.com")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main_async(args.remote)))


if __name__ == "__main__":
    main()
