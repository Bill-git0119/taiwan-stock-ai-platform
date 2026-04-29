"""growth: referrals + blog posts + stock picks

Revision ID: 0003_growth
Revises: 0002_auth_billing
Create Date: 2026-04-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_growth"
down_revision: Union[str, None] = "0002_auth_billing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "referrals",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("referrer_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("code", sa.String(16), nullable=False, index=True),
        sa.Column("invitee_email", sa.String(128), nullable=False, index=True),
        sa.Column("invitee_user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("converted_at", sa.DateTime),
        sa.Column("reward_granted", sa.Boolean, server_default=sa.false()),
        sa.Column("reward_kind", sa.String(32)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("referrer_id", "invitee_email", name="uq_ref_inviter_invitee"),
    )

    op.create_table(
        "blog_posts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(128), nullable=False, unique=True, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text, server_default=""),
        sa.Column("body_md", sa.Text, nullable=False),
        sa.Column("tags", sa.String(200), server_default=""),
        sa.Column("published_at", sa.DateTime, server_default=sa.func.now(), index=True),
    )

    op.create_table(
        "stock_picks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("name", sa.String(64), server_default=""),
        sa.Column("rank", sa.Integer, server_default="0"),
        sa.Column("entry_price", sa.Float, server_default="0"),
        sa.Column("return_pct", sa.Float, server_default="0"),
        sa.UniqueConstraint("date", "symbol", name="uq_picks_date_symbol"),
    )
    op.create_index("ix_picks_date", "stock_picks", ["date"])


def downgrade() -> None:
    op.drop_index("ix_picks_date", table_name="stock_picks")
    op.drop_table("stock_picks")
    op.drop_table("blog_posts")
    op.drop_table("referrals")
