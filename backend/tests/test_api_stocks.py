import pytest


@pytest.mark.asyncio
async def test_top10_anonymous_is_free_tier(client):
    r = await client.get("/api/v1/stocks/top10")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "tier" in body
    assert body["tier"]["plan"] == "free"
    assert body["tier"]["limit"] == 3
    assert len(body["items"]) == 3
    scores = [i["total_score"] for i in body["items"]]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_top10_shortcut(client):
    r = await client.get("/api/v1/top10")
    assert r.status_code == 200
    assert r.json()["tier"]["plan"] == "free"


@pytest.mark.asyncio
async def test_stock_detail_fallback(client):
    r = await client.get("/api/v1/stocks/2330")
    assert r.status_code == 200
    j = r.json()
    assert j["symbol"] == "2330"
    assert j["latest_score"]["total_score"] > 0


@pytest.mark.asyncio
async def test_stock_detail_unknown(client):
    r = await client.get("/api/v1/stocks/NOSUCH")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_market_summary(client):
    r = await client.get("/api/v1/market/summary")
    assert r.status_code == 200
    j = r.json()
    assert j["stock_count"] >= 0
    assert j["total_volume"] >= 0
