from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.leaderboard_service import weekly_leaderboard

router = APIRouter()


@router.get("/weekly")
async def get_weekly(session: AsyncSession = Depends(get_db)):
    rows = await weekly_leaderboard(session)
    return {"period": "7d", "items": rows}
