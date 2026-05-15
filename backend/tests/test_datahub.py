"""Datahub freshness / integrity endpoints smoke tests.

We don't hit external networks here — just verify the endpoints respond
and that DataFreshness rows are read/written correctly.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select

from app.db.models import DataFreshness, DataIntegrityReport
from app.db.session import async_session_maker


@pytest.mark.asyncio
async def test_freshness_endpoint_empty(client):
    r = await client.get("/api/v1/datahub/freshness")
    assert r.status_code == 200
    body = r.json()
    assert "sources" in body
    assert isinstance(body["sources"], list)


@pytest.mark.asyncio
async def test_freshness_endpoint_returns_seeded_row(client):
    async with async_session_maker() as s:
        s.add(DataFreshness(
            source="test.source",
            latest_data_at=datetime.utcnow(),
            last_succeeded_at=datetime.utcnow(),
            rows_last_run=42,
            consecutive_failures=0,
        ))
        await s.commit()
    r = await client.get("/api/v1/datahub/freshness")
    body = r.json()
    test_row = next((s for s in body["sources"] if s["source"] == "test.source"), None)
    assert test_row is not None
    assert test_row["rows_last_run"] == 42
    assert test_row["severity"] == "ok"


@pytest.mark.asyncio
async def test_integrity_endpoint_lists_recent(client):
    async with async_session_maker() as s:
        s.add(DataIntegrityReport(
            source="daily_prices", check_name="test.check",
            severity="warn", affected_symbols=3, detail="{}",
        ))
        await s.commit()
    r = await client.get("/api/v1/datahub/integrity")
    body = r.json()
    assert "reports" in body
    assert any(rep["check_name"] == "test.check" for rep in body["reports"])


@pytest.mark.asyncio
async def test_run_collector_unknown_source(client):
    r = await client.post("/api/v1/datahub/run/nonsense")
    assert r.status_code == 404
