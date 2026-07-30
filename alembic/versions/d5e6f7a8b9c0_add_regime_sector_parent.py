# ruff: noqa
"""add parent column to regime_sector_features (子行业下钻).

Revision ID: d5e6f7a8b9c0
Revises: c4d2e3f5a6b7
Create Date: 2026-07-30 02:00:00.000000
"""
from typing import Sequence, Union

import sqlmodel  # noqa: F401
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, Sequence[str], None] = 'c4d2e3f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'regime_sector_features',
        sa.Column('parent', sqlmodel.sql.sqltypes.AutoString(length=30), nullable=True),
    )
    op.create_index(op.f('ix_regime_sector_features_parent'), 'regime_sector_features', ['parent'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_regime_sector_features_parent'), table_name='regime_sector_features')
    op.drop_column('regime_sector_features', 'parent')
