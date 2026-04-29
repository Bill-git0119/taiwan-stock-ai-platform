"""TTL cache abstraction with optional Redis backend.

Falls back to in-process dict + asyncio.Lock when REDIS_URL is not set.
Used by hot endpoints (top3 / top10 / top30) to keep p95 < 200ms.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Optional

from app.core.config import get_settings

settings = get_settings()

try:
    import redis.asyncio as aioredis  # type: ignore
except Exception:
    aioredis = None  # type: ignore


class _MemoryCache:
    def __init__(self) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            row = self._data.get(key)
            if not row:
                return None
            expires, value = row
            if expires < time.time():
                self._data.pop(key, None)
                return None
            return value

    async def set(self, key: str, value: Any, ttl: int) -> None:
        async with self._lock:
            self._data[key] = (time.time() + ttl, value)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._data.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._data.clear()


class CacheService:
    """Async TTL cache. JSON-serializable values only."""

    def __init__(self) -> None:
        self._memory = _MemoryCache()
        self._redis = None
        url = getattr(settings, "redis_url", None)
        if url and aioredis is not None:
            try:
                self._redis = aioredis.from_url(url, decode_responses=True)
            except Exception:
                self._redis = None

    async def get(self, key: str) -> Optional[Any]:
        if self._redis is not None:
            try:
                raw = await self._redis.get(key)
                return json.loads(raw) if raw else None
            except Exception:
                pass
        return await self._memory.get(key)

    async def set(self, key: str, value: Any, ttl: int = 60) -> None:
        if self._redis is not None:
            try:
                await self._redis.set(key, json.dumps(value, default=str), ex=ttl)
                return
            except Exception:
                pass
        await self._memory.set(key, value, ttl)

    async def delete(self, key: str) -> None:
        if self._redis is not None:
            try:
                await self._redis.delete(key)
                return
            except Exception:
                pass
        await self._memory.delete(key)

    async def clear(self) -> None:
        await self._memory.clear()
        if self._redis is not None:
            try:
                await self._redis.flushdb()
            except Exception:
                pass


cache = CacheService()


async def cached(key: str, loader, ttl: int = 60):
    """Cache-aside helper: loader is awaited only on miss."""
    hit = await cache.get(key)
    if hit is not None:
        return hit
    value = await loader()
    await cache.set(key, value, ttl)
    return value
