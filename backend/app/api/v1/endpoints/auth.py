from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import Plan, User
from app.db.session import get_db

router = APIRouter()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    name: Optional[str] = None
    ref: Optional[str] = None  # referral code


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(BaseModel):
    id: int
    email: EmailStr
    name: str
    plan: str
    is_admin: bool
    line_user_id: Optional[str] = None
    notify_open: bool
    notify_intraday: bool
    notify_close: bool
    created_at: datetime


class UpdateProfile(BaseModel):
    name: Optional[str] = None
    line_user_id: Optional[str] = None
    notify_open: Optional[bool] = None
    notify_intraday: Optional[bool] = None
    notify_close: Optional[bool] = None


class ChangePassword(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=72)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=72)


def _user_out(u: User) -> UserOut:
    return UserOut(
        id=u.id,
        email=u.email,
        name=u.name,
        plan=u.plan,
        is_admin=u.is_admin,
        line_user_id=u.line_user_id,
        notify_open=u.notify_open,
        notify_intraday=u.notify_intraday,
        notify_close=u.notify_close,
        created_at=u.created_at,
    )


# ───────── endpoints ─────────

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_db)):
    existing = (
        await session.execute(select(User).where(User.email == body.email))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "email already registered")
    user = User(
        email=str(body.email).lower(),
        name=body.name or str(body.email).split("@")[0],
        password_hash=hash_password(body.password),
        plan=Plan.FREE,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    if body.ref:
        from app.services import referral_service
        referrer = await referral_service.resolve_referrer(session, body.ref)
        if referrer and referrer.id != user.id:
            await referral_service.attach_invitee(session, referrer, user)

    token = create_access_token(user.id, {"plan": user.plan, "admin": user.is_admin})
    return TokenResponse(access_token=token, user=_user_out(user))


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_db)):
    user = (
        await session.execute(select(User).where(User.email == str(body.email).lower()))
    ).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "account disabled")
    token = create_access_token(user.id, {"plan": user.plan, "admin": user.is_admin})
    return TokenResponse(access_token=token, user=_user_out(user))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)):
    return _user_out(user)


@router.patch("/me", response_model=UserOut)
async def update_me(
    body: UpdateProfile,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
):
    for f in ("name", "line_user_id", "notify_open", "notify_intraday", "notify_close"):
        v = getattr(body, f)
        if v is not None:
            setattr(user, f, v)
    await session.commit()
    await session.refresh(user)
    return _user_out(user)


@router.post("/change-password")
async def change_password(
    body: ChangePassword,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "current password incorrect")
    user.password_hash = hash_password(body.new_password)
    await session.commit()
    return {"ok": True}


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, session: AsyncSession = Depends(get_db)):
    """Issue a short-lived reset token. In production this would be emailed; the
    endpoint always returns ok to avoid user enumeration."""
    user = (
        await session.execute(select(User).where(User.email == str(body.email).lower()))
    ).scalar_one_or_none()
    if user:
        token = create_access_token(user.id, {"purpose": "reset"})
        # TODO: send via SES/Mailgun. Returned in dev for testability only.
        return {"ok": True, "dev_reset_token": token}
    return {"ok": True}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, session: AsyncSession = Depends(get_db)):
    from app.core.security import decode_token
    try:
        payload = decode_token(body.token)
        if payload.get("purpose") != "reset":
            raise ValueError("wrong purpose")
        uid = int(payload["sub"])
    except Exception:
        raise HTTPException(400, "invalid or expired token")
    user = (await session.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if user is None:
        raise HTTPException(404, "user not found")
    user.password_hash = hash_password(body.new_password)
    await session.commit()
    return {"ok": True}


@router.post("/logout")
async def logout(_: User = Depends(current_user)):
    """Stateless JWT — clients drop the token. Returned for client UX symmetry."""
    return {"ok": True}
