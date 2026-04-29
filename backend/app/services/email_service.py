"""Email service with Resend / SendGrid support and a drip funnel.

If neither API key is set, emails are logged only (dev/test mode) — every
call still records a NotificationLog so admins can audit.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import NotificationLog, User

logger = logging.getLogger(__name__)


# ───────── drip templates (sent on Day 0/2/5/10) ─────────

DRIP_TEMPLATES = [
    {
        "day": 0,
        "subject": "歡迎加入 Taiwan Stock AI ｜今日熱門股已為您準備",
        "html": """
<h1>歡迎加入！</h1>
<p>嗨 {name}，您的帳號已開通 Free 方案。</p>
<p>我們已替您整理今日 AI TOP 3 強勢股 — 三維度 (籌碼/基本面/技術面) 評分。</p>
<p><a href="{base}">→ 查看今日 TOP 3</a></p>
""".strip(),
    },
    {
        "day": 2,
        "subject": "升級 PRO 限時優惠 ｜每日 TOP 10 + 即時訊號",
        "html": """
<h2>專屬優惠</h2>
<p>升級 Pro（NT$299/月）即可解鎖每日 TOP 10 強勢股。</p>
<p>輸入優惠碼 <strong>WELCOME20</strong> 享首月 8 折。</p>
<p><a href="{base}/pricing">→ 立即升級</a></p>
""".strip(),
    },
    {
        "day": 5,
        "subject": "成功案例 ｜AI 選股 1 週績效 +12.5%",
        "html": """
<h2>本週 AI 績效</h2>
<p>奇鋐 +12.5%、廣達 +6.1%、台積電 +8.2%</p>
<p><a href="{base}/leaderboard">→ 查看完整戰績</a></p>
""".strip(),
    },
    {
        "day": 10,
        "subject": "限時 Elite 體驗 ｜LINE 即時推播 + 回測中心",
        "html": """
<h2>升級 Elite 享受全套功能</h2>
<p>每日 TOP 30、LINE 即時推播、專屬回測中心、1499 元/月。</p>
<p><a href="{base}/pricing">→ 升級 Elite</a></p>
""".strip(),
    },
]


async def _send_via_resend(to: str, subject: str, html: str) -> tuple[bool, Optional[str]]:
    settings = get_settings()
    if not settings.resend_api_key:
        return False, "no_api_key"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={"from": settings.email_from, "to": [to], "subject": subject, "html": html},
            )
            if r.status_code >= 400:
                return False, f"resend_{r.status_code}: {r.text[:120]}"
            return True, None
    except Exception as e:  # pragma: no cover
        return False, f"resend_exc: {e}"


async def _send_via_sendgrid(to: str, subject: str, html: str) -> tuple[bool, Optional[str]]:
    settings = get_settings()
    if not settings.sendgrid_api_key:
        return False, "no_api_key"
    try:
        payload = {
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": settings.email_from},
            "subject": subject,
            "content": [{"type": "text/html", "value": html}],
        }
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {settings.sendgrid_api_key}"},
                json=payload,
            )
            if r.status_code >= 400:
                return False, f"sendgrid_{r.status_code}: {r.text[:120]}"
            return True, None
    except Exception as e:  # pragma: no cover
        return False, f"sendgrid_exc: {e}"


async def send_email(
    session: AsyncSession,
    user: Optional[User],
    to: str,
    subject: str,
    html: str,
    kind: str = "transactional",
) -> bool:
    settings = get_settings()
    ok, err = False, "no_provider"
    if settings.resend_api_key:
        ok, err = await _send_via_resend(to, subject, html)
    elif settings.sendgrid_api_key:
        ok, err = await _send_via_sendgrid(to, subject, html)
    else:
        logger.info("[email-stub] to=%s kind=%s subject=%s", to, kind, subject)
        ok, err = True, None  # stub success in dev

    log = NotificationLog(
        user_id=user.id if user else None,
        channel="email", kind=kind, message=f"{subject} → {to}",
        success=ok, error=err,
    )
    session.add(log)
    await session.commit()
    return ok


async def send_drip(session: AsyncSession, user: User, day: int) -> bool:
    """Pick the right template by `day` (0/2/5/10) and send."""
    tpl = next((t for t in DRIP_TEMPLATES if t["day"] == day), None)
    if not tpl:
        return False
    base = get_settings().app_base_url
    html = tpl["html"].format(name=user.name or "投資人", base=base)
    return await send_email(
        session, user, user.email, tpl["subject"], html, kind=f"drip_d{day}"
    )


async def run_due_drips(session: AsyncSession) -> int:
    """Find users at Day 0/2/5/10 since registration and send the right email."""
    now = datetime.utcnow()
    sent = 0
    for day in (0, 2, 5, 10):
        target = now - timedelta(days=day)
        window_lo = target - timedelta(hours=12)
        window_hi = target + timedelta(hours=12)
        users = (
            await session.execute(
                select(User).where(User.created_at >= window_lo, User.created_at <= window_hi)
            )
        ).scalars().all()
        for u in users:
            already = (
                await session.execute(
                    select(NotificationLog).where(
                        NotificationLog.user_id == u.id,
                        NotificationLog.kind == f"drip_d{day}",
                        NotificationLog.success.is_(True),
                    )
                )
            ).scalar_one_or_none()
            if already:
                continue
            if await send_drip(session, u, day):
                sent += 1
    return sent
