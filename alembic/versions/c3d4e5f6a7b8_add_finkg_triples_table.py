# ruff: noqa
"""add finkg triples table.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-02 00:00:00.000000
"""
from typing import Sequence, Union

import sqlmodel  # noqa: F401
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — 新增 FinReflectKG 三元组表（论文 5 元组格式）。"""
    op.create_table(
        'finkg_triples',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('head', sqlmodel.sql.sqltypes.AutoString(length=300), nullable=False),
        sa.Column('head_type', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column('relation', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column('tail', sqlmodel.sql.sqltypes.AutoString(length=300), nullable=False),
        sa.Column('tail_type', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column('evidence', sa.Text(), nullable=False),
        sa.Column('compliant', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('violations', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('extraction_mode', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False, server_default='reflection'),
        sa.Column('chunk_id', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
        sa.Column('source_doc_id', sa.Uuid(), nullable=True),
        sa.Column('document_url', sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
        sa.Column('ticker', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
        sa.ForeignKeyConstraint(['source_doc_id'], ['graph_source_documents.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_finkg_triples_id', 'finkg_triples', ['id'], unique=False)
    op.create_index('ix_finkg_triples_head', 'finkg_triples', ['head'], unique=False)
    op.create_index('ix_finkg_triples_head_type', 'finkg_triples', ['head_type'], unique=False)
    op.create_index('ix_finkg_triples_relation', 'finkg_triples', ['relation'], unique=False)
    op.create_index('ix_finkg_triples_tail', 'finkg_triples', ['tail'], unique=False)
    op.create_index('ix_finkg_triples_tail_type', 'finkg_triples', ['tail_type'], unique=False)
    op.create_index('ix_finkg_triples_compliant', 'finkg_triples', ['compliant'], unique=False)
    op.create_index('ix_finkg_triples_source_doc_id', 'finkg_triples', ['source_doc_id'], unique=False)
    op.create_index('ix_finkg_triples_ticker', 'finkg_triples', ['ticker'], unique=False)


def downgrade() -> None:
    """Downgrade schema — 删除 FinReflectKG 三元组表。"""
    op.drop_table('finkg_triples')
