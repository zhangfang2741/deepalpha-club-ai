# ruff: noqa
"""add watchlist_item table.

Revision ID: 66b09f6e0faf
Revises: b3e7c9d1f2a4
Create Date: 2026-09-19 20:22:30.089090
"""

from typing import Sequence, Union

import sqlmodel  # noqa: F401
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "66b09f6e0faf"
down_revision: Union[str, Sequence[str], None] = "b3e7c9d1f2a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "watchlist_item",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("market", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("symbol", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "market", "symbol", name="uq_watchlist_user_market_symbol"),
    )
    op.create_index(op.f("ix_watchlist_item_id"), "watchlist_item", ["id"], unique=False)
    op.create_index(op.f("ix_watchlist_item_symbol"), "watchlist_item", ["symbol"], unique=False)
    op.create_index(op.f("ix_watchlist_item_user_id"), "watchlist_item", ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_watchlist_item_user_id"), table_name="watchlist_item")
    op.drop_index(op.f("ix_watchlist_item_symbol"), table_name="watchlist_item")
    op.drop_index(op.f("ix_watchlist_item_id"), table_name="watchlist_item")
    op.drop_table("watchlist_item")
