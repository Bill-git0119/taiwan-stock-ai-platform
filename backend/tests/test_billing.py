import json

import pytest
from sqlalchemy import select

from app.db.models import Plan, Subscription, User
from app.db.session import async_session_maker


@pytest.mark.asyncio
async def test_plans_endpoint(client):
    r = await client.get("/api/v1/billing/plans")
    assert r.status_code == 200
    j = r.json()
    assert j["pro"]["price_twd"] == 299
    assert j["elite"]["price_twd"] == 1499
    assert j["free"]["top_n"] == 3


@pytest.mark.asyncio
async def test_checkout_unauthenticated(client):
    r = await client.post("/api/v1/billing/checkout", json={"plan": "pro"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_checkout_authenticated_fallback(client, auth_headers):
    headers, _ = auth_headers
    r = await client.post("/api/v1/billing/checkout", json={"plan": "pro"}, headers=headers)
    # Without STRIPE_SECRET_KEY in test env we get a mock URL fallback.
    assert r.status_code == 200
    body = r.json()
    assert body["plan"] == "pro"
    assert "url" in body


@pytest.mark.asyncio
async def test_subscription_returns_default_when_none(client, auth_headers):
    headers, _ = auth_headers
    r = await client.get("/api/v1/billing/subscription", headers=headers)
    assert r.status_code == 200
    j = r.json()
    assert j["plan"] == "free"
    assert j["price_twd"] == 0


@pytest.mark.asyncio
async def test_webhook_checkout_completed_upgrades_plan(client, auth_headers):
    headers, email = auth_headers
    payload = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "sub_test_pro_1",
                "customer": "cus_test_1",
                "customer_details": {"email": email},
                "subscription": "sub_test_pro_1",
                "status": "active",
                "metadata": {"plan": "pro"},
                "current_period_end": 1893456000,
            }
        },
    }
    r = await client.post(
        "/api/v1/billing/webhook",
        content=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200
    assert r.json()["received"] is True

    async with async_session_maker() as s:
        u = (await s.execute(select(User).where(User.email == email))).scalar_one()
        assert u.plan == Plan.PRO
        sub = (await s.execute(select(Subscription).where(Subscription.user_id == u.id))).scalar_one()
        assert sub.plan == "pro"
        assert sub.status == "active"
        assert sub.price_twd == 299


@pytest.mark.asyncio
async def test_webhook_subscription_deleted_downgrades(client, auth_headers):
    headers, email = auth_headers
    # First upgrade
    upgrade = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "sub_x", "customer": "cus_x", "customer_details": {"email": email},
            "subscription": "sub_x", "status": "active", "metadata": {"plan": "elite"},
        }},
    }
    await client.post("/api/v1/billing/webhook", content=json.dumps(upgrade),
                      headers={"Content-Type": "application/json"})
    async with async_session_maker() as s:
        u = (await s.execute(select(User).where(User.email == email))).scalar_one()
        assert u.plan == "elite"

    # Then delete
    delete = {
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": "sub_x", "customer": "cus_x",
                            "customer_details": {"email": email}, "status": "canceled"}},
    }
    r = await client.post("/api/v1/billing/webhook", content=json.dumps(delete),
                          headers={"Content-Type": "application/json"})
    assert r.status_code == 200
    async with async_session_maker() as s:
        u = (await s.execute(select(User).where(User.email == email))).scalar_one()
        assert u.plan == "free"


@pytest.mark.asyncio
async def test_webhook_unknown_email_silent(client):
    payload = {
        "type": "checkout.session.completed",
        "data": {"object": {"customer_details": {"email": "ghost@nowhere.io"},
                            "metadata": {"plan": "pro"}}},
    }
    r = await client.post("/api/v1/billing/webhook", content=json.dumps(payload),
                          headers={"Content-Type": "application/json"})
    assert r.status_code == 200
    assert r.json()["received"] is True
