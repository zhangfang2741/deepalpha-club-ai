# ruff: noqa
"""add regime_features table.

Revision ID: b3c1d2e4f5a6
Revises: 46eafaa1a288
Create Date: 2026-07-29 00:00:00.000000
"""
from typing import Sequence, Union

import sqlmodel  # noqa: F401
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c1d2e4f5a6'
down_revision: Union[str, Sequence[str], None] = '46eafaa1a288'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'regime_features',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('trade_date', sqlmodel.sql.sqltypes.AutoString(length=10), nullable=False),
        sa.Column('qqq_return', sa.Float(), nullable=True),
        sa.Column('realized_vol', sa.Float(), nullable=True),
        sa.Column('vix', sa.Float(), nullable=True),
        sa.Column('ods', sa.Float(), nullable=True),
        sa.Column('cf', sa.Float(), nullable=True),
        sa.Column('obv_slope', sa.Float(), nullable=True),
        sa.Column('cmf', sa.Float(), nullable=True),
        sa.Column('p_risk_on', sa.Float(), nullable=True),
        sa.Column('p_neutral', sa.Float(), nullable=True),
        sa.Column('p_risk_off', sa.Float(), nullable=True),
        sa.Column('regime_label', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
        sa.Column('confirmed_label', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
        sa.Column('params_version', sqlmodel.sql.sqltypes.AutoString(length=10), nullable=True),
        sa.Column('factor_weight', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_regime_features_id'), 'regime_features', ['id'], unique=False)
    op.create_index(op.f('ix_regime_features_trade_date'), 'regime_features', ['trade_date'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_regime_features_trade_date'), table_name='regime_features')
    op.drop_index(op.f('ix_regime_features_id'), table_name='regime_features')
    op.drop_table('regime_features')
