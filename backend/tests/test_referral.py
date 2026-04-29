import pytest
from sqlalchemy import select

from app.db.models import Plan, Referral, User
from app.db.session import async_session_maker
from app.services import referral_service


@pytest.mark.asyncio
async def test_code_is_stable_per_user():
    async with async_session_maker() as s:
        u = User(email="ref1@test.io", name="r1", plan="free")
        s.add(u); await s.commit(); await s.refresh(u)
    c1 = referral_service.code_for(u)
    c2 = referral_service.code_for(u)
    assert c1 == c2 and len(c1) >= 8


@pytest.mark.asyncio
async def test_referral_stats_initial_zero(client, auth_headers):
    headers, _ = auth_headers
    r = await client.get("/api/v1/referral/me", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["invited"] == 0
    assert body["converted"] == 0
    assert body["next_target"] == 1
    assert body["share_url"].startswith("/register?ref=")


@pytest.mark.asyncio
async def test_register_with_referral_attaches_invitee(client):
    # referrer
    r = await client.post("/api/v1/auth/register", json={
        "email": "refA@test.io", "password": "StrongPass1!",
    })
    assert r.status_code == 201
    code = (await client.get("/api/v1/referral/me", headers={
        "Authorization": f"Bearer {r.json()['access_token']}"
    })).json()["code"]

    # invitee registers with ref
    r2 = await client.post("/api/v1/auth/register", json={
        "email": "refB@test.io", "password": "StrongPass1!", "ref": code,
    })
    assert r2.status_code == 201

    async with async_session_maker() as s:
        rows = (await s.execute(select(Referral))).scalars().all()
    assert any(rw.invitee_email.lower() == "refb@test.io" for rw in rows)


@pytest.mark.asyncio
async def test_mark_converted_grants_pro_7d():
    async with async_session_maker() as s:
        ref = User(email="g_ref@test.io", name="g", plan=Plan.FREE)
        inv = User(email="g_inv@test.io", name="i", plan=Plan.FREE)
        s.add_all([ref, inv]); await s.commit()
        await s.refresh(ref); await s.refresh(inv)
        await referral_service.attach_invitee(s, ref, inv)
        # invitee now becomes a paying user
        inv.plan = Plan.PRO
        await s.commit()
        row = await referral_service.mark_converted(s, inv.id)
    assert row is not None
    async with async_session_maker() as s:
        u = (await s.execute(select(User).where(User.email == "g_ref@test.io"))).scalar_one()
    assert u.plan == Plan.PRO  # reward granted
