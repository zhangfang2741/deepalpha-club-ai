# ruff: noqa
"""user 表增加 phone 列，email 改可空.

手工裁剪过：autogenerate 原本还产出了 800 多行无关内容，包括对 8 张表的
drop_table（signal_*、concept_*、creator_processed_videos、earnings_call_details）
——那些表在库里真实存在，只是没有对应的 SQLModel 模型声明，Alembic 便认为
应该删掉。还有一批 supply_chain_* / graph_* 的时区类型漂移和外键 ondelete
丢失。全部剔除，本迁移只动 user 表。

Revision ID: 81931160d5f6
Revises: f8b1c2d3e4a5
Create Date: 2026-08-22 12:32:32.950242
"""

from typing import Sequence, Union

import sqlmodel  # noqa: F401
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "81931160d5f6"
down_revision: Union[str, Sequence[str], None] = "f8b1c2d3e4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # phone 可空：存量用户都是邮箱注册的，没有手机号。
    op.add_column("user", sa.Column("phone", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True))
    # email 改可空：手机号注册的用户没有邮箱。Postgres 的 unique 允许多行 NULL，
    # 所以 email 和 phone 同时「可空且唯一」是安全的。
    op.alter_column("user", "email", existing_type=sa.VARCHAR(), nullable=True)
    op.create_index(op.f("ix_user_phone"), "user", ["phone"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_user_phone"), table_name="user")
    # 回滚前提是没有手机号注册的用户，否则 email 为 NULL 的行会让这一步失败。
    op.alter_column("user", "email", existing_type=sa.VARCHAR(), nullable=False)
    op.drop_column("user", "phone")
