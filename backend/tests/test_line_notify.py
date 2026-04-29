from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, select

from app.db.models import NotificationLog, Plan, User
from app.db.session import async_session_maker
from app.services import line_notify
from app.services.line_notify import broadcast_top10, format_top10, send_to_user


def test_format_top10_text():
    rows = [
        {"symbol": "2330", "name": "台積電", "total_score": 92.1, "reason": "外資連買3日 + MA多頭"},
        {"symbol": "2454", "name": "聯發科", "total_score": 86.0, "reason": ""},
    ]
    text = format_top10(rows, header="🌅 開盤觀察股")
    assert "開盤觀察股" in text
    assert "2330" in text
    assert "台積電" in text
    assert "外資連買3日" in text
    assert text.count("\n") >= 3


@pytest.mark.asyncio
async def test_send_to_user_failure_logged(monkeypatch):
    monkeypatch.setattr(line_notify, "_push_line", AsyncMock(return_value=(False, "no token")))
    async with async_session_maker() as s:
        u = User(email="line1@test.io", name="t", plan="elite", line_user_id="U_test")
        s.add(u)
        await s.commit()
        await s.refresh(u)

        ok = await send_to_user(s, u, "test", "hello")
        assert ok is False

        log = (
            await s.execute(select(NotificationLog).where(NotificationLog.user_id == u.id))
        ).scalar_one()
        assert log.success is False
        assert "no token" in (log.error or "")
        assert log.kind == "test"


@pytest.mark.asyncio
async def test_broadcast_only_to_eligible_users(monkeypatch):
    monkeypatch.setattr(line_notify, "_push_line", AsyncMock(return_value=(True, None)))
    async with async_session_maker() as s:
        await s.execute(delete(NotificationLog))
        await s.execute(delete(User))
        await s.commit()
        s.add_all([
            User(email="bc_free@test.io", name="f", plan="free", line_user_id="U_free"),
            User(email="bc_pro@test.io",  name="p", plan="pro",  line_user_id="U_pro"),
            User(email="bc_elite@test.io",name="e", plan="elite",line_user_id="U_elite"),
            User(email="bc_elite_noid@test.io", name="e2", plan="elite", line_user_id=None),
            User(email="bc_elite_off@test.io",  name="e3", plan="elite",
                 line_user_id="U_off", notify_close=False),
        ])
        await s.commit()

        rows = [{"symbol": "2330", "name": "台積電", "total_score": 92, "reason": "test"}]
        result = await broadcast_top10(s, rows, kind="close", min_plan=Plan.ELITE)

    # Only one user matches all criteria (elite + line_user_id set + notify_close=True default).
    assert result["sent"] == 1
    assert result["failed"] == 0
