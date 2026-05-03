"""Boot-time admin upgrade.

Render free tier has no Shell access, so we use env vars to grant a
single user ELITE + admin on every startup. Idempotent.

Env vars:
  BOOTSTRAP_ADMIN_EMAIL    — required; the user to upgrade.
  BOOTSTRAP_ADMIN_PASSWORD — optional; if set AND the user does not exist,
                             create them with this password so the user can
                             log in even after an ephemeral SQLite wipe.

After confirming you can log in as that account, you can leave the env
vars in place (idempotent) or delete them to disable bootstrapping.
"""
from __future__ import annotations

import os

from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import Plan, User
from app.db.session import async_session_maker


async def run_admin_bootstrap() -> None:
    email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
    if not email:
        return
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "").strip()

    try:
        async with async_session_maker() as session:
            user = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()

            if user is None:
                if not password:
                    print(f"[bootstrap] user {email} not found; "
                          f"set BOOTSTRAP_ADMIN_PASSWORD to auto-create.")
                    return
                user = User(
                    email=email,
                    name=email.split("@")[0],
                    password_hash=hash_password(password),
                    plan=Plan.ELITE,
                    is_admin=True,
                )
                session.add(user)
                await session.commit()
                print(f"[bootstrap] created admin {email} (elite, is_admin=True)")
                return

            changed = []
            if user.plan != Plan.ELITE:
                changed.append(f"plan {user.plan!r}->'elite'")
                user.plan = Plan.ELITE
            if not user.is_admin:
                changed.append("is_admin False->True")
                user.is_admin = True
            if changed:
                await session.commit()
                print(f"[bootstrap] upgraded {email}: " + ", ".join(changed))
            else:
                print(f"[bootstrap] {email} already elite + admin")
    except Exception as e:  # noqa: BLE001
        # Never block app startup on bootstrap failure (e.g. tables missing).
        print(f"[bootstrap] skipped: {e!r}")
