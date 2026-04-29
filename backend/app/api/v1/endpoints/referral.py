from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user
from app.db.models import User
from app.db.session import get_db
from app.services import referral_service

router = APIRouter()


class InviteIn(BaseModel):
    email: EmailStr


@router.get("/me")
async def my_referral(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
):
    return await referral_service.stats_for(session, user)


@router.post("/invite")
async def invite(
    body: InviteIn,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
):
    row = await referral_service.record_invite(session, user, str(body.email))
    return {"ok": True, "code": row.code, "invitee_email": row.invitee_email}


class ResolveIn(BaseModel):
    code: str


@router.post("/resolve")
async def resolve(body: ResolveIn, session: AsyncSession = Depends(get_db)):
    referrer = await referral_service.resolve_referrer(session, body.code)
    if not referrer:
        return {"ok": False}
    return {"ok": True, "referrer_id": referrer.id, "referrer_name": referrer.name or referrer.email}
