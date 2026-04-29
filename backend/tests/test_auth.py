import uuid

import pytest


@pytest.mark.asyncio
async def test_register_login_me(client):
    email = f"r{uuid.uuid4().hex[:8]}@test.io"
    r = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Sup3rSecret!", "name": "Bob",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["user"]["email"] == email
    assert body["user"]["plan"] == "free"
    token = body["access_token"]

    # duplicate email rejected
    r2 = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Sup3rSecret!"
    })
    assert r2.status_code == 409

    # login
    r3 = await client.post("/api/v1/auth/login", json={
        "email": email, "password": "Sup3rSecret!",
    })
    assert r3.status_code == 200

    # wrong password
    r4 = await client.post("/api/v1/auth/login", json={
        "email": email, "password": "wrong",
    })
    assert r4.status_code == 401

    # me with token
    r5 = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r5.status_code == 200
    assert r5.json()["email"] == email


@pytest.mark.asyncio
async def test_me_requires_auth(client):
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_change_password_flow(client, auth_headers):
    headers, _ = auth_headers
    r = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "Sup3rSecret!", "new_password": "N3wPassw0rd!"},
        headers=headers,
    )
    assert r.status_code == 200

    # wrong current pw
    r2 = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "wrong", "new_password": "N3wPassw0rd!"},
        headers=headers,
    )
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_update_profile(client, auth_headers):
    headers, _ = auth_headers
    r = await client.patch("/api/v1/auth/me", json={"name": "Alice", "line_user_id": "U123"}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Alice"
    assert body["line_user_id"] == "U123"


@pytest.mark.asyncio
async def test_forgot_then_reset_password(client):
    email = f"fp{uuid.uuid4().hex[:8]}@test.io"
    await client.post("/api/v1/auth/register", json={"email": email, "password": "Initial1!"})
    r = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert r.status_code == 200
    token = r.json()["dev_reset_token"]

    r2 = await client.post("/api/v1/auth/reset-password", json={
        "token": token, "new_password": "Updated2!",
    })
    assert r2.status_code == 200

    # login with new password
    r3 = await client.post("/api/v1/auth/login", json={"email": email, "password": "Updated2!"})
    assert r3.status_code == 200
