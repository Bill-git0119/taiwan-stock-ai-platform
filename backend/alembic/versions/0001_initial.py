"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stocks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(16), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("market", sa.String(8), nullable=False, server_default="TWSE"),
        sa.Column("sector", sa.String(64)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "daily_prices",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("stock_id", sa.Integer, sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("open", sa.Float, nullable=False),
        sa.Column("high", sa.Float, nullable=False),
        sa.Column("low", sa.Float, nullable=False),
        sa.Column("close", sa.Float, nullable=False),
        sa.Column("volume", sa.BigInteger, nullable=False, server_default="0"),
        sa.UniqueConstraint("stock_id", "date", name="uq_daily_prices_stock_date"),
    )
    op.create_index("ix_daily_prices_stock_date", "daily_prices", ["stock_id", "date"])

    op.create_table(
        "chip_data",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("stock_id", sa.Integer, sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("foreign_buy", sa.Float, server_default="0"),
        sa.Column("investment_buy", sa.Float, server_default="0"),
        sa.Column("dealer_buy", sa.Float, server_default="0"),
        sa.UniqueConstraint("stock_id", "date", name="uq_chip_data_stock_date"),
    )
    op.create_index("ix_chip_data_stock_date", "chip_data", ["stock_id", "date"])

    op.create_table(
        "scores",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("stock_id", sa.Integer, sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("chip_score", sa.Float, server_default="0"),
        sa.Column("fundamental_score", sa.Float, server_default="0"),
        sa.Column("technical_score", sa.Float, server_default="0"),
        sa.Column("total_score", sa.Float, server_default="0"),
        sa.Column("reason", sa.String(256)),
        sa.UniqueConstraint("stock_id", "date", name="uq_scores_stock_date"),
    )
    op.create_index("ix_scores_stock_date", "scores", ["stock_id", "date"])
    op.create_index("ix_scores_date_total", "scores", ["date", "total_score"])


def downgrade() -> None:
    op.drop_index("ix_scores_date_total", table_name="scores")
    op.drop_index("ix_scores_stock_date", table_name="scores")
    op.drop_table("scores")
    op.drop_index("ix_chip_data_stock_date", table_name="chip_data")
    op.drop_table("chip_data")
    op.drop_index("ix_daily_prices_stock_date", table_name="daily_prices")
    op.drop_table("daily_prices")
    op.drop_table("stocks")
