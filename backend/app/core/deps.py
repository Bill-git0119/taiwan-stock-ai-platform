"""FastAPI dependency: identity, plan tier, admin."""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.models import Plan, User
from app.db.session import get_db


def _bearer_token(request: Request) -> Optional[str]:
    h = request.headers.get("Authorization") or ""
    if h.lower().startswith("bearer "):
        return h.split(" ", 1)[1].strip() or None
    return None


async def current_user_optional(
    request: Request, session: AsyncSession = Depends(get_db)
) -> Optional[User]:
    token = _bearer_token(request)
    if not token:
        return None
    try:
        payload = decode_token(token)
        uid = int(payload.get("sub", 0))
    except Exception:
        return None
    if not uid:
        return None
    res = await session.execute(select(User).where(User.id == uid))
    user = res.scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    return user


async def current_user(
    user: Optional[User] = Depends(current_user_optional),
) -> User:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    return user


async def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin required")
    return user


def plan_of(user: Optional[User]) -> str:
    return user.plan if (user and user.plan in Plan.ALL) else Plan.FREE


def top_n_for(user: Optional[User]) -> int:
    return Plan.LIMIT.get(plan_of(user), Plan.LIMIT[Plan.FREE])


def require_plan(min_plan: str):
    """Dependency factory: raise 402 with upgrade prompt if user under tier."""

    async def _dep(user: Optional[User] = Depends(current_user_optional)) -> User:
        cur = plan_of(user)
        if not Plan.at_least(cur, min_plan):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "upgrade_required",
                    "current_plan": cur,
                    "required_plan": min_plan,
                    "message": f"此功能需 {min_plan.upper()} 方案，請升級。",
                    "upgrade_url": "/pricing",
                },
            )
        # user could still be None if the endpoint allows guest+free
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="login required")
        return user

    return _dep
