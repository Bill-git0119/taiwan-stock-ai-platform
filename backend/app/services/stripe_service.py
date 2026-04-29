"""Thin wrapper around stripe-python; safe to import without keys (no-op)."""
from __future__ import annotations

import logging
from typing import Optional

import stripe

from app.core.config import get_settings

log = logging.getLogger(__name__)

_PLAN_PRICE_TWD = {"pro": 299, "elite": 1499}


def _ensure() -> bool:
    s = get_settings()
    if not s.stripe_secret_key:
        return False
    stripe.api_key = s.stripe_secret_key
    return True


def price_id_for(plan: str) -> Optional[str]:
    s = get_settings()
    if plan == "pro":
        return s.stripe_price_pro or None
    if plan == "elite":
        return s.stripe_price_elite or None
    return None


def amount_twd(plan: str) -> int:
    return _PLAN_PRICE_TWD.get(plan, 0)


def create_checkout_session(*, plan: str, customer_email: str, success_url: str, cancel_url: str) -> dict:
    """Returns {"url": "..."} for redirect. Falls back to a local mock URL when
    Stripe is not configured (dev/test)."""
    if not _ensure() or plan not in _PLAN_PRICE_TWD:
        return {"url": f"{success_url}?mock=1&plan={plan}"}
    price = price_id_for(plan)
    if not price:
        return {"url": f"{success_url}?mock=1&plan={plan}"}
    sess = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        customer_email=customer_email,
        line_items=[{"price": price, "quantity": 1}],
        success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=cancel_url,
        metadata={"plan": plan},
    )
    return {"url": sess.url, "id": sess.id}


def create_billing_portal(*, customer_id: str, return_url: str) -> dict:
    if not _ensure() or not customer_id:
        return {"url": return_url}
    sess = stripe.billing_portal.Session.create(customer=customer_id, return_url=return_url)
    return {"url": sess.url}


def verify_webhook(payload: bytes, sig_header: str) -> dict:
    """Validate Stripe signature and return the parsed event dict.
    Raises ValueError on failure.
    """
    s = get_settings()
    if not s.stripe_webhook_secret:
        # In dev/test, accept raw JSON for easier local testing.
        import json
        return json.loads(payload.decode("utf-8"))
    if not _ensure():
        raise ValueError("stripe not configured")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, s.stripe_webhook_secret)
    except Exception as e:  # SignatureVerificationError, ValueError, ...
        raise ValueError(f"invalid signature: {e}") from e
    return event
