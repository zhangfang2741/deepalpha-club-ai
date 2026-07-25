# ruff: noqa
"""add etymology and example sentence to vocabulary words.

Revision ID: 46eafaa1a288
Revises: 830dbe01edf1
Create Date: 2026-07-25 19:05:00.000000

手写而非 autogenerate：本地开发库（Neon）在其它无关表上存在与模型定义不一致的
历史 schema drift（缺表/字段类型不同步），autogenerate 会把那些无关的 drop
table/alter column 也混进 diff。为避免部署时误删生产表，这里只手写这次真正需要
的两列变更，不引入其它表的 diff。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "46eafaa1a288"
down_revision: Union[str, Sequence[str], None] = "830dbe01edf1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "vocabulary_words",
        sa.Column("etymology", sa.String(length=500), nullable=False, server_default=""),
    )
    op.add_column(
        "vocabulary_words",
        sa.Column("example_sentence", sa.String(length=1000), nullable=False, server_default=""),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("vocabulary_words", "example_sentence")
    op.drop_column("vocabulary_words", "etymology")
