"""Local single-user dependencies.

Phase 1 removed the SaaS surface area (auth / pricing / admin / billing).
What used to be a JWT-gated multi-tenant system is now a local research
workstation, so every "current_user" call returns the same hardcoded
Elite user and every plan check is a no-op.

We keep the function signatures (current_user / require_plan / etc.) so
endpoints that imported them still work without rewrites — they just
never block anyone.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Plan, User
from app.db.session import get_db

LOCAL_USER_EMAIL = "local@workstation"
LOCAL_USER_NAME = "Local Research User"


async def _get_or_create_local_user(session: AsyncSession) -> User:
    res = await session.execute(select(User).where(User.email == LOCAL_USER_EMAIL))
    user = res.scalar_one_or_none()
    if user is None:
        user = User(
            email=LOCAL_USER_EMAIL,
            name=LOCAL_USER_NAME,
            password_hash="",
            plan=Plan.ELITE,
            is_admin=True,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def current_user_optional(session: AsyncSession = Depends(get_db)) -> Optional[User]:
    return await _get_or_create_local_user(session)


async def current_user(session: AsyncSession = Depends(get_db)) -> User:
    return await _get_or_create_local_user(session)


async def admin_user(session: AsyncSession = Depends(get_db)) -> User:
    return await _get_or_create_local_user(session)


def plan_of(_user: Optional[User] = None) -> str:
    return Plan.ELITE


def top_n_for(_user: Optional[User] = None) -> int:
    return Plan.LIMIT.get(Plan.ELITE, 30)


def require_plan(_min_plan: str):
    """No-op gate — Phase 1 is local single-user mode."""

    async def _dep(session: AsyncSession = Depends(get_db)) -> User:
        return await _get_or_create_local_user(session)

    return _dep
