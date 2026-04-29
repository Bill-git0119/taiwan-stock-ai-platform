from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import admin_user
from app.db.models import NotificationLog, Plan, Referral, Subscription, User
from app.db.session import get_db
from app.services import scheduler as scheduler_svc

router = APIRouter()


class AdminStats(BaseModel):
    total_users: int
    active_users: int
    paid_users: int
    pro_users: int
    elite_users: int
    mrr_twd: int
    notifications_24h: int
    notification_success_rate: float


class UserRow(BaseModel):
    id: int
    email: str
    name: str
    plan: str
    is_admin: bool
    is_active: bool
    created_at: datetime


class RevenueMonth(BaseModel):
    month: str
    revenue_twd: int
    paid_subscriptions: int


class NotificationRow(BaseModel):
    id: int
    user_id: int | None
    kind: str
    success: bool
    error: str | None
    created_at: datetime


@router.get("/stats", response_model=AdminStats)
async def stats(_: User = Depends(admin_user), session: AsyncSession = Depends(get_db)):
    total = (await session.execute(select(func.count(User.id)))).scalar() or 0
    active = (await session.execute(select(func.count(User.id)).where(User.is_active == True))).scalar() or 0  # noqa: E712
    pro = (await session.execute(select(func.count(User.id)).where(User.plan == Plan.PRO))).scalar() or 0
    elite = (await session.execute(select(func.count(User.id)).where(User.plan == Plan.ELITE))).scalar() or 0
    mrr = (
        await session.execute(
            select(func.coalesce(func.sum(Subscription.price_twd), 0)).where(Subscription.status == "active")
        )
    ).scalar() or 0

    since = datetime.now(timezone.utc) - timedelta(days=1)
    n24 = (
        await session.execute(select(func.count(NotificationLog.id)).where(NotificationLog.created_at >= since))
    ).scalar() or 0
    n24_ok = (
        await session.execute(
            select(func.count(NotificationLog.id)).where(
                NotificationLog.created_at >= since, NotificationLog.success == True  # noqa: E712
            )
        )
    ).scalar() or 0
    rate = (n24_ok / n24) if n24 else 1.0

    return AdminStats(
        total_users=int(total),
        active_users=int(active),
        paid_users=int(pro + elite),
        pro_users=int(pro),
        elite_users=int(elite),
        mrr_twd=int(mrr),
        notifications_24h=int(n24),
        notification_success_rate=round(float(rate), 4),
    )


@router.get("/users", response_model=List[UserRow])
async def users(
    limit: int = 50,
    _: User = Depends(admin_user),
    session: AsyncSession = Depends(get_db),
):
    rows = (
        await session.execute(select(User).order_by(User.id.desc()).limit(limit))
    ).scalars().all()
    return [
        UserRow(
            id=u.id, email=u.email, name=u.name, plan=u.plan,
            is_admin=u.is_admin, is_active=u.is_active, created_at=u.created_at,
        )
        for u in rows
    ]


@router.get("/subscriptions")
async def subscriptions(_: User = Depends(admin_user), session: AsyncSession = Depends(get_db)):
    rows = (
        await session.execute(
            select(Subscription, User)
            .join(User, User.id == Subscription.user_id)
            .order_by(Subscription.id.desc())
            .limit(100)
        )
    ).all()
    return [
        {
            "id": sub.id,
            "user_email": u.email,
            "plan": sub.plan,
            "status": sub.status,
            "price_twd": sub.price_twd,
            "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
            "stripe_subscription_id": sub.stripe_subscription_id,
        }
        for sub, u in rows
    ]


@router.get("/revenue", response_model=List[RevenueMonth])
async def revenue_monthly(_: User = Depends(admin_user), session: AsyncSession = Depends(get_db)):
    """Group active subscriptions by month-of-creation."""
    rows = (
        await session.execute(
            select(
                func.strftime("%Y-%m", Subscription.created_at).label("ym"),
                func.coalesce(func.sum(Subscription.price_twd), 0),
                func.count(Subscription.id),
            )
            .where(Subscription.status == "active")
            .group_by("ym")
            .order_by("ym")
        )
    ).all()
    return [RevenueMonth(month=str(ym or "—"), revenue_twd=int(rev), paid_subscriptions=int(n)) for ym, rev, n in rows]


@router.get("/notifications", response_model=List[NotificationRow])
async def notifications(
    limit: int = 50,
    _: User = Depends(admin_user),
    session: AsyncSession = Depends(get_db),
):
    rows = (
        await session.execute(
            select(NotificationLog).order_by(NotificationLog.id.desc()).limit(limit)
        )
    ).scalars().all()
    return [
        NotificationRow(
            id=n.id, user_id=n.user_id, kind=n.kind, success=n.success,
            error=n.error, created_at=n.created_at,
        )
        for n in rows
    ]


@router.get("/growth")
async def growth_metrics(_: User = Depends(admin_user), session: AsyncSession = Depends(get_db)):
    """Growth KPIs: MRR, churn, CAC/LTV (heuristic), conversion, referral lift."""
    total = int((await session.execute(select(func.count(User.id)))).scalar() or 0)
    paid_now = int(
        (await session.execute(
            select(func.count(User.id)).where(User.plan.in_([Plan.PRO, Plan.ELITE]))
        )).scalar() or 0
    )
    canceled = int(
        (await session.execute(
            select(func.count(Subscription.id)).where(Subscription.status == "canceled")
        )).scalar() or 0
    )
    paid_ever = int(
        (await session.execute(
            select(func.count(func.distinct(Subscription.user_id)))
        )).scalar() or 0
    )

    mrr = int(
        (await session.execute(
            select(func.coalesce(func.sum(Subscription.price_twd), 0)).where(Subscription.status == "active")
        )).scalar() or 0
    )

    arpu = (mrr / paid_now) if paid_now else 0.0
    churn_rate = (canceled / paid_ever) if paid_ever else 0.0
    # heuristic CAC = NT$200 (avg ad cost), LTV = ARPU / churn (or 12mo if no churn)
    cac_twd = 200
    ltv_twd = (arpu / churn_rate) if churn_rate > 0 else arpu * 12

    trial_to_paid = (paid_ever / total) if total else 0.0

    referrals_total = int(
        (await session.execute(select(func.count(Referral.id)))).scalar() or 0
    )
    referrals_converted = int(
        (await session.execute(
            select(func.count(Referral.id)).where(Referral.converted_at.is_not(None))
        )).scalar() or 0
    )
    referral_lift = (referrals_converted / paid_ever) if paid_ever else 0.0

    return {
        "mrr_twd": mrr,
        "arpu_twd": round(arpu, 2),
        "paid_users_now": paid_now,
        "paid_users_ever": paid_ever,
        "churn_rate": round(churn_rate, 4),
        "cac_twd": cac_twd,
        "ltv_twd": round(ltv_twd, 2),
        "ltv_cac_ratio": round((ltv_twd / cac_twd) if cac_twd else 0, 2),
        "trial_to_paid_rate": round(trial_to_paid, 4),
        "total_users": total,
        "referrals_total": referrals_total,
        "referrals_converted": referrals_converted,
        "referral_lift_pct": round(referral_lift, 4),
    }


@router.get("/health")
async def system_health(_: User = Depends(admin_user)):
    return {
        "ok": True,
        "scheduler_jobs": scheduler_svc.list_jobs(),
        "service": "taiwan-stock-ai-platform",
    }
