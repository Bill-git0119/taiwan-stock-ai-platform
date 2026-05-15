"""BaseCollector — common machinery for every datahub source.

Contract:
  * subclass overrides `source` (str) and `_collect(...)` (async)
  * `_collect` returns a CollectorResult: rows ingested + latest_data_at
  * BaseCollector handles retry/backoff, freshness table updates, logging
  * Never silent: raises on hard failure AND records last_error in
    data_freshness so the UI can flag it red
"""
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from loguru import logger
from sqlalchemy import select

from app.db.models import DataFreshness
from app.db.session import async_session_maker


@dataclass
class CollectorResult:
    rows: int
    latest_data_at: Optional[datetime] = None
    note: Optional[str] = None


class CollectorError(Exception):
    """Hard failure — collector did NOT produce real data."""


class BaseCollector:
    source: str = "base"             # override
    max_attempts: int = 3
    base_backoff_seconds: float = 2.0

    async def _collect(self) -> CollectorResult:  # override
        raise NotImplementedError

    async def run(self) -> CollectorResult:
        attempt = 0
        last_err: Optional[Exception] = None
        await self._mark_attempted()
        while attempt < self.max_attempts:
            attempt += 1
            try:
                logger.info("collector.{} attempt={}", self.source, attempt)
                result = await self._collect()
                await self._mark_succeeded(result)
                logger.info("collector.{} ok rows={} latest={}",
                            self.source, result.rows, result.latest_data_at)
                return result
            except Exception as e:
                last_err = e
                logger.warning("collector.{} failed attempt={} err={}",
                               self.source, attempt, e)
                if attempt < self.max_attempts:
                    delay = self.base_backoff_seconds * (2 ** (attempt - 1))
                    delay = delay + random.uniform(0, delay / 2)
                    await asyncio.sleep(delay)

        await self._mark_failed(last_err)
        raise CollectorError(f"{self.source} failed after {self.max_attempts} attempts: {last_err}")

    # ── freshness bookkeeping ────────────────────────────────────────────

    async def _row(self):
        async with async_session_maker() as s:
            row = (await s.execute(
                select(DataFreshness).where(DataFreshness.source == self.source)
            )).scalar_one_or_none()
            if row is None:
                row = DataFreshness(source=self.source)
                s.add(row)
                await s.commit()
                await s.refresh(row)
            return row

    async def _mark_attempted(self):
        async with async_session_maker() as s:
            row = (await s.execute(
                select(DataFreshness).where(DataFreshness.source == self.source)
            )).scalar_one_or_none()
            if row is None:
                row = DataFreshness(source=self.source)
                s.add(row)
            row.last_attempted_at = datetime.utcnow()
            await s.commit()

    async def _mark_succeeded(self, result: CollectorResult):
        async with async_session_maker() as s:
            row = (await s.execute(
                select(DataFreshness).where(DataFreshness.source == self.source)
            )).scalar_one_or_none()
            if row is None:
                row = DataFreshness(source=self.source)
                s.add(row)
            row.last_succeeded_at = datetime.utcnow()
            row.consecutive_failures = 0
            row.last_error = None
            row.rows_last_run = result.rows
            if result.latest_data_at:
                row.latest_data_at = result.latest_data_at
            await s.commit()

    async def _mark_failed(self, err: Optional[Exception]):
        async with async_session_maker() as s:
            row = (await s.execute(
                select(DataFreshness).where(DataFreshness.source == self.source)
            )).scalar_one_or_none()
            if row is None:
                row = DataFreshness(source=self.source)
                s.add(row)
            row.consecutive_failures = (row.consecutive_failures or 0) + 1
            row.last_error = str(err)[:500] if err else "unknown"
            await s.commit()
