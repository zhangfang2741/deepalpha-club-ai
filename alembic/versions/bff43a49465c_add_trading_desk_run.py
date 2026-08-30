# ruff: noqa
"""add trading_desk_run.

手工裁剪过：autogenerate 原本产出了 800 多行无关内容（对 8 张历史表的
drop_table / supply_chain_* / graph_* 的时区类型漂移与外键 ondelete 丢失等
——都是预先存在的漂移，不属于本次任务）。本迁移只新建 trading_desk_run。

Revision ID: bff43a49465c
Revises: 81931160d5f6
Create Date: 2026-08-30 12:35:31.906599
"""

from typing import Sequence, Union

import sqlmodel  # noqa: F401
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "bff43a49465c"
down_revision: Union[str, Sequence[str], None] = "81931160d5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "trading_desk_run",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("trade_date", sqlmodel.sql.sqltypes.AutoString(length=10), nullable=False),
        sa.Column("engine", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False),
        sa.Column("verdict", sa.JSON(), nullable=True),
        sa.Column("signals", sa.JSON(), nullable=True),
        sa.Column("turns", sa.JSON(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_trading_desk_run_id"), "trading_desk_run", ["id"], unique=False)
    op.create_index(op.f("ix_trading_desk_run_status"), "trading_desk_run", ["status"], unique=False)
    op.create_index(op.f("ix_trading_desk_run_ticker"), "trading_desk_run", ["ticker"], unique=False)
    op.create_index(op.f("ix_trading_desk_run_user_id"), "trading_desk_run", ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_trading_desk_run_user_id"), table_name="trading_desk_run")
    op.drop_index(op.f("ix_trading_desk_run_ticker"), table_name="trading_desk_run")
    op.drop_index(op.f("ix_trading_desk_run_status"), table_name="trading_desk_run")
    op.drop_index(op.f("ix_trading_desk_run_id"), table_name="trading_desk_run")
    op.drop_table("trading_desk_run")