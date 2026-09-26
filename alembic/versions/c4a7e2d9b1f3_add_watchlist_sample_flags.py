# ruff: noqa
"""add is_sample / hidden to watchlist_item.

示例自选：每个用户默认送美/A/港龙头各一只（is_sample），不占名额；用户删除时只置
hidden、不真删，用来记住「已经送过」，下次打开不再补回来。

Revision ID: c4a7e2d9b1f3
Revises: 66b09f6e0faf
Create Date: 2026-09-26 16:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c4a7e2d9b1f3"
down_revision: Union[str, Sequence[str], None] = "66b09f6e0faf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default=false：存量记录都是用户自己加的普通自选
    op.add_column(
        "watchlist_item",
        sa.Column("is_sample", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "watchlist_item",
        sa.Column("hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("watchlist_item", "hidden")
    op.drop_column("watchlist_item", "is_sample")
