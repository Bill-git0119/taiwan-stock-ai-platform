"""research infrastructure: MFE/MAE + sector + universe_snapshots + strategy_performance_daily

Revision ID: 0005_research_infra
Revises: 0004_edge_tracking
Create Date: 2026-05-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_research_infra"
down_revision: Union[str, None] = "0004_edge_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # edge_signals — add sector / mfe_r / mae_r
    with op.batch_alter_table("edge_signals") as batch:
        batch.add_column(sa.Column("sector", sa.String(48), nullable=True))
        batch.add_column(sa.Column("mfe_r", sa.Float(), nullable=True))
        batch.add_column(sa.Column("mae_r", sa.Float(), nullable=True))
    op.create_index("ix_edge_signals_sector", "edge_signals", ["sector"])

    # universe_snapshots
    op.create_table(
        "universe_snapshots",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("name", sa.String(64), server_default=""),
        sa.Column("market", sa.String(8), server_default="TWSE"),
        sa.Column("sector_zh", sa.String(48), server_default="其他"),
        sa.Column("sector_en", sa.String(48), server_default="Other"),
        sa.Column("avg_volume_20d", sa.BigInteger, server_default="0"),
        sa.Column("last_close", sa.Float, server_default="0"),
        sa.Column("notional_twd", sa.Float, server_default="0"),
        sa.Column("is_active", sa.Boolean, server_default=sa.true()),
        sa.Column("rank_by_notional", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("date", "symbol", name="uq_universe_snapshots_date_symbol"),
    )
    op.create_index("ix_universe_snapshots_date_active", "universe_snapshots",
                    ["date", "is_active"])

    # strategy_performance_daily
    op.create_table(
        "strategy_performance_daily",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("strategy", sa.String(48), nullable=False),
        sa.Column("signals_emitted", sa.Integer, server_default="0"),
        sa.Column("evaluated_count", sa.Integer, server_default="0"),
        sa.Column("wins", sa.Integer, server_default="0"),
        sa.Column("losses", sa.Integer, server_default="0"),
        sa.Column("expectancy_r", sa.Float, server_default="0"),
        sa.Column("profit_factor", sa.Float, server_default="0"),
        sa.Column("avg_mfe_r", sa.Float, server_default="0"),
        sa.Column("avg_mae_r", sa.Float, server_default="0"),
        sa.Column("decay_score", sa.Float, server_default="0"),
        sa.Column("is_active", sa.Boolean, server_default=sa.true()),
        sa.Column("production_status", sa.String(16), server_default="UNKNOWN"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("date", "strategy", name="uq_strategy_perf_date_strategy"),
    )
    op.create_index("ix_strategy_perf_strategy_date", "strategy_performance_daily",
                    ["strategy", "date"])


def downgrade() -> None:
    op.drop_index("ix_strategy_perf_strategy_date", table_name="strategy_performance_daily")
    op.drop_table("strategy_performance_daily")
    op.drop_index("ix_universe_snapshots_date_active", table_name="universe_snapshots")
    op.drop_table("universe_snapshots")
    op.drop_index("ix_edge_signals_sector", table_name="edge_signals")
    with op.batch_alter_table("edge_signals") as batch:
        batch.drop_column("mae_r")
        batch.drop_column("mfe_r")
        batch.drop_column("sector")
