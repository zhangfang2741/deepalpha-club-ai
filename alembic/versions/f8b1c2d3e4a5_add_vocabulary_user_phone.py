# ruff: noqa
"""add phone to vocabulary_users (WordLens 手机号注册).

手机号与邮箱都可作为登录标识，两者至少有一个。因此 email 由 NOT NULL 放宽为
可空，并加 CHECK 约束兜底，防止出现两者皆空、永远登不上的孤儿账号。

Revision ID: f8b1c2d3e4a5
Revises: e7a9c1b4d2f3
Create Date: 2026-08-15 14:00:00.000000
"""

from typing import Sequence, Union

import sqlmodel  # noqa: F401
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f8b1c2d3e4a5"
down_revision: Union[str, Sequence[str], None] = "e7a9c1b4d2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "vocabulary_users",
        sa.Column("phone", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
    )
    op.create_index(op.f("ix_vocabulary_users_phone"), "vocabulary_users", ["phone"], unique=True)

    # 手机号注册的账号没有邮箱，email 不能再强制非空。
    op.alter_column("vocabulary_users", "email", existing_type=sa.VARCHAR(length=255), nullable=True)

    # 应用层已经保证至少有一个标识，这里再加一道数据库兜底：漏掉一处校验就可能
    # 写进一个既无邮箱也无手机号的账号，那个账号永远登不上、也删不掉。
    op.create_check_constraint(
        "ck_vocabulary_user_has_identifier",
        "vocabulary_users",
        "email IS NOT NULL OR phone IS NOT NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_vocabulary_user_has_identifier", "vocabulary_users", type_="check")

    # 回滚前先清掉纯手机号账号：email 要恢复 NOT NULL，这些行没有邮箱可填，
    # 留着会让 ALTER 直接失败。
    op.execute("DELETE FROM vocabulary_users WHERE email IS NULL")

    op.alter_column("vocabulary_users", "email", existing_type=sa.VARCHAR(length=255), nullable=False)
    op.drop_index(op.f("ix_vocabulary_users_phone"), table_name="vocabulary_users")
    op.drop_column("vocabulary_users", "phone")
