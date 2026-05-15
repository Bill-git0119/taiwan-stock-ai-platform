import pytest
from sqlalchemy import select

from app.db.models import Plan, User
from app.db.session import async_session_maker


async def _set_plan(email: str, plan: str) -> None:
    async with async_session_maker() as s:
        u = (await s.execute(select(User).where(User.email == email))).scalar_one()
        u.plan = plan
        await s.commit()


@pytest.mark.asyncio
async def test_free_user_sees_top3(client, auth_headers, seeded_scores):
    # Clear top30 cache so seeded_scores is observed for this test
    from app.services.cache_service import cache
    await cache.delete("stocks:top30")
    headers, _ = auth_headers
    r = await client.get("/api/v1/top10", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["tier"]["plan"] == "free"
    assert body["tier"]["limit"] == 3
    assert len(body["items"]) == 3
    assert body["tier"]["upgrade_message"] is not None


@pytest.mark.asyncio
async def test_pro_user_sees_top10(client, auth_headers, seeded_scores):
    from app.services.cache_service import cache
    await cache.delete("stocks:top30")
    headers, email = auth_headers
    await _set_plan(email, Plan.PRO)
    r = await client.get("/api/v1/top10", headers=headers)
    body = r.json()
    assert body["tier"]["plan"] == "pro"
    assert body["tier"]["limit"] == 10
    assert len(body["items"]) == 10


@pytest.mark.asyncio
async def test_elite_user_sees_top30(client, auth_headers, seeded_scores):
    from app.services.cache_service import cache
    await cache.delete("stocks:top30")
    headers, email = auth_headers
    await _set_plan(email, Plan.ELITE)
    r = await client.get("/api/v1/top10", headers=headers)
    body = r.json()
    assert body["tier"]["plan"] == "elite"
    assert body["tier"]["limit"] == 30
    assert len(body["items"]) == 30


@pytest.mark.asyncio
async def test_notify_test_requires_elite(client, auth_headers):
    headers, _ = auth_headers  # default = free
    r = await client.post("/api/v1/notify/test", headers=headers)
    assert r.status_code == 402
    body = r.json()
    assert body["detail"]["error"] == "upgrade_required"
    assert body["detail"]["required_plan"] == "elite"


@pytest.mark.asyncio
async def test_admin_endpoints_require_admin(client, auth_headers):
    headers, _ = auth_headers
    r = await client.get("/api/v1/admin/stats", headers=headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_stats_ok(client, admin_headers):
    r = await client.get("/api/v1/admin/stats", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    for f in ("total_users", "active_users", "paid_users", "mrr_twd"):
        assert f in body


def test_plan_at_least_ordering():
    assert Plan.at_least(Plan.ELITE, Plan.PRO)
    assert Plan.at_least(Plan.PRO, Plan.PRO)
    assert not Plan.at_least(Plan.FREE, Plan.PRO)
    assert not Plan.at_least(Plan.PRO, Plan.ELITE)
