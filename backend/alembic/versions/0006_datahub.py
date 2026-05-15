"""datahub freshness + integrity tables

Revision ID: 0006_datahub
Revises: 0005_research_infra
Create Date: 2026-05-15
"""
from alembic import op
import sqlalchemy as sa


revision = "0006_datahub"
down_revision = "0005_research_infra"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_freshness",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("latest_data_at", sa.DateTime),
        sa.Column("last_attempted_at", sa.DateTime),
        sa.Column("last_succeeded_at", sa.DateTime),
        sa.Column("rows_last_run", sa.Integer, server_default="0"),
        sa.Column("last_error", sa.Text),
        sa.Column("consecutive_failures", sa.Integer, server_default="0"),
        sa.Column(
            "updated_at", sa.DateTime,
            server_default=sa.func.now(), onupdate=sa.func.now(),
        ),
    )
    op.create_table(
        "data_integrity_reports",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(64), nullable=False, index=True),
        sa.Column("check_name", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(8), nullable=False),
        sa.Column("affected_symbols", sa.Integer, server_default="0"),
        sa.Column("detail", sa.Text),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), index=True),
    )


def downgrade() -> None:
    op.drop_table("data_integrity_reports")
    op.drop_table("data_freshness")
