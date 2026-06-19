# ruff: noqa
"""add supply chain graph tables.

Revision ID: a1b2c3d4e5f6
Revises: f8b40f61ef5b
Create Date: 2026-06-19 00:00:00.000000
"""
from typing import Sequence, Union

import sqlmodel  # noqa: F401
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f8b40f61ef5b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — 新增供应链因果图谱三张表。"""
    # ── 来源文档表 ──────────────────────────────────────
    op.create_table(
        'graph_source_documents',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('url', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('document_type', sqlmodel.sql.sqltypes.AutoString(length=30), nullable=False),
        sa.Column('ticker', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
        sa.Column('company_name', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
        sa.Column('filing_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('period_of_report', sa.DateTime(timezone=True), nullable=True),
        sa.Column('section', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.Column('chunk_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('fact_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False, server_default='pending'),
        sa.Column('error_message', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.Column('ingested_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_graph_source_documents_id', 'graph_source_documents', ['id'], unique=False)
    op.create_index('ix_graph_source_documents_ticker', 'graph_source_documents', ['ticker'], unique=False)
    op.create_index('ix_graph_source_documents_url', 'graph_source_documents', ['url'], unique=False)

    # ── 实体节点表 ──────────────────────────────────────
    op.create_table(
        'graph_entities',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('entity_type', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=300), nullable=False),
        sa.Column('aliases', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=True),
        sa.Column('ticker', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
        sa.Column('source_doc_ids', sa.JSON(), nullable=False, server_default='[]'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_graph_entities_id', 'graph_entities', ['id'], unique=False)
    op.create_index('ix_graph_entities_name', 'graph_entities', ['name'], unique=False)
    op.create_index('ix_graph_entities_entity_type', 'graph_entities', ['entity_type'], unique=False)
    op.create_index('ix_graph_entities_ticker', 'graph_entities', ['ticker'], unique=False)

    # ── 事实关系表 ──────────────────────────────────────
    op.create_table(
        'graph_facts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source_entity_id', sa.Uuid(), nullable=False),
        sa.Column('target_entity_id', sa.Uuid(), nullable=False),
        sa.Column('relation_type', sqlmodel.sql.sqltypes.AutoString(length=30), nullable=False),
        sa.Column('evidence_text', sa.Text(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='0.8'),
        sa.Column('event_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ingestion_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source_doc_id', sa.Uuid(), nullable=True),
        sa.Column('document_url', sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
        sa.Column('document_section', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
        sa.Column('chunk_id', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
        sa.ForeignKeyConstraint(['source_entity_id'], ['graph_entities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_entity_id'], ['graph_entities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_doc_id'], ['graph_source_documents.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_graph_facts_id', 'graph_facts', ['id'], unique=False)
    op.create_index('ix_graph_facts_source_entity_id', 'graph_facts', ['source_entity_id'], unique=False)
    op.create_index('ix_graph_facts_target_entity_id', 'graph_facts', ['target_entity_id'], unique=False)
    op.create_index('ix_graph_facts_relation_type', 'graph_facts', ['relation_type'], unique=False)
    op.create_index('ix_graph_facts_event_time', 'graph_facts', ['event_time'], unique=False)
    op.create_index('ix_graph_facts_ingestion_time', 'graph_facts', ['ingestion_time'], unique=False)
    op.create_index('ix_graph_facts_source_doc_id', 'graph_facts', ['source_doc_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema — 删除供应链因果图谱三张表。"""
    op.drop_table('graph_facts')
    op.drop_table('graph_entities')
    op.drop_table('graph_source_documents')
