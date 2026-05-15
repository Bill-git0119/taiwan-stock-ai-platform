import pytest


@pytest.mark.asyncio
async def test_top10_local_returns_elite_tier(client, seeded_scores):
    """Phase 1: local single-user mode always serves Elite tier (30 items)."""
    from app.services.cache_service import cache
    await cache.delete("stocks:top30")
    r = await client.get("/api/v1/stocks/top10")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "tier" in body
    assert body["tier"]["plan"] == "elite"
    assert body["tier"]["limit"] == 30
    assert len(body["items"]) == 30
    scores = [i["total_score"] for i in body["items"]]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_top10_shortcut(client):
    r = await client.get("/api/v1/top10")
    assert r.status_code == 200
    assert r.json()["tier"]["plan"] == "elite"


@pytest.mark.asyncio
async def test_top10_empty_when_no_scores(client):
    """P0 audit: when DB has no scores, return empty — never fabricate."""
    from app.services.cache_service import cache
    # Wipe scores so this test isolates the empty-DB path. Idempotent.
    from sqlalchemy import delete

    from app.db.models import Score
    from app.db.session import async_session_maker
    async with async_session_maker() as s:
        await s.execute(delete(Score))
        await s.commit()
    await cache.delete("stocks:top30")
    r = await client.get("/api/v1/stocks/top10")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []


@pytest.mark.asyncio
async def test_stock_detail_unknown_returns_404(client):
    """P0 audit: unknown symbol must 404, not return mocked fallback stock."""
    r = await client.get("/api/v1/stocks/NOSUCH_TICKER_XYZ")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_market_summary(client):
    r = await client.get("/api/v1/market/summary")
    assert r.status_code == 200
    j = r.json()
    assert j["stock_count"] >= 0
    assert j["total_volume"] >= 0
