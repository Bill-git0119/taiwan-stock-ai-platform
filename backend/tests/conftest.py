import os
import sys
from pathlib import Path

# Route to in-memory SQLite before app import
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["APP_ENV"] = "test"
os.environ["JWT_SECRET"] = "test-jwt-secret"

_backend = Path(__file__).resolve().parents[1]
_root = _backend.parent
for p in (_backend, _root):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import async_session_maker, engine
from app.main import app

# clear cached settings from any previous import
get_settings.cache_clear()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def session():
    async with async_session_maker() as s:
        yield s


@pytest_asyncio.fixture
async def seeded_scores():
    """Insert 30 real Stock+Score rows for tests that exercise tier limits.

    Mock fallback was removed (P0 audit) — tests that previously relied on
    `_MOCK_TOP30` must seed their own data here. Always reseeds today's
    scores so the order in which other tests run doesn't matter, and clears
    the top30 cache so the fresh rows are visible immediately."""
    from datetime import date

    from sqlalchemy import select

    from app.db.models import Score, Stock
    from app.services.cache_service import cache

    async with async_session_maker() as s:
        today = date.today()
        for i in range(30):
            sym = f"SEED{i:04d}"
            stk = (await s.execute(select(Stock).where(Stock.symbol == sym))).scalar_one_or_none()
            if stk is None:
                stk = Stock(symbol=sym, name=f"測試{i}", market="TWSE")
                s.add(stk)
                await s.flush()
            score = 95 - i
            existing_score = (await s.execute(
                select(Score).where(Score.stock_id == stk.id, Score.date == today)
            )).scalar_one_or_none()
            if existing_score is None:
                s.add(Score(
                    stock_id=stk.id, date=today,
                    chip_score=score, fundamental_score=score, technical_score=score,
                    total_score=float(score), reason="seeded for tier-limit test",
                ))
        await s.commit()
    await cache.delete("stocks:top30")


@pytest_asyncio.fixture
async def auth_headers(client):
    """Create a fresh free-tier user and return Bearer-token headers."""
    import uuid
    email = f"u{uuid.uuid4().hex[:10]}@test.io"
    r = await client.post("/api/v1/auth/register", json={
        "email": email, "password": "Sup3rSecret!", "name": "T",
    })
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, email


@pytest_asyncio.fixture
async def admin_headers(client):
    """Create an admin user via DB direct write and return Bearer headers."""
    import uuid

    from sqlalchemy import select

    from app.core.security import create_access_token, hash_password
    from app.db.models import User

    email = f"admin{uuid.uuid4().hex[:6]}@test.io"
    async with async_session_maker() as s:
        u = User(
            email=email, name="admin", password_hash=hash_password("Adm!nPass1"),
            plan="elite", is_admin=True, is_active=True,
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
    token = create_access_token(u.id, {"plan": u.plan, "admin": True})
    return {"Authorization": f"Bearer {token}"}
