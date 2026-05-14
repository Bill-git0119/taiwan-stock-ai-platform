"""edge_signals: persistent record of every LONG plan + outcome

Revision ID: 0004_edge_tracking
Revises: 0003_growth
Create Date: 2026-05-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_edge_tracking"
down_revision: Union[str, None] = "0003_growth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "edge_signals",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("setup", sa.String(48), nullable=False),
        sa.Column("bias", sa.String(8), server_default="LONG"),
        sa.Column("regime", sa.String(32)),
        sa.Column("entry", sa.Float, nullable=False),
        sa.Column("stop_loss", sa.Float, nullable=False),
        sa.Column("tp1", sa.Float, nullable=False),
        sa.Column("tp2", sa.Float, nullable=False),
        sa.Column("risk_reward", sa.Float, server_default="0"),
        sa.Column("confidence", sa.Float, server_default="0"),
        sa.Column("edge_score", sa.Float, server_default="0"),
        sa.Column("evaluated", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("evaluated_at", sa.DateTime),
        sa.Column("exit_reason", sa.String(16)),
        sa.Column("exit_price", sa.Float),
        sa.Column("realized_r", sa.Float),
        sa.Column("win", sa.Boolean),
        sa.Column("bars_held", sa.Integer),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("date", "symbol", "setup", name="uq_edge_signals_date_symbol_setup"),
    )
    op.create_index("ix_edge_signals_setup_date", "edge_signals", ["setup", "date"])
    op.create_index("ix_edge_signals_evaluated", "edge_signals", ["evaluated"])


def downgrade() -> None:
    op.drop_index("ix_edge_signals_evaluated", table_name="edge_signals")
    op.drop_index("ix_edge_signals_setup_date", table_name="edge_signals")
    op.drop_table("edge_signals")
