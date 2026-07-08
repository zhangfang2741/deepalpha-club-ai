"""Add company-centric supply-chain graph tables.

Revision ID: d7e8f9a0b1c2
Revises: 68ea9ec7f3b6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d7e8f9a0b1c2"
down_revision: str | None = "68ea9ec7f3b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    """Create graph and task tables."""
    op.create_table("supply_chain_runs", *_base_columns(), sa.Column("run_type", sa.String(), nullable=False), sa.Column("universe", sa.String(), nullable=False), sa.Column("status", sa.String(), nullable=False), sa.Column("total", sa.Integer(), nullable=False), sa.Column("completed", sa.Integer(), nullable=False), sa.Column("failed", sa.Integer(), nullable=False), sa.Column("params", sa.JSON(), nullable=False), sa.Column("quota_paused_at", sa.DateTime(timezone=True)), sa.Column("resume_after", sa.DateTime(timezone=True)), sa.Column("probe_attempts", sa.Integer(), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("finished_at", sa.DateTime(timezone=True)), sa.PrimaryKeyConstraint("id"))
    op.create_table("supply_chain_nodes", *_base_columns(), sa.Column("node_id", sa.String(), nullable=False), sa.Column("node_type", sa.String(), nullable=False), sa.Column("name", sa.String(), nullable=False), sa.Column("properties", sa.JSON(), nullable=False), sa.Column("first_seen_run_id", postgresql.UUID(as_uuid=True)), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("node_id"))
    op.create_table("supply_chain_edges", *_base_columns(), sa.Column("edge_id", sa.String(), nullable=False), sa.Column("src_node_id", sa.String(), nullable=False), sa.Column("src_type", sa.String(), nullable=False), sa.Column("dst_node_id", sa.String(), nullable=False), sa.Column("dst_type", sa.String(), nullable=False), sa.Column("edge_type", sa.String(), nullable=False), sa.Column("timestamp", sa.BigInteger(), nullable=False), sa.Column("properties", sa.JSON(), nullable=False), sa.Column("confidence", sa.Integer(), nullable=False), sa.Column("confidence_source", sa.String(), nullable=False), sa.Column("last_run_id", postgresql.UUID(as_uuid=True)), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("edge_id"))
    op.create_table("supply_chain_clues", *_base_columns(), sa.Column("edge_id", sa.String()), sa.Column("node_id", sa.String()), sa.Column("source_type", sa.String(), nullable=False), sa.Column("document_url", sa.String(), nullable=False), sa.Column("section", sa.String()), sa.Column("filing_date", sa.Date()), sa.Column("snippet_text", sa.String(), nullable=False), sa.Column("stance", sa.String(), nullable=False), sa.Column("confidence_delta", sa.Integer()), sa.Column("run_id", postgresql.UUID(as_uuid=True)), sa.PrimaryKeyConstraint("id"))
    op.create_table("supply_chain_tasks", *_base_columns(), sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("ticker", sa.String(), nullable=False), sa.Column("stage", sa.String(), nullable=False), sa.Column("status", sa.String(), nullable=False), sa.Column("retries", sa.Integer(), nullable=False), sa.Column("max_retries", sa.Integer(), nullable=False), sa.Column("quota_retries", sa.Integer(), nullable=False), sa.Column("celery_task_id", sa.String()), sa.Column("error", sa.String()), sa.Column("resume_after", sa.DateTime(timezone=True)), sa.Column("result_summary", sa.JSON(), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("finished_at", sa.DateTime(timezone=True)), sa.ForeignKeyConstraint(["run_id"], ["supply_chain_runs.id"]), sa.PrimaryKeyConstraint("id"))
    for table, columns in {"supply_chain_runs": ["status"], "supply_chain_nodes": ["node_id", "node_type", "name"], "supply_chain_edges": ["edge_id", "src_node_id", "dst_node_id", "edge_type", "confidence", "confidence_source"], "supply_chain_clues": ["edge_id", "node_id", "source_type", "stance"], "supply_chain_tasks": ["run_id", "ticker", "status"]}.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    """Drop task and graph tables."""
    for table in ("supply_chain_tasks", "supply_chain_clues", "supply_chain_edges", "supply_chain_nodes", "supply_chain_runs"):
        op.drop_table(table)
