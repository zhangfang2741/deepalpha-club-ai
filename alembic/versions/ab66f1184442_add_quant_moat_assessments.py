# ruff: noqa
"""add quant moat assessments.

Revision ID: ab66f1184442
Revises: 94805ad5391a
Create Date: 2026-10-01 16:37:07.731742
"""

from typing import Sequence, Union

import sqlmodel  # noqa: F401
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "ab66f1184442"
down_revision: Union[str, Sequence[str], None] = "94805ad5391a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """只建护城河表（autogenerate 带出的其它表历史漂移与本次无关，已删除）。"""
    op.create_table(
        "quant_moat_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("market", sqlmodel.sql.sqltypes.AutoString(length=8), nullable=False),
        sa.Column("symbol", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("accession", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column("filed_date", sqlmodel.sql.sqltypes.AutoString(length=10), nullable=True),
        sa.Column("tenk_url", sqlmodel.sql.sqltypes.AutoString(length=300), nullable=True),
        sa.Column("method_version", sqlmodel.sql.sqltypes.AutoString(length=8), nullable=False),
        sa.Column("rating", sqlmodel.sql.sqltypes.AutoString(length=8), nullable=False),
        sa.Column("trend", sqlmodel.sql.sqltypes.AutoString(length=10), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("threats", sa.JSON(), nullable=False),
        sa.Column("model_name", sqlmodel.sql.sqltypes.AutoString(length=60), nullable=True),
        sa.Column("assessed_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market", "symbol", "accession", "method_version", name="uq_quant_moat"),
    )
    op.create_index(op.f("ix_quant_moat_assessments_id"), "quant_moat_assessments", ["id"], unique=False)
    op.create_index("ix_quant_moat_market_symbol", "quant_moat_assessments", ["market", "symbol"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_quant_moat_market_symbol", table_name="quant_moat_assessments")
    op.drop_index(op.f("ix_quant_moat_assessments_id"), table_name="quant_moat_assessments")
    op.drop_table("quant_moat_assessments")
