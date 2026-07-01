# ruff: noqa
"""add processed_chunks and cache_key to source documents.

Revision ID: b2c3d4e5f6a7
Revises: f21f0c8e8055
Create Date: 2026-07-01 00:00:00.000000
"""
from typing import Sequence, Union

import sqlmodel  # noqa: F401
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "f21f0c8e8055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — 文档表新增处理进度与缓存去重键。"""
    op.add_column(
        "graph_source_documents",
        sa.Column("processed_chunks", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "graph_source_documents",
        sa.Column("cache_key", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.create_index(
        "ix_graph_source_documents_cache_key",
        "graph_source_documents",
        ["cache_key"],
    )


def downgrade() -> None:
    """Downgrade schema。"""
    op.drop_index("ix_graph_source_documents_cache_key", table_name="graph_source_documents")
    op.drop_column("graph_source_documents", "cache_key")
    op.drop_column("graph_source_documents", "processed_chunks")
