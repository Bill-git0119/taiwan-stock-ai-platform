import asyncio

import pytest

from app.services.cache_service import CacheService, cached


@pytest.mark.asyncio
async def test_cache_set_get_expire():
    c = CacheService()
    await c.set("k", {"x": 1}, ttl=1)
    assert await c.get("k") == {"x": 1}
    await asyncio.sleep(1.2)
    assert await c.get("k") is None


@pytest.mark.asyncio
async def test_cache_delete_clear():
    c = CacheService()
    await c.set("k1", "v1", ttl=10)
    await c.set("k2", "v2", ttl=10)
    await c.delete("k1")
    assert await c.get("k1") is None
    assert await c.get("k2") == "v2"
    await c.clear()
    assert await c.get("k2") is None


@pytest.mark.asyncio
async def test_cached_calls_loader_once():
    calls = {"n": 0}

    async def loader():
        calls["n"] += 1
        return {"answer": 42}

    a = await cached("unit:test:cached", loader, ttl=5)
    b = await cached("unit:test:cached", loader, ttl=5)
    assert a == b == {"answer": 42}
    assert calls["n"] == 1
