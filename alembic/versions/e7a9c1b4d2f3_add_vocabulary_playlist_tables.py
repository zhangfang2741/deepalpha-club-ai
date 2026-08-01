# ruff: noqa
"""add vocabulary playlist tables (WordLens 自定义歌单).

Revision ID: e7a9c1b4d2f3
Revises: d5e6f7a8b9c0
Create Date: 2026-08-01 10:00:00.000000
"""

from typing import Sequence, Union

import sqlmodel  # noqa: F401
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e7a9c1b4d2f3"
down_revision: Union[str, Sequence[str], None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "vocabulary_playlists",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["vocabulary_users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_vocabulary_playlist_user_name"),
    )
    op.create_index(op.f("ix_vocabulary_playlists_id"), "vocabulary_playlists", ["id"], unique=False)
    op.create_index(op.f("ix_vocabulary_playlists_user_id"), "vocabulary_playlists", ["user_id"], unique=False)
    op.create_table(
        "vocabulary_playlist_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("playlist_id", sa.Uuid(), nullable=False),
        sa.Column("word_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["playlist_id"],
            ["vocabulary_playlists.id"],
        ),
        sa.ForeignKeyConstraint(
            ["word_id"],
            ["vocabulary_words.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("playlist_id", "word_id", name="uq_vocabulary_playlist_item"),
    )
    op.create_index(op.f("ix_vocabulary_playlist_items_id"), "vocabulary_playlist_items", ["id"], unique=False)
    op.create_index(
        op.f("ix_vocabulary_playlist_items_playlist_id"), "vocabulary_playlist_items", ["playlist_id"], unique=False
    )
    op.create_index(
        op.f("ix_vocabulary_playlist_items_word_id"), "vocabulary_playlist_items", ["word_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_vocabulary_playlist_items_word_id"), table_name="vocabulary_playlist_items")
    op.drop_index(op.f("ix_vocabulary_playlist_items_playlist_id"), table_name="vocabulary_playlist_items")
    op.drop_index(op.f("ix_vocabulary_playlist_items_id"), table_name="vocabulary_playlist_items")
    op.drop_table("vocabulary_playlist_items")
    op.drop_index(op.f("ix_vocabulary_playlists_user_id"), table_name="vocabulary_playlists")
    op.drop_index(op.f("ix_vocabulary_playlists_id"), table_name="vocabulary_playlists")
    op.drop_table("vocabulary_playlists")
