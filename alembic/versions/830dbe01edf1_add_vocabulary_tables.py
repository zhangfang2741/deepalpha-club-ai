# ruff: noqa
"""add vocabulary tables.

Revision ID: 830dbe01edf1
Revises: e1f2a3b4c5d6
Create Date: 2026-07-25 15:28:58.600025
"""

from typing import Sequence, Union

import sqlmodel  # noqa: F401
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "830dbe01edf1"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "vocabulary_users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("email", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("hashed_password", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_vocabulary_users_email"), "vocabulary_users", ["email"], unique=True)
    op.create_index(op.f("ix_vocabulary_users_id"), "vocabulary_users", ["id"], unique=False)
    op.create_table(
        "vocabulary_words",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("word", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column("phonetic_ipa", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column("part_of_speech", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("definition_zh", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(length=10), nullable=False),
        sa.Column("repetition_count", sa.Integer(), nullable=False),
        sa.Column("easiness_factor", sa.Float(), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("next_review_at", sa.DateTime(), nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["vocabulary_users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "word", name="uq_vocabulary_word_user_word"),
    )
    op.create_index(op.f("ix_vocabulary_words_id"), "vocabulary_words", ["id"], unique=False)
    op.create_index(op.f("ix_vocabulary_words_status"), "vocabulary_words", ["status"], unique=False)
    op.create_index(op.f("ix_vocabulary_words_user_id"), "vocabulary_words", ["user_id"], unique=False)
    op.create_index(op.f("ix_vocabulary_words_word"), "vocabulary_words", ["word"], unique=False)
    op.create_table(
        "vocabulary_review_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("word_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
        sa.Column("interval_before", sa.Integer(), nullable=False),
        sa.Column("interval_after", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["word_id"],
            ["vocabulary_words.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_vocabulary_review_logs_id"), "vocabulary_review_logs", ["id"], unique=False)
    op.create_index(op.f("ix_vocabulary_review_logs_word_id"), "vocabulary_review_logs", ["word_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_vocabulary_review_logs_word_id"), table_name="vocabulary_review_logs")
    op.drop_index(op.f("ix_vocabulary_review_logs_id"), table_name="vocabulary_review_logs")
    op.drop_table("vocabulary_review_logs")
    op.drop_index(op.f("ix_vocabulary_words_word"), table_name="vocabulary_words")
    op.drop_index(op.f("ix_vocabulary_words_user_id"), table_name="vocabulary_words")
    op.drop_index(op.f("ix_vocabulary_words_status"), table_name="vocabulary_words")
    op.drop_index(op.f("ix_vocabulary_words_id"), table_name="vocabulary_words")
    op.drop_table("vocabulary_words")
    op.drop_index(op.f("ix_vocabulary_users_id"), table_name="vocabulary_users")
    op.drop_index(op.f("ix_vocabulary_users_email"), table_name="vocabulary_users")
    op.drop_table("vocabulary_users")
