"""TWSE 三大法人 chip data collector.

Pulls institutional buy/sell data from TWSE's public T86 endpoint and
upserts into ChipData. The endpoint is free and stable; we go through it
politely (sleep between calls, retry on 429).
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import Optional

import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.datahub.collectors.base import BaseCollector, CollectorResult
from app.db.models import ChipData, Stock
from app.db.session import async_session_maker

TWSE_T86_URL = "https://www.twse.com.tw/rwd/zh/fund/T86"


def _to_float(v: str | None) -> float:
    if not v or v in ("--", "-", ""):
        return 0.0
    return float(v.replace(",", ""))


class TwseChipsCollector(BaseCollector):
    """Single-day chip pull. Loops if `days` > 1."""
    source = "twse.chips"

    def __init__(self, days: int = 5):
        self.days = days

    async def _collect(self) -> CollectorResult:
        async with async_session_maker() as s:
            stocks = (await s.execute(select(Stock))).scalars().all()
        sym_to_id = {st.symbol: st.id for st in stocks if st.market != "TPEX"}
        if not sym_to_id:
            raise RuntimeError("no TWSE stocks — seed universe first")

        rows_total = 0
        latest: Optional[datetime] = None
        end = date.today()
        async with httpx.AsyncClient(timeout=30, headers={
            "User-Agent": "tsa-local-research/0.1 (single-user research)",
        }) as client:
            for offset in range(self.days):
                d = end - timedelta(days=offset)
                # Skip weekends quickly
                if d.weekday() >= 5:
                    continue
                params = {
                    "response": "json",
                    "date": d.strftime("%Y%m%d"),
                    "selectType": "ALLBUT0999",
                }
                try:
                    r = await client.get(TWSE_T86_URL, params=params)
                    r.raise_for_status()
                except Exception as e:
                    logger.warning("twse.chips {} fetch failed: {}", d, e)
                    continue

                try:
                    j = r.json()
                except Exception:
                    logger.warning("twse.chips {} not json", d)
                    continue

                data = j.get("data") or []
                fields = j.get("fields") or []
                # TWSE schema changes; identify by header
                f = {name: i for i, name in enumerate(fields)}
                # required fields
                idx_sym = f.get("證券代號")
                idx_foreign = f.get("外陸資買賣超股數(不含外資自營商)") or f.get("外資及陸資買賣超股數")
                idx_invest = f.get("投信買賣超股數")
                idx_dealer = f.get("自營商買賣超股數")
                if idx_sym is None or idx_foreign is None:
                    logger.warning("twse.chips {} schema unrecognized", d)
                    continue

                rows = []
                for row in data:
                    try:
                        sym = (row[idx_sym] or "").strip()
                        if sym not in sym_to_id:
                            continue
                        rows.append({
                            "stock_id": sym_to_id[sym],
                            "date": d,
                            "foreign_buy": _to_float(row[idx_foreign]) / 1000.0,
                            "investment_buy": _to_float(row[idx_invest]) / 1000.0 if idx_invest else 0.0,
                            "dealer_buy": _to_float(row[idx_dealer]) / 1000.0 if idx_dealer else 0.0,
                        })
                    except Exception as e:
                        logger.debug("twse.chips parse row failed: {}", e)

                if rows:
                    async with async_session_maker() as s:
                        stmt = sqlite_insert(ChipData).values(rows)
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["stock_id", "date"],
                            set_={
                                "foreign_buy": stmt.excluded.foreign_buy,
                                "investment_buy": stmt.excluded.investment_buy,
                                "dealer_buy": stmt.excluded.dealer_buy,
                            },
                        )
                        await s.execute(stmt)
                        await s.commit()
                    rows_total += len(rows)
                    if latest is None or datetime.combine(d, datetime.min.time()) > latest:
                        latest = datetime.combine(d, datetime.min.time())
                # courtesy delay
                await asyncio.sleep(0.5)

        if rows_total == 0:
            raise RuntimeError(f"twse.chips: 0 rows ingested across {self.days} days")
        return CollectorResult(rows=rows_total, latest_data_at=latest)
