from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import current_user
from app.db.models import Plan, SubStatus, Subscription, User
from app.db.session import get_db
from app.services import stripe_service

router = APIRouter()


class CheckoutRequest(BaseModel):
    plan: Literal["pro", "elite"]


class CheckoutResponse(BaseModel):
    url: str
    plan: str


class CurrentSubscription(BaseModel):
    plan: str
    status: str
    price_twd: int
    current_period_end: Optional[datetime] = None
    canceled_at: Optional[datetime] = None
    stripe_customer_id: Optional[str] = None


@router.get("/plans")
async def plans():
    return {
        "free": {"price_twd": 0, "top_n": Plan.LIMIT[Plan.FREE], "features": ["TOP3 強勢股", "延遲資料"]},
        "pro": {"price_twd": 299, "top_n": Plan.LIMIT[Plan.PRO], "features": ["TOP10 強勢股", "即時訊號", "主力籌碼"]},
        "elite": {"price_twd": 1499, "top_n": Plan.LIMIT[Plan.ELITE], "features": ["TOP30 強勢股", "LINE 推播", "回測功能", "VIP 指標"]},
    }


@router.post("/checkout", response_model=CheckoutResponse)
async def checkout(body: CheckoutRequest, user: User = Depends(current_user)):
    s = get_settings()
    success_url = f"{s.app_base_url}/account/subscription"
    cancel_url = f"{s.app_base_url}/pricing"
    res = stripe_service.create_checkout_session(
        plan=body.plan,
        customer_email=user.email,
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return CheckoutResponse(url=res["url"], plan=body.plan)


@router.get("/portal")
async def portal(user: User = Depends(current_user), session: AsyncSession = Depends(get_db)):
    s = get_settings()
    sub = (
        await session.execute(
            select(Subscription)
            .where(Subscription.user_id == user.id)
            .order_by(Subscription.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    cust = sub.stripe_customer_id if sub else None
    return stripe_service.create_billing_portal(
        customer_id=cust or "", return_url=f"{s.app_base_url}/account/subscription"
    )


@router.get("/subscription", response_model=CurrentSubscription)
async def current_subscription(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_db)
):
    sub = (
        await session.execute(
            select(Subscription)
            .where(Subscription.user_id == user.id)
            .order_by(Subscription.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if sub is None:
        return CurrentSubscription(plan=user.plan, status="active", price_twd=0)
    return CurrentSubscription(
        plan=sub.plan,
        status=sub.status,
        price_twd=sub.price_twd,
        current_period_end=sub.current_period_end,
        canceled_at=sub.canceled_at,
        stripe_customer_id=sub.stripe_customer_id,
    )


# ───────── webhook ─────────

async def _apply_event(session: AsyncSession, event: dict) -> None:
    etype = event.get("type", "")
    obj = (event.get("data") or {}).get("object") or {}

    customer_id = obj.get("customer")
    sub_id = obj.get("subscription") or obj.get("id")
    customer_email = (obj.get("customer_details") or {}).get("email") or obj.get("customer_email")
    plan = (obj.get("metadata") or {}).get("plan")
    status_ = obj.get("status") or SubStatus.ACTIVE

    user: Optional[User] = None
    if customer_email:
        user = (
            await session.execute(select(User).where(User.email == str(customer_email).lower()))
        ).scalar_one_or_none()

    if user is None and customer_id:
        sub_row = (
            await session.execute(select(Subscription).where(Subscription.stripe_customer_id == customer_id))
        ).scalar_one_or_none()
        if sub_row:
            user = (await session.execute(select(User).where(User.id == sub_row.user_id))).scalar_one_or_none()

    if user is None:
        return  # nothing to do; event for unknown account

    # Resolve plan from price ID if metadata absent
    if not plan:
        items = (obj.get("items") or {}).get("data") or []
        if items:
            price = items[0].get("price") or {}
            pid = price.get("id")
            s = get_settings()
            if pid and pid == s.stripe_price_pro:
                plan = "pro"
            elif pid and pid == s.stripe_price_elite:
                plan = "elite"

    if etype in ("checkout.session.completed", "customer.subscription.created", "customer.subscription.updated", "invoice.paid"):
        plan = plan or user.plan or Plan.FREE
        was_paid = user.plan in (Plan.PRO, Plan.ELITE)
        if plan in (Plan.PRO, Plan.ELITE):
            user.plan = plan
            if not was_paid:
                try:
                    from app.services import referral_service
                    await referral_service.mark_converted(session, user.id)
                except Exception:
                    pass
        sub_row = (
            await session.execute(
                select(Subscription)
                .where(Subscription.user_id == user.id)
                .order_by(Subscription.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        period_end_ts = obj.get("current_period_end")
        period_end = (
            datetime.fromtimestamp(int(period_end_ts), tz=timezone.utc) if period_end_ts else None
        )
        price_twd = stripe_service.amount_twd(plan)
        if sub_row is None:
            sub_row = Subscription(
                user_id=user.id,
                plan=plan,
                status=status_,
                stripe_customer_id=customer_id,
                stripe_subscription_id=sub_id,
                price_twd=price_twd,
                current_period_end=period_end,
            )
            session.add(sub_row)
        else:
            sub_row.plan = plan
            sub_row.status = status_
            sub_row.stripe_customer_id = customer_id or sub_row.stripe_customer_id
            sub_row.stripe_subscription_id = sub_id or sub_row.stripe_subscription_id
            sub_row.price_twd = price_twd
            sub_row.current_period_end = period_end or sub_row.current_period_end
    elif etype in ("customer.subscription.deleted", "invoice.payment_failed"):
        user.plan = Plan.FREE
        sub_row = (
            await session.execute(
                select(Subscription)
                .where(Subscription.user_id == user.id)
                .order_by(Subscription.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if sub_row:
            sub_row.status = SubStatus.CANCELED
            sub_row.canceled_at = datetime.now(timezone.utc)


@router.post("/webhook")
async def stripe_webhook(request: Request, session: AsyncSession = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe_service.verify_webhook(payload, sig)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    await _apply_event(session, event)
    await session.commit()
    return {"received": True, "type": event.get("type", "")}
