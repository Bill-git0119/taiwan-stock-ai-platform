"""Referral code + reward bookkeeping.

Reward tiers:
  - 1 paid invitee → +7 days Pro (or stack on existing)
  - 3 paid invitees → upgrade to Elite for 30 days
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Plan, Referral, Subscription, User


def code_for(user: User) -> str:
    """Stable, human-friendly code derived from user id + email."""
    seed = f"{user.id}-{user.email}".encode("utf-8")
    h = hashlib.sha256(seed).hexdigest().upper()
    # 6 alphanumeric chars + uid suffix → ~uniqueness, easy to type
    return f"{h[:6]}{user.id:02d}"


async def stats_for(session: AsyncSession, user: User) -> dict:
    rows = (
        await session.execute(
            select(Referral).where(Referral.referrer_id == user.id)
        )
    ).scalars().all()
    invited = len(rows)
    converted = sum(1 for r in rows if r.converted_at is not None)
    granted = sum(1 for r in rows if r.reward_granted)

    rewards: list[str] = []
    if converted >= 1: rewards.append("+7d Pro")
    if converted >= 3: rewards.append("+30d Elite")

    next_target = 1 if converted < 1 else (3 if converted < 3 else None)
    progress = converted / next_target if next_target else 1.0

    return {
        "code": code_for(user),
        "invited": invited,
        "converted": converted,
        "granted": granted,
        "rewards_unlocked": rewards,
        "next_target": next_target,
        "progress": min(1.0, progress),
        "share_url": f"/register?ref={code_for(user)}",
    }


async def record_invite(session: AsyncSession, referrer: User, invitee_email: str) -> Referral:
    existing = (
        await session.execute(
            select(Referral).where(
                Referral.referrer_id == referrer.id,
                Referral.invitee_email == invitee_email,
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    row = Referral(
        referrer_id=referrer.id,
        code=code_for(referrer),
        invitee_email=invitee_email,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def resolve_referrer(session: AsyncSession, code: str) -> Optional[User]:
    if not code:
        return None
    code = code.strip().upper()
    row = (
        await session.execute(select(Referral).where(Referral.code == code).limit(1))
    ).scalar_one_or_none()
    if row:
        return await session.get(User, row.referrer_id)
    # Fallback: scan users and recompute code (small scale).
    users = (await session.execute(select(User))).scalars().all()
    for u in users:
        if code_for(u) == code:
            return u
    return None


async def attach_invitee(
    session: AsyncSession, referrer: User, invitee: User
) -> Referral:
    row = await record_invite(session, referrer, invitee.email)
    if row.invitee_user_id != invitee.id:
        row.invitee_user_id = invitee.id
        await session.commit()
    return row


async def mark_converted(session: AsyncSession, invitee_user_id: int) -> Optional[Referral]:
    row = (
        await session.execute(
            select(Referral)
            .where(Referral.invitee_user_id == invitee_user_id, Referral.converted_at.is_(None))
            .limit(1)
        )
    ).scalar_one_or_none()
    if not row:
        return None
    row.converted_at = datetime.utcnow()
    await session.commit()
    await _maybe_grant_reward(session, row.referrer_id)
    return row


async def _maybe_grant_reward(session: AsyncSession, referrer_id: int) -> None:
    converted_count = (
        await session.execute(
            select(func.count(Referral.id)).where(
                Referral.referrer_id == referrer_id,
                Referral.converted_at.is_not(None),
            )
        )
    ).scalar_one()
    user = await session.get(User, referrer_id)
    if not user:
        return
    grant: Optional[tuple[str, str, int]] = None
    if converted_count >= 3 and user.plan != Plan.ELITE:
        grant = ("elite_30d", Plan.ELITE, 30)
    elif converted_count >= 1 and user.plan == Plan.FREE:
        grant = ("pro_7d", Plan.PRO, 7)
    if not grant:
        return
    kind, target_plan, days = grant
    user.plan = target_plan
    sub = Subscription(
        user_id=user.id, plan=target_plan, status="active",
        price_twd=0, current_period_end=datetime.utcnow() + timedelta(days=days),
    )
    session.add(sub)
    pending = (
        await session.execute(
            select(Referral).where(
                Referral.referrer_id == referrer_id,
                Referral.reward_granted.is_(False),
                Referral.converted_at.is_not(None),
            )
        )
    ).scalars().all()
    for r in pending:
        r.reward_granted = True
        r.reward_kind = kind
    await session.commit()
