"""Full data pipeline — backfill 180 days of OHLCV + chips for the universe.

Run modes
---------
    python scripts/full_data_pipeline.py                    # default 180d, default universe
    python scripts/full_data_pipeline.py --days 365         # longer history
    python scripts/full_data_pipeline.py --symbols 2330,2317
    python scripts/full_data_pipeline.py --skip-chips       # OHLCV only

Idempotent — uses (stock_id, date) upserts, safe to run repeatedly.

Sources
-------
    OHLCV   : yfinance (.TW + .TWO fallback) — covers full backfill in one call
    Chips   : TWSE T86 institutional CSV — last `chip_days` trading days
    (MOPS fundamentals are wired separately via scripts/mops_collector.py.)

Failure policy
--------------
    Network/parse errors per-symbol are logged but never abort the run.
    Returns a structured report dict for the verifier to consume.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Optional

# repo root + backend on sys.path
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

import httpx  # noqa: E402
import pandas as pd  # noqa: E402
from sqlalchemy import select, func  # noqa: E402
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.models import ChipData, DailyPrice, Stock  # noqa: E402
from app.db.session import async_session_maker, engine  # noqa: E402

log = logging.getLogger("full_data_pipeline")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")


# Production universe — extend as needed. Each tuple: (symbol, display name, market).
UNIVERSE: List[tuple[str, str, str]] = [
    ("2330", "台積電",   "TWSE"),
    ("2317", "鴻海",     "TWSE"),
    ("2454", "聯發科",   "TWSE"),
    ("2303", "聯電",     "TWSE"),
    ("2382", "廣達",     "TWSE"),
    ("2603", "長榮",     "TWSE"),
    ("2308", "台達電",   "TWSE"),
    ("2891", "中信金",   "TWSE"),
    ("2882", "國泰金",   "TWSE"),
    ("2412", "中華電",   "TWSE"),
    ("3008", "大立光",   "TWSE"),
    ("0050", "元大台灣50", "TWSE"),
    ("0056", "元大高股息", "TWSE"),
]


# ─────────────────────────── OHLCV via yfinance ───────────────────────────

def fetch_yahoo_history(symbol: str, days: int) -> pd.DataFrame:
    """Pull `days` calendar days of OHLCV via yfinance. Tries .TW then .TWO."""
    import yfinance as yf

    end = date.today() + timedelta(days=1)
    start = end - timedelta(days=days + 7)  # padding for weekends/holidays

    for suffix in (".TW", ".TWO"):
        ticker = f"{symbol}{suffix}"
        try:
            df = yf.download(
                ticker,
                start=start.isoformat(),
                end=end.isoformat(),
                progress=False,
                auto_adjust=False,
                threads=False,
            )
        except Exception as e:
            log.warning("yfinance %s failed: %s", ticker, e)
            df = pd.DataFrame()
        if df is None or df.empty:
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        })
        df = df.reset_index().rename(columns={"Date": "date"})
        df["symbol"] = symbol
        df["market"] = "TWSE" if suffix == ".TW" else "TPEX"
        df = df[["date", "symbol", "market", "open", "high", "low", "close", "volume"]].dropna()
        if not df.empty:
            return df
    return pd.DataFrame()


# ─────────────────────────── Chips via TWSE T86 ───────────────────────────

@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((httpx.HTTPError,)),
)
async def fetch_twse_chips(client: httpx.AsyncClient, d: date) -> pd.DataFrame:
    """TWSE T86 institutional net-buy for one trading day."""
    settings = get_settings()
    url = f"{settings.twse_base_url}/fund/T86"
    params = {"response": "csv", "date": d.strftime("%Y%m%d"), "selectType": "ALLBUT0999"}
    r = await client.get(url, params=params, timeout=30)
    r.raise_for_status()
    text = r.text
    blocks = [b for b in text.split("\n\n") if "證券代號" in b]
    if not blocks:
        return pd.DataFrame()
    df = pd.read_csv(io.StringIO(blocks[0]), thousands=",")
    df.columns = [str(c).strip('"').strip() for c in df.columns]
    sym_col = next((c for c in df.columns if "證券代號" in c), None)
    if sym_col is None:
        return pd.DataFrame()
    df["symbol"] = df[sym_col].astype(str).str.strip().str.replace('"', "", regex=False)
    fc = next((c for c in df.columns if "外陸資" in c and "買賣超" in c), None) \
        or next((c for c in df.columns if "外資" in c and "買賣超" in c), None)
    ic = next((c for c in df.columns if "投信" in c and "買賣超" in c), None)
    dc = next((c for c in df.columns if "自營商" in c and "買賣超" in c and "合計" in c), None) \
        or next((c for c in df.columns if "自營商" in c and "買賣超" in c), None)
    for src, dst in ((fc, "foreign_buy"), (ic, "investment_buy"), (dc, "dealer_buy")):
        if src:
            df[dst] = pd.to_numeric(df[src].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
        else:
            df[dst] = 0.0
    df["date"] = d
    return df[["date", "symbol", "foreign_buy", "investment_buy", "dealer_buy"]]


def _trading_days_back(n: int) -> List[date]:
    """Approximate trading days — drop weekends. Holidays will simply 404."""
    out = []
    d = date.today()
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out


async def collect_chips(symbols_filter: Optional[set[str]], chip_days: int = 30) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    days = _trading_days_back(chip_days)
    async with httpx.AsyncClient() as cli:
        for d in days:
            try:
                df = await fetch_twse_chips(cli, d)
                if df.empty:
                    continue
                if symbols_filter:
                    df = df[df["symbol"].isin(symbols_filter)]
                if not df.empty:
                    frames.append(df)
                # be polite to TWSE
                await asyncio.sleep(0.4)
            except Exception as e:
                log.warning("chips %s skipped: %s", d, e)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["date", "symbol", "foreign_buy", "investment_buy", "dealer_buy"]
    )


# ─────────────────────────── persistence (idempotent) ───────────────────────────

async def ensure_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def upsert_stocks(session, rows: Iterable[tuple[str, str, str]]) -> dict[str, int]:
    id_by_symbol: dict[str, int] = {}
    for sym, name, market in rows:
        existing = (
            await session.execute(select(Stock).where(Stock.symbol == sym))
        ).scalar_one_or_none()
        if existing is None:
            existing = Stock(symbol=sym, name=name, market=market)
            session.add(existing)
            await session.flush()
        else:
            # keep name fresh
            if name and existing.name != name:
                existing.name = name
        id_by_symbol[sym] = existing.id
    await session.commit()
    return id_by_symbol


async def upsert_prices(session, id_by_symbol: dict[str, int], df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    n = 0
    for _, row in df.iterrows():
        sid = id_by_symbol.get(row["symbol"])
        if sid is None:
            continue
        d = row["date"]
        if hasattr(d, "date"):
            d = d.date()
        existing = (
            await session.execute(
                select(DailyPrice).where(DailyPrice.stock_id == sid, DailyPrice.date == d)
            )
        ).scalar_one_or_none()
        fields = dict(
            open=float(row["open"]), high=float(row["high"]),
            low=float(row["low"]),  close=float(row["close"]),
            volume=int(row.get("volume") or 0),
        )
        if existing is None:
            session.add(DailyPrice(stock_id=sid, date=d, **fields))
        else:
            for k, v in fields.items():
                setattr(existing, k, v)
        n += 1
    await session.commit()
    return n


async def upsert_chips(session, id_by_symbol: dict[str, int], df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    n = 0
    for _, row in df.iterrows():
        sid = id_by_symbol.get(row["symbol"])
        if sid is None:
            continue
        d = row["date"]
        if hasattr(d, "date"):
            d = d.date()
        existing = (
            await session.execute(
                select(ChipData).where(ChipData.stock_id == sid, ChipData.date == d)
            )
        ).scalar_one_or_none()
        fields = dict(
            foreign_buy=float(row.get("foreign_buy") or 0),
            investment_buy=float(row.get("investment_buy") or 0),
            dealer_buy=float(row.get("dealer_buy") or 0),
        )
        if existing is None:
            session.add(ChipData(stock_id=sid, date=d, **fields))
        else:
            for k, v in fields.items():
                setattr(existing, k, v)
        n += 1
    await session.commit()
    return n


# ─────────────────────────── orchestrator ───────────────────────────

async def run_pipeline(
    days: int = 180,
    symbols: Optional[List[str]] = None,
    skip_chips: bool = False,
    chip_days: int = 30,
) -> dict:
    universe = [u for u in UNIVERSE if (symbols is None or u[0] in symbols)]
    sym_filter = {u[0] for u in universe}
    report = {
        "universe": [u[0] for u in universe],
        "days": days,
        "ohlcv_rows": 0,
        "chip_rows": 0,
        "errors": [],
        "started_at": datetime.utcnow().isoformat() + "Z",
    }

    await ensure_tables()

    # 1) Pull yfinance OHLCV — synchronous calls in a thread to avoid event-loop blocking.
    loop = asyncio.get_running_loop()
    frames: List[pd.DataFrame] = []
    for sym, name, market in universe:
        try:
            df = await loop.run_in_executor(None, fetch_yahoo_history, sym, days)
            if df.empty:
                report["errors"].append(f"{sym}: no yfinance data")
                continue
            df["__name__"] = name
            df["__market__"] = market
            frames.append(df)
            log.info("yfinance %s: %d rows", sym, len(df))
        except Exception as e:
            log.exception("yfinance %s failed", sym)
            report["errors"].append(f"{sym}: {e}")

    price_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    # 2) Optional chips backfill
    chip_df = pd.DataFrame()
    if not skip_chips:
        try:
            chip_df = await collect_chips(sym_filter, chip_days=chip_days)
            log.info("chips backfill: %d rows", len(chip_df))
        except Exception as e:
            log.warning("chip backfill failed: %s", e)
            report["errors"].append(f"chips: {e}")

    # 3) Persist
    async with async_session_maker() as session:
        id_map = await upsert_stocks(session, universe)
        report["ohlcv_rows"] = await upsert_prices(session, id_map, price_df)
        report["chip_rows"] = await upsert_chips(session, id_map, chip_df)

        # quick coverage stats
        per_symbol = {}
        for sym, sid in id_map.items():
            cnt = (
                await session.execute(
                    select(func.count(DailyPrice.id)).where(DailyPrice.stock_id == sid)
                )
            ).scalar() or 0
            per_symbol[sym] = int(cnt)
        report["coverage"] = per_symbol

    report["finished_at"] = datetime.utcnow().isoformat() + "Z"
    log.info("pipeline report: %s", report)
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=180, help="OHLCV backfill window (calendar days)")
    ap.add_argument("--chip-days", type=int, default=30, help="Trading days of chips to fetch")
    ap.add_argument("--symbols", help="Comma-separated subset, e.g. 2330,2317")
    ap.add_argument("--skip-chips", action="store_true")
    args = ap.parse_args()
    syms = [s.strip() for s in args.symbols.split(",")] if args.symbols else None
    asyncio.run(run_pipeline(days=args.days, symbols=syms,
                             skip_chips=args.skip_chips, chip_days=args.chip_days))


if __name__ == "__main__":
    main()
