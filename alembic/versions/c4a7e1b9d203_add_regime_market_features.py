# ruff: noqa
"""add regime market features (A 股 / 港股大盘状态).

Revision ID: c4a7e1b9d203
Revises: ab66f1184442
Create Date: 2026-10-05 18:00:00.000000
"""

from typing import Sequence, Union

import sqlmodel  # noqa: F401
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c4a7e1b9d203"
down_revision: Union[str, Sequence[str], None] = "ab66f1184442"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """只建 A 股 / 港股大盘状态表。"""
    op.create_table(
        "regime_market_features",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("market", sqlmodel.sql.sqltypes.AutoString(length=8), nullable=False),
        sa.Column("trade_date", sqlmodel.sql.sqltypes.AutoString(length=10), nullable=False),
        sa.Column("benchmark_return", sa.Float(), nullable=True),
        sa.Column("realized_vol", sa.Float(), nullable=True),
        sa.Column("vol_ratio", sa.Float(), nullable=True),
        sa.Column("ods", sa.Float(), nullable=True),
        sa.Column("cf", sa.Float(), nullable=True),
        sa.Column("obv_slope", sa.Float(), nullable=True),
        sa.Column("cmf", sa.Float(), nullable=True),
        sa.Column("p_risk_on", sa.Float(), nullable=True),
        sa.Column("p_neutral", sa.Float(), nullable=True),
        sa.Column("p_risk_off", sa.Float(), nullable=True),
        sa.Column("regime_label", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
        sa.Column("confirmed_label", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
        sa.Column("params_version", sqlmodel.sql.sqltypes.AutoString(length=10), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market", "trade_date", name="uq_regime_market_date"),
    )
    op.create_index(op.f("ix_regime_market_features_id"), "regime_market_features", ["id"], unique=False)
    op.create_index(op.f("ix_regime_market_features_market"), "regime_market_features", ["market"], unique=False)
    op.create_index(op.f("ix_regime_market_features_trade_date"), "regime_market_features", ["trade_date"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_regime_market_features_trade_date"), table_name="regime_market_features")
    op.drop_index(op.f("ix_regime_market_features_market"), table_name="regime_market_features")
    op.drop_index(op.f("ix_regime_market_features_id"), table_name="regime_market_features")
    op.drop_table("regime_market_features")
