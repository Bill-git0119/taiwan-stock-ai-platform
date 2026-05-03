"""Upgrade a single user to ELITE + admin.

Usage:
    python scripts/upgrade_user.py [email]

If no email passed, reads from $UPGRADE_EMAIL or falls back to
the project owner. Idempotent — safe to run multiple times.

Notes:
  * Plan column stores lowercase strings ("free" / "pro" / "elite").
  * Auto-adapts to whatever DB driver $DATABASE_URL points at
    (SQLite or Postgres) via app.db.session._normalize_async_url.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Allow `python scripts/upgrade_user.py` from backend/ without install.
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from sqlalchemy import select  # noqa: E402

from app.db.models import Plan, User  # noqa: E402
from app.db.session import async_session_maker  # noqa: E402

DEFAULT_EMAIL = "zhangbaixun93@gmail.com"


async def upgrade(email: str) -> int:
    email = email.strip().lower()
    async with async_session_maker() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()

        if user is None:
            print(f"[upgrade] user not found: {email} -- register via /register first")
            return 1

        before = (user.plan, user.is_admin)
        user.plan = Plan.ELITE
        user.is_admin = True
        await session.commit()
        print(f"[upgrade] OK {email}: {before} -> ('elite', True)")
        return 0


def main() -> int:
    email = (
        sys.argv[1] if len(sys.argv) > 1
        else os.environ.get("UPGRADE_EMAIL", DEFAULT_EMAIL)
    )
    return asyncio.run(upgrade(email))


if __name__ == "__main__":
    sys.exit(main())
