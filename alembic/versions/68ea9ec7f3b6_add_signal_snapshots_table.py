# ruff: noqa
"""add signal_snapshots table.

Revision ID: 68ea9ec7f3b6
Revises: c3d4e5f6a7b8
Create Date: 2026-07-04 01:59:45.774154
"""

from typing import Sequence, Union

import sqlmodel  # noqa: F401
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "68ea9ec7f3b6"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "signal_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("symbol", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("snapshot_date", sqlmodel.sql.sqltypes.AutoString(length=10), nullable=False),
        sa.Column("eps_estimate", sa.Float(), nullable=True),
        sa.Column("revenue_estimate", sa.Float(), nullable=True),
        sa.Column("price_target_avg", sa.Float(), nullable=True),
        sa.Column("call_oi", sa.Integer(), nullable=True),
        sa.Column("put_oi", sa.Integer(), nullable=True),
        sa.Column("call_vol", sa.Integer(), nullable=True),
        sa.Column("put_vol", sa.Integer(), nullable=True),
        sa.Column("atm_iv", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "snapshot_date", name="uq_signal_snapshot"),
    )
    op.create_index(op.f("ix_signal_snapshots_id"), "signal_snapshots", ["id"], unique=False)
    op.create_index(
        op.f("ix_signal_snapshots_snapshot_date"), "signal_snapshots", ["snapshot_date"], unique=False
    )
    op.create_index(op.f("ix_signal_snapshots_symbol"), "signal_snapshots", ["symbol"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_signal_snapshots_symbol"), table_name="signal_snapshots")
    op.drop_index(op.f("ix_signal_snapshots_snapshot_date"), table_name="signal_snapshots")
    op.drop_index(op.f("ix_signal_snapshots_id"), table_name="signal_snapshots")
    op.drop_table("signal_snapshots")
