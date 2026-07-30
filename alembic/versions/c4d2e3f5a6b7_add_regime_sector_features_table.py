# ruff: noqa
"""add regime_sector_features table.

Revision ID: c4d2e3f5a6b7
Revises: b3c1d2e4f5a6
Create Date: 2026-07-30 01:00:00.000000
"""
from typing import Sequence, Union

import sqlmodel  # noqa: F401
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d2e3f5a6b7'
down_revision: Union[str, Sequence[str], None] = 'b3c1d2e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'regime_sector_features',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('trade_date', sqlmodel.sql.sqltypes.AutoString(length=10), nullable=False),
        sa.Column('sector', sqlmodel.sql.sqltypes.AutoString(length=30), nullable=False),
        sa.Column('sector_ret', sa.Float(), nullable=True),
        sa.Column('sector_vol', sa.Float(), nullable=True),
        sa.Column('vix', sa.Float(), nullable=True),
        sa.Column('rs_vs_market', sa.Float(), nullable=True),
        sa.Column('sector_cmf', sa.Float(), nullable=True),
        sa.Column('p_risk_on', sa.Float(), nullable=True),
        sa.Column('p_neutral', sa.Float(), nullable=True),
        sa.Column('p_risk_off', sa.Float(), nullable=True),
        sa.Column('regime_label', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
        sa.Column('confirmed_label', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
        sa.Column('params_version', sqlmodel.sql.sqltypes.AutoString(length=10), nullable=True),
        sa.Column('factor_weight', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('trade_date', 'sector', name='uq_regime_sector'),
    )
    op.create_index(op.f('ix_regime_sector_features_id'), 'regime_sector_features', ['id'], unique=False)
    op.create_index(op.f('ix_regime_sector_features_trade_date'), 'regime_sector_features', ['trade_date'], unique=False)
    op.create_index(op.f('ix_regime_sector_features_sector'), 'regime_sector_features', ['sector'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_regime_sector_features_sector'), table_name='regime_sector_features')
    op.drop_index(op.f('ix_regime_sector_features_trade_date'), table_name='regime_sector_features')
    op.drop_index(op.f('ix_regime_sector_features_id'), table_name='regime_sector_features')
    op.drop_table('regime_sector_features')
