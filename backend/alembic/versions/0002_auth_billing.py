"""auth & billing schema

Revision ID: 0002_auth_billing
Revises: 0001_initial
Create Date: 2026-04-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_auth_billing"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(128), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(64), nullable=False, server_default=""),
        sa.Column("password_hash", sa.String(255)),
        sa.Column("plan", sa.String(16), nullable=False, server_default="free"),
        sa.Column("is_admin", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("line_user_id", sa.String(64)),
        sa.Column("notify_open", sa.Boolean, server_default=sa.true()),
        sa.Column("notify_intraday", sa.Boolean, server_default=sa.true()),
        sa.Column("notify_close", sa.Boolean, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("plan", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("stripe_customer_id", sa.String(64), index=True),
        sa.Column("stripe_subscription_id", sa.String(64), unique=True, index=True),
        sa.Column("price_twd", sa.Integer, server_default="0"),
        sa.Column("current_period_end", sa.DateTime),
        sa.Column("canceled_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "favorites",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "symbol", name="uq_favorites_user_symbol"),
    )

    op.create_table(
        "notification_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), index=True),
        sa.Column("channel", sa.String(16), server_default="line"),
        sa.Column("kind", sa.String(24)),
        sa.Column("message", sa.Text),
        sa.Column("success", sa.Boolean, server_default=sa.false()),
        sa.Column("error", sa.String(255)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), index=True),
    )


def downgrade() -> None:
    op.drop_table("notification_logs")
    op.drop_table("favorites")
    op.drop_table("subscriptions")
    op.drop_table("users")
