"""Daily market data collector.

Pulls TWSE daily quotes & institutional net buy; falls back to yfinance when
TWSE is unreachable. Persists to Postgres/SQLite via SQLAlchemy models.

Usage
-----
    python scripts/data_collector.py                 # today
    python scripts/data_collector.py --date 20260423 # specific YYYYMMDD
    python scripts/data_collector.py --symbols 2330,2317
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

# repo root on sys.path so `from backend.app...` & top-level modules both work
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

import httpx  # noqa: E402
import pandas as pd  # noqa: E402
from sqlalchemy import select  # noqa: E402
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.models import ChipData, DailyPrice, Stock  # noqa: E402
from app.db.session import async_session_maker, engine  # noqa: E402
from app.db.base import Base  # noqa: E402

log = logging.getLogger("data_collector")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")

_DEFAULT_SYMBOLS = [
    ("2330", "台積電"), ("2317", "鴻海"), ("2454", "聯發科"),
    ("2303", "聯電"), ("2881", "富邦金"), ("2882", "國泰金"),
    ("3008", "大立光"), ("1301", "台塑"), ("2412", "中華電"),
    ("2603", "長榮"), ("1216", "統一"), ("2891", "中信金"),
    ("2308", "台達電"), ("2002", "中鋼"), ("2207", "和泰車"),
]


# ─────────────────────────── TWSE ───────────────────────────

@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((httpx.HTTPError,)),
)
async def fetch_twse_daily(d: date) -> pd.DataFrame:
    """TWSE daily quote CSV for all listed stocks on `d`."""
    settings = get_settings()
    url = f"{settings.twse_base_url}/exchangeReport/MI_INDEX"
    params = {"response": "csv", "date": d.strftime("%Y%m%d"), "type": "ALL"}
    async with httpx.AsyncClient(timeout=30) as cli:
        r = await cli.get(url, params=params)
        r.raise_for_status()
        text = r.text
    blocks = [b for b in text.split("\n\n") if "證券代號" in b and "收盤價" in b]
    if not blocks:
        raise RuntimeError(f"TWSE: no quote block for {d}")
    df = pd.read_csv(io.StringIO(blocks[0]), thousands=",")
    df.columns = [str(c).strip('"').strip() for c in df.columns]
    sym_col = next((c for c in df.columns if "證券代號" in c), None)
    name_col = next((c for c in df.columns if "證券名稱" in c), None)
    if sym_col is None:
        raise RuntimeError("TWSE: missing symbol column")
    df["symbol"] = df[sym_col].astype(str).str.strip().str.replace('"', "", regex=False)
    df["name"] = df[name_col].astype(str).str.strip() if name_col else df["symbol"]
    for src, dst in (("開盤價", "open"), ("最高價", "high"), ("最低價", "low"), ("收盤價", "close"), ("成交股數", "volume")):
        col = next((c for c in df.columns if src in c), None)
        if col is None:
            continue
        df[dst] = pd.to_numeric(df[col].astype(str).str.replace(",", ""), errors="coerce")
    return df[["symbol", "name", "open", "high", "low", "close", "volume"]].dropna()


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((httpx.HTTPError,)),
)
async def fetch_twse_institutional(d: date) -> pd.DataFrame:
    """Three major institutional net buy, per stock, for `d`."""
    settings = get_settings()
    url = f"{settings.twse_base_url}/fund/T86"
    params = {"response": "csv", "date": d.strftime("%Y%m%d"), "selectType": "ALLBUT0999"}
    async with httpx.AsyncClient(timeout=30) as cli:
        r = await cli.get(url, params=params)
        r.raise_for_status()
        text = r.text
    blocks = [b for b in text.split("\n\n") if "證券代號" in b]
    if not blocks:
        raise RuntimeError(f"TWSE fund: no block for {d}")
    df = pd.read_csv(io.StringIO(blocks[0]), thousands=",")
    df.columns = [str(c).strip('"').strip() for c in df.columns]
    sym_col = next((c for c in df.columns if "證券代號" in c), None)
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
    return df[["symbol", "foreign_buy", "investment_buy", "dealer_buy"]]


# ─────────────────────────── yfinance fallback ───────────────────────────

def fetch_yahoo(symbol: str, start: date, end: date) -> pd.DataFrame:
    """Fetch a single Taiwan stock via yfinance (sync)."""
    import yfinance as yf

    ticker = f"{symbol}.TW"
    df = yf.download(ticker, start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
                     progress=False, auto_adjust=False)
    if df.empty:
        ticker = f"{symbol}.TWO"
        df = yf.download(ticker, start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
                         progress=False, auto_adjust=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={"Open": "open", "High": "high", "Low": "low",
                            "Close": "close", "Volume": "volume"})
    df = df.reset_index().rename(columns={"Date": "date"})
    df["symbol"] = symbol
    return df[["date", "symbol", "open", "high", "low", "close", "volume"]]


# ─────────────────────────── persistence ───────────────────────────

async def ensure_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def upsert_stocks(session, rows: Iterable[dict]) -> dict[str, int]:
    """Insert missing stocks, return {symbol: id}."""
    id_by_symbol: dict[str, int] = {}
    for r in rows:
        sym = r["symbol"]
        res = await session.execute(select(Stock).where(Stock.symbol == sym))
        existing = res.scalar_one_or_none()
        if existing is None:
            existing = Stock(symbol=sym, name=r.get("name") or sym, market=r.get("market", "TWSE"))
            session.add(existing)
            await session.flush()
        id_by_symbol[sym] = existing.id
    return id_by_symbol


async def upsert_prices(session, d: date, id_by_symbol: dict[str, int], df: pd.DataFrame) -> int:
    n = 0
    for _, row in df.iterrows():
        sid = id_by_symbol.get(row["symbol"])
        if sid is None:
            continue
        res = await session.execute(
            select(DailyPrice).where(DailyPrice.stock_id == sid, DailyPrice.date == d)
        )
        obj = res.scalar_one_or_none()
        fields = dict(
            open=float(row["open"]), high=float(row["high"]), low=float(row["low"]),
            close=float(row["close"]), volume=int(row.get("volume") or 0),
        )
        if obj is None:
            session.add(DailyPrice(stock_id=sid, date=d, **fields))
        else:
            for k, v in fields.items():
                setattr(obj, k, v)
        n += 1
    return n


async def upsert_chips(session, d: date, id_by_symbol: dict[str, int], df: pd.DataFrame) -> int:
    n = 0
    for _, row in df.iterrows():
        sid = id_by_symbol.get(row["symbol"])
        if sid is None:
            continue
        res = await session.execute(
            select(ChipData).where(ChipData.stock_id == sid, ChipData.date == d)
        )
        obj = res.scalar_one_or_none()
        fields = dict(
            foreign_buy=float(row.get("foreign_buy") or 0),
            investment_buy=float(row.get("investment_buy") or 0),
            dealer_buy=float(row.get("dealer_buy") or 0),
        )
        if obj is None:
            session.add(ChipData(stock_id=sid, date=d, **fields))
        else:
            for k, v in fields.items():
                setattr(obj, k, v)
        n += 1
    return n


# ─────────────────────────── orchestrator ───────────────────────────

async def collect(target_date: date, symbols: Optional[List[str]] = None) -> dict:
    await ensure_tables()
    report = {"date": target_date.isoformat(), "prices": 0, "chips": 0, "source": "twse"}

    price_df: pd.DataFrame
    chip_df: pd.DataFrame
    try:
        price_df = await fetch_twse_daily(target_date)
        chip_df = await fetch_twse_institutional(target_date)
    except Exception as e:  # TWSE down or holiday
        log.warning("TWSE unavailable (%s); falling back to yfinance", e)
        report["source"] = "yfinance"
        sym_pool = symbols or [s for s, _ in _DEFAULT_SYMBOLS]
        frames = []
        for s in sym_pool:
            try:
                df = fetch_yahoo(s, target_date - timedelta(days=5), target_date)
                if not df.empty:
                    frames.append(df.tail(1))
            except Exception as ex:
                log.warning("yfinance %s failed: %s", s, ex)
        price_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
            columns=["symbol", "open", "high", "low", "close", "volume"]
        )
        if not price_df.empty:
            price_df["name"] = price_df["symbol"].map(dict(_DEFAULT_SYMBOLS))
            price_df = price_df[["symbol", "name", "open", "high", "low", "close", "volume"]]
        chip_df = pd.DataFrame(columns=["symbol", "foreign_buy", "investment_buy", "dealer_buy"])

    if symbols:
        price_df = price_df[price_df["symbol"].isin(symbols)]
        chip_df = chip_df[chip_df["symbol"].isin(symbols)]

    async with async_session_maker() as session:
        base_rows = [{"symbol": r["symbol"], "name": r.get("name")} for _, r in price_df.iterrows()]
        id_map = await upsert_stocks(session, base_rows)
        report["prices"] = await upsert_prices(session, target_date, id_map, price_df)
        if not chip_df.empty:
            report["chips"] = await upsert_chips(session, target_date, id_map, chip_df)
        await session.commit()

    log.info("collector done: %s", report)
    return report


def _parse_date(s: Optional[str]) -> date:
    if not s:
        return date.today()
    return datetime.strptime(s, "%Y%m%d").date()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYYMMDD, default today")
    ap.add_argument("--symbols", help="comma-separated e.g. 2330,2317")
    args = ap.parse_args()
    symbols = [s.strip() for s in args.symbols.split(",")] if args.symbols else None
    asyncio.run(collect(_parse_date(args.date), symbols))


if __name__ == "__main__":
    main()
