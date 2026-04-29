"""LINE Messaging API push helper.

For each notification we record a NotificationLog row regardless of whether the
HTTP call to LINE succeeds, so the admin panel can show delivery history.
"""
from __future__ import annotations

import logging
from typing import Iterable, List, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import NotificationLog, Plan, User

log = logging.getLogger(__name__)
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


def format_top10(rows: Iterable[dict], header: str = "📊 今日 TOP 強勢股") -> str:
    lines = [header, ""]
    for i, r in enumerate(rows, 1):
        name = r.get("name", "")
        sym = r.get("symbol", "")
        score = r.get("total_score", 0)
        reason = (r.get("reason") or "").strip()
        line = f"{i:>2}. {sym} {name}  AI {score:.0f}"
        if reason:
            line += f"\n    {reason}"
        lines.append(line)
    return "\n".join(lines)


async def _push_line(channel_token: str, to: str, text: str) -> tuple[bool, Optional[str]]:
    if not channel_token or not to:
        return False, "missing channel_token or recipient"
    try:
        async with httpx.AsyncClient(timeout=10) as cli:
            r = await cli.post(
                LINE_PUSH_URL,
                headers={
                    "Authorization": f"Bearer {channel_token}",
                    "Content-Type": "application/json",
                },
                json={"to": to, "messages": [{"type": "text", "text": text[:4900]}]},
            )
        if 200 <= r.status_code < 300:
            return True, None
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


async def send_to_user(session: AsyncSession, user: User, kind: str, text: str) -> bool:
    s = get_settings()
    ok, err = await _push_line(s.line_channel_token, user.line_user_id or "", text)
    session.add(
        NotificationLog(
            user_id=user.id,
            channel="line",
            kind=kind,
            message=text,
            success=ok,
            error=err,
        )
    )
    await session.commit()
    return ok


async def broadcast_top10(
    session: AsyncSession,
    rows: List[dict],
    *,
    kind: str = "close",
    min_plan: str = Plan.ELITE,
    header: Optional[str] = None,
) -> dict:
    """Push to every active user whose plan ≥ min_plan and notify-flag for this kind is on."""
    text = format_top10(rows, header=header or {
        "open": "🌅 開盤觀察股",
        "intraday": "🕒 尾盤強勢股",
        "close": "📊 收盤 TOP 強勢股",
    }.get(kind, "📊 強勢股"))

    candidates = (
        await session.execute(select(User).where(User.is_active == True))  # noqa: E712
    ).scalars().all()

    sent = 0
    failed = 0
    for u in candidates:
        if not Plan.at_least(u.plan, min_plan):
            continue
        if not u.line_user_id:
            continue
        flag = {"open": u.notify_open, "intraday": u.notify_intraday, "close": u.notify_close}.get(kind, True)
        if not flag:
            continue
        ok = await send_to_user(session, u, kind, text)
        if ok:
            sent += 1
        else:
            failed += 1
    return {"sent": sent, "failed": failed, "candidates": len(candidates)}
