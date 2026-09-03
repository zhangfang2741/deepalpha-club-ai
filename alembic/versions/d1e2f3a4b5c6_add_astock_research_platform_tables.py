# ruff: noqa
"""add A 股投研平台 tables: analysts, reports, report_outcomes, price_bars, subscriptions.

Revision ID: d1e2f3a4b5c6
Revises: 7f27b19b7abd
Create Date: 2026-09-03 00:00:00.000000

注：本环境无可连的 Postgres，无法用 --autogenerate 生成；本文件按模型定义
手写，与 app/models/{analyst,report,price_bar,subscription}.py 严格对齐。
"""

from typing import Sequence, Union

import sqlmodel  # noqa: F401
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "7f27b19b7abd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- analysts ---
    op.create_table(
        "analysts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("display_name", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("bio", sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=False),
        sa.Column("avatar_url", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("monthly_price_cents", sa.Integer(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_analysts_user_id"),
    )
    op.create_index(op.f("ix_analysts_id"), "analysts", ["id"], unique=False)
    op.create_index(op.f("ix_analysts_user_id"), "analysts", ["user_id"], unique=True)
    op.create_index(op.f("ix_analysts_status"), "analysts", ["status"], unique=False)

    # --- reports ---
    op.create_table(
        "reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analyst_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False),
        sa.Column("symbol_name", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        sa.Column("summary", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("direction", sqlmodel.sql.sqltypes.AutoString(length=8), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("target_price", sa.Float(), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(length=12), nullable=False),
        sa.Column("visibility", sqlmodel.sql.sqltypes.AutoString(length=12), nullable=False),
        sa.Column("mark_price", sa.Float(), nullable=True),
        sa.Column("mark_date", sqlmodel.sql.sqltypes.AutoString(length=10), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_reports_id"), "reports", ["id"], unique=False)
    op.create_index(op.f("ix_reports_analyst_id"), "reports", ["analyst_id"], unique=False)
    op.create_index(op.f("ix_reports_symbol"), "reports", ["symbol"], unique=False)
    op.create_index(op.f("ix_reports_direction"), "reports", ["direction"], unique=False)
    op.create_index(op.f("ix_reports_status"), "reports", ["status"], unique=False)
    op.create_index(op.f("ix_reports_mark_date"), "reports", ["mark_date"], unique=False)
    op.create_index(op.f("ix_reports_published_at"), "reports", ["published_at"], unique=False)

    # --- report_outcomes ---
    op.create_table(
        "report_outcomes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(length=12), nullable=False),
        sa.Column("horizon_end_date", sqlmodel.sql.sqltypes.AutoString(length=10), nullable=False),
        sa.Column("price_at_horizon", sa.Float(), nullable=True),
        sa.Column("actual_return_pct", sa.Float(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_id", name="uq_report_outcome_report"),
    )
    op.create_index(op.f("ix_report_outcomes_id"), "report_outcomes", ["id"], unique=False)
    op.create_index(op.f("ix_report_outcomes_report_id"), "report_outcomes", ["report_id"], unique=False)
    op.create_index(op.f("ix_report_outcomes_status"), "report_outcomes", ["status"], unique=False)

    # --- price_bars ---
    op.create_table(
        "price_bars",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False),
        sa.Column("date", sqlmodel.sql.sqltypes.AutoString(length=10), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "date", name="uq_price_bar_symbol_date"),
    )
    op.create_index(op.f("ix_price_bars_id"), "price_bars", ["id"], unique=False)
    op.create_index(op.f("ix_price_bars_symbol"), "price_bars", ["symbol"], unique=False)
    op.create_index(op.f("ix_price_bars_date"), "price_bars", ["date"], unique=False)

    # --- subscriptions ---
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("tier", sqlmodel.sql.sqltypes.AutoString(length=12), nullable=False),
        sa.Column("analyst_id", sa.Uuid(), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(length=12), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_subscriptions_id"), "subscriptions", ["id"], unique=False)
    op.create_index(op.f("ix_subscriptions_user_id"), "subscriptions", ["user_id"], unique=False)
    op.create_index(op.f("ix_subscriptions_tier"), "subscriptions", ["tier"], unique=False)
    op.create_index(op.f("ix_subscriptions_analyst_id"), "subscriptions", ["analyst_id"], unique=False)
    op.create_index(op.f("ix_subscriptions_status"), "subscriptions", ["status"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_subscriptions_status"), table_name="subscriptions")
    op.drop_index(op.f("ix_subscriptions_analyst_id"), table_name="subscriptions")
    op.drop_index(op.f("ix_subscriptions_tier"), table_name="subscriptions")
    op.drop_index(op.f("ix_subscriptions_user_id"), table_name="subscriptions")
    op.drop_index(op.f("ix_subscriptions_id"), table_name="subscriptions")
    op.drop_table("subscriptions")

    op.drop_index(op.f("ix_price_bars_date"), table_name="price_bars")
    op.drop_index(op.f("ix_price_bars_symbol"), table_name="price_bars")
    op.drop_index(op.f("ix_price_bars_id"), table_name="price_bars")
    op.drop_table("price_bars")

    op.drop_index(op.f("ix_report_outcomes_status"), table_name="report_outcomes")
    op.drop_index(op.f("ix_report_outcomes_report_id"), table_name="report_outcomes")
    op.drop_index(op.f("ix_report_outcomes_id"), table_name="report_outcomes")
    op.drop_table("report_outcomes")

    op.drop_index(op.f("ix_reports_published_at"), table_name="reports")
    op.drop_index(op.f("ix_reports_mark_date"), table_name="reports")
    op.drop_index(op.f("ix_reports_status"), table_name="reports")
    op.drop_index(op.f("ix_reports_direction"), table_name="reports")
    op.drop_index(op.f("ix_reports_symbol"), table_name="reports")
    op.drop_index(op.f("ix_reports_analyst_id"), table_name="reports")
    op.drop_index(op.f("ix_reports_id"), table_name="reports")
    op.drop_table("reports")

    op.drop_index(op.f("ix_analysts_status"), table_name="analysts")
    op.drop_index(op.f("ix_analysts_user_id"), table_name="analysts")
    op.drop_index(op.f("ix_analysts_id"), table_name="analysts")
    op.drop_table("analysts")
