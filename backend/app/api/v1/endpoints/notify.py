from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user, require_plan
from app.db.models import Plan, User
from app.db.session import get_db
from app.services.line_notify import send_to_user

router = APIRouter()


class NotifySettings(BaseModel):
    line_user_id: str | None
    notify_open: bool
    notify_intraday: bool
    notify_close: bool


@router.get("/settings", response_model=NotifySettings)
async def get_settings(user: User = Depends(current_user)):
    return NotifySettings(
        line_user_id=user.line_user_id,
        notify_open=user.notify_open,
        notify_intraday=user.notify_intraday,
        notify_close=user.notify_close,
    )


@router.post("/test")
async def send_test(
    user: User = Depends(require_plan(Plan.ELITE)),
    session: AsyncSession = Depends(get_db),
):
    if not user.line_user_id:
        raise HTTPException(400, "請先在會員中心設定 LINE user id")
    ok = await send_to_user(session, user, "test", "✅ 這是來自 Taiwan Stock AI 的測試訊息")
    return {"ok": ok}
