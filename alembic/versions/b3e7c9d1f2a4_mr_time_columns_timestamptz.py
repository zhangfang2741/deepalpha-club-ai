"""晨报/设备token 表时间列改为 timestamptz

Revision ID: b3e7c9d1f2a4
Revises: a969cfdb8f18
Create Date: 2026-09-08

UUIDModel 的默认时间戳是 aware datetime，asyncpg 写 naive 列会抛
DataError（对齐 trading_desk_run 迁移 7f27b19b7abd 的既有规范）。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b3e7c9d1f2a4"
down_revision: str | Sequence[str] | None = "a969cfdb8f18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NAIVE = postgresql.TIMESTAMP()
AWARE = sa.DateTime(timezone=True)


def upgrade() -> None:
    """时间列 naive → timestamptz。"""
    op.alter_column("morning_report", "created_at", existing_type=NAIVE, type_=AWARE, existing_nullable=False)
    op.alter_column("morning_report", "updated_at", existing_type=NAIVE, type_=AWARE, existing_nullable=False)
    op.alter_column("morning_report", "generated_at", existing_type=NAIVE, type_=AWARE, existing_nullable=True)
    op.alter_column("device_token", "created_at", existing_type=NAIVE, type_=AWARE, existing_nullable=False)
    op.alter_column("device_token", "updated_at", existing_type=NAIVE, type_=AWARE, existing_nullable=False)


def downgrade() -> None:
    """时间列 timestamptz → naive。"""
    op.alter_column("device_token", "updated_at", existing_type=AWARE, type_=NAIVE, existing_nullable=False)
    op.alter_column("device_token", "created_at", existing_type=AWARE, type_=NAIVE, existing_nullable=False)
    op.alter_column("morning_report", "generated_at", existing_type=AWARE, type_=NAIVE, existing_nullable=True)
    op.alter_column("morning_report", "updated_at", existing_type=AWARE, type_=NAIVE, existing_nullable=False)
    op.alter_column("morning_report", "created_at", existing_type=AWARE, type_=NAIVE, existing_nullable=False)

