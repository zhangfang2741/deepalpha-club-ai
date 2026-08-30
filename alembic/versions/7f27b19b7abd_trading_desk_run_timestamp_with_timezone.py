# ruff: noqa
"""trading_desk_run timestamp with timezone.

迁移原因:bff43a49465c 把 created_at/updated_at/finished_at 建成
TIMESTAMP WITHOUT TIME ZONE,但 SQLModel 的 UUIDModel 在 INSERT 时
用 datetime.now(UTC) 写入带 tz 的 datetime。asyncpg 不允许在 naive 列
存 aware 值,生产 POST /api/v1/trading-desk/runs 直接 500。

修法:把这 3 列改成 TIMESTAMP WITH TIME ZONE,匹配应用层一直用的 UTC aware
时间,同时保留 Python 端 UTC 处理惯例。

Revision ID: 7f27b19b7abd
Revises: bff43a49465c
Create Date: 2026-08-30 13:49:53.498727
"""

from typing import Sequence, Union

import sqlmodel  # noqa: F401
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7f27b19b7abd"
down_revision: Union[str, Sequence[str], None] = "bff43a49465c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """把 3 个时间列从 naive 改成 aware。"""
    op.alter_column(
        "trading_desk_run", "created_at",
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
    )
    op.alter_column(
        "trading_desk_run", "updated_at",
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
    )
    op.alter_column(
        "trading_desk_run", "finished_at",
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=True,
    )


def downgrade() -> None:
    """回退到 naive。"""
    op.alter_column(
        "trading_desk_run", "finished_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=True,
    )
    op.alter_column(
        "trading_desk_run", "updated_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=False,
    )
    op.alter_column(
        "trading_desk_run", "created_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=False,
    )