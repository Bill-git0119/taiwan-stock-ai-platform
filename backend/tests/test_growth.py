import pytest


@pytest.mark.asyncio
async def test_leaderboard_weekly(client):
    r = await client.get("/api/v1/leaderboard/weekly")
    assert r.status_code == 200
    body = r.json()
    assert body["period"] == "7d"
    assert isinstance(body["items"], list) and len(body["items"]) > 0
    top = body["items"][0]
    assert "symbol" in top and "return_pct" in top


@pytest.mark.asyncio
async def test_blog_index_seeds(client):
    r = await client.get("/api/v1/blog/")
    assert r.status_code == 200
    posts = r.json()
    assert len(posts) >= 4  # 4 evergreen + today
    slugs = [p["slug"] for p in posts]
    assert "can-i-buy-tsmc" in slugs


@pytest.mark.asyncio
async def test_blog_post_detail(client):
    r = await client.get("/api/v1/blog/foreign-net-buy-ranking")
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == "foreign-net-buy-ranking"
    assert "外資" in body["title"]
    assert len(body["body_md"]) > 100


@pytest.mark.asyncio
async def test_blog_post_404(client):
    r = await client.get("/api/v1/blog/no-such-slug-12345")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_admin_growth_metrics(client, admin_headers):
    r = await client.get("/api/v1/admin/growth", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    for f in ("mrr_twd", "arpu_twd", "churn_rate", "ltv_twd", "ltv_cac_ratio",
              "trial_to_paid_rate", "referrals_total"):
        assert f in body


@pytest.mark.asyncio
async def test_admin_growth_requires_admin(client, auth_headers):
    headers, _ = auth_headers
    r = await client.get("/api/v1/admin/growth", headers=headers)
    assert r.status_code == 403
